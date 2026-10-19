from flask import Blueprint, render_template, redirect, request, session, current_app

from shared.extensions import db
from shared.models import Exam, Mark, Student
from shared.decorators import login_required, advisor_required
from shared.services.course_service import courses_for, semesters_for_year

marks_bp = Blueprint("marks", __name__)


@marks_bp.route(
    "/edit/<string:roll_no>/<string:subject>/<int:exam_id>",
    methods=["POST", "GET"],
    endpoint="edit"
)
@login_required
@advisor_required
def edit(roll_no: str, subject: str, exam_id: int):
    advisor_dept = session["advisor_dept"]
    advisor_year = int(session["advisor_year"])
    advisor_section = session["advisor_section"]

    student = Student.query.filter_by(roll_no=roll_no).first()

    if not student:
        current_app.logger.warning(
            f"{session.get('username', '')} tried to edit marks "
            f"for non-existent student {roll_no}"
        )
        return redirect("/home")

    # Never trust the roll number in the URL by itself.
    if (
        student.department != advisor_dept
        or student.year != advisor_year
        or student.section != advisor_section
    ):
        current_app.logger.warning(
            f"{session.get('username', '')} attempted unauthorized "
            f"mark edit for student {roll_no}"
        )
        return render_template(
            "Error.html",
            data="You are not the class advisor of this student's department, year and section.",
            location="/home"
        )

    # Only exams and courses that belong to this group's current year can be
    # edited, so a crafted URL can't write marks for some other semester or
    # a course the group doesn't study.
    exam = Exam.query.filter_by(exam_id=exam_id).first()
    valid_courses = {c.code for c in courses_for(advisor_dept, advisor_year)}
    if (
        exam is None
        or exam.semester not in semesters_for_year(advisor_year)
        or subject not in valid_courses
    ):
        current_app.logger.warning(
            f"{session.get('username', '')} tried to edit marks for an "
            f"invalid exam/course ({exam_id}, {subject})"
        )
        return render_template(
            "Error.html",
            data="That exam or course is not available for your class.",
            location="/home"
        )

    mark = Mark.query.filter(
        Mark.roll_no == roll_no,
        Mark.subject == subject,
        Mark.exam_id == exam_id
    ).first()

    if not mark:
        # No Mark row yet for this student/course/exam - create it on the
        # first edit so a teacher can add a first mark the same way they
        # edit an existing one.
        mark = Mark(
            roll_no=roll_no,
            year=advisor_year,
            exam_id=exam_id,
            subject=subject,
            marks=0
        )
        db.session.add(mark)

    if request.method == "POST":
        mar = request.form.get("content", "").strip()

        try:
            value = int(mar)
        except ValueError:
            db.session.rollback()
            return render_template(
                "Error.html",
                data="Marks must be a valid number.",
                location="/home"
            )

        if not 0 <= value <= 100:
            db.session.rollback()
            return render_template(
                "Error.html",
                data="Marks must be between 0 and 100.",
                location="/home"
            )

        mark.marks = value

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
