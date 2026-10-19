"""End-to-end checks of the college features against a throw-away SQLite
database, with the real templates rendered: management (courses, students,
CSV import, promotion), teacher (marks, results, leaderboard, attendance) and
the grading / attendance rules. Never touches a real database."""
import importlib.util
import io
import json
import os
import sys
from datetime import date

import pytest

from college_helpers import log_in_session, register_college
from shared import colleges

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def register_college_for_slug(app, slug):
    """Point another side's app contexts at an already registered college."""
    from flask.ctx import AppContext

    class CollegeAppContext(AppContext):
        def push(self):
            super().push()
            colleges.activate(slug)

    app.test_college = slug
    app.app_context = lambda: CollegeAppContext(app)


def load_side(side, db_url):
    pkg = os.path.join(ROOT, f"{side}_side", "app")
    name = f"{side}_app_under_test"
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(pkg, "__init__.py"), submodule_search_locations=[pkg])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.create_app()


@pytest.fixture()
def apps(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'college.db'}")
    management = load_side("management", None)
    teacher = load_side("teacher", None)
    # Each college has its own database; both sides share this test college.
    register_college(management)
    teacher.test_college = management.test_college
    register_college_for_slug(teacher, management.test_college)
    return management, teacher


login = log_in_session


def test_default_exams_are_seeded_per_semester(apps):
    management, _ = apps
    from shared.models import Exam
    with management.app_context():
        assert Exam.query.count() == 8 * 4
        assert Exam.query.filter_by(exam_name="Sem 5 - End Semester", semester=5).count() == 1


def test_management_pages_render(apps):
    management, _ = apps
    c = management.test_client()
    login(c)
    for path in ["/home", "/attendance", "/teachers_data", "/courses", "/add_student",
                 "/add_teacher", "/import_csv", "/about"]:
        assert c.get(path).status_code == 200, path


def test_courses_add_duplicate_and_delete(apps):
    management, _ = apps
    c = management.test_client()
    login(c)
    r = c.post("/courses/add", data={"code": "cs301", "name": "Data Structures", "department": "CSE",
                                      "semester": "5", "credits": "4"})
    assert r.status_code == 302
    page = c.get("/courses?department=CSE").get_data(as_text=True)
    assert "CS301" in page and "Data Structures" in page
    assert b"already exists" in c.post("/courses/add", data={"code": "CS301", "name": "X", "department": "CSE",
                                                              "semester": "5", "credits": "3"}).data
    assert b"Invalid department" in c.post("/courses/add", data={"code": "Z1", "name": "X", "department": "BIO",
                                                                   "semester": "1", "credits": "3"}).data
    assert c.post("/courses/delete/CS301").status_code == 302


def test_add_student_with_alphanumeric_roll_and_duplicate_rejected(apps):
    management, _ = apps
    from shared import db
    c = management.test_client()
    login(c)
    data = {"roll_no": "21cs001", "student_name": "Asha", "department": "CSE", "year": "3", "section": "A"}
    assert c.post("/add_student", data=data).status_code == 302
    from shared.models import Student
    with management.app_context():
        assert db.session.get(Student, "21CS001").department == "CSE"
    assert b"already exists" in c.post("/add_student", data=data).data
    bad = dict(data, roll_no="21/CS/002")
    assert b"valid roll number" in c.post("/add_student", data=bad).data
    assert b"between 1 and 4" in c.post("/add_student", data=dict(data, roll_no="X1", year="9")).data


def _csv(text):
    return {"department": "CSE", "year": "3", "section": "A",
            "csv_file": (io.BytesIO(text.encode()), "students.csv")}


