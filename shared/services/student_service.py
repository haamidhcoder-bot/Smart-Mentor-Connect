"""Read-only queries used by the student side. Every function is scoped to
one roll number, so a student can only ever see their own records."""
from calendar import monthrange
from datetime import date

from sqlalchemy import func

from shared.extensions import db
from shared.models import Attendance, Exam, Mark, Student
from shared.services import grading
from shared.services.course_service import course_credits, course_name


def get_student(roll_no):
    return Student.query.filter_by(roll_no=roll_no).first()


def exams_for_student(student):
    """Exams for the semesters the student has reached, oldest first
    (semester 1 up to the second semester of their current year)."""
    last_semester = 2 * student.year
    return (
        Exam.query.filter(Exam.semester <= last_semester)
        .order_by(Exam.exam_id)
        .all()
    )


def exams_with_marks(roll_no):
    """Exams this student has at least one non-zero mark in, oldest first."""
    rows = (
        db.session.query(Exam)
        .join(Mark, Mark.exam_id == Exam.exam_id)
        .filter(Mark.roll_no == roll_no, Mark.marks > 0)
        .order_by(Exam.exam_id)
        .distinct()
        .all()
    )
    return rows


def all_exams():
    return Exam.query.order_by(Exam.exam_id).all()


def marks_for_exam(roll_no, exam_id):
    rows = (
        Mark.query.filter_by(roll_no=roll_no, exam_id=exam_id)
        .order_by(Mark.subject)
        .all()
    )
    subjects = []
    for m in rows:
        value = m.marks or 0
        entered = value > 0
        grade, point = grading.grade_for(value) if entered else ("-", None)
        subjects.append({
            "subject": m.subject,
            "name": course_name(m.subject),
            "credits": course_credits(m.subject),
            "marks": value,
            "grade": grade,
            "grade_point": point,
            "status": "Not entered" if not entered else ("Pass" if grading.is_pass(value) else "Fail"),
        })
    entered = [s for s in subjects if s["marks"] > 0]
    total = sum(s["marks"] for s in subjects)
    count = len(subjects)
    complete = bool(subjects) and len(entered) == count
    summary = {
        "total": total,
        "out_of": count * 100,
        "percentage": round(total / (count * 100) * 100, 1) if count else 0,
        "complete": complete,
        "passed": sum(1 for s in subjects if s["status"] == "Pass"),
        "count": count,
        # Grade point average for this exam, once every course has marks.
        "gpa": grading.gpa((s["marks"], s["credits"]) for s in subjects) if complete else None,
        "arrears": sum(1 for s in subjects if s["status"] == "Fail"),
    }
    return subjects, summary


def class_rank(student, exam_id):
    """(rank, section_size, total) among section-mates who have a full set of
    marks for the exam, or None if this student has no complete result yet."""
    totals = (
        db.session.query(Mark.roll_no, func.sum(Mark.marks), func.min(Mark.marks))
        .join(Student, Student.roll_no == Mark.roll_no)
        .filter(
            Student.year == student.year,
            Student.section == student.section,
            Mark.exam_id == exam_id,
        )
        .group_by(Mark.roll_no)
        .all()
    )
    complete = sorted(
        ((roll, int(total)) for roll, total, lowest in totals if lowest and lowest > 0),
        key=lambda x: -x[1],
    )
    for position, (roll, total) in enumerate(complete, start=1):
        if roll == student.roll_no:
            # ties share the better rank
            rank = 1 + sum(1 for _, t in complete if t > total)
            return rank, len(complete), total
    return None


def podium(student, exam_id):
    """Top three of the student's own department, year and section for one exam."""
    rows = (
        db.session.query(Student.student_name, func.sum(Mark.marks), func.min(Mark.marks))
        .join(Mark, Student.roll_no == Mark.roll_no)
        .filter(
            Student.year == student.year,
            Student.section == student.section,
            Mark.exam_id == exam_id,
        )
        .group_by(Student.roll_no, Student.student_name)
        .all()
    )
    complete = sorted(((n, int(t)) for n, t, lo in rows if lo and lo > 0), key=lambda x: -x[1])
    return [{"rank": i, "name": n, "marks": t} for i, (n, t) in enumerate(complete[:3], start=1)]


def attendance_month(roll_no, year, month):
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    rows = Attendance.query.filter(
        Attendance.roll_no == roll_no,
        Attendance.date >= first,
        Attendance.date <= last,
    ).all()
    by_day = {r.date.day: r.status for r in rows}
    counts = {"present": 0, "absent": 0, "leave": 0}
    for status in by_day.values():
        if status in counts:
            counts[status] += 1
    return by_day, counts


def attendance_overall(roll_no, year=None):
    """Attendance totals. Pass the student's current year to count only this
    year's attendance (the percentage starts afresh after promotion)."""
    query = db.session.query(Attendance.status, func.count()).filter(
        Attendance.roll_no == roll_no
    )
    if year is not None:
        query = query.filter(Attendance.year == year)
    rows = query.group_by(Attendance.status).all()
    counts = {"present": 0, "absent": 0, "leave": 0}
    for status, n in rows:
        if status in counts:
            counts[status] = n
    marked = sum(counts.values())
    pct = round(counts["present"] / marked * 100, 1) if marked else None
    return counts, marked, pct
