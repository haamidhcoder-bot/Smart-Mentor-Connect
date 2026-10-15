from shared.extensions import db


class Teacher(db.Model):
    __tablename__ = "teachers"

    Gmail = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(255), nullable=False)
    class_teacher=db.Column(db.Integer)
    class_teacher_sec=db.Column(db.String(1))
    face_id=db.Column(db.String(200))
