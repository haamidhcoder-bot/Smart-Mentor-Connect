from flask import Blueprint, render_template, redirect, request, session, current_app

from shared.extensions import db
from shared.models import Mark, Student
from shared.decorators import login_required, class_teacher_required

marks_bp = Blueprint("marks", __name__)


@marks_bp.route(
    "/edit/<int:roll_no>/<string:subject>/<int:exam_id>",
    methods=["POST", "GET"],
    endpoint="edit"
)
@login_required
@class_teacher_required
def edit(roll_no: int, subject: str, exam_id: int):
    teacher_class = int(session["class_teacher"])
    teacher_section = session["class_teacher_sec"]

    student = Student.query.filter_by(roll_no=roll_no).first()

    if not student:
        current_app.logger.warning(
            f"{session.get('username', '')} tried to edit marks "
            f"for non-existent student {roll_no}"
        )
        return redirect("/home")

    # Never trust the roll number in the URL by itself.
    if (
        student.student_class != teacher_class
        or student.section != teacher_section
    ):
        current_app.logger.warning(
            f"{session.get('username', '')} attempted unauthorized "
            f"mark edit for student {roll_no}"
        )
        return render_template(
            "Error.html",
            data="You are not the class teacher of this student's class and section.",
            location="/home"
        )

    mark = Mark.query.filter(
        Mark.roll_no == roll_no,
        Mark.student_class == teacher_class,
        Mark.subject == subject,
        Mark.exam_id == exam_id
    ).first()

    if not mark:
        # No Mark row yet for this student/subject/exam - happens for
        # newly imported students and for anyone just promoted into this
        # class (promote() now clears old marks). Create it here instead
        # of failing, so a teacher can add a student's first mark the same
        # way they edit an existing one. A bad exam_id/roll_no still fails
        # safely via the FK constraint when db.session.commit() runs below.
        mark = Mark(
            roll_no=roll_no,
            student_class=teacher_class,
            exam_id=exam_id,
            subject=subject,
            marks=0
        )
        db.session.add(mark)

    if request.method == "POST":
        mar = request.form.get("content", "").strip()

        try:
            mark.marks = int(mar)
        except ValueError:
            return render_template(
                "Error.html",
                data="Marks must be a valid number.",
                location="/home"
            )

        try:
            db.session.commit()
            current_app.logger.info(
                f"{session.get('username', '')} edited marks "
                f"of student {roll_no}"
            )
            return redirect("/home")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(e)
            return redirect("/home")

    return render_template("edit.html", marks=mark)
