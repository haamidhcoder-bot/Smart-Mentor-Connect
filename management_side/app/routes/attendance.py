from datetime import date

from flask import Blueprint, render_template, request, session, current_app

from shared.models.student import Student
from shared.models import Attendance
from shared import login_required
from shared.services.attendance_service import attendance_shortage
from .home import parse_group, selected_group

attendance_bp = Blueprint("attendance", __name__)


def _build_attendance_context(dept, year, sec, month_param):
    try:
        view_year, view_month = [int(part) for part in month_param.split("-")]
        date(view_year, view_month, 1)
    except (ValueError, AttributeError):
        today = date.today()
        view_year, view_month = today.year, today.month
    selected_month = f"{view_year:04d}-{view_month:02d}"

    students_exist = Student.query.filter(
        Student.department == dept,
        Student.year == year,
        Student.section == sec
    ).order_by(Student.roll_no).all()
    students = [{"roll_no": s.roll_no, "name": s.student_name} for s in students_exist]

    records = Attendance.query.filter(
        Attendance.department == dept,
        Attendance.year == year,
        Attendance.section == sec,
        Attendance.date >= date(view_year, view_month, 1),
        Attendance.date < date(
            view_year + (1 if view_month == 12 else 0),
            1 if view_month == 12 else view_month + 1,
            1
        )
    ).all()

    existing_records = {}
    for row in records:
        existing_records.setdefault(str(row.roll_no), {})[str(row.date.day)] = row.status

    return students, existing_records, selected_month


def _render(dept, year, sec, month_param):
    students, existing_records, selected_month = _build_attendance_context(dept, year, sec, month_param)

    current_app.logger.info(
        f"{session.get('username', '')} viewed attendance for {dept} {year}-{sec}, {selected_month}"
    )

    return render_template(
        "attendance.html",
        students=students,
        dept=dept,
        year=year,
        sec=sec,
        selected_month=selected_month,
        existing_records=existing_records,
        shortage=attendance_shortage(dept, year, sec),
    )


@attendance_bp.route("/attendance", methods=["GET", "POST"], endpoint="attendance")
@login_required
def attendance():
    if request.method == "POST":
        group, error = parse_group(
            request.form.get("department"),
            request.form.get("year"),
            request.form.get("sec"),
        )
        if error:
            return render_template("Error.html", data=error, location="/attendance")

        dept, year, sec = group
        students_exist = Student.query.filter(
            Student.department == dept,
            Student.year == year,
            Student.section == sec
        ).first()
        if not students_exist:
            current_app.logger.error("No matching students found")
            return render_template("Error.html", data="No matching students found", location="/attendance")

        session["dept"], session["year"], session["sec"] = dept, year, sec
        return _render(dept, year, sec, request.form.get("month", ""))

    # GET - render an empty selector if no group is chosen yet
    dept, year, sec = selected_group()

    if not dept or not year or not sec:
        return render_template(
            "attendance.html",
            students=[],
            dept=None,
            year=None,
            sec="",
            selected_month="",
            existing_records={},
            shortage=[],
        )

    return _render(dept, year, sec, request.args.get("month", ""))
