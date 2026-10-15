from flask import Blueprint, render_template, session, request, redirect, url_for, current_app, jsonify
import hashlib
import hmac
import os
import secrets
import time
import bcrypt as bp
from datetime import datetime

from shared import db,login_required
from shared.models import Teacher,Admin,Student
from shared.services.create_account_service import create_account
from shared.services.face_id_service import save_face, face_detected, FACE_ID_DIR
from shared import settings as app_settings
from shared.services.email_service import email, NoInternetError, EmailSendError
from shared.services.profile_service import initials_for_name, password_bytes

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/about", endpoint="about")
def about():
    return render_template("about_us.html")


@pages_bp.route("/support", endpoint="support")
def support():
    return render_template("support.html")


@pages_bp.route("/forget_pass", methods=["GET", "POST"], endpoint="forgot_password")
def forgot_password():
    if request.method == "POST":
        gmail = request.form.get("email", "").strip()

        if not gmail:
            return render_template("forgot_password.html", error="Please enter your email address.")

        account = Admin.query.filter(Admin.Gmail == gmail).first()
        if not account:
            return render_template("forgot_password.html", error="No Admin account found for that email.")

        # Store only the account identifier and OTP in the session.
        # Never put a password in a URL or store a plaintext password in the session.
        otp = str(secrets.randbelow(9000) + 1000)
        otp_hash = hmac.new(
            current_app.secret_key.encode("utf-8"),
            otp.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        session["reset_email"] = gmail
        # Flask's default session is client-side, so never store the plaintext OTP.
        session["reset_otp_hash"] = otp_hash
        session["reset_otp_expires"] = time.time() + 300  # 5 minutes
        session["reset_otp_attempts"] = 0
        session.pop("reset_otp_verified", None)

        try:
            email(
                app_settings.administrator1(),
                gmail,
                "OTP verification",
                f"The OTP for {gmail} is --{otp}-- for changing your password. It expires in 5 minutes.",
                app_settings.app_password_for(app_settings.administrator1()),
            )
        except NoInternetError as e:
            current_app.logger.error(e)
            session.pop("reset_email", None)
            session.pop("reset_otp_hash", None)
            session.pop("reset_otp_expires", None)
            session.pop("reset_otp_attempts", None)
            return render_template("forgot_password.html", error=str(e))
        except (EmailSendError, app_settings.MissingSettingError) as e:
            current_app.logger.error(e)
            session.pop("reset_email", None)
            session.pop("reset_otp_hash", None)
            session.pop("reset_otp_expires", None)
            session.pop("reset_otp_attempts", None)
            return render_template(
                "forgot_password.html",
                error="Could not send the OTP email. Please try again later.",
            )

        return render_template("forgot_password_verification.html")

    return render_template("forgot_password.html", email=request.args.get("email", ""))


@pages_bp.route("/forgot_password_verification", methods=["POST", "GET"])
def forgot_password_verification():
    if request.method == "GET":
        if not session.get("reset_email") or not session.get("reset_otp_hash"):
            return redirect(url_for("pages.forgot_password"))
        return render_template("forgot_password_verification.html")

    if request.is_json:
        data = request.get_json(silent=True) or {}
        otp = str(data.get("onepass", "")).strip()
    else:
        otp = request.form.get("onepass", "").strip()

    stored_otp_hash = session.get("reset_otp_hash")
    expires_at = session.get("reset_otp_expires", 0)
    attempts = session.get("reset_otp_attempts", 0)

    if not stored_otp_hash or time.time() > expires_at:
        session.pop("reset_otp_hash", None)
        session.pop("reset_otp_expires", None)
        session.pop("reset_otp_attempts", None)
        session.pop("reset_otp_verified", None)
        message = "The OTP has expired. Please request a new one."
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("pages.forgot_password"))

    if attempts >= 5:
        session.pop("reset_otp_hash", None)
        session.pop("reset_otp_expires", None)
        session.pop("reset_otp_attempts", None)
        session.pop("reset_otp_verified", None)
        message = "Too many incorrect attempts. Please request a new OTP."
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("pages.forgot_password"))

    submitted_otp_hash = hmac.new(
        current_app.secret_key.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not secrets.compare_digest(submitted_otp_hash, str(stored_otp_hash)):
        session["reset_otp_attempts"] = attempts + 1
        message = "Incorrect OTP."
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("pages.forgot_password"))

    session["reset_otp_verified"] = True
    session.pop("reset_otp_hash", None)
    session.pop("reset_otp_expires", None)
    session.pop("reset_otp_attempts", None)

    if request.is_json:
        return jsonify({"success": True, "message": "Code verified.", "redirect": url_for("pages.reset_password")})

    return redirect(url_for("pages.reset_password"))


