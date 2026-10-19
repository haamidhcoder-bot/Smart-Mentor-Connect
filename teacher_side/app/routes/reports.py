import json
from datetime import date

from flask import Blueprint, render_template, request, session, current_app, redirect, url_for
from shared.extensions import db
from shared.models import Attendance, Student
from shared.models import Exam
from shared.services.attendance_service import attendance_shortage
from shared.services.course_service import course_count, exams_for_year
from shared.services.graph_service import generate_graph, generate_pie_graph
from shared.services.leaderboard_service import compute_leaderboard
from shared.decorators import login_required, advisor_required

reports_bp = Blueprint("reports", __name__)


def _assigned_group():
    return (
        session["advisor_dept"],
        int(session["advisor_year"]),
        session["advisor_section"],
    )


def _student_in_assigned_group(roll_no):
    dept, year, sec = _assigned_group()
    return Student.query.filter(
        Student.roll_no == roll_no,
        Student.department == dept,
        Student.year == year,
        Student.section == sec
    ).first()


@reports_bp.route(
    "/graph/<string:roll_no>/<string:subject>/<int:exam_id>",
    methods=["GET", "POST"],
    endpoint="graph"
)
@login_required
@advisor_required
def graph(roll_no: str, subject: str, exam_id: int):
    try:
        if not subject or not _student_in_assigned_group(roll_no):
            return render_template(
                "Error.html",
                data="You are not authorized to view this student's report.",
                location="/home"
            )

        dept, year, sec = _assigned_group()
        graph_image, _exam1 = generate_graph(
            roll_no=roll_no,
            subject=subject,
            exam_id=exam_id,
            department=dept,
            year=year,
            sec=sec
        )
        return render_template("graph.html", graph=graph_image)
    except Exception as e:
       print(f'ERROR:{e}')
       return render_template("Error.html",data="Enter the marks for all the subject to display",location="/home")

@reports_bp.route(
    "/piegraph/<string:roll_no>/<int:exam_id>",
    methods=["GET", "POST"],
    endpoint="piegraph"
)
@login_required
@advisor_required
def piegraph(roll_no: str, exam_id: int):
    try:
        if not _student_in_assigned_group(roll_no):
               return render_template(
                   "Error.html",
                   data="You are not authorized to view this student's report.",
                   location="/home"
               )
       
        dept, year, sec = _assigned_group()
        graph_image, _exam1 = generate_pie_graph(
            roll_no=roll_no,
            exam_id=exam_id,
            department=dept,
            year=year,
            sec=sec
        )
        return render_template("graph.html", graph=graph_image)
    except Exception as e:
       print(f'ERROR:{e}')
       return render_template("Error.html",data="Enter the marks for all the subject to display",location="/home")
    
@reports_bp.route("/leaderboard", methods=["GET", "POST"], endpoint="leaderboard")
@login_required
@advisor_required
def leaderboard():
    dept, year, sec = _assigned_group()
    exams = exams_for_year(year)

    if request.method == "GET":
        return render_template(
            "leaderboard.html",
            dept=dept,
            year=year,
            sec=sec,
            exams=exams,
            exam=""
        )

    exam_name = request.form.get("exam", "").strip()
    if not exam_name:
        return render_template(
            "Error.html",
            data="Select an exam.",
            location="/leaderboard"
        )

    exam_row = Exam.query.filter(Exam.exam_name == exam_name).first()
    if exam_row is not None and exam_row.semester not in {e.semester for e in exams}:
        exam_row = None

    result = compute_leaderboard(dept, year, sec, exam_name) if exam_row else None
    if result is None:
        return render_template(
            "Error.html",
            data="No matching exam found.",
            location="/leaderboard"
        )

    students, podium, total_marks = result

    return render_template(
        "leaderboard.html",
        dept=dept,
        year=year,
        sec=sec,
        exams=exams,
        students=students,
        names={s.roll_no: s.student_name for s in students},
        total_marks=total_marks,
        course_total=course_count(dept, exam_row.semester),
        podium=podium,
        sub="All",
        exam=exam_name
    )


@reports_bp.route("/attendence", methods=["GET"], endpoint="attendence_legacy")
def attendence_legacy():
    """Old, misspelled URL kept so existing bookmarks still work."""
    return redirect(url_for("reports.attendence", **request.args), code=301)


@reports_bp.route("/attendance", methods=["GET", "POST"], endpoint="attendence")
@login_required
@advisor_required
def attendence():
    dept, class_year, sec = _assigned_group()

    if request.method == "POST":
        payload = request.form.get("attendance_data", "")
        if not payload:
            return render_template(
                "Error.html",
                data="No attendance data received",
                location="/attendance"
            )

        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return render_template(
                "Error.html",
                data="Invalid attendance data",
                location="/attendance"
            )

        month_str = data.get("month", "")
        records = data.get("records", {})

        try:
            year, month = [int(part) for part in month_str.split("-")]
        except (ValueError, AttributeError):
            return render_template(
                "Error.html",
                data="Invalid month",
                location="/attendance"
            )

        for roll_no, days in records.items():
            roll_no = str(roll_no)

            # Reject attendance submissions for students outside the
            # logged-in teacher's assigned class and section.
            if not _student_in_assigned_group(roll_no):
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
                    date=entry_date
                ).first()

                if existing:
                    existing.status = status
                    existing.marked_by = session.get("username", "")
                else:
                    db.session.add(
                        Attendance(
                            roll_no=roll_no,
                            department=dept,
                            year=class_year,
                            section=sec,
                            date=entry_date,
                            status=status,
                            marked_by=session.get("username", "")
                        )
                    )

        db.session.commit()

    students_exist = Student.query.filter(
        Student.department == dept,
        Student.year == class_year,
        Student.section == sec
    ).order_by(Student.roll_no).all()

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
        Attendance.department == dept,
        Attendance.year == class_year,
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
        dept=dept,
        year=class_year,
        sec=sec,
        shortage=attendance_shortage(dept, class_year, sec),
        selected_month=selected_month,
        existing_records=existing_records
    )
