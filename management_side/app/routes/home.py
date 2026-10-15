from datetime import datetime

from flask import Blueprint, render_template, redirect, request, session, current_app,Response

from shared import db,login_required
from shared.models import Student,Teacher
from shared.services.export_service import export_csv,import_csv,promote
from shared.services.remove_service import remove

home_bp = Blueprint("home", __name__)


@home_bp.route("/home", endpoint="home", strict_slashes=False)
@login_required
def home():
    class_value = int(session.get("class_value", 0)) or None
    sec = session.get("sec", "")


    if not class_value:
        return render_template("Home.html", class_value=None, sec=sec, students=[], log1=False)

    students = Student.query.filter(
        Student.student_class == class_value,
        Student.section == sec
    ).all()

    current_app.logger.info(f"{session.get('username','')} has entered home")

    return render_template(
            "Home.html",
            class_value=class_value,
            students=students,
            log1=True
        )

@home_bp.route("/show_students", methods=["GET", "POST"], endpoint="show_students")
@login_required
def show_students():
    if request.method == "POST":
        class_input = request.form.get("class", "").strip()
        sec = request.form.get("section", "").strip() or session.get("sec", "")
        session["sec"] = sec
        students_exist = []
        log1 = False
        if class_input:
            try:
                class_input = int(class_input)
            except ValueError:
                return render_template("Error.html",data="invalid class value", location="/home")
            students_exist = Student.query.filter(Student.student_class == class_input,Student.section==session.get("sec","")).all()
            if not students_exist:
                current_app.logger.error("No matching students found")
                log1=False
            else:
                log1=True
                
            session["class_value"] = class_input

        class_value = session.get("class_value")
        if class_value is None:
            return render_template("Error.html", data="select a class first", location="/home")

        if not class_input:
            students_exist = Student.query.filter(
                Student.student_class == class_value,
                Student.section == sec
            ).all()
            log1 = bool(students_exist)

        current_app.logger.info(f"{session.get('username','')} is seeing the details of {class_input}-{sec}")
        return render_template(
                "Home.html",
                class_value=class_value,
                sec=sec,
                students=students_exist,
                log1=log1
            )
    return redirect("/home")

@home_bp.route("/teachers_data", methods=["GET", "POST"], endpoint="/teachers_data",)
@login_required
def teachers_data():
    current_app.logger.info(f"{session.get('username','')} is seeing the details of the teachers")
    teachers=Teacher.query.all() 
    return render_template("teachers_data.html",teachers=teachers)

@home_bp.route("/edit/<int:roll_no>", methods=["GET", "POST"])
@login_required
def edit(roll_no: int):
    student = Student.query.filter(
        Student.roll_no == roll_no
    ).first()
    if request.method == "POST" and not student:
        return render_template("Error.html", data=f"No student found with roll number {roll_no}.", location="/home")

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
        class_teacher=request.form.get("class_teacher","").strip()
        class_teacher_sec=request.form.get("class_teacher_sec","").strip()

        if class_teacher and not class_teacher.isdigit():
            return render_template("Error.html", data="Invalid class value.", location=f"/edit_teacher/{Gmail}")
        teacher.class_teacher = int(class_teacher) if class_teacher else None
        teacher.class_teacher_sec = class_teacher_sec or None
        
        try:
                current_app.logger.info(f"{session.get('username', '')} has changed class teacher position  of {Gmail}")
                db.session.commit()  # commiting it
                return redirect("/teachers_data")  # back to home
        except Exception as e:
            current_app.logger.error(e)
            return redirect("/")
        # create a new task
    else:
        return render_template("edit_teacher.html", teacher=teacher)

@home_bp.route("/export_csv", methods=["GET"])
@login_required
def export():
    class_input = request.args.get("class", "").strip() or session.get("class_value","")
    sec = request.args.get("section", "").strip() or session.get("sec", "")

    try:
     class_input = int(class_input)
    except (TypeError, ValueError):
     return render_template("Error.html",data="invalid class value", location="/home")

    if not class_input:
        return render_template(
            "Error.html",
            data="Please select a class first.",
            location="/home"
        )

    if not sec:
        return render_template(
            "Error.html",
            data="Please select a section first.",
            location="/home"
        )

    try:
        csv_data = export_csv(class_input, sec)

        filename = f"students_{class_input}-{sec}.csv"

        current_app.logger.info(f"{session.get('username','')} has exported the data of {class_input}-{sec}")
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
        class_input = request.form.get("class", "").strip()
        sec = request.form.get("section", "").strip() or session.get("sec", "")
        csv_file = request.files.get("csv_file")

        if not csv_file or csv_file.filename == "":
            return render_template("Error.html", data="Please choose a CSV file to upload.", location="/import_csv")

        if not csv_file.filename.lower().endswith(".csv"):
            return render_template("Error.html", data="Only .csv files are supported.", location="/import_csv")

        try:
            added= import_csv(csv_file.stream, class_value=int(class_input), sec=sec)
            
        except Exception as e:
            current_app.logger.error(f"CSV import failed: {e}")
            return render_template("Error.html", data="Could not import that file. Check it matches the expected format.", location="/import_csv")

        current_app.logger.info(f"{session.get('username', '')} imported a CSV: {added} added")
        return redirect("/home")

    class_value = request.args.get("class", session.get("class_value", ""))
    sec = request.args.get("section", session.get("sec", ""))
    return render_template("import_csv.html", class_value=class_value, sec=sec)

@home_bp.route("/delete/<int:roll_no>", methods=["GET", "POST"])
@login_required
def remove_student(roll_no:int):
    remove(roll_no=roll_no)
    class_input = request.form.get("class", "").strip() or session.get("class_value","")
    sec = request.form.get("section", "").strip() or session.get("sec", "")
    students_exist = Student.query.filter(
                Student.student_class == class_input,
                Student.section == sec
            ).all()
    current_app.logger.info(f"{session.get('username','')} has removed the student with roll no:{roll_no}")
    return render_template(
            "Home.html",
            class_value=class_input,
            sec=sec,
            remove=True,
            students=students_exist
        )

@home_bp.route("/delete_teacher/<string:gmail>", methods=["GET", "POST"])
@login_required
def remove_teacher(gmail:str):
    remove(name=gmail)
    teachers_exist = Teacher.query.all()
    current_app.logger.info(f"{session.get('username','')} has removed the teacher with gmail:{gmail}")
    return render_template(
            "teachers_data.html",
            remove=True,
            teachers=teachers_exist
        )

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

    # Every class just shifted, so whatever class/section was being viewed
    # no longer means the same thing - clear it and let the admin re-select.
    session.pop("class_value", None)
    session.pop("sec", None)

    current_app.logger.info(
        f"{session.get('username','')} promoted all classes "
        f"({result['promoted']} promoted, {result['graduated']} graduated)"
    )

    return render_template(
            "Home.html",
            class_value=None,
            sec="",
            students=[],
            log1=False,
            promoted=True,
            promoted_count=result["promoted"],
            graduated_count=result["graduated"],
        )