def test_csv_import_adds_updates_and_never_deletes(apps):
    management, _ = apps
    c = management.test_client()
    login(c)
    from shared import db
    from shared.models import Student
    with management.app_context():
        db.session.add(Student(roll_no="21CS900", student_name="Keep Me", department="ECE", year=3, section="A"))
        db.session.add(Student(roll_no="21CS901", student_name="Same Group", department="CSE", year=3, section="A"))
        db.session.commit()

    good = "roll_no,student_name,student_gmail,DOB,mobile_no\n21CS001,Asha,a@x.com,2004-02-03,9876543210\n21CS901,Renamed,,03/04/2004,\n"
    r = c.post("/import_csv", data=_csv(good), content_type="multipart/form-data")
    assert r.status_code == 302
    with management.app_context():
        assert db.session.get(Student, "21CS001").student_name == "Asha"
        assert db.session.get(Student, "21CS901").student_name == "Renamed"
        assert db.session.get(Student, "21CS900").student_name == "Keep Me"       # other department untouched
        assert Student.query.count() == 3

    # a roll number that belongs to another department is rejected, nothing is half-imported
    clash = "roll_no,student_name\n21CS002,New One\n21CS900,Thief\n"
    r = c.post("/import_csv", data=_csv(clash), content_type="multipart/form-data")
    assert b"already belongs to" in r.data
    with management.app_context():
        assert db.session.get(Student, "21CS002") is None
        assert db.session.get(Student, "21CS900").student_name == "Keep Me"

    missing = "student_name\nNo Roll\n"
    assert b"Missing required column" in c.post("/import_csv", data=_csv(missing), content_type="multipart/form-data").data


def test_promotion_moves_years_archives_graduates_and_keeps_marks(apps, tmp_path, monkeypatch):
    management, _ = apps
    from shared import db, settings
    from shared.models import Mark, Student
    from shared.services import export_service
    monkeypatch.setattr(settings, "PROJECT_ROOT", str(tmp_path))
    with management.app_context():
        db.session.add_all([
            Student(roll_no="A1", student_name="Fresher", department="CSE", year=1, section="A"),
            Student(roll_no="A4", student_name="Final", department="CSE", year=4, section="A"),
        ])
        db.session.commit()
        db.session.add_all([Mark(roll_no="A1", year=1, exam_id=1, subject="CS101", marks=77),
                            Mark(roll_no="A4", year=4, exam_id=1, subject="CS101", marks=66)])
        db.session.commit()

        result = export_service.promote()
        assert result == {"graduated": 1, "promoted": 1}
        fresher = db.session.get(Student, "A1")
        assert fresher.year == 2 and fresher.roll_no == "A1"          # roll number never changes
        assert db.session.get(Student, "A4") is None
        assert Mark.query.filter_by(roll_no="A1").one().marks == 77   # earlier marks are kept
        assert Mark.query.filter_by(roll_no="A4").count() == 0
    archive = tmp_path / "archive" / management.test_college      # one folder per college
    names = sorted(p.name for p in archive.iterdir())
    assert any(n.startswith("graduated_students_") for n in names)
    assert any(n.startswith("graduated_marks_") for n in names)


def seed_teacher_group(app):
    from shared import db
    from shared.models import Course, Student, Teacher
    with app.app_context():
        db.session.add_all([
            Course(code="CS301", name="Data Structures", department="CSE", semester=5, credits=4),
            Course(code="CS302", name="Algorithms", department="CSE", semester=5, credits=3),
            Course(code="CS401", name="Other Year", department="CSE", semester=7, credits=3),
            Course(code="EC301", name="Signals", department="ECE", semester=5, credits=3),
            Student(roll_no="21CS001", student_name="Asha", department="CSE", year=3, section="A", student_gmail="a@x.com"),
            Student(roll_no="21CS002", student_name="Bala", department="CSE", year=3, section="A"),
            Student(roll_no="21EC001", student_name="Other Dept", department="ECE", year=3, section="A"),
            Teacher(Gmail="adv@example.com", password="x", advisor_dept="CSE", advisor_year=3, advisor_section="A"),
        ])
        db.session.commit()


def exam_id(app, name):
    from shared.models import Exam
    with app.app_context():
        return Exam.query.filter_by(exam_name=name).one().exam_id


