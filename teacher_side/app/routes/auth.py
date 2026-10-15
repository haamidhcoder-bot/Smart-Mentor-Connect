from flask import Blueprint, render_template, redirect, request, session, url_for, current_app, jsonify
import os
from logging.handlers import RotatingFileHandler
import bcrypt as bp

from shared.models import Teacher
from shared.services.face_id_service import match_face
from shared.services.email_service import email_file, EmailSendError
from shared import settings as app_settings
from shared.services.profile_service import password_bytes

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/has-face-id", methods=["POST"], endpoint="has_face_id")
def has_face_id():
    """
    Lets the login page check, right after the username is entered,
    whether that teacher has Face ID set up - so the Face ID button
    is only shown to people it will actually work for.
    """
    username = request.form.get("username", "").strip()
    if not username:
        return jsonify({"has_face_id": False})

    teacher = Teacher.query.filter(Teacher.Gmail == username).first()
    return jsonify({"has_face_id": bool(teacher and teacher.face_id)})



@auth_bp.route("/", methods=["POST", "GET"], endpoint="login_page")
def login_page():
    if request.method == "POST":
        user_n = request.form.get("username", "").strip()
        pass_n = request.form.get("password", "")
        session["username"] = user_n
        remember = request.form.get("remember", "")

        teacher = Teacher.query.filter(Teacher.Gmail == user_n).first()

        if teacher and bp.checkpw(pass_n.encode(), password_bytes(teacher.password)):
            if teacher.class_teacher is None or not teacher.class_teacher_sec:
                session.clear()
                current_app.logger.error(f"{user_n} has no class assigned")
                return render_template("Error.html", data="No class is assigned to this account yet. Ask the administrator.", location="/")
            session["logged_in"] = True
            if remember:
                session.permanent = True
            current_app.logger.info(f"{session.get('username', '')} logged in")
            return render_template(
                "Home.html",
                class_value=int(teacher.class_teacher),
                sec=teacher.class_teacher_sec
            )
        else:
            current_app.logger.error("incorrect username or password")
            return render_template("Error.html", data=" incorrect username or password", location="/")
    elif session.permanent:
        current_app.logger.info(f"{session.get('username', '')} logged in back")
        return render_template(
            "Home.html",
            class_value=int(session.get("class_value", 0)),
            sec=session.get("sec", ""),
            log=session.permanent,
            user=session.get("username", "")
        )
    return render_template("login_page.html")


@auth_bp.route("/login-face", methods=["POST"], endpoint="login_face")
def login_face():
    image = request.files.get("face")

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

    if matched_teacher and (matched_teacher.class_teacher is None or not matched_teacher.class_teacher_sec):
        current_app.logger.error(f"{matched_teacher.Gmail} has no class assigned")
        return render_template("Error.html", data="No class is assigned to this account yet. Ask the administrator.", location="/")

    if matched_teacher:
        session["username"] = matched_teacher.Gmail
        session["logged_in"] = True
        current_app.logger.info(f"{session.get('username', '')} logged in with Face ID")
        return render_template(
            "Home.html",
            class_value=int(matched_teacher.class_teacher),
            sec=matched_teacher.class_teacher_sec
        )

    current_app.logger.error("face id login failed: no matching face")
    # Send them back to the password step (not the email step) so they
    # don't have to re-type their email after a failed Face ID attempt.
    retry_location = url_for("auth.login_page", email=username) if username else url_for("auth.login_page")
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
