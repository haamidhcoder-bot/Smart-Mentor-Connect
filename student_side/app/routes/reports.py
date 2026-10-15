from flask import Blueprint, render_template

from shared import login_required
from shared.services.graph_service import generate_graph, generate_pie_graph
from shared.services import student_service as svc
from .home import current_student

reports_bp = Blueprint("reports", __name__)

RED_BG = "#aa111e"


@reports_bp.route("/graph/<string:subject>/<int:exam_id>", endpoint="graph")
@login_required
def graph(subject, exam_id):
    student = current_student()
    if student is None:
        return render_template("Error.html", data="Please log in again.", location="/")
    try:
        # roll_no always comes from the session, never from the URL.
        image, exam_name = generate_graph(
            student.roll_no, subject, exam_id,
            student.student_class, student.section, bg=RED_BG,
        )
    except Exception:
        return render_template("Error.html", data="No marks are available for that graph yet.", location="/home")
    return render_template("graph.html", graph=image, title=f"{subject} progress", back=f"/home?exam={exam_id}")


@reports_bp.route("/piegraph/<int:exam_id>", endpoint="piegraph")
@login_required
def piegraph(exam_id):
    student = current_student()
    if student is None:
        return render_template("Error.html", data="Please log in again.", location="/")
    try:
        image, exam_name = generate_pie_graph(
            student.roll_no, exam_id, student.student_class, student.section, bg=RED_BG,
        )
    except Exception:
        return render_template(
            "Error.html",
            data="Marks for all subjects are needed to show this graph.",
            location=f"/home?exam={exam_id}",
        )
    return render_template("graph.html", graph=image, title="Marks breakdown", back=f"/home?exam={exam_id}")