@pages_bp.route("/reset_password", methods=["GET", "POST"], endpoint="reset_password")
def reset_password():
    if not session.get("reset_otp_verified") or not session.get("reset_email"):
        return redirect(url_for("pages.forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not new_password or not confirm_password:
            return render_template("reset_password.html", error="Please fill in all fields.")

        if new_password != confirm_password:
            return render_template("reset_password.html", error="Passwords do not match.")

        if len(new_password) < 8:
            return render_template("reset_password.html", error="New password must contain at least 8 characters.")

        gmail = session.get("reset_email")
        account = Admin.query.filter(Admin.Gmail == gmail).first()
        if not account:
            session.pop("reset_email", None)
            session.pop("reset_otp_verified", None)
            return redirect(url_for("pages.forgot_password"))

        account.password = bp.hashpw(new_password.encode(), bp.gensalt()).decode("utf-8")
        db.session.commit()

        session.pop("reset_email", None)
        session.pop("reset_otp_verified", None)
        current_app.logger.info(f"Password reset completed for {gmail}")
        return redirect(url_for("auth.login_page"))

    return render_template("reset_password.html")

@pages_bp.route("/profile", endpoint="profile")
@login_required
def profile():
    username = session.get("username", "")
    admin = Admin.query.filter_by(Gmail=username).first()
    if not admin:
        session.clear()
        return redirect(url_for("auth.login_page"))

    display_name = admin.name.strip() if admin.name and admin.name.strip() else "Set your name"
    return render_template(
        "profile.html",
        account=admin,
        display_name=display_name,
        initials=initials_for_name(admin.name),
        role="Administrator",
    )


@pages_bp.route("/profile-details", methods=["GET", "POST"], endpoint="profile_details")
@login_required
def profile_details():
    username = session.get("username", "")
    admin = Admin.query.filter_by(Gmail=username).first()
    if not admin:
        session.clear()
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return render_template("profile_details.html", account=admin, role="Administrator", error="Please enter your name.")
        if len(name) > 100:
            return render_template("profile_details.html", account=admin, role="Administrator", error="Name must be 100 characters or fewer.")

        admin.name = name
        db.session.commit()
        current_app.logger.info(f"{username} updated profile name")
        return redirect(url_for("pages.profile"))

    return render_template("profile_details.html", account=admin, role="Administrator")


@pages_bp.route("/delete-account", methods=["GET", "POST"], endpoint="delete_account")
@login_required
def delete_account():
    username = session.get("username", "")
    admin = Admin.query.filter_by(Gmail=username).first()
    if not admin:
        session.clear()
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        password = request.form.get("password", "")

        if not password:
            return render_template("delete_account.html", role="Administrator", error="Please enter your password.")

        if not bp.checkpw(password.encode(), password_bytes(admin.password)):
            return render_template("delete_account.html", role="Administrator", error="Incorrect password.")

        if Admin.query.count() <= 1:
            return render_template(
                "delete_account.html",
                role="Administrator",
                error="This is the only administrator account, so it can't be deleted.",
            )

        db.session.delete(admin)
        db.session.commit()
        current_app.logger.info(f"{username} deleted their own admin account")
        session.clear()
        return redirect(url_for("auth.login_page", account_deleted=1))

    return render_template("delete_account.html", role="Administrator")


@pages_bp.route("/settings", endpoint="settings")
@login_required
def settings():
    admin = Admin.query.filter_by(Gmail=session.get("username", "")).first()
    if not admin:
        session.clear()
        return redirect(url_for("auth.login_page"))
    return render_template("settings.html", role="Administrator", face_enabled=bool(admin.face_id))


@pages_bp.route("/change-password", methods=["GET", "POST"], endpoint="change_password")
@login_required
def change_password():
    username = session.get("username", "")
    admin = Admin.query.filter_by(Gmail=username).first()
    if not admin:
        session.clear()
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_password or not new_password or not confirm_password:
            return render_template("change_password.html", error="Please fill in all fields.", role="Administrator")

        if not bp.checkpw(current_password.encode(), password_bytes(admin.password)):
            return render_template("change_password.html", error="Current password is incorrect.", role="Administrator")

        if new_password != confirm_password:
            return render_template("change_password.html", error="New passwords do not match.", role="Administrator")

        if len(new_password) < 8:
            return render_template("change_password.html", error="New password must contain at least 8 characters.", role="Administrator")

        admin.password = bp.hashpw(new_password.encode(), bp.gensalt()).decode("utf-8")
        db.session.commit()
        current_app.logger.info(f"{username} changed the password")
        return redirect(url_for("pages.settings", password_changed=1))

    return render_template("change_password.html", role="Administrator")

@pages_bp.route("/face-id", methods=["GET", "POST"], endpoint="face_id")
@login_required
def face_id():
    username = session.get("username", "")
    admin = Admin.query.filter_by(Gmail=username).first()
    if not admin:
        session.clear()
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        image = request.files.get("face")
        if not image:
            return render_template("face_id.html", error="Please capture your face before saving.", enabled=bool(admin.face_id))

        image_bytes = image.read()
        if not face_detected(image_bytes):
            return render_template(
                "face_id.html",
                error="No face was detected in that photo. Please try again with your face clearly visible and well lit.",
                enabled=bool(admin.face_id),
            )
        image.stream.seek(0)

        old_face = admin.face_id
        new_face = save_face(image)
        admin.face_id = new_face
        db.session.commit()

        if old_face:
            old_path = os.path.join(FACE_ID_DIR, old_face)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    current_app.logger.warning(f"Could not remove old Face ID file for {username}")

        current_app.logger.info(f"{username} updated Face ID")
        return redirect(url_for("pages.settings", face_updated=1))

    return render_template("face_id.html", enabled=bool(admin.face_id))


@pages_bp.route("/add_teacher", methods=["GET", "POST"],endpoint="add_teacher")
@login_required
def add_teacher():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            class_teacher=request.form.get("class_teacher","").strip()
            class_teacher_sec=request.form.get("class_teacher_sec","").strip()
            confirm_password = request.form.get("confirm_password", "").strip()

            teacher=Teacher.query.filter(Teacher.class_teacher==class_teacher,
                                  Teacher.class_teacher_sec==class_teacher_sec
                                  ).first()
            
            if not username or not password or not confirm_password:
                return render_template("Error.html", data="Please fill in all fields.",location="/")

            print(teacher)

            if not teacher:
                verification=create_account(user=username,password=password,confirm_password=confirm_password,Table=Teacher,class_teacher=class_teacher,class_teacher_sec=class_teacher_sec,face_id=None)

                if not verification:
                    return render_template("Error.html", data="duplicate entry.",location="/add_teacher")

                if  verification=="pass":
                    return render_template("Error.html", data="passwords are not same.",location="/home")

                if verification:
                    return redirect("/teachers_data")
                current_app.logger.info(f"{session.get('username','')} has added {username} as a teacher")
            else:
                return render_template("Error.html", data="duplicate entry.",location="/add_teacher")
        return render_template("add_teacher.html")

@pages_bp.route("/add_student", methods=["GET", "POST"], endpoint="add_student")
@login_required
def add_student():
    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        class_input = request.form.get("class", "").strip()
        sec = request.form.get("section", "").strip()
        student_gmail = request.form.get("student_gmail", "").strip()
        dob = request.form.get("DOB", "").strip()
        mobile_no = request.form.get("mobile_no", "").strip()

        if not student_name or not class_input or not sec:
            return render_template("Error.html", data="Please fill in all required fields.", location="/add_student")

        try:
            class_value = int(class_input)
        except ValueError:
            return render_template("Error.html", data="invalid class value", location="/add_student")

        if class_value < 1 or class_value > 12:
            return render_template("Error.html", data="Class must be between 1 and 12.", location="/add_student")

        if sec not in ("A", "B", "C"):
            return render_template("Error.html", data="invalid section", location="/add_student")

        dob_value = None
        if dob:
            try:
                dob_value = datetime.strptime(dob, "%Y-%m-%d").date()
            except ValueError:
                return render_template("Error.html", data="invalid date of birth", location="/add_student")

        mobile_value = None
        if mobile_no:
            if not mobile_no.isdigit():
                return render_template("Error.html", data="invalid mobile number", location="/add_student")
            mobile_value = int(mobile_no)

        # Automatically generate the next roll number for this class and section.
        # A=1, B=2, C=3:
        # Class 5-A -> 50101, 50102, ...
        # Class 5-B -> 50201, 50202, ...
        # Class 5-C -> 50301, 50302, ...
        section_code = {"A": 1, "B": 2, "C": 3}[sec]
        roll_prefix = class_value * 1000 + section_code * 100

        last_student = (
            Student.query
            .filter(
                Student.student_class == class_value,
                Student.section == sec
            )
            .order_by(Student.roll_no.desc())
            .first()
        )

        if last_student:
            next_roll_no = last_student.roll_no + 1
        else:
            next_roll_no = roll_prefix + 1

        # Allow roll numbers 01 through 99 within each class/section.
        if next_roll_no > roll_prefix + 99:
            return render_template(
                "Error.html",
                data=f"No more roll numbers available for Class {class_value}-{sec}.",
                location="/add_student"
            )

        # Protect against an already-used generated roll number.
        while Student.query.filter_by(roll_no=next_roll_no).first():
            next_roll_no += 1
            if next_roll_no > roll_prefix + 99:
                return render_template(
                    "Error.html",
                    data=f"No more roll numbers available for Class {class_value}-{sec}.",
                    location="/add_student"
                )

        student = Student(
            roll_no=next_roll_no,
            student_name=student_name,
            student_class=class_value,
            section=sec,
            student_gmail=student_gmail or None,
            DOB=dob_value,
            mobile_no=mobile_value
        )

        try:
            db.session.add(student)
            current_app.logger.info(f"{session.get('username','')} has added {student_name} as a student")
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Could not add student: {e}")
            return render_template("Error.html", data="Could not add the student.", location="/add_student")

        current_app.logger.info(f"{session.get('username', '')} added student {student_name} (roll no {student.roll_no})")

        session["class_value"] = class_value
        session["sec"] = sec

        return redirect("/home")

    return render_template("add_student.html")