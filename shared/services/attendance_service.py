"""Attendance queries for a whole department / year / section (used by the
teacher and management sides)."""
from sqlalchemy import func

from shared.extensions import db
from shared.models import Attendance, Student
from shared.services import grading


def attendance_shortage(department, year, section):
    """Students of one group whose overall attendance is below the minimum
    percentage (75% by default), lowest first."""
    rows = (
        db.session.query(Attendance.roll_no, Attendance.status, func.count())
        .filter(
            Attendance.department == department,
            Attendance.year == year,
            Attendance.section == section,
        )
        .group_by(Attendance.roll_no, Attendance.status)
        .all()
    )
    per_student = {}
    for roll_no, status, n in rows:
        entry = per_student.setdefault(roll_no, {"present": 0, "marked": 0})
        entry["marked"] += n
        if status == "present":
            entry["present"] += n

    names = {
        s.roll_no: s.student_name
        for s in Student.query.filter_by(department=department, year=year, section=section)
    }
    result = []
    for roll_no, entry in per_student.items():
        if roll_no not in names:
            continue
        info = grading.attendance_status(entry["present"], entry["marked"])
        if info["shortage"]:
            result.append({
                "roll_no": roll_no,
                "name": names[roll_no],
                "present": entry["present"],
                "marked": entry["marked"],
                "pct": info["pct"],
                "need": info["need"],
            })
    return sorted(result, key=lambda r: r["pct"])
