from shared.extensions import db


class Mark(db.Model):
    __tablename__ = "marks"

    roll_no = db.Column(
        db.String(20),
        db.ForeignKey("students.roll_no", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )

    # Year of study the mark was recorded in.
    year = db.Column(db.Integer, nullable=False)

    exam_id = db.Column(
        db.Integer,
        db.ForeignKey("exams.exam_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )

    # Course code (courses.code), e.g. "CS3351".
    subject = db.Column(db.String(20), primary_key=True)

    marks = db.Column(db.Integer, default=0)