def test_teacher_marks_flow_validation_and_results(apps):
    _, teacher = apps
    seed_teacher_group(teacher)
    c = teacher.test_client()
    login(c, username="adv@example.com")
    e5 = exam_id(teacher, "Sem 5 - Internal 1")
    e1 = exam_id(teacher, "Sem 1 - Internal 1")

    home = c.get("/home").get_data(as_text=True)
    assert "CSE" in home and "Year 3" in home
    assert "CS301" in home and "CS302" in home
    assert "EC301" not in home and "CS401" not in home          # only this group's year/department
    assert "Sem 5 - Internal 1" in home and "Sem 1 - Internal 1" not in home

    assert b"Select the course and exam" in c.post("/show_results", data={}).data
    assert b"not available for your year" in c.post("/show_results", data={"subject": "CS301", "exam": "Sem 1 - Internal 1"}).data
    assert b"does not belong" in c.post("/show_results", data={"subject": "CS401", "exam": "Sem 5 - Internal 1"}).data
    assert c.post("/show_results", data={"subject": "CS301", "exam": "Sem 5 - Internal 1"}).status_code == 302

    page = c.get("/home").get_data(as_text=True)
    assert "Asha" in page and "Bala" in page and "Other Dept" not in page

    # edit marks: valid, out of range, non-numeric, wrong course / semester, other department's student
    assert c.post(f"/edit/21CS001/CS301/{e5}", data={"content": "82"}).status_code == 302
    assert b"between 0 and 100" in c.post(f"/edit/21CS001/CS301/{e5}", data={"content": "101"}).data
    assert b"between 0 and 100" in c.post(f"/edit/21CS001/CS301/{e5}", data={"content": "-1"}).data
    assert b"valid number" in c.post(f"/edit/21CS001/CS301/{e5}", data={"content": "abc"}).data
    assert b"not available for your class" in c.post(f"/edit/21CS001/CS401/{e5}", data={"content": "50"}).data
    assert b"not available for your class" in c.post(f"/edit/21CS001/CS301/{e1}", data={"content": "50"}).data
    assert b"not the class advisor" in c.post(f"/edit/21EC001/CS301/{e5}", data={"content": "50"}).data

    from shared.models import Mark
    with teacher.app_context():
        assert Mark.query.filter_by(roll_no="21CS001", subject="CS301", exam_id=e5).one().marks == 82
        assert Mark.query.filter_by(roll_no="21EC001").count() == 0

    page = c.get("/home").get_data(as_text=True)
    assert ">82<" in page and "A+" in page                         # 82 -> grade A+


def test_teacher_all_courses_view_and_leaderboard(apps):
    _, teacher = apps
    seed_teacher_group(teacher)
    c = teacher.test_client()
    login(c, username="adv@example.com")
    e5 = exam_id(teacher, "Sem 5 - Internal 1")
    # Asha: both semester-5 courses entered (one failing); Bala: only one course entered.
    c.post(f"/edit/21CS001/CS301/{e5}", data={"content": "90"})
    c.post(f"/edit/21CS001/CS302/{e5}", data={"content": "45"})
    c.post(f"/edit/21CS002/CS301/{e5}", data={"content": "70"})

    c.post("/show_results", data={"subject": "All", "exam": "Sem 5 - Internal 1"})
    page = c.get("/home").get_data(as_text=True)
    assert "Arrear" in page                                         # 45 < pass mark of 50
    assert "67.50" in page                                          # (90+45) / 200
    assert "Null" in page                                           # Bala is incomplete

    r = c.post("/leaderboard", data={"exam": "Sem 5 - Internal 1"})
    assert r.status_code == 200 and b"Asha" in r.data
    assert b"not available" not in r.data
    assert b"No matching exam" in c.post("/leaderboard", data={"exam": "Sem 1 - Internal 1"}).data


