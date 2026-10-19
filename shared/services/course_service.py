"""Courses (subjects) and exams for a department / year of study."""
from flask import g, has_request_context
from sqlalchemy import or_

from shared.extensions import db
from shared.models import Course, Exam, COMMON_DEPARTMENT

EXAM_TYPES = ["Internal 1", "Internal 2", "Model Exam", "End Semester"]
SEMESTERS = range(1, 9)


def semesters_for_year(year):
    """Year 1 -> semesters 1, 2; year 2 -> 3, 4; ..."""
    year = int(year)
    return (2 * year - 1, 2 * year)


def courses_for(department, year):
    """Courses a (department, year) group studies this year, including the
    ones common to every department."""
    return (
        Course.query.filter(
            or_(Course.department == department, Course.department == COMMON_DEPARTMENT),
            Course.semester.in_(semesters_for_year(year)),
        )
        .order_by(Course.semester, Course.code)
        .all()
    )


def course_count(department, semester):
    return Course.query.filter(
        or_(Course.department == department, Course.department == COMMON_DEPARTMENT),
        Course.semester == semester,
    ).count()


def exams_for_year(year):
    """Exams belonging to the semesters of this year of study."""
    return (
        Exam.query.filter(Exam.semester.in_(semesters_for_year(year)))
        .order_by(Exam.exam_id)
        .all()
    )


def course_map():
    """{code: Course}. Cached for the length of a request."""
    if has_request_context():
        cached = g.get("_course_map")
        if cached is not None:
            return cached
    mapping = {c.code: c for c in Course.query.all()}
    if has_request_context():
        g._course_map = mapping
    return mapping


def course_name(code):
    course = course_map().get(code)
    return course.name if course else code


def course_credits(code, default=3):
    course = course_map().get(code)
    return course.credits if course and course.credits else default


def ensure_default_exams(session=None):
    """Create the standard exams for all 8 semesters on a fresh database.

    ``session`` is a plain SQLAlchemy session bound to one college's database
    (used when a college is created); by default the current request's
    session is used."""
    session = session or db.session
    if session.query(Exam).count():
        return
    for semester in SEMESTERS:
        for kind in EXAM_TYPES:
            session.add(Exam(exam_name=f"Sem {semester} - {kind}", semester=semester))
    session.commit()
