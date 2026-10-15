from shared.extensions import db

class Student(db.Model):
    __tablename__ = "students"

    roll_no = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(100), nullable=False)
    student_class = db.Column("class", db.Integer, nullable=False)
    section = db.Column(db.String(1), nullable=False)
    student_gmail = db.Column(db.String(100))
    DOB=db.Column(db.Date)
    mobile_no = db.Column(db.BigInteger)