from flask import g, Blueprint, render_template, redirect, request, session, url_for, current_app, jsonify
import os
from logging.handlers import RotatingFileHandler
import bcrypt as bp

from shared.models import Teacher
from shared.services.face_id_service import match_face
from shared.services.email_service import email_file, EmailSendError
from shared import colleges
from shared.security import LoginThrottle
from shared import settings as app_settings
from shared.services.profile_service import password_bytes

auth_bp = Blueprint("auth", __name__)
throttle = LoginThrottle()


def _login_form(error, info=None, email=""):
    return render_template(
        "login_page.html", error=error, prefill_email=email,
        selected_college=info.slug if info else request.form.get("college", ""),
    )


def _has_assignment(teacher):
    """True if the teacher is class advisor of a department / year / section."""
    return bool(
        teacher.advisor_dept
        and teacher.advisor_year is not None
        and teacher.advisor_section
    )


def _remember_assignment(teacher):
    session["advisor_dept"] = teacher.advisor_dept
    session["advisor_year"] = int(teacher.advisor_year)
    session["advisor_section"] = teacher.advisor_section


@auth_bp.route("/has-face-id", methods=["POST"], endpoint="has_face_id")
def has_face_id():
    """
    Lets the login page check, right after the username is entered,
    whether that teacher has Face ID set up - so the Face ID button
    is only shown to people it will actually work for.
    """
    username = request.form.get("username", "").strip()
    if not username or colleges.activate(request.form.get("college", "")) is None:
        return jsonify({"has_face_id": False})

    teacher = Teacher.query.filter(Teacher.Gmail == username).first()
    return jsonify({"has_face_id": bool(teacher and teacher.face_id)})



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

        teacher = Teacher.query.filter(Teacher.Gmail == user_n).first()

        if teacher and bp.checkpw(pass_n.encode(), password_bytes(teacher.password)):
            if not _has_assignment(teacher):
                current_app.logger.error(f"{user_n} has no class assigned")
                return _login_form("No class is assigned to this account yet. Ask the administrator.", info, user_n)
            throttle.clear(key)
            session.clear()
            session["username"] = user_n
            session["logged_in"] = True
            session["college"] = info.slug
            _remember_assignment(teacher)
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
    # that teacher when it's supplied (falls back to checking everyone if
    # not, keeping this endpoint backward compatible).
    username = request.form.get("username", "").strip()
    candidates_query = Teacher.query.filter(Teacher.face_id.isnot(None))
    if username:
        candidates_query = candidates_query.filter(Teacher.Gmail == username)
    candidates = candidates_query.all()

    matched_teacher = None
    for teacher in candidates:
        if match_face(teacher.face_id, captured_bytes):
            matched_teacher = teacher
            break

    if matched_teacher and not _has_assignment(matched_teacher):
        current_app.logger.error(f"{matched_teacher.Gmail} has no class assigned")
        return render_template("Error.html", data="No class is assigned to this account yet. Ask the administrator.", location="/")

    if matched_teacher:
        session["username"] = matched_teacher.Gmail
        session["logged_in"] = True
        session["college"] = g.college_slug
        _remember_assignment(matched_teacher)
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
    current_app.logger.info(
        f"{session.get('username', '')} has logged out"
    )

    # Hand off to the RotatingFileHandler's own rollover instead of opening
    # App.log directly: doRollover() closes the live stream, renames it to
    # App.log.1, and opens a fresh App.log - all under the handler's lock,
    # so it can't race with (or get corrupted by) log lines other requests
    # are writing at the same time.
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
            email_file(app_settings.administrator2(), app_settings.administrator1(), "log file", f"this is the log file of {session.get('username','')}", backup_log_path, app_settings.app_password_for(app_settings.administrator2()))
        except (EmailSendError, app_settings.MissingSettingError) as e:
            # Don't block logout just because the log-file backup email
            # couldn't be sent (e.g. no internet connection).
            current_app.logger.warning(f"Could not email log file on logout: {e}")

    session.clear()
    return redirect(url_for("auth.login_page"))
