from flask import Blueprint, redirect, render_template, request, session, url_for

from shared import login_required
from shared.services import student_service as svc

home_bp = Blueprint("home", __name__)


def current_student():
    """The logged-in student, or None (and the session is cleared) if their
    record no longer exists."""
    student = svc.get_student(session.get("roll_no"))
    if student is None:
        session.clear()
    return student


@home_bp.route("/home", endpoint="home", strict_slashes=False)
@login_required
def home():
    student = current_student()
    if student is None:
        return redirect(url_for("auth.login_page"))

    exams = svc.all_exams()
    scored = svc.exams_with_marks(student.roll_no)

    # Selected exam: ?exam=<id>, else the latest exam that has marks.
    chosen = request.args.get("exam", type=int)
    valid_ids = {e.exam_id for e in exams}
    if chosen not in valid_ids:
        chosen = scored[-1].exam_id if scored else None

    subjects, summary, rank = [], None, None
    exam_name = ""
    if chosen is not None:
        subjects, summary = svc.marks_for_exam(student.roll_no, chosen)
        exam_name = next(e.exam_name for e in exams if e.exam_id == chosen)
        if summary["complete"]:
            rank = svc.class_rank(student, chosen)

    counts, marked, attendance_pct = svc.attendance_overall(student.roll_no)
    return render_template(
        "Home.html",
        student=student,
        exams=exams,
        exam_id=chosen,
        exam_name=exam_name,
        subjects=subjects,
        summary=summary,
        rank=rank,
        attendance_pct=attendance_pct,
        attendance_marked=marked,
    )
