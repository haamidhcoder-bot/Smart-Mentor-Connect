from sqlalchemy import func

from shared.extensions import db
from shared.models import Student, Exam, Mark


def compute_leaderboard(class_value, section, exam_name):
    """Return leaderboard data for exactly one class and section."""
    students = Student.query.filter(
        Student.student_class == class_value,
        Student.section == section
    ).all()

    exam = Exam.query.filter(
        Exam.exam_name == exam_name
    ).first()

    if exam is None:
        return None

    leaderboard = db.session.query(
        Mark.roll_no,
        func.sum(Mark.marks).label("total")
    ).join(
        Student,
        Student.roll_no == Mark.roll_no
    ).filter(
        Mark.student_class == class_value,
        Student.section == section,
        Mark.exam_id == exam.exam_id
    ).group_by(
        Mark.roll_no
    ).order_by(
        func.sum(Mark.marks).desc()
    ).all()

    name_lookup = {
        student.roll_no: student.student_name
        for student in students
    }

    podium = [
        {
            "rank": idx,
            "name": name_lookup.get(roll_no, "Unknown"),
            "marks": total
        }
        for idx, (roll_no, total) in enumerate(
            leaderboard[:3],
            start=1
        )
    ]

    total_marks = {
        row.roll_no: row.total
        for row in leaderboard[3:]
    }

    return students, podium, total_marks
