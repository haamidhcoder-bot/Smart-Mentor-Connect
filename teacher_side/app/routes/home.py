from flask import Blueprint, render_template, request, session, url_for,redirect,current_app,jsonify
from sqlalchemy import func

from shared.extensions import db
from shared.models import Student, Exam, Mark
from shared.decorators import login_required, class_teacher_required
from shared.services.AI_service import ask_ai

home_bp = Blueprint("home", __name__)


def _teacher_class_context():
    class_value = session.get("class_teacher")
    sec = session.get("class_teacher_sec")

    if class_value is None or not sec:
        return None, None

    return int(class_value), sec


def _load_results(class_value, sec, subject, exam_name):
    students = Student.query.filter(
        Student.student_class == class_value,
        Student.section == sec
    ).all()

    exam = Exam.query.filter(Exam.exam_name == exam_name).first() if exam_name else None

    results = []
    if exam is not None and subject and subject != "All":
        # Every Mark row that already exists for this class/subject/exam.
        existing = {
            m.roll_no: m
            for m in Mark.query.join(
                Student, Student.roll_no == Mark.roll_no
            ).filter(
                Mark.student_class == class_value,
                Student.section == sec,
                Mark.exam_id == exam.exam_id,
                Mark.subject == subject
            ).all()
        }

        # Show every student in the class, not just the ones who already
        # have a Mark row. Newly imported or just-promoted students have
        # none yet, so without this they'd never appear here and the
        # teacher would have no "Edit" link to add their first mark.
        # These stand-in Mark objects are never added to the session -
        # the real row gets created when the teacher actually edits it
        # (see marks.py's edit()).
        for stu in students:
            results.append(existing.get(stu.roll_no) or Mark(
                roll_no=stu.roll_no,
                student_class=class_value,
                exam_id=exam.exam_id,
                subject=subject,
                marks=0
            ))

    return students, exam, results


@home_bp.route("/home", endpoint="home", strict_slashes=False)
@login_required
@class_teacher_required
def home():
    class_value, sec = _teacher_class_context()
    if class_value is None:
        return render_template(
            "Error.html",
            data="No class-teacher assignment found.",
            location="/"
        )

    sub = session.get("subject", "")
    exa = session.get("exam", "")

    students, exam, results = _load_results(
        class_value, sec, sub, exa
    )

    if sub == "All" and exam is not None:
        totals = (
            db.session.query(
                Mark.roll_no,
                func.sum(Mark.marks).label("total")
            )
            .join(
                Student,
                Student.roll_no == Mark.roll_no
            )
            .filter(
                Mark.student_class == class_value,
                Student.section == sec,
                Mark.exam_id == exam.exam_id
            )
            .group_by(Mark.roll_no)
            .having(func.count(Mark.subject) == 5)
            .having(func.min(Mark.marks) > 0)
            .all()
        )

        total_marks = {row.roll_no: row.total for row in totals}

        return render_template(
            "Home.html",
            class_value=class_value,
            students=students,
            total_marks=total_marks,
            sub=sub,
            exam=exa,
            exam_id=exam.exam_id,
            sec=sec
        )
    current_app.logger.info(f"{session.get('username','')} has entered home")

    return render_template(
        "Home.html",
        class_value=class_value,
        students=students,
        results=results,
        sub=sub,
        exam=exa,
        sec=sec
    )


@home_bp.route("/show_results", methods=["POST"], endpoint="show_results")
@login_required
@class_teacher_required
def show_results():
    class_value, sec = _teacher_class_context()

    if class_value is None:
        return render_template(
            "Error.html",
            data="No class-teacher assignment found.",
            location="/home"
        )

    sub = request.form.get("subject10", "") or request.form.get("subject12", "")
    exa = request.form.get("exam", "")

    if not sub or not exa:
        return render_template(
            "Error.html",
            data="Select the subject and exam.",
            location="/home"
        )

    # The class and section are deliberately NOT read from the form.
    # They always come from the logged-in teacher's assignment.
    session["class_value"] = class_value
    session["sec"] = sec
    session["subject"] = sub
    session["exam"] = exa

    current_app.logger.info(f"{session.get('username','')} is seeing the details of {class_value}-{sec}")
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