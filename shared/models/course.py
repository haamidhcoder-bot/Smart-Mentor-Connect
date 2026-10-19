from shared.extensions import db

COMMON_DEPARTMENT = "ALL"   # a course taken by every department (e.g. Maths I)


class Course(db.Model):
    __tablename__ = "courses"

    code = db.Column(db.String(20), primary_key=True)        # e.g. CS3351
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(10), nullable=False)    # CSE, ECE ... or ALL
    semester = db.Column(db.Integer, nullable=False)         # 1-8
    credits = db.Column(db.Integer, nullable=False, default=3)
