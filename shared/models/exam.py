from shared.extensions import db


class Exam(db.Model):
    __tablename__ = "exams"

    exam_id = db.Column(db.Integer, primary_key=True)
    exam_name = db.Column(db.String(50), unique=True, nullable=False)
