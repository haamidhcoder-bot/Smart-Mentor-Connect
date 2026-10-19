from flask import Blueprint, render_template, request, session, url_for, redirect, current_app, jsonify
from sqlalchemy import func

from shared.extensions import db
from shared.models import Student, Exam, Mark
from shared.decorators import login_required, advisor_required
from shared.services.AI_service import ask_ai
from shared.services.course_service import (
    course_count,
    courses_for,
    exams_for_year,
    semesters_for_year,
)

home_bp = Blueprint("home", __name__)


def _advisor_group():
    """(department, year, section) the logged-in teacher is class advisor of."""
    dept = session.get("advisor_dept")
    year = session.get("advisor_year")
    sec = session.get("advisor_section")

    if not dept or year is None or not sec:
        return None, None, None

    return dept, int(year), sec


def _load_results(dept, year, sec, subject, exam_name):
    students = Student.query.filter(
        Student.department == dept,
        Student.year == year,
        Student.section == sec
    ).order_by(Student.roll_no).all()

    exam = Exam.query.filter(Exam.exam_name == exam_name).first() if exam_name else None

    results = []
    if exam is not None and subject and subject != "All":
        # Every Mark row that already exists for this group/course/exam.
        existing = {
            m.roll_no: m
            for m in Mark.query.join(
                Student, Student.roll_no == Mark.roll_no
            ).filter(
                Student.department == dept,
                Student.year == year,
                Student.section == sec,
                Mark.exam_id == exam.exam_id,
                Mark.subject == subject
            ).all()
        }

        # Show every student in the group, not just the ones who already
        # have a Mark row, so a teacher always gets an "Edit" link to add a
        # first mark. These stand-in Mark objects are never added to the
        # session - the real row is created when the teacher edits it
        # (see marks.py's edit()).
        for stu in students:
            results.append(existing.get(stu.roll_no) or Mark(
                roll_no=stu.roll_no,
                year=year,
                exam_id=exam.exam_id,
                subject=subject,
                marks=0
            ))

    return students, exam, results


@home_bp.route("/home", endpoint="home", strict_slashes=False)
@login_required
@advisor_required
def home():
    dept, year, sec = _advisor_group()
    if dept is None:
        return render_template(
            "Error.html",
            data="No class-advisor assignment found.",
            location="/"
        )

    sub = session.get("subject", "")
    exa = session.get("exam", "")

    students, exam, results = _load_results(dept, year, sec, sub, exa)

    common = dict(
        dept=dept,
        year=year,
        sec=sec,
        courses=courses_for(dept, year),
        exams=exams_for_year(year),
        students=students,
        sub=sub,
        exam=exa,
    )

    if sub == "All" and exam is not None:
        course_total = course_count(dept, exam.semester)

        totals = []
        if course_total:
            totals = (
                db.session.query(
                    Mark.roll_no,
                    func.sum(Mark.marks).label("total"),
                    func.min(Mark.marks).label("lowest"),
                )
                .join(
                    Student,
                    Student.roll_no == Mark.roll_no
                )
                .filter(
                    Student.department == dept,
                    Student.year == year,
                    Student.section == sec,
                    Mark.exam_id == exam.exam_id
                )
                .group_by(Mark.roll_no)
                .having(func.count(Mark.subject) == course_total)
                .having(func.min(Mark.marks) > 0)
                .all()
            )

        return render_template(
            "Home.html",
            total_marks={row.roll_no: row.total for row in totals},
            lowest_marks={row.roll_no: row.lowest for row in totals},
            course_total=course_total,
            exam_id=exam.exam_id,
            **common
        )
    current_app.logger.info(f"{session.get('username','')} has entered home")

    return render_template("Home.html", results=results, **common)


@home_bp.route("/show_results", methods=["POST"], endpoint="show_results")
@login_required
@advisor_required
def show_results():
    dept, year, sec = _advisor_group()

    if dept is None:
        return render_template(
            "Error.html",
            data="No class-advisor assignment found.",
            location="/home"
        )

    sub = request.form.get("subject", "")
    exa = request.form.get("exam", "")

    if not sub or not exa:
        return render_template(
            "Error.html",
            data="Select the course and exam.",
            location="/home"
        )

    # The department, year and section are deliberately NOT read from the
    # form. They always come from the logged-in teacher's assignment.
    exam = Exam.query.filter(Exam.exam_name == exa).first()
    if exam is None or exam.semester not in semesters_for_year(year):
        return render_template(
            "Error.html",
            data="That exam is not available for your year.",
            location="/home"
        )

    if sub != "All":
        course = next((c for c in courses_for(dept, year) if c.code == sub), None)
        if course is None or course.semester != exam.semester:
            return render_template(
                "Error.html",
                data="That course does not belong to the selected exam's semester.",
                location="/home"
            )

    session["dept"] = dept
    session["year"] = year
    session["sec"] = sec
    session["subject"] = sub
    session["exam"] = exa

    current_app.logger.info(
        f"{session.get('username','')} is seeing the details of {dept} {year}-{sec}"
    )
    return redirect(url_for("home.home"))

@home_bp.route("/chatbot", methods=["POST","GET"], endpoint="chatbot")
@login_required
def chatbot():
    if request.method == "GET":
        return redirect("/")

    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()

    if not question:
        return jsonify({"answer": "Please type a question."}), 400

    try:
        answer = ask_ai(question)
    except Exception:
        current_app.logger.exception(
            f"chatbot ask_ai failed for {session.get('username','')}"
        )
        return jsonify({"answer": "Sorry, something went wrong. Please try again."}), 500

    current_app.logger.info(f"{session.get('username','')} asked the AI buddy a question")
    return jsonify({"answer": answer})
