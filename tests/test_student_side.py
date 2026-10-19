"""Student side: login, throttling, data isolation and page smoke tests.
Runs against a throw-away SQLite database - never your real collegedb."""
import importlib.util
import os
from datetime import date

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'student.db'}")
    monkeypatch.setenv("STUDENT_SECRET_KEY", "test-student-secret-key-0123456789")

    pkg = os.path.join(ROOT, "student_side", "app")
    spec = importlib.util.spec_from_file_location(
        "student_app_under_test", os.path.join(pkg, "__init__.py"),
        submodule_search_locations=[pkg],
    )
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    app = module.create_app()

    from college_helpers import register_college
    register_college(app, "Test College")
    from shared import db
    from shared.models import Attendance, Exam, Mark, Student
    from student_app_under_test.routes import auth as auth_routes
    auth_routes._failures.clear()

    from shared.models import Course
    with app.app_context():
        # create_app() seeds the standard exams for every semester.
        exam = Exam.query.filter_by(exam_name="Sem 1 - Internal 1").one()
        for code, name, credits in [("MA101", "Mathematics 1", 4), ("CS101", "Programming in C", 3),
                                    ("PH101", "Physics", 3), ("EN101", "English", 2),
                                    ("CS102", "Problem Solving", 3)]:
            db.session.add(Course(code=code, name=name, department="ALL" if code in ("MA101", "PH101", "EN101") else "CSE",
                                  semester=1, credits=credits))
        db.session.commit()
        for i, name in enumerate(["Asha", "Bala"]):
            roll = f"21CSA00{1 + i}"
            db.session.add(Student(roll_no=roll, student_name=name, department="CSE", year=1, section="A",
                                   student_gmail=f"{name.lower()}@gmail.com", DOB=date(2006, 1, 1 + i)))
            db.session.flush()
            for subject, marks in [("MA101", 80 - i * 30), ("CS101", 90), ("PH101", 70),
                                   ("EN101", 60), ("CS102", 50)]:
                db.session.add(Mark(roll_no=roll, year=1, exam_id=exam.exam_id,
                                    subject=subject, marks=marks))
            # Asha attends 4 of 4 days; Bala 1 of 4 (shortage).
            for d in range(1, 5):
                present = i == 0 or d == 1
                db.session.add(Attendance(roll_no=roll, department="CSE", year=1, section="A",
                                          date=date(2026, 10, d), status="present" if present else "absent"))
        db.session.commit()
    test_client = app.test_client()
    test_client.college = app.test_college
    return test_client


def login(client, roll="21CSA001", dob="2006-01-01"):
    return client.post("/", data={"roll_no": roll, "dob": dob, "college": client.college})


def test_pages_require_login(client):
    for path in ["/home", "/leaderboard", "/attendance", "/profile", "/graph/MA101/1", "/piegraph/1"]:
        r = client.get(path)
        assert r.status_code == 302 and r.headers["Location"].endswith("/")


def test_login_success_and_pages(client):
    r = login(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/home")
    for path in ["/home", "/leaderboard", "/attendance?month=2026-10", "/profile", "/about",
                 "/graph/MA101/1", "/piegraph/1"]:
        assert client.get(path).status_code == 200, path


def test_wrong_credentials_rejected(client):
    for roll, dob in [("21CSA001", "2000-01-01"), ("99999", "2006-01-01"), ("a/b", "2006-01-01"),
                      ("21CSA001", "not-a-date")]:
        r = login(client, roll, dob)
        assert r.status_code == 200 and b"Incorrect" in r.data
    assert client.get("/home").status_code == 302


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        login(client, dob="2000-01-01")
    r = login(client)  # correct DOB, but locked
    assert b"Too many failed attempts" in r.data
    assert client.get("/home").status_code == 302


def test_student_only_sees_own_marks(client):
    login(client, "21CSA002", "2006-01-02")
    body = client.get("/home").get_data(as_text=True)
    assert "Bala" in body and "Asha" not in body
    assert "50 / 100" in body  # Bala's Mathematics = 50; Asha's would be 80
    assert b"Bala" in client.get("/profile").data


def test_roll_number_login_is_case_insensitive(client):
    r = login(client, roll="21csa001")
    assert r.status_code == 302 and r.headers["Location"].endswith("/home")


def test_home_shows_grades_gpa_and_names(client):
    login(client)
    body = client.get("/home").get_data(as_text=True)
    assert "Programming in C" in body            # course name, not just the code
    assert "GPA (this exam)" in body
    assert "CSE" in body and "Year 1-A" in body


def test_pass_mark_is_50_and_boundary_is_a_pass(client):
    # Bala's Problem Solving mark is exactly 50 -> pass; Maths 50 too.
    login(client, "21CSA002", "2006-01-02")
    body = client.get("/home").get_data(as_text=True)
    assert "Arrear" not in body
    assert "Pass mark is 50 out of 100" in body


def test_attendance_shortage_is_flagged_for_low_attendance_only(client):
    login(client, "21CSA002", "2006-01-02")      # 1 of 4 present = 25%
    body = client.get("/attendance?month=2026-10").get_data(as_text=True)
    assert "Attendance shortage" in body
    client.get("/log-out")
    login(client)                                # Asha 100%
    body = client.get("/attendance?month=2026-10").get_data(as_text=True)
    assert "Attendance OK" in body


def test_logout_clears_session(client):
    login(client)
    assert client.get("/log-out").status_code == 302
    assert client.get("/home").status_code == 302
