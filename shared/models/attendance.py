from datetime import datetime

from shared.extensions import db


class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(20), nullable=False)
    department = db.Column(db.String(10), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False)  # "present" | "absent" | "leave"
    marked_by = db.Column(db.String(120), nullable=True)  # teacher's Gmail
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("roll_no", "date", name="uq_attendance_student_day"),
        db.Index("idx_attendance_group", "department", "year", "section", "date"),
    )

    def __repr__(self):
        return f"<Attendance roll_no={self.roll_no} date={self.date} status={self.status}>"
