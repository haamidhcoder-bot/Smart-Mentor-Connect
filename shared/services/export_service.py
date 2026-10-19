import csv
import io
import os
from datetime import datetime

from shared import settings
from shared.extensions import db
from shared.models import Attendance, Mark, Student
from shared.services.roll_no import normalise

CSV_COLUMNS = ["roll_no", "student_name", "student_gmail", "DOB", "mobile_no"]


def export_csv(department: str, year: int, sec: str):
    """CSV of one department / year / section, in the same column layout the
    import expects."""
    students = (
        Student.query.filter_by(department=department, year=year, section=sec)
        .order_by(Student.roll_no)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)
    for s in students:
        writer.writerow([s.roll_no, s.student_name, s.student_gmail, s.DOB, s.mobile_no])
    return output.getvalue()


def _parse_dob(value, line_no):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"Line {line_no}: invalid date '{value}'. Use YYYY-MM-DD or DD/MM/YYYY."
    )


def import_csv(file, department: str, year: int, sec: str):
    """Add or update students of one department / year / section from a CSV.

    Required columns: roll_no, student_name. Optional: student_gmail, DOB,
    mobile_no. Existing roll numbers in the same group are updated; nothing is
    ever deleted. A roll number that already belongs to a different
    department / year / section is rejected instead of being moved.
    Everything is rolled back if any row is invalid.

    Returns (created, updated).
    """
    reader = csv.DictReader(io.TextIOWrapper(file, encoding="utf-8-sig"))
    if not reader.fieldnames:
        raise ValueError("The file is empty.")

    columns = {name.strip().lower(): name for name in reader.fieldnames if name}
    for required in ("roll_no", "student_name"):
        if required not in columns:
            raise ValueError(f"Missing required column '{required}'.")

    created = updated = 0
    seen = set()

    try:
        for line_no, row in enumerate(reader, start=2):
            def cell(key):
                return (row.get(columns[key]) or "").strip() if key in columns else ""

            if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                continue

            roll_no = normalise(cell("roll_no"))
            if not roll_no:
                raise ValueError(f"Line {line_no}: invalid or missing roll number.")
            if roll_no in seen:
                raise ValueError(f"Line {line_no}: roll number {roll_no} appears twice.")
            seen.add(roll_no)

            name = cell("student_name")
            if not name:
                raise ValueError(f"Line {line_no}: missing student name.")

            gmail = cell("student_gmail") or None
            if gmail and "@" not in gmail:
                raise ValueError(f"Line {line_no}: invalid email '{gmail}'.")

            dob = _parse_dob(cell("dob"), line_no) if cell("dob") else None

            mobile = cell("mobile_no")
            if mobile and not mobile.isdigit():
                raise ValueError(f"Line {line_no}: invalid mobile number '{mobile}'.")

            student = db.session.get(Student, roll_no)
            if student is None:
                db.session.add(Student(
                    roll_no=roll_no, student_name=name, department=department,
                    year=year, section=sec, student_gmail=gmail, DOB=dob,
                    mobile_no=int(mobile) if mobile else None,
                ))
                created += 1
            else:
                if (student.department, student.year, student.section) != (department, year, sec):
                    raise ValueError(
                        f"Line {line_no}: roll number {roll_no} already belongs to "
                        f"{student.department} year {student.year}-{student.section}."
                    )
                student.student_name = name
                if gmail:
                    student.student_gmail = gmail
                if dob:
                    student.DOB = dob
                if mobile:
                    student.mobile_no = int(mobile)
                updated += 1

        db.session.commit()
        return created, updated
    except Exception:
        db.session.rollback()
        raise


def _archive_dir():
    # One folder per college, so two colleges promoting at the same time
    # never mix their graduates.
    from shared import colleges

    path = os.path.join(settings.PROJECT_ROOT, "archive", colleges.active_slug() or "")
    os.makedirs(path, exist_ok=True)
    return path


def promote():
    """End-of-year promotion: every year moves up by one.

    Final-year students graduate: their details, marks and attendance are
    written to CSV files in ./archive/<college> and then removed from the database.
    Roll numbers never change, and marks from earlier semesters are kept.
    """
    final_year = settings.max_year()
    try:
        graduating = Student.query.filter(Student.year == final_year).all()
        roll_numbers = [s.roll_no for s in graduating]
        graduated = len(roll_numbers)

        if graduated:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            folder = _archive_dir()

            with open(os.path.join(folder, f"graduated_students_{stamp}.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["roll_no", "student_name", "department", "year", "section",
                            "student_gmail", "DOB", "mobile_no"])
                for s in graduating:
                    w.writerow([s.roll_no, s.student_name, s.department, s.year,
                                s.section, s.student_gmail, s.DOB, s.mobile_no])

            with open(os.path.join(folder, f"graduated_marks_{stamp}.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["roll_no", "exam_id", "subject", "marks"])
                for m in Mark.query.filter(Mark.roll_no.in_(roll_numbers)).all():
                    w.writerow([m.roll_no, m.exam_id, m.subject, m.marks])

            Mark.query.filter(Mark.roll_no.in_(roll_numbers)).delete(synchronize_session=False)
            Attendance.query.filter(Attendance.roll_no.in_(roll_numbers)).delete(synchronize_session=False)
            Student.query.filter(Student.roll_no.in_(roll_numbers)).delete(synchronize_session=False)

        promoted = (
            Student.query.filter(Student.year < final_year)
            .update({Student.year: Student.year + 1}, synchronize_session=False)
        )

        db.session.commit()
        return {"graduated": graduated, "promoted": promoted}
    except Exception:
        db.session.rollback()
        raise
