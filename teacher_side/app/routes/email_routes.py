import threading
import uuid

from flask import Blueprint, render_template, request, session, jsonify, current_app

from shared import colleges
from shared import settings as app_settings
from shared.models import Student, Exam, Mark
from shared.services import grading
from shared.services.course_service import course_name, courses_for, semesters_for_year
from shared.services.email_service import email, NoInternetError, EmailSendError
from shared import login_required
from shared.decorators import advisor_required

email_bp = Blueprint("email", __name__)

# --- In-memory job store -----------------------------------------------
# Keyed by job_id -> {status, sent_count, total, message, cancel_requested, username}
# NOTE: this lives in process memory. It's fine for a single Flask process,
# but if you ever run multiple gunicorn/uwsgi workers, a job started on one
# worker won't be visible to another. Move this to Redis or a DB table if
# you scale beyond one worker.
_jobs = {}
_jobs_lock = threading.Lock()


@email_bp.route("/loading", endpoint="loading")
def loading():
    """Shown immediately after the user clicks 'Send Results'.
    This page's JS kicks off /send_results (which starts a background
    thread and returns a job_id right away), then polls
    /send_results/status/<job_id> until it's done."""
    sub = request.args.get("sub", "")
    exa = request.args.get("exam", "")
    return render_template("loading.html", sub=sub, exam=exa)


@email_bp.route("/success", endpoint="success")
def success():
    sent_count = request.args.get("sent", "0")
    sub = request.args.get("sub", "")
    exa = request.args.get("exam", "")
    current_app.logger.info(f"{session.get('username', '')} susccesfully sent emails")
    return render_template("success.html", sent_count=sent_count, sub=sub, exam=exa)


@email_bp.route("/error_page", endpoint="error_page")
def error_page():
    msg = request.args.get("msg", "Something went wrong while sending results.")
    current_app.logger.error("Something went wrong while sending results.")
    return render_template("Error.html", data=msg, location="/home")


def _run_send_job(app, college_slug, job_id, sender, password, dept, year, sec, sub, exa):
    """Runs on a background thread. Sends every email and keeps _jobs[job_id]
    updated so the frontend can poll for progress/completion."""
    with app.app_context():
        # The background thread has no request, so say which college's
        # database to read the results from.
        colleges.activate(college_slug)
        try:
            students = Student.query.filter(
                Student.department == dept,
                Student.year == year,
                Student.section == sec
            ).all()

            exam = Exam.query.filter(Exam.exam_name == exa).first()
            res = []
            if exam is not None:
                res = Mark.query.join(
                    Student, Student.roll_no == Mark.roll_no
                ).filter(
                    Student.department == dept,
                    Student.year == year,
                    Student.section == sec,
                    Mark.exam_id == exam.exam_id,
                    Mark.subject == sub
                ).all()

            pairs = [
                (stu, mark)
                for stu in students
                for mark in res
                if stu.roll_no == mark.roll_no
            ]

            with _jobs_lock:
                _jobs[job_id]["total"] = len(pairs)

            sent_count = 0
            for stu, mark in pairs:
                with _jobs_lock:
                    if _jobs[job_id]["cancel_requested"]:
                        _jobs[job_id]["status"] = "cancelled"
                        return

                if not stu.student_gmail:
                    continue  # no email address on file

                grade, _point = grading.grade_for(mark.marks)
                result = (
                    f"passed with grade {grade}"
                    if grading.is_pass(mark.marks)
                    else "did not reach the pass mark"
                )
                title = f"{course_name(sub)} ({sub})"
                msg = f"""Dear {stu.student_name},

Your result for {title} in the {exa}: {mark.marks} / 100 - you {result}.
(Pass mark: {grading.pass_mark()}.)
Please speak to your class advisor if you would like to discuss your progress.

Regards,
Class Advisor / College Administration"""
                try:
                    email(sender, stu.student_gmail, f"{sub}-{exa}-Marks", msg, password)
                    sent_count += 1
                    with _jobs_lock:
                        _jobs[job_id]["sent_count"] = sent_count
                except NoInternetError as e:
                    # No internet / can't reach the mail server - stop the job
                    # and surface a clear, actionable message instead of
                    # silently losing the rest of the emails.
                    app.logger.error(e)
                    with _jobs_lock:
                        _jobs[job_id]["status"] = "error"
                        _jobs[job_id]["message"] = (
                            f"{e} Results already sent to {sent_count} "
                            f"student(s) before the connection was lost."
                        )
                    return
                except (EmailSendError, app_settings.MissingSettingError) as e:
                    app.logger.error(e)
                    with _jobs_lock:
                        _jobs[job_id]["status"] = "error"
                        _jobs[job_id]["message"] = f"{e}\nContact the developer"
                    return

            with _jobs_lock:
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["sent_count"] = sent_count

        except Exception as e:
            app.logger.exception("send_results background job crashed")
            with _jobs_lock:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["message"] = str(e)


