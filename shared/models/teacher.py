from shared.extensions import db


class Teacher(db.Model):
    """A faculty member. The advisor_* columns say which department / year /
    section they are class advisor (mentor) for; that group is the only one
    they can see and edit on the teacher side."""
    __tablename__ = "teachers"

    Gmail = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(255), nullable=False)
    advisor_dept = db.Column(db.String(10))
    advisor_year = db.Column(db.Integer)
    advisor_section = db.Column(db.String(2))
    face_id = db.Column(db.String(200))
