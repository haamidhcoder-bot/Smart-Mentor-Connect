from flask import g, Blueprint, render_template, redirect, request, session, url_for, current_app, jsonify
import hashlib
import hmac
import os
import re
import secrets
import time
from logging.handlers import RotatingFileHandler
import bcrypt as bp

from shared import db
from shared.models import Admin
from shared.services.create_account_service import create_account
from shared.services.face_id_service import match_face
from shared.services.email_service import email, email_file, NoInternetError, EmailSendError
from shared import colleges
from shared.security import LoginThrottle
from shared.colleges import CollegeError
from shared import settings as app_settings
from shared.services.profile_service import password_bytes


auth_bp = Blueprint("auth", __name__)
throttle = LoginThrottle()


def _login_form(error, info=None, email=""):
    return render_template(
        "login_page.html", error=error, prefill_email=email,
        selected_college=info.slug if info else request.form.get("college", ""),
    )


@auth_bp.route("/has-face-id", methods=["POST"], endpoint="has_face_id")
def has_face_id():
    """
    Lets the login page check, right after the username is entered,
    whether that admin has Face ID set up - so the Face ID button is
    only shown to people it will actually work for.
    """
    username = request.form.get("username", "").strip()
    if not username or colleges.activate(request.form.get("college", "")) is None:
        return jsonify({"has_face_id": False})

    admin = Admin.query.filter(Admin.Gmail == username).first()
    return jsonify({"has_face_id": bool(admin and admin.face_id)})


@auth_bp.route("/", methods=["POST", "GET"], endpoint="login_page")
def login_page():
    if request.method == "POST":
        info = colleges.activate(request.form.get("college", ""))
        user_n = request.form.get("username", "").strip()
        if info is None:
            return _login_form("Please select your college.", None, user_n)
        pass_n = request.form.get("password", "")
        remember = request.form.get("remember", "")

        key = throttle.key(info.slug, user_n)
        wait = throttle.locked_for(key)
        if wait:
            current_app.logger.warning(f"login locked for {user_n}")
            return _login_form(f"Too many failed attempts. Try again in {wait // 60 + 1} minute(s).", info, user_n)

        Admins = Admin.query.filter(
            Admin.Gmail == user_n
        ).first()

        if Admins and bp.checkpw(pass_n.encode(), password_bytes(Admins.password)):
            throttle.clear(key)
            session.clear()
            session["username"] = user_n
            session["logged_in"] = True
            session["college"] = info.slug
            if remember:
                session.permanent = True
            current_app.logger.info(f"{session.get('username', '')} logged in")
            return redirect("/home")
        else:
            throttle.record_failure(key)
            current_app.logger.error("incorrect username or password")
            return _login_form("Incorrect email or password.", info, user_n)
    elif session.get("logged_in"):
        current_app.logger.info(f"{session.get('username', '')} logged in back")
        return redirect("/home")
    return render_template("login_page.html", selected_college=request.args.get("college", ""))


@auth_bp.route("/login-face", methods=["POST"], endpoint="login_face")
def login_face():
    image = request.files.get("face")

    if colleges.activate(request.form.get("college", "")) is None:
        return render_template("Error.html", data="Please select your college.", location="/")

    if not image:
        return render_template("Error.html", data="No image received", location="/")

    captured_bytes = image.read()

    # The login page now asks for the email first, so narrow the search to
    # that admin when it's supplied (falls back to checking everyone if not,
    # keeping this endpoint backward compatible).
    username = request.form.get("username", "").strip()
    candidates_query = Admin.query.filter(Admin.face_id.isnot(None))
    if username:
        candidates_query = candidates_query.filter(Admin.Gmail == username)
    candidates = candidates_query.all()

    matched_admin = None
    for admin in candidates:
        if match_face(admin.face_id, captured_bytes):
            matched_admin = admin
            break

    if matched_admin:
        session["username"] = matched_admin.Gmail
        session["logged_in"] = True
        session["college"] = g.college_slug
        current_app.logger.info(f"{session.get('username', '')} logged in with Face ID")
        return redirect("/home")

    current_app.logger.error("face id login failed: no matching face")
    # Send them back to the password step (not the email step) so they
    # don't have to re-type their email after a failed Face ID attempt.
    retry_location = (
        url_for("auth.login_page", email=username, college=g.college_slug)
        if username else url_for("auth.login_page", college=g.college_slug)
    )
    return render_template("Error.html", data="Face not recognized", location=retry_location)


