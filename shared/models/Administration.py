from shared.extensions import db


class Admin(db.Model):
    __tablename__ = "Admin"

    Gmail = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(255), nullable=False)
    face_id = db.Column(db.String(200))
