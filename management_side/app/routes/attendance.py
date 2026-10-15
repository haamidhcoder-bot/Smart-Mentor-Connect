from datetime import date

from flask import Blueprint, render_template, request, session, current_app

from shared.models.student import Student
from shared.models import Attendance
from shared import login_required

attendance_bp = Blueprint("attendance", __name__)


def _build_attendance_context(class_value, sec, month_param):
    try:
        view_year, view_month = [int(part) for part in month_param.split("-")]
    except (ValueError, AttributeError):
        today = date.today()
        view_year, view_month = today.year, today.month
    selected_month = f"{view_year:04d}-{view_month:02d}"

    students_exist = Student.query.filter(
        Student.student_class == class_value,
        Student.section == sec
    ).all()
    students = [{"roll_no": s.roll_no, "name": s.student_name} for s in students_exist]

    records = Attendance.query.filter(
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
    for row in records:
        existing_records.setdefault(str(row.roll_no), {})[str(row.date.day)] = row.status

    return students, existing_records, selected_month


@attendance_bp.route("/attendance", methods=["GET", "POST"], endpoint="attendance")
@login_required
def attendance():
    if request.method == "POST":
        class_input = request.form.get("class", "").strip()
        sec =  request.form.get("sec", "").strip() or session.get("sec", "")
        session["sec"] = sec

        if class_input:
            try:
                class_input = int(class_input)
            except ValueError:
                return render_template("Error.html", data="invalid class value", location="/attendance")

            # same existence check pattern as home.show_students: class + section combo
            students_exist = Student.query.filter(
                Student.student_class == class_input,
                Student.section == sec
            ).all()
            if not students_exist:
                current_app.logger.error("No matching students found")
                return render_template("Error.html", data="No matching students found", location="/attendance")

            session["class_value"] = class_input

        class_value = session.get("class_value")
        if class_value is None:
            return render_template("Error.html", data="select a class first", location="/attendance")

        month_param = request.form.get("month", "")
        students, existing_records, selected_month = _build_attendance_context(class_value, sec, month_param)

        current_app.logger.info(
            f"{session.get('username', '')} viewed attendance for class {class_value}{sec}, {selected_month}"
        )

        return render_template(
            "attendance.html",
            students=students,
            class_value=class_value,
            sec=sec,
            selected_month=selected_month,
            existing_records=existing_records
        )

    # GET — mirrors home.home(): render an empty selector if no class is chosen yet
    class_value = session.get("class_value")
    sec = session.get("sec", "")

    if class_value is None:
        return render_template(
            "attendance.html",
            students=[],
            class_value=None,
            sec="",
            selected_month="",
            existing_records={}
        )

    month_param = request.args.get("month", "")
    students, existing_records, selected_month = _build_attendance_context(class_value, sec, month_param)

    current_app.logger.info(
        f"{session.get('username', '')} viewed attendance for class {class_value}{sec}, {selected_month}"
    )

    return render_template(
        "attendance.html",
        students=students,
        class_value=class_value,
        sec=sec,
        selected_month=selected_month,
        existing_records=existing_records
    )