def test_teacher_attendance_save_and_shortage_panel(apps):
    _, teacher = apps
    seed_teacher_group(teacher)
    c = teacher.test_client()
    login(c, username="adv@example.com")
    payload = {"month": "2026-10", "records": {
        "21CS001": {"1": "present", "2": "present", "3": "present", "4": "present"},
        "21CS002": {"1": "present", "2": "absent", "3": "absent", "4": "absent"},
        "21EC001": {"1": "present"},                                  # not this advisor's student
    }}
    assert c.post("/attendance", data={"attendance_data": json.dumps(payload)}).status_code == 200
    page = c.get("/attendance?month=2026-10").get_data(as_text=True)
    assert "Attendance shortage" in page and "Bala" in page and "25.0%" in page
    assert "needs 8 more present" in page                           # (0.75*4 - 1) / 0.25 = 8
    from shared.models import Attendance
    with teacher.app_context():
        assert Attendance.query.filter_by(roll_no="21EC001").count() == 0
        row = Attendance.query.filter_by(roll_no="21CS001", date=date(2026, 10, 1)).one()
        assert (row.department, row.year, row.section) == ("CSE", 3, "A")


def test_teacher_graphs_render_and_are_group_scoped(apps):
    _, teacher = apps
    seed_teacher_group(teacher)
    c = teacher.test_client()
    login(c, username="adv@example.com")
    e5 = exam_id(teacher, "Sem 5 - Internal 1")
    c.post(f"/edit/21CS001/CS301/{e5}", data={"content": "90"})
    c.post(f"/edit/21CS001/CS302/{e5}", data={"content": "75"})
    assert b"data:image/png" in c.get(f"/graph/21CS001/CS301/{e5}").data
    assert b"data:image/png" in c.get(f"/piegraph/21CS001/{e5}").data
    assert b"not authorized" in c.get(f"/graph/21EC001/CS301/{e5}").data


def test_advisor_without_assignment_is_blocked(apps):
    _, teacher = apps
    from shared import db
    from shared.models import Teacher
    with teacher.app_context():
        db.session.add(Teacher(Gmail="free@example.com", password="x"))
        db.session.commit()
    c = teacher.test_client()
    login(c, username="free@example.com")
    assert c.get("/home").status_code == 403


# ---- grading and attendance rules ---------------------------------------

def test_grade_scale_and_pass_mark():
    from shared.services import grading
    assert grading.grade_for(95) == ("O", 10)
    assert grading.grade_for(90) == ("O", 10)
    assert grading.grade_for(89) == ("A+", 9)
    assert grading.grade_for(50) == ("C", 5)
    assert grading.grade_for(49) == ("F", 0)
    assert grading.is_pass(50) and not grading.is_pass(49) and not grading.is_pass(None)


def test_pass_mark_can_be_changed_with_environment(monkeypatch):
    from shared.services import grading
    monkeypatch.setenv("PASS_MARK", "40")
    assert grading.is_pass(40) and grading.grade_for(45) == ("P", 4)


def test_gpa_is_credit_weighted_and_failures_count_as_zero():
    from shared.services import grading
    assert grading.gpa([(90, 4), (80, 2)]) == round((10 * 4 + 9 * 2) / 6, 2)
    assert grading.gpa([(90, 3), (30, 3)]) == 5.0
    assert grading.gpa([]) is None


def test_attendance_status_numbers():
    from shared.services import grading
    low = grading.attendance_status(1, 4)
    assert low["shortage"] and low["need"] == 8 and low["pct"] == 25.0
    ok = grading.attendance_status(9, 10)
    assert not ok["shortage"] and ok["can_miss"] == 2               # 9/12 = 75%
    edge = grading.attendance_status(3, 4)
    assert not edge["shortage"] and edge["can_miss"] == 0
    assert grading.attendance_status(0, 0)["pct"] is None


def test_roll_number_normalisation():
    from shared.services.roll_no import normalise
    assert normalise(" 21cs001 ") == "21CS001"
    assert normalise("912522104001") == "912522104001"
    for bad in ["", None, "21/CS/1", "a b", "x" * 21, "-abc"]:
        assert normalise(bad) is None
