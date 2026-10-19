from datetime import datetime

from flask import Blueprint, render_template, redirect, request, session, current_app, Response, flash

from shared import db, login_required, settings
from shared.models import Student, Teacher
from shared.services.export_service import export_csv, import_csv, promote
from shared.services.remove_service import remove

home_bp = Blueprint("home", __name__)


def parse_group(dept_raw, year_raw, sec_raw):
    """Validate a department / year / section picked on a form.

    Returns ((dept, year, sec), None) or (None, error_message).
    """
    dept = (dept_raw or "").strip().upper()
    sec = (sec_raw or "").strip().upper()

    if dept not in settings.departments():
        return None, "Invalid department."
    try:
        year = int((year_raw or "").strip())
    except ValueError:
        return None, "Invalid year."
    if not 1 <= year <= settings.max_year():
        return None, f"Year must be between 1 and {settings.max_year()}."
    if sec not in settings.sections():
        return None, "Invalid section."
    return (dept, year, sec), None


def selected_group():
    """The department / year / section the admin last picked (or Nones)."""
    year = session.get("year")
    return session.get("dept"), int(year) if year else None, session.get("sec")


def _students_in(dept, year, sec):
    return (
        Student.query.filter(
            Student.department == dept,
            Student.year == year,
            Student.section == sec,
        )
        .order_by(Student.roll_no)
        .all()
    )


@home_bp.route("/home", endpoint="home", strict_slashes=False)
@login_required
def home():
    dept, year, sec = selected_group()

    if not dept or not year or not sec:
        return render_template("Home.html", dept=None, year=None, sec="", students=[], log1=False)

    students = _students_in(dept, year, sec)

    current_app.logger.info(f"{session.get('username','')} has entered home")

    return render_template(
        "Home.html",
        dept=dept,
        year=year,
        sec=sec,
        students=students,
        log1=bool(students),
    )

@home_bp.route("/show_students", methods=["GET", "POST"], endpoint="show_students")
@login_required
def show_students():
    if request.method == "POST":
        group, error = parse_group(
            request.form.get("department"),
            request.form.get("year"),
            request.form.get("section"),
        )
        if error:
            return render_template("Error.html", data=error, location="/home")

        dept, year, sec = group
        session["dept"], session["year"], session["sec"] = dept, year, sec

        students_exist = _students_in(dept, year, sec)
        if not students_exist:
            current_app.logger.error("No matching students found")

        current_app.logger.info(f"{session.get('username','')} is seeing the details of {dept} {year}-{sec}")
        return render_template(
            "Home.html",
            dept=dept,
            year=year,
            sec=sec,
            students=students_exist,
            log1=bool(students_exist),
        )
    return redirect("/home")

@home_bp.route("/teachers_data", methods=["GET", "POST"], endpoint="/teachers_data",)
@login_required
def teachers_data():
    current_app.logger.info(f"{session.get('username','')} is seeing the details of the teachers")
    teachers=Teacher.query.all()
    return render_template("teachers_data.html",teachers=teachers)

@home_bp.route("/edit/<string:roll_no>", methods=["GET", "POST"])
@login_required
def edit(roll_no: str):
    student = Student.query.filter(
        Student.roll_no == roll_no
    ).first()

    if student is None:
        return render_template("Error.html", data=f"No student found with roll number {roll_no}.", location="/home")

    if request.method == "POST":
        DOB = request.form.get("content","").strip()  # to get info from input box
        Mobile = request.form.get("Mobile","").strip()
        if DOB:
            try:
                student.DOB = datetime.strptime(DOB, "%Y-%m-%d").date()
            except ValueError:
                return render_template("Error.html", data="Invalid date of birth.", location=f"/edit/{roll_no}")
        if Mobile:
            if not Mobile.isdigit():
                return render_template("Error.html", data="Invalid mobile number.", location=f"/edit/{roll_no}")
            student.mobile_no = int(Mobile)
        try:
                current_app.logger.info(f"{session.get('username', '')} has editted date of birth and phone number of student with roll no {roll_no}")
                db.session.commit()  # commiting it
                return redirect("/home")  # back to home
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(e)
            return redirect("/")
    else:
        return render_template("edit.html", student=student)

