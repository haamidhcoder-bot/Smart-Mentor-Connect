"""Creates DEMO colleges with demo data (resets them if they already exist).

    python sample_data/populate_college_database.py --yes

Every college has its OWN database, so this registers two demo colleges and
fills each one:

* "Demo Engineering College"      - CSE + ECE, sections A/B, 15 students each
* "Sample Institute of Technology" - CSE + IT,  section A,   12 students each

Each gets 4 years of students, a small sample curriculum, the standard exams,
random marks and attendance, one demo administrator and one demo class
advisor. The roll numbers repeat between the two colleges on purpose: they are
completely separate databases. Other colleges you registered are not touched.
Do not run this against data you care about (the two demo colleges are reset).
"""
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bcrypt as bp  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from person_names_720 import person_names  # noqa: E402
from shared import colleges, db  # noqa: E402
from shared.models import Admin, Attendance, Course, Exam, Mark, Student, Teacher  # noqa: E402

EXAM_TYPES = ["Internal 1", "Internal 2", "Model Exam", "End Semester"]
YEARS = 4

DEMO_COLLEGES = [
    {
        "name": "Demo Engineering College",
        "departments": ["CSE", "ECE"],
        "sections": ["A", "B"],
        "students_per_section": 15,
        "advisor": ("CSE", 3, "A"),
    },
    {
        "name": "Sample Institute of Technology",
        "departments": ["CSE", "IT"],
        "sections": ["A"],
        "students_per_section": 12,
        "advisor": ("IT", 2, "A"),
    },
]

ADMIN_LOGIN = ("admin@example.com", "pass@123")
ADVISOR_LOGIN = ("demo-advisor@example.com", "pass@123")


def sample_courses(departments):
    """(code, name, department, semester, credits) - sample data, not a real syllabus."""
    courses = []
    for sem in range(1, 9):
        courses.append((f"MA{sem}01", f"Mathematics {sem}" if sem <= 4 else f"Professional Elective {sem}", "ALL", sem, 4))
        for dept in departments:
            for n in range(1, 4):
                courses.append((f"{dept}{sem}{n:02d}", f"{dept} Course {sem}.{n}", dept, sem, 3))
    return courses


def reset_college(name):
    """Create the college, or empty its tables if it already exists."""
    existing = colleges.get_college(colleges.slugify(name))
    if existing is None:
        return colleges.create_college(name)
    engine = colleges.engine_for(existing)
    db.metadata.drop_all(engine)
    colleges.init_college_schema(engine)
    return existing


def populate(spec):
    info = reset_college(spec["name"])
    engine = colleges.engine_for(info)
    departments, sections = spec["departments"], spec["sections"]
    courses = sample_courses(departments)

    names = person_names[:]
    random.shuffle(names)
    name_index = 0
    attendance_start = date.today() - timedelta(days=40)
    status_choices = ["present"] * 8 + ["absent", "leave"]

    with Session(engine) as session:
        session.add_all(
            Course(code=c, name=n, department=d, semester=s, credits=cr) for c, n, d, s, cr in courses
        )
        exam_ids = {(e.semester, e.exam_name.split(" - ", 1)[1]): e.exam_id for e in session.query(Exam)}

        for dept in departments:
            for year in range(1, YEARS + 1):
                semesters = (2 * year - 1, 2 * year)
                year_courses = [c for c in courses if c[2] in (dept, "ALL") and c[3] == semesters[0]]
                for section in sections:
                    for n in range(1, spec["students_per_section"] + 1):
                        roll_no = f"{20 + YEARS - year + 1}{dept}{section}{n:03d}"
                        name = names[name_index]
                        name_index += 1
                        session.add(Student(
                            roll_no=roll_no, student_name=name, department=dept, year=year, section=section,
                            student_gmail=name.replace(" ", "").lower() + "@example.com",
                            DOB=date(2008 - year, 1, 1) + timedelta(days=random.randint(0, 364)),
                            mobile_no=random.randint(6000000000, 9999999999),
                        ))
                        session.flush()

                        # Only the first semester of the year has finished.
                        for code, _name, _dept, sem, _credits in year_courses:
                            for kind in EXAM_TYPES:
                                session.add(Mark(roll_no=roll_no, year=year, exam_id=exam_ids[(sem, kind)],
                                                 subject=code, marks=random.randint(35, 98)))

                        for offset in range(30):
                            day = attendance_start + timedelta(days=offset)
                            if day.weekday() >= 5:
                                continue
                            session.add(Attendance(roll_no=roll_no, department=dept, year=year, section=section,
                                                   date=day, status=random.choice(status_choices),
                                                   marked_by=ADVISOR_LOGIN[0]))

        dept, year, section = spec["advisor"]
        session.add(Admin(Gmail=ADMIN_LOGIN[0], name="Demo Admin",
                          password=bp.hashpw(ADMIN_LOGIN[1].encode(), bp.gensalt()).decode()))
        session.add(Teacher(Gmail=ADVISOR_LOGIN[0], name="Demo Advisor",
                            password=bp.hashpw(ADVISOR_LOGIN[1].encode(), bp.gensalt()).decode(),
                            advisor_dept=dept, advisor_year=year, advisor_section=section))
        session.commit()
    return info


def main():
    if "--yes" not in sys.argv:
        sys.exit("This resets the demo colleges and fills them with demo data. Re-run with --yes to confirm.")

    colleges.init_registry()
    print("Demo colleges created. Choose the college on every login page:\n")
    for spec in DEMO_COLLEGES:
        info = populate(spec)
        dept, year, section = spec["advisor"]
        first_dept = spec["departments"][0]
        first_section = spec["sections"][0]
        print(f"  {info.name}")
        print(f"    Management: {ADMIN_LOGIN[0]} / {ADMIN_LOGIN[1]}")
        print(f"    Teacher:    {ADVISOR_LOGIN[0]} / {ADVISOR_LOGIN[1]}  ({dept}, year {year}, section {section})")
        print(f"    Student:    roll number such as {20 + YEARS}{first_dept}{first_section}001 and the date of birth"
              " (see the students table)\n")


if __name__ == "__main__":
    main()
