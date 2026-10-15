import json
from datetime import date

from flask import Blueprint, render_template, request, session, current_app
from shared.extensions import db
from shared.models import Attendance, Student
from shared.services.graph_service import generate_graph, generate_pie_graph
from shared.services.leaderboard_service import compute_leaderboard
from shared.decorators import login_required, class_teacher_required

reports_bp = Blueprint("reports", __name__)


def _assigned_class():
    return int(session["class_teacher"]), session["class_teacher_sec"]


def _student_in_assigned_class(roll_no):
    class_value, sec = _assigned_class()
    return Student.query.filter(
        Student.roll_no == roll_no,
        Student.student_class == class_value,
        Student.section == sec
    ).first()


@reports_bp.route(
    "/graph/<int:roll_no>/<string:subject>/<int:exam_id>",
    methods=["GET", "POST"],
    endpoint="graph"
)
@login_required
@class_teacher_required
def graph(roll_no: int, subject: str, exam_id: int):
    try:
        if not subject or not _student_in_assigned_class(roll_no):
            return render_template(
                "Error.html",
                data="You are not authorized to view this student's report.",
                location="/home"
            )

        class_value, sec = _assigned_class()
        graph_image, _exam1 = generate_graph(
            roll_no=roll_no,
            subject=subject,
            exam_id=exam_id,
            class_value=class_value,
            sec=sec
        )
        return render_template("graph.html", graph=graph_image)
    except Exception as e:
       print(f'ERROR:{e}')
       return render_template("Error.html",data="Enter the marks for all the subject to display",location="/home")

@reports_bp.route(
    "/piegraph/<int:roll_no>/<int:exam_id>",
    methods=["GET", "POST"],
    endpoint="piegraph"
)
@login_required
@class_teacher_required
def piegraph(roll_no: int, exam_id: int):
    try:
        if not _student_in_assigned_class(roll_no):
               return render_template(
                   "Error.html",
                   data="You are not authorized to view this student's report.",
                   location="/home"
               )
       
        class_value, sec = _assigned_class()
        graph_image, _exam1 = generate_pie_graph(
            roll_no=roll_no,
            exam_id=exam_id,
            class_value=class_value,
            sec=sec
        )
        return render_template("graph.html", graph=graph_image)
    except Exception as e:
       print(f'ERROR:{e}')
       return render_template("Error.html",data="Enter the marks for all the subject to display",location="/home")
    
@reports_bp.route("/leaderboard", methods=["GET", "POST"], endpoint="leaderboard")
@login_required
@class_teacher_required
def leaderboard():
    class_value, sec = _assigned_class()

    if request.method == "GET":
        return render_template(
            "leaderboard.html",
            class_value=class_value,
            sec=sec,
            exam=""
        )

    exam_name = request.form.get("exam", "").strip()
    if not exam_name:
        return render_template(
            "Error.html",
            data="Select an exam.",
            location="/leaderboard"
        )

    result = compute_leaderboard(class_value, sec, exam_name)
    if result is None:
        return render_template(
            "Error.html",
            data="No matching exam found.",
            location="/leaderboard"
        )

    students, podium, total_marks = result

    session["class_value"] = class_value
    session["sec"] = sec

    return render_template(
        "leaderboard.html",
        class_value=class_value,
        sec=sec,
        students=students,
        total_marks=total_marks,
        podium=podium,
        sub="All",
        exam=exam_name
    )


@reports_bp.route("/attendence", methods=["GET", "POST"], endpoint="attendence")
@login_required
@class_teacher_required
def attendence():
    class_value, sec = _assigned_class()

    if request.method == "POST":
        payload = request.form.get("attendance_data", "")
        if not payload:
            return render_template(
                "Error.html",
                data="No attendance data received",
                location="/attendence"
            )

        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return render_template(
                "Error.html",
                data="Invalid attendance data",
                location="/attendence"
            )

        month_str = data.get("month", "")
        records = data.get("records", {})

        try:
            year, month = [int(part) for part in month_str.split("-")]
        except (ValueError, AttributeError):
            return render_template(
                "Error.html",
                data="Invalid month",
                location="/attendence"
            )

        for roll_no_str, days in records.items():
            try:
                roll_no = int(roll_no_str)
            except (ValueError, TypeError):
                continue

            # Reject attendance submissions for students outside the
            # logged-in teacher's assigned class and section.
            if not _student_in_assigned_class(roll_no):
                current_app.logger.warning(
                    f"{session.get('username', '')} attempted unauthorized "
                    f"attendance update for student {roll_no}"
                )
                continue

            for day_str, status in days.items():
                if status not in ("present", "absent", "leave"):
                    continue

                try:
                    day = int(day_str)
                    entry_date = date(year, month, day)
                except (ValueError, TypeError):
                    continue

                existing = Attendance.query.filter_by(
                    roll_no=roll_no,
                    class_value=class_value,
                    section=sec,
                    date=entry_date
                ).first()

                if existing:
                    existing.status = status
                    existing.marked_by = session.get("username", "")
                else:
                    db.session.add(
                        Attendance(
                            roll_no=roll_no,
                            class_value=class_value,
                            section=sec,
                            date=entry_date,
                            status=status,
                            marked_by=session.get("username", "")
                        )
                    )

        db.session.commit()

    students_exist = Student.query.filter(
        Student.student_class == class_value,
        Student.section == sec
    ).all()

    students = [
        {"roll_no": student.roll_no, "name": student.student_name}
        for student in students_exist
    ]

    month_param = request.values.get("month", "")
    try:
        view_year, view_month = [int(part) for part in month_param.split("-")]
    except (ValueError, AttributeError):
        today = date.today()
        view_year, view_month = today.year, today.month

    selected_month = f"{view_year:04d}-{view_month:02d}"

    existing = Attendance.query.filter(
        Attendance.class_value == class_value,
        Attendance.section == sec,
        Attendance.date >= date(view_year, view_month, 1),
        Attendance.date < date(
            view_year + (1 if view_month == 12 else 0),
            1 if view_month == 12 else view_month + 1,
            1
        )
    ).all()

    existing_records = {}
    for row in existing:
        existing_records.setdefault(
            str(row.roll_no), {}
        )[str(row.date.day)] = row.status

    return render_template(
        "attendence.html",
        students=students,
        class_value=class_value,
        sec=sec,
        selected_month=selected_month,
        existing_records=existing_records
    )
