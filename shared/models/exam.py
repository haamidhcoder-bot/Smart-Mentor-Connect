from shared.extensions import db


class Exam(db.Model):
    __tablename__ = "exams"

    exam_id = db.Column(db.Integer, primary_key=True)
    exam_name = db.Column(db.String(50), unique=True, nullable=False)
    # Semester (1-8) the exam belongs to. Exam names are per-semester
    # ("Sem 3 - Internal 1") so marks from earlier semesters are kept after
    # students move up a year.
    semester = db.Column(db.Integer, nullable=True)
