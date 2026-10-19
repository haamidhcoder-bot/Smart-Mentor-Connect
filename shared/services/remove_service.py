from shared.extensions import db
from shared.models import Attendance, Mark, Student, Teacher


def remove(roll_no="", name=""):
    """Delete a student (with their marks and attendance) by roll number, or
    a teacher by Gmail address."""
    try:
        if roll_no:
            Mark.query.filter_by(roll_no=roll_no).delete()
            Attendance.query.filter_by(roll_no=roll_no).delete()
            Student.query.filter_by(roll_no=roll_no).delete()
        elif name:
            Teacher.query.filter_by(Gmail=name).delete()

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
