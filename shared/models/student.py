from shared.extensions import db


class Student(db.Model):
    __tablename__ = "students"

    # Register / roll number issued by the college or university
    # (alphanumeric, e.g. "21CS001" or "912522104001").
    roll_no = db.Column(db.String(20), primary_key=True)
    student_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(10), nullable=False)   # e.g. CSE, ECE
    year = db.Column(db.Integer, nullable=False)            # year of study, 1-4
    section = db.Column(db.String(2), nullable=False)       # A, B, C ...
    student_gmail = db.Column(db.String(100))
    DOB = db.Column(db.Date)
    mobile_no = db.Column(db.BigInteger)

    __table_args__ = (
        db.Index("idx_student_group", "department", "year", "section"),
    )
