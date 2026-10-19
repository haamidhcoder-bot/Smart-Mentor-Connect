"""Multi-college behaviour: every college has its own database, the college
is chosen on the login pages, and new colleges can register. Uses throw-away
SQLite files only."""
import os
import re
from datetime import date

import bcrypt
import pytest

from college_helpers import load_side
from shared import colleges, db
from shared.models import Admin, Student, Teacher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'smc.db'}")
    monkeypatch.setenv("STUDENT_SECRET_KEY", "test-student-secret-key-0123456789")
    colleges.reset_caches()
    yield
    colleges.reset_caches()


def hashed(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def add_to_college(app, slug, *objects):
    with app.app_context():
        colleges.activate(slug)
        db.session.add_all(objects)
        db.session.commit()


def make_two_colleges(*apps):
    alpha = colleges.create_college("Alpha Engineering College")
    beta = colleges.create_college("Beta Institute of Technology")
    return alpha, beta


def test_create_college_makes_separate_database_and_rejects_duplicates(env):
    alpha, beta = make_two_colleges()
    assert alpha.slug == "alpha_engineering_college" and alpha.db_name != beta.db_name
    assert [c.name for c in colleges.list_colleges()] == [
        "Alpha Engineering College", "Beta Institute of Technology"]
    with pytest.raises(colleges.CollegeError):
        colleges.create_college("alpha engineering college")   # same slug, different case
    with pytest.raises(colleges.CollegeError):
        colleges.create_college("x")                             # too short
    with pytest.raises(colleges.CollegeError):
        colleges.create_college("Bad; DROP DATABASE x")          # not allowed characters


def test_same_roll_number_can_exist_in_two_colleges_with_separate_data(env):
    student_app = load_side("student", ROOT)
    alpha, beta = make_two_colleges()
    for slug, name, dob in [(alpha.slug, "Asha", date(2006, 1, 1)), (beta.slug, "Bala", date(2005, 5, 5))]:
        add_to_college(student_app, slug, Student(
            roll_no="21CSA001", student_name=name, department="CSE", year=1, section="A", DOB=dob))

    c = student_app.test_client()
    # Same roll number, but the date of birth only matches the college it belongs to.
    r = c.post("/", data={"college": alpha.slug, "roll_no": "21CSA001", "dob": "2005-05-05"})
    assert r.status_code == 200 and b"Incorrect" in r.data
    r = c.post("/", data={"college": beta.slug, "roll_no": "21CSA001", "dob": "2005-05-05"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/home")
    body = c.get("/home").get_data(as_text=True)
    assert "Bala" in body and "Asha" not in body
    assert "Beta Institute of Technology" in body       # college name shown in the page


def test_student_login_needs_a_valid_college(env):
    student_app = load_side("student", ROOT)
    alpha, _ = make_two_colleges()
    add_to_college(student_app, alpha.slug, Student(
        roll_no="21CSA001", student_name="Asha", department="CSE", year=1, section="A", DOB=date(2006, 1, 1)))
    c = student_app.test_client()
    for college in ["", "no_such_college", "../etc"]:
        r = c.post("/", data={"college": college, "roll_no": "21CSA001", "dob": "2006-01-01"})
        assert r.status_code == 200 and b"select your college" in r.data
        assert c.get("/home").status_code == 302


def test_login_pages_list_the_registered_colleges(env):
    for side in ("student", "teacher", "management"):
        app = load_side(side, ROOT)
    make_two_colleges()
    for side in ("student", "teacher", "management"):
        page = load_side(side, ROOT).test_client().get("/").get_data(as_text=True)
        assert 'name="college"' in page
        assert "Alpha Engineering College" in page and "Beta Institute of Technology" in page


def test_teacher_and_admin_login_are_per_college(env):
    teacher_app = load_side("teacher", ROOT)
    management_app = load_side("management", ROOT)
    alpha, beta = make_two_colleges()
    # The same e-mail address is a teacher in Alpha only, with different passwords in each college.
    add_to_college(teacher_app, alpha.slug, Teacher(
        Gmail="t@example.com", name="T", password=hashed("alpha-pass1"),
        advisor_dept="CSE", advisor_year=1, advisor_section="A"))
    add_to_college(teacher_app, beta.slug, Admin(Gmail="t@example.com", name="Admin B", password=hashed("beta-pass1")))

    t = teacher_app.test_client()
    bad = t.post("/", data={"college": beta.slug, "username": "t@example.com", "password": "alpha-pass1"})
    assert bad.status_code == 200 and t.get("/home").status_code == 302      # not a teacher in Beta
    ok = t.post("/", data={"college": alpha.slug, "username": "t@example.com", "password": "alpha-pass1"})
    assert ok.status_code == 302
    with t.session_transaction() as sess:
        assert sess["college"] == alpha.slug

    m = management_app.test_client()
    assert m.post("/", data={"username": "t@example.com", "password": "beta-pass1"}).status_code == 200  # no college
    assert m.post("/", data={"college": alpha.slug, "username": "t@example.com", "password": "beta-pass1"}).status_code == 200
    assert m.post("/", data={"college": beta.slug, "username": "t@example.com", "password": "beta-pass1"}).status_code == 302
    assert m.get("/home").status_code == 200


def test_failed_login_for_another_college_does_not_switch_a_logged_in_session(env):
    teacher_app = load_side("teacher", ROOT)
    alpha, beta = make_two_colleges()
    add_to_college(teacher_app, alpha.slug, Teacher(
        Gmail="t@example.com", password=hashed("alpha-pass1"), advisor_dept="CSE", advisor_year=1, advisor_section="A"))
    t = teacher_app.test_client()
    t.post("/", data={"college": alpha.slug, "username": "t@example.com", "password": "alpha-pass1"})
    t.post("/", data={"college": beta.slug, "username": "t@example.com", "password": "wrong"})
    with t.session_transaction() as sess:
        assert sess["college"] == alpha.slug


def test_session_from_before_colleges_existed_is_logged_out(env):
    management_app = load_side("management", ROOT)
    make_two_colleges()
    c = management_app.test_client()
    with c.session_transaction() as sess:
        sess["logged_in"] = True          # old session: no college stored
        sess["username"] = "old@example.com"
    assert c.get("/home").status_code == 302


def test_register_a_new_college_with_its_first_admin(env, monkeypatch):
    management_app = load_side("management", ROOT)
    from management_multi_college_app.routes import auth as auth_routes

    sent = {}
    monkeypatch.setattr(auth_routes, "email", lambda sender, to, subject, body, pw: sent.update(body=body))
    monkeypatch.setenv("ADMIN1_EMAIL", "owner1@example.com")

    c = management_app.test_client()
    data = {"college_mode": "new", "new_college_name": "Gamma College of Arts", "username": "boss@example.com",
            "password": "secret123", "confirm_password": "secret123"}
    assert c.post("/register", data=data).status_code == 200
    assert "Gamma College of Arts (new college)" in sent["body"]
    assert colleges.list_colleges() == []            # nothing is created until the OTP is verified

    otp = re.search(r"--(\d+)--", sent["body"]).group(1)
    r = c.post("/register_verification", data={"onepass": otp})
    assert r.status_code == 302 and "college=gamma_college_of_arts" in r.headers["Location"]
    assert [x.name for x in colleges.list_colleges()] == ["Gamma College of Arts"]

    r = c.post("/", data={"college": "gamma_college_of_arts", "username": "boss@example.com", "password": "secret123"})
    assert r.status_code == 302


def test_register_new_college_validation_and_existing_college_admin(env, monkeypatch):
    management_app = load_side("management", ROOT)
    from management_multi_college_app.routes import auth as auth_routes
    sent = {}
    monkeypatch.setattr(auth_routes, "email", lambda sender, to, subject, body, pw: sent.update(body=body))
    monkeypatch.setenv("ADMIN1_EMAIL", "owner1@example.com")
    alpha, _ = make_two_colleges()

    c = management_app.test_client()
    base = {"username": "a2@example.com", "password": "secret123", "confirm_password": "secret123"}
    r = c.post("/register", data=dict(base, college_mode="new", new_college_name="alpha engineering college"))
    assert b"already registered" in r.data
    r = c.post("/register", data=dict(base, college_mode="new", new_college_name="!"))
    assert b"College name must be" in r.data
    r = c.post("/register", data=dict(base, college_mode="existing", college="nope"))
    assert b"select your college" in r.data

    # An administrator for an existing college.
    assert c.post("/register", data=dict(base, college_mode="existing", college=alpha.slug)).status_code == 200
    assert "Alpha Engineering College" in sent["body"]
    otp = re.search(r"--(\d+)--", sent["body"]).group(1)
    assert c.post("/register_verification", data={"onepass": otp}).status_code == 302
    with management_app.app_context():
        colleges.activate(alpha.slug)
        assert Admin.query.filter_by(Gmail="a2@example.com").count() == 1
        colleges.activate("beta_institute_of_technology")
        assert Admin.query.count() == 0


def test_forgot_password_needs_a_registered_college(env):
    teacher_app = load_side("teacher", ROOT)
    make_two_colleges()
    c = teacher_app.test_client()
    r = c.post("/forget_pass", data={"email": "t@example.com", "college": "nope"})
    assert b"select your college" in r.data
    r = c.post("/forget_pass", data={"email": "t@example.com", "college": "alpha_engineering_college"})
    assert b"No Teacher account found" in r.data


def test_post_without_csrf_token_is_rejected_and_with_token_accepted(monkeypatch):
    """CSRF protection is on by default (the suite switches it off globally)."""
    monkeypatch.delenv("CSRF_DISABLED", raising=False)
    import re
    from flask import Flask
    from shared.security import init_security

    app = Flask(__name__)
    app.secret_key = "x" * 32
    import jinja2
    app.jinja_loader = jinja2.DictLoader({"Error.html": "{{ data }}"})

    @app.route("/form", methods=["GET", "POST"])
    def form():
        from flask import request
        from shared.security import csrf_token
        return csrf_token() if request.method == "GET" else "ok"

    init_security(app)
    c = app.test_client()
    token = c.get("/form").get_data(as_text=True)
    assert c.post("/form", data={}).status_code == 400
    assert c.post("/form", data={"csrf_token": token}).status_code == 200
    assert c.post("/form", headers={"X-CSRF-Token": token}).status_code == 200
