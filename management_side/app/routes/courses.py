"""Courses (subjects) taught in each department and semester.

Teachers pick from these when entering marks, so add a department's courses
here before its class advisors start recording results.
"""
from flask import Blueprint, current_app, redirect, render_template, request, session

from shared import db, login_required, settings
from shared.models import Course, Mark, COMMON_DEPARTMENT

courses_bp = Blueprint("courses", __name__)


def _course_departments():
    return settings.departments() + [COMMON_DEPARTMENT]


@courses_bp.route("/courses", methods=["GET"], endpoint="courses")
@login_required
def courses():
    dept = request.args.get("department", "").strip().upper()
    semester = request.args.get("semester", type=int)

    query = Course.query
    if dept in _course_departments():
        query = query.filter(Course.department == dept)
    else:
        dept = ""
    if semester and 1 <= semester <= 2 * settings.max_year():
        query = query.filter(Course.semester == semester)
    else:
        semester = None

    items = query.order_by(Course.department, Course.semester, Course.code).all()
    return render_template(
        "courses.html",
        courses=items,
        dept=dept,
        semester=semester,
        course_departments=_course_departments(),
        semesters=list(range(1, 2 * settings.max_year() + 1)),
        common=COMMON_DEPARTMENT,
    )


@courses_bp.route("/courses/add", methods=["POST"], endpoint="add_course")
@login_required
def add_course():
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    dept = request.form.get("department", "").strip().upper()
    semester = request.form.get("semester", type=int)
    credits = request.form.get("credits", type=int)

    if not code or not name:
        return render_template("Error.html", data="Enter the course code and name.", location="/courses")
    if len(code) > 20 or "/" in code or any(c.isspace() for c in code):
        return render_template(
            "Error.html",
            data="Course code can be at most 20 characters, with no spaces or '/'.",
            location="/courses",
        )
    if len(name) > 100:
        return render_template("Error.html", data="Course name is too long (100 characters max).", location="/courses")
    if dept not in _course_departments():
        return render_template("Error.html", data="Invalid department.", location="/courses")
    if not semester or not 1 <= semester <= 2 * settings.max_year():
        return render_template("Error.html", data="Invalid semester.", location="/courses")
    if not credits or not 1 <= credits <= 10:
        return render_template("Error.html", data="Credits must be between 1 and 10.", location="/courses")

    if db.session.get(Course, code):
        return render_template("Error.html", data=f"Course {code} already exists.", location="/courses")

    try:
        db.session.add(Course(code=code, name=name, department=dept, semester=semester, credits=credits))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Could not add course: {e}")
        return render_template("Error.html", data="Could not add the course.", location="/courses")

    current_app.logger.info(f"{session.get('username','')} added course {code}")
    return redirect(f"/courses?department={dept}&semester={semester}")


@courses_bp.route("/courses/delete/<string:code>", methods=["POST"], endpoint="delete_course")
@login_required
def delete_course(code):
    course = db.session.get(Course, code)
    if course is None:
        return render_template("Error.html", data="Course not found.", location="/courses")

    if Mark.query.filter_by(subject=code).first():
        return render_template(
            "Error.html",
            data=f"{code} already has marks recorded, so it can't be deleted.",
            location="/courses",
        )

    db.session.delete(course)
    db.session.commit()
    current_app.logger.info(f"{session.get('username','')} deleted course {code}")
    return redirect("/courses")