@auth_bp.route("/log-out", methods=["POST", "GET"])
def log_out():
    current_app.logger.info(f"{session.get('username', '')} has logged out")

    # Hand off to the RotatingFileHandler's own rollover instead of opening
    # App.log directly: doRollover() closes the live stream, renames it to
    # App.log.1, and opens a fresh App.log - all under the handler's lock,
    # so it can't race with (or get corrupted by) log lines other requests
    # are writing at the same time. Manually truncating the file the
    # handler still had open was the old bug here.
    backup_log_path = None
    file_handler = next(
        (h for h in current_app.logger.handlers if isinstance(h, RotatingFileHandler)),
        None,
    )
    if file_handler:
        file_handler.acquire()
        try:
            file_handler.doRollover()
            backup_log_path = f"{file_handler.baseFilename}.1"
        except OSError as e:
            # Rolling over can still fail transiently (antivirus scan,
            # cloud-sync lock, another process briefly holding the file) -
            # that should never stop someone from logging out. Just skip
            # this logout's backup/email and move on.
            current_app.logger.warning(f"Could not rotate log file on logout: {e}")
        finally:
            file_handler.release()

    if backup_log_path and os.path.exists(backup_log_path):
        try:
            email_file(
                app_settings.administrator2(),
                app_settings.administrator1(),
                "log file",
                f"this is the log file of {session.get('username', '')}",
                backup_log_path,
                app_settings.app_password_for(app_settings.administrator2()),
            )
        except (EmailSendError, app_settings.MissingSettingError) as e:
            # Don't block logout just because the log-file backup email
            # couldn't be sent (e.g. no internet connection).
            current_app.logger.warning(f"Could not email log file on logout: {e}")

    session.clear()
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/register", methods=["POST", "GET"])
def register():
    """Start administrator registration without putting credentials in the URL."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not password or not confirm_password:
            return render_template("Error.html", data="Please fill in all fields.", location="/")

        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match.")

        if not re.match(r"^(?=.*[0-9])(?=.*[a-z]).+$", password):
            return render_template(
                "register.html",
                error="Password must contain at least one lowercase letter and one number.",
            )

        # Which college is this administrator for - an existing one, or a
        # brand-new college that gets its own database once the OTP is verified?
        if request.form.get("college_mode") == "new":
            try:
                college_name = colleges.validate_name(request.form.get("new_college_name", ""))
            except CollegeError as e:
                return render_template("register.html", error=str(e))
            if colleges.get_college(colleges.slugify(college_name)):
                return render_template(
                    "register.html",
                    error="A college with this name is already registered. Choose it from the list instead.",
                )
            college_label = f"{college_name} (new college)"
            new_college_name, college_slug = college_name, None
        else:
            existing = colleges.get_college(request.form.get("college", ""))
            if existing is None:
                return render_template("register.html", error="Please select your college.")
            college_label = existing.name
            new_college_name, college_slug = None, existing.slug

        # Do not put username/password in the verification URL.
        # The password is hashed before being placed in Flask's signed session.
        password_hash = bp.hashpw(password.encode(), bp.gensalt()).decode("utf-8")

        otp = str(secrets.randbelow(9000) + 1000)
        otp_hash = hmac.new(
            current_app.secret_key.encode("utf-8"),
            otp.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        session["registration_email"] = username
        session["registration_college"] = college_slug
        session["registration_new_college"] = new_college_name
        session["registration_password_hash"] = password_hash
        session["registration_otp_hash"] = otp_hash
        session["registration_otp_expires"] = time.time() + 300
        session["registration_otp_attempts"] = 0

        try:
            email(
                app_settings.administrator1(),
                app_settings.administrator2(),
                "OTP verification",
                f"The OTP for {username} is --{otp}-- for registering an account for {college_label}. It expires in 5 minutes.",
                app_settings.app_password_for(app_settings.administrator1()),
            )
        except NoInternetError as e:
            current_app.logger.error(e)
            session.pop("registration_email", None)
            session.pop("registration_password_hash", None)
            session.pop("registration_otp_hash", None)
            session.pop("registration_otp_expires", None)
            session.pop("registration_otp_attempts", None)
            session.pop("registration_college", None)
            session.pop("registration_new_college", None)
            return render_template("register.html", error=str(e))
        except (EmailSendError, app_settings.MissingSettingError) as e:
            current_app.logger.error(e)
            session.pop("registration_email", None)
            session.pop("registration_password_hash", None)
            session.pop("registration_otp_hash", None)
            session.pop("registration_otp_expires", None)
            session.pop("registration_otp_attempts", None)
            session.pop("registration_college", None)
            session.pop("registration_new_college", None)
            return render_template(
                "register.html",
                error="Could not send the OTP email. Please try again later.",
            )

        current_app.logger.info(f"Registration OTP sent for {username}")
        return render_template("register_verification.html")

    return render_template("register.html")


@auth_bp.route("/register_verification", methods=["POST", "GET"])
def register_verification():
    """Verify registration OTP and create the account without exposing credentials in the URL."""
    if not session.get("registration_email") or not session.get("registration_password_hash"):
        return redirect(url_for("auth.register"))

    if request.method == "GET":
        return render_template("register_verification.html")

    if request.is_json:
        data = request.get_json(silent=True) or {}
        otp = str(data.get("onepass", "")).strip()
    else:
        otp = request.form.get("onepass", "").strip()

    stored_otp_hash = session.get("registration_otp_hash")
    expires_at = session.get("registration_otp_expires", 0)
    attempts = session.get("registration_otp_attempts", 0)

    def clear_registration_state():
        for key in (
            "registration_email",
            "registration_password_hash",
            "registration_otp_hash",
            "registration_otp_expires",
            "registration_otp_attempts",
            "registration_college",
            "registration_new_college",
        ):
            session.pop(key, None)

    if not stored_otp_hash or time.time() > expires_at:
        clear_registration_state()
        message = "The OTP has expired. Please start registration again."
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("auth.register"))

    if attempts >= 5:
        clear_registration_state()
        message = "Too many incorrect attempts. Please start registration again."
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("auth.register"))

    submitted_otp_hash = hmac.new(
        current_app.secret_key.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not secrets.compare_digest(submitted_otp_hash, str(stored_otp_hash)):
        session["registration_otp_attempts"] = attempts + 1
        message = "Incorrect OTP."
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("auth.register"))

    username = session["registration_email"]
    password_hash = session["registration_password_hash"]

    # Work out the college: create the new one now (the OTP proves the
    # owners approved it), or use the existing one chosen on the form.
    try:
        if session.get("registration_new_college"):
            college = colleges.create_college(session["registration_new_college"])
        else:
            college = colleges.get_college(session.get("registration_college"))
    except CollegeError as e:
        clear_registration_state()
        message = str(e)
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("auth.register"))

    if college is None:
        clear_registration_state()
        message = "Please select your college."
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("auth.register"))
    colleges.activate(college.slug)

    # The password was already validated and hashed before OTP verification.
    if Admin.query.filter_by(Gmail=username).first():
        clear_registration_state()
        message = "An account with this email already exists."
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        return render_template("Error.html", data=message, location=url_for("auth.register"))

    verified = create_account(
        user=username,
        password_hash=password_hash,
        Table=Admin,
    )

    if verified is True:
        clear_registration_state()
        current_app.logger.info(f"{username} completed account registration")
        if request.is_json:
            return jsonify({"success": True, "message": "Code verified.", "redirect": url_for("auth.login_page", college=college.slug)})
        return redirect(url_for("auth.login_page", college=college.slug))

    clear_registration_state()
    message = "Unable to create the account. Please try again."

    if request.is_json:
        return jsonify({"success": False, "message": message}), 400
    return render_template("Error.html", data=message, location=url_for("auth.register"))
