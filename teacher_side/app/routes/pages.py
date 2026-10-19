from flask import Blueprint, render_template, session, request, redirect, url_for, current_app, jsonify
import hashlib
import hmac
import secrets
import time
import bcrypt as bp
import os

from shared.extensions import db
from shared import colleges
from shared import login_required
from shared.models import Teacher
from shared import settings as app_settings
from shared.services.email_service import email, NoInternetError, EmailSendError
from shared.services.face_id_service import save_face, face_detected, FACE_ID_DIR
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

        info = colleges.activate(request.form.get("college", ""))
        if info is None:
            return render_template("forgot_password.html", error="Please select your college.", email=gmail)

        account = Teacher.query.filter(Teacher.Gmail == gmail).first()
        if not account:
            return render_template("forgot_password.html", error="No Teacher account found for that email in this college.", email=gmail)

        # Store only the account identifier and OTP in the session.
        # Never put a password in a URL or store a plaintext password in the session.
        otp = str(secrets.randbelow(9000) + 1000)
        otp_hash = hmac.new(
            current_app.secret_key.encode("utf-8"),
            otp.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        session["reset_email"] = gmail
        session["reset_college"] = info.slug
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
            session.pop("reset_college", None)
            session.pop("reset_otp_hash", None)
            session.pop("reset_otp_expires", None)
            session.pop("reset_otp_attempts", None)
            return render_template("forgot_password.html", error=str(e))
        except (EmailSendError, app_settings.MissingSettingError) as e:
            current_app.logger.error(e)
            session.pop("reset_email", None)
            session.pop("reset_college", None)
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

    # The account belongs to the college chosen on the forgot-password page.
    if colleges.activate(session.get("reset_college")) is None:
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
        account = Teacher.query.filter(Teacher.Gmail == gmail).first()
        if not account:
            session.pop("reset_email", None)
            session.pop("reset_college", None)
            session.pop("reset_otp_verified", None)
            return redirect(url_for("pages.forgot_password"))

        account.password = bp.hashpw(new_password.encode(), bp.gensalt()).decode("utf-8")
        db.session.commit()

        session.pop("reset_email", None)

        session.pop("reset_college", None)
        session.pop("reset_otp_verified", None)
        current_app.logger.info(f"Password reset completed for {gmail}")
        return redirect(url_for("auth.login_page"))

    return render_template("reset_password.html")

@pages_bp.route("/profile", endpoint="profile")
@login_required
def profile():
    username = session.get("username", "")
    teacher = Teacher.query.filter_by(Gmail=username).first()
    if not teacher:
        session.clear()
        return redirect(url_for("auth.login_page"))

    display_name = teacher.name.strip() if teacher.name and teacher.name.strip() else "Set your name"
    return render_template(
        "profile.html",
        account=teacher,
        display_name=display_name,
        initials=initials_for_name(teacher.name),
        role="Teacher",
    )


@pages_bp.route("/profile-details", methods=["GET", "POST"], endpoint="profile_details")
@login_required
def profile_details():
    username = session.get("username", "")
    teacher = Teacher.query.filter_by(Gmail=username).first()
    if not teacher:
        session.clear()
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return render_template("profile_details.html", account=teacher, role="Teacher", error="Please enter your name.")
        if len(name) > 100:
            return render_template("profile_details.html", account=teacher, role="Teacher", error="Name must be 100 characters or fewer.")

        teacher.name = name
        db.session.commit()
        current_app.logger.info(f"{username} updated profile name")
        return redirect(url_for("pages.profile"))

    return render_template("profile_details.html", account=teacher, role="Teacher")


@pages_bp.route("/settings", endpoint="settings")
@login_required
def settings():
    teacher = Teacher.query.filter_by(Gmail=session.get("username", "")).first()
    if not teacher:
        session.clear()
        return redirect(url_for("auth.login_page"))
    return render_template("settings.html", role="Teacher", face_enabled=bool(teacher.face_id))


@pages_bp.route("/change-password", methods=["GET", "POST"], endpoint="change_password")
@login_required
def change_password():
    username = session.get("username", "")
    teacher = Teacher.query.filter_by(Gmail=username).first()
    if not teacher:
        session.clear()
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_password or not new_password or not confirm_password:
            return render_template("change_password.html", error="Please fill in all fields.", role="Teacher")

        if not bp.checkpw(current_password.encode(), password_bytes(teacher.password)):
            return render_template("change_password.html", error="Current password is incorrect.", role="Teacher")

        if new_password != confirm_password:
            return render_template("change_password.html", error="New passwords do not match.", role="Teacher")

        if len(new_password) < 8:
            return render_template("change_password.html", error="New password must contain at least 8 characters.", role="Teacher")

        teacher.password = bp.hashpw(new_password.encode(), bp.gensalt()).decode("utf-8")
        db.session.commit()
        current_app.logger.info(f"{username} changed the password")
        return redirect(url_for("pages.settings", password_changed=1))

    return render_template("change_password.html", role="Teacher")


@pages_bp.route("/face-id", methods=["GET", "POST"], endpoint="face_id")
@login_required
def face_id():
    username = session.get("username", "")
    teacher = Teacher.query.filter_by(Gmail=username).first()
    if not teacher:
        session.clear()
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        image = request.files.get("face")
        if not image:
            return render_template("face_id.html", error="Please capture your face before saving.", enabled=bool(teacher.face_id))

        image_bytes = image.read()
        if not face_detected(image_bytes):
            return render_template(
                "face_id.html",
                error="No face was detected in that photo. Please try again with your face clearly visible and well lit.",
                enabled=bool(teacher.face_id),
            )
        image.stream.seek(0)

        old_face = teacher.face_id
        new_face = save_face(image)
        teacher.face_id = new_face
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

    return render_template("face_id.html", enabled=bool(teacher.face_id))
