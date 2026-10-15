"""Student side: login, throttling, data isolation and page smoke tests.
Runs against a throw-away SQLite database - never your real schooldb."""
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

    from shared import db
    from shared.models import Attendance, Exam, Mark, Student
    from student_app_under_test.routes import auth as auth_routes
    auth_routes._failures.clear()

    with app.app_context():
        exam = Exam(exam_name="Unit Test 1")
        db.session.add(exam)
        db.session.commit()
        for i, name in enumerate(["Asha", "Bala"]):
            roll = 50101 + i
            db.session.add(Student(roll_no=roll, student_name=name, student_class=5, section="A",
                                   student_gmail=f"{name.lower()}@gmail.com", DOB=date(2015, 1, 1 + i)))
            db.session.flush()
            for subject, marks in [("English", 80 - i * 30), ("Maths", 90), ("Science", 70),
                                   ("Social", 60), ("Tamil", 50)]:
                db.session.add(Mark(roll_no=roll, student_class=5, exam_id=exam.exam_id,
                                    subject=subject, marks=marks))
            db.session.add(Attendance(roll_no=roll, class_value=5, section="A",
                                      date=date(2026, 10, 1), status="present"))
        db.session.commit()
    return app.test_client()


def login(client, roll="50101", dob="2015-01-01"):
    return client.post("/", data={"roll_no": roll, "dob": dob})


def test_pages_require_login(client):
    for path in ["/home", "/leaderboard", "/attendance", "/profile", "/graph/Maths/1", "/piegraph/1"]:
        r = client.get(path)
        assert r.status_code == 302 and r.headers["Location"].endswith("/")


def test_login_success_and_pages(client):
    r = login(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/home")
    for path in ["/home", "/leaderboard", "/attendance?month=2026-10", "/profile", "/about",
                 "/graph/Maths/1", "/piegraph/1"]:
        assert client.get(path).status_code == 200, path


def test_wrong_credentials_rejected(client):
    for roll, dob in [("50101", "2000-01-01"), ("99999", "2015-01-01"), ("abc", "2015-01-01"),
                      ("50101", "not-a-date")]:
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
    login(client, "50102", "2015-01-02")
    body = client.get("/home").get_data(as_text=True)
    assert "Bala" in body and "Asha" not in body
    assert "50 / 100" in body  # Bala's English = 50; Asha's would be 80
    assert b"Bala" in client.get("/profile").data


def test_logout_clears_session(client):
    login(client)
    assert client.get("/log-out").status_code == 302
    assert client.get("/home").status_code == 302
