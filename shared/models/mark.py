from shared.extensions import db


class Mark(db.Model):
    __tablename__ = "marks"

    roll_no = db.Column(
        db.Integer,
        db.ForeignKey("students.roll_no"),
        primary_key=True
    )

    student_class = db.Column(
        "class", db.Integer,
        nullable=False
    )

    exam_id = db.Column(
        db.Integer,
        db.ForeignKey("exams.exam_id"),
        primary_key=True
    )

    subject = db.Column(db.String(30), primary_key=True)

    marks = db.Column(db.Integer, default=0)