@email_bp.route("/send_results", methods=["POST"], endpoint="send_results")
@login_required
@advisor_required
def send_results():
    """Called via fetch() from loading.html. Starts sending emails on a
    background thread and returns a job_id immediately, instead of blocking
    the request until every email is sent."""
    # Results go out from the college's sender account (ADMIN1_EMAIL).
    # Teacher logins are teachers' own addresses, which have no app password
    # configured, so looking the logged-in teacher up always failed before.
    try:
        sender = app_settings.administrator1()
        PASSWORD = app_settings.app_password_for(sender)
    except app_settings.MissingSettingError as e:
        current_app.logger.error(e)
        PASSWORD = None
    if not PASSWORD:
        return jsonify({"status": "error", "message": "Email sender account is not configured on the server."}), 500

    # The group always comes from the logged-in advisor's assignment.
    dept = session["advisor_dept"]
    year = int(session["advisor_year"])
    sec = session["advisor_section"]
    sub = request.form.get("subject", "")
    exa = request.form.get("exam", "")

    if not sub or not exa:
        return jsonify({"status": "error", "message": "Missing course or exam."}), 400

    if sub == "All":
        return jsonify({"status": "error", "message": "Select a single course to send results for."}), 400

    exam = Exam.query.filter(Exam.exam_name == exa).first()
    course = next((c for c in courses_for(dept, year) if c.code == sub), None)
    if exam is None or exam.semester not in semesters_for_year(year) or course is None or course.semester != exam.semester:
        return jsonify({"status": "error", "message": "That course and exam do not belong together for your class."}), 400

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "sent_count": 0,
            "total": 0,
            "message": "",
            "cancel_requested": False,
            "username": session.get("username", ""),
        }

    thread = threading.Thread(
        target=_run_send_job,
        args=(
            current_app._get_current_object(),
            session["college"],
            job_id,
            sender,
            PASSWORD,
            dept,
            year,
            sec,
            sub,
            exa,
        ),
        daemon=True,
    )
    thread.start()

    return jsonify({"status": "started", "job_id": job_id})


@email_bp.route("/send_results/status/<job_id>", methods=["GET"], endpoint="send_results_status")
@login_required
def send_results_status(job_id):
    """Polled by loading.html (while on the page) and by the background
    watcher script (after the user backgrounds the job) to check progress."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return jsonify({"status": "error", "message": "Unknown or expired job."}), 404
        if job["username"] != session.get("username", ""):
            return jsonify({"status": "error", "message": "Not your job."}), 403

        return jsonify({
            "status": job["status"],
            "sent_count": job["sent_count"],
            "total": job["total"],
            "message": job["message"],
        })


@email_bp.route("/send_results/cancel/<job_id>", methods=["POST"], endpoint="send_results_cancel")
@login_required
def send_results_cancel(job_id):
    """Sets a cancel flag the background thread checks between emails.
    Emails already sent stay sent - this just stops the rest from going out."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return jsonify({"status": "error", "message": "Unknown or expired job."}), 404
        if job["username"] != session.get("username", ""):
            return jsonify({"status": "error", "message": "Not your job."}), 403
        job["cancel_requested"] = True

    return jsonify({"status": "ok"})