@home_bp.route("/edit_teacher/<Gmail>", methods=["GET", "POST"])
@login_required
def edit_teacher(Gmail: str):
    teacher = Teacher.query.filter(
        Teacher.Gmail == Gmail
    ).first()
    if teacher is None:
        return render_template("Error.html", data="Teacher not found.", location="/teachers_data")

    if request.method == "POST":
        group, error = parse_group(
            request.form.get("advisor_dept"),
            request.form.get("advisor_year"),
            request.form.get("advisor_section"),
        )
        if error:
            return render_template("Error.html", data=error, location=f"/edit_teacher/{Gmail}")

        dept, year, sec = group
        taken = Teacher.query.filter(
            Teacher.advisor_dept == dept,
            Teacher.advisor_year == year,
            Teacher.advisor_section == sec,
            Teacher.Gmail != Gmail,
        ).first()
        if taken:
            return render_template(
                "Error.html",
                data=f"{taken.Gmail} is already the class advisor of {dept} year {year}-{sec}.",
                location=f"/edit_teacher/{Gmail}",
            )

        teacher.advisor_dept, teacher.advisor_year, teacher.advisor_section = dept, year, sec

        try:
                current_app.logger.info(f"{session.get('username', '')} has changed class advisor position  of {Gmail}")
                db.session.commit()  # commiting it
                return redirect("/teachers_data")  # back to home
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(e)
            return redirect("/")
    else:
        return render_template("edit_teacher.html", teacher=teacher)

@home_bp.route("/export_csv", methods=["GET"])
@login_required
def export():
    s_dept, s_year, s_sec = selected_group()
    group, error = parse_group(
        request.args.get("department") or s_dept,
        request.args.get("year") or (str(s_year) if s_year else ""),
        request.args.get("section") or s_sec,
    )
    if error:
        return render_template("Error.html", data="Please select a department, year and section first.", location="/home")

    dept, year, sec = group
    try:
        csv_data = export_csv(dept, year, sec)

        filename = f"students_{dept}_{year}-{sec}.csv"

        current_app.logger.info(f"{session.get('username','')} has exported the data of {dept} {year}-{sec}")
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        current_app.logger.error(f"CSV export failed: {e}")
        return render_template(
            "Error.html",
            data="Could not export the student data.",
            location="/home"
        )

@home_bp.route("/import_csv", methods=["GET", "POST"])
@login_required
def import_file():
    if request.method == "POST":
        group, error = parse_group(
            request.form.get("department"),
            request.form.get("year"),
            request.form.get("section"),
        )
        csv_file = request.files.get("csv_file")

        if error:
            return render_template("Error.html", data=error, location="/import_csv")

        if not csv_file or csv_file.filename == "":
            return render_template("Error.html", data="Please choose a CSV file to upload.", location="/import_csv")

        if not csv_file.filename.lower().endswith(".csv"):
            return render_template("Error.html", data="Only .csv files are supported.", location="/import_csv")

        dept, year, sec = group
        try:
            created, updated = import_csv(csv_file.stream, department=dept, year=year, sec=sec)
        except ValueError as e:
            # Validation problems carry a line number, so show them as they are.
            current_app.logger.error(f"CSV import rejected: {e}")
            return render_template("Error.html", data=str(e), location="/import_csv")
        except Exception as e:
            current_app.logger.error(f"CSV import failed: {e}")
            return render_template("Error.html", data="Could not import that file. Check it matches the expected format.", location="/import_csv")

        session["dept"], session["year"], session["sec"] = dept, year, sec
        current_app.logger.info(
            f"{session.get('username', '')} imported a CSV into {dept} {year}-{sec}: "
            f"{created} added, {updated} updated"
        )
        return redirect("/home")

    s_dept, s_year, s_sec = selected_group()
    return render_template(
        "import_csv.html",
        dept=request.args.get("department", s_dept or ""),
        year=request.args.get("year", s_year or ""),
        sec=request.args.get("section", s_sec or ""),
    )

@home_bp.route("/delete/<string:roll_no>", methods=["POST"])
@login_required
def remove_student(roll_no: str):
    remove(roll_no=roll_no)
    current_app.logger.info(f"{session.get('username','')} has removed the student with roll no:{roll_no}")
    flash(f"Student {roll_no} was deleted.", "success")
    return redirect("/home")

@home_bp.route("/delete_teacher/<string:gmail>", methods=["POST"])
@login_required
def remove_teacher(gmail:str):
    remove(name=gmail)
    current_app.logger.info(f"{session.get('username','')} has removed the teacher with gmail:{gmail}")
    flash(f"Teacher {gmail} was deleted.", "success")
    return redirect("/teachers_data")

@home_bp.route("/promote", methods=["POST"])
@login_required
def promote_func():
    try:
        result = promote()
    except Exception as e:
        current_app.logger.error(f"Promotion failed: {e}")
        return render_template(
            "Error.html",
            data="Could not promote students. No changes were made.",
            location="/home"
        )

    # Every year just shifted, so whatever group was being viewed no longer
    # means the same thing - clear it and let the admin re-select.
    session.pop("dept", None)
    session.pop("year", None)
    session.pop("sec", None)

    current_app.logger.info(
        f"{session.get('username','')} promoted all years "
        f"({result['promoted']} promoted, {result['graduated']} graduated)"
    )

    return render_template(
            "Home.html",
            dept=None,
            year=None,
            sec="",
            students=[],
            log1=False,
            promoted=True,
            promoted_count=result["promoted"],
            graduated_count=result["graduated"],
        )
