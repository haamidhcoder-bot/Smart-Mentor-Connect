from flask import Blueprint, redirect, render_template, url_for

from shared import login_required
from shared.services import student_service as svc
from .home import current_student

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/about", endpoint="about")
def about():
    return render_template("about_us.html")


@pages_bp.route("/support", endpoint="support")
def support():
    return render_template("support.html")


@pages_bp.route("/leaderboard", endpoint="leaderboard")
@login_required
def leaderboard():
    from flask import request

    student = current_student()
    if student is None:
        return redirect(url_for("auth.login_page"))

    exams = svc.all_exams()
    valid = {e.exam_id for e in exams}
    chosen = request.args.get("exam", type=int)
    scored = svc.exams_with_marks(student.roll_no)
    if chosen not in valid:
        chosen = scored[-1].exam_id if scored else None

    podium, rank, my_total = [], None, None
    exam_name = ""
    if chosen is not None:
        exam_name = next(e.exam_name for e in exams if e.exam_id == chosen)
        podium = svc.podium(student, chosen)
        rank = svc.class_rank(student, chosen)
    return render_template(
        "leaderboard.html",
        student=student,
        exams=exams,
        exam_id=chosen,
        exam_name=exam_name,
        podium=podium,
        rank=rank,
    )


@pages_bp.route("/profile", endpoint="profile")
@login_required
def profile():
    student = current_student()
    if student is None:
        return redirect(url_for("auth.login_page"))
    initials = "".join(w[0] for w in student.student_name.split()[:2]).upper() or "S"
    return render_template("profile.html", student=student, initials=initials)
