import threading
import time
from datetime import datetime

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from shared.models import Student

auth_bp = Blueprint("auth", __name__)

# The database has no student passwords, so a student signs in with their
# roll number and date of birth. Because a date of birth is guessable, failed
# attempts are throttled per roll number (not per session, which an attacker
# could simply reset by clearing cookies).
MAX_FAILURES = 5
LOCK_SECONDS = 300
_failures = {}
_lock = threading.Lock()


def _locked_for(roll_no):
    with _lock:
        count, since = _failures.get(roll_no, (0, 0))
        if count >= MAX_FAILURES:
            remaining = LOCK_SECONDS - (time.time() - since)
            if remaining > 0:
                return int(remaining) + 1
            _failures.pop(roll_no, None)
    return 0


def _record_failure(roll_no):
    with _lock:
        count, _ = _failures.get(roll_no, (0, 0))
        _failures[roll_no] = (count + 1, time.time())


def _clear_failures(roll_no):
    with _lock:
        _failures.pop(roll_no, None)


@auth_bp.route("/", methods=["GET", "POST"], endpoint="login_page")
def login_page():
    if request.method == "GET":
        if session.get("logged_in"):
            return redirect(url_for("home.home"))
        return render_template("login_page.html")

    roll_raw = request.form.get("roll_no", "").strip()
    dob_raw = request.form.get("dob", "").strip()
    generic = "Incorrect roll number or date of birth."

    if not roll_raw.isdigit() or not dob_raw:
        return render_template("login_page.html", error=generic, roll_no=roll_raw)
    roll_no = int(roll_raw)

    wait = _locked_for(roll_no)
    if wait:
        current_app.logger.warning(f"login locked for roll {roll_no}")
        return render_template(
            "login_page.html",
            error=f"Too many failed attempts. Try again in {wait // 60 + 1} minute(s).",
            roll_no=roll_raw,
        )

    try:
        dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()
    except ValueError:
        return render_template("login_page.html", error=generic, roll_no=roll_raw)

    student = Student.query.filter_by(roll_no=roll_no).first()
    if not student or student.DOB is None or student.DOB != dob:
        _record_failure(roll_no)
        current_app.logger.error(f"failed login for roll {roll_no}")
        return render_template("login_page.html", error=generic, roll_no=roll_raw)

    _clear_failures(roll_no)
    session.clear()
    session["logged_in"] = True
    session["roll_no"] = student.roll_no
    if request.form.get("remember"):
        session.permanent = True
    current_app.logger.info(f"roll {roll_no} logged in")
    return redirect(url_for("home.home"))


@auth_bp.route("/log-out", methods=["GET", "POST"], endpoint="log_out")
def log_out():
    current_app.logger.info(f"roll {session.get('roll_no', '?')} logged out")
    session.clear()
    return redirect(url_for("auth.login_page"))
