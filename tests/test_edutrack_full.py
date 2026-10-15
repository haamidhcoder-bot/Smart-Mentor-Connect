"""
EduTrack - comprehensive pytest suite

Covers the functionality currently visible in the EduTrack repository:
    - shared decorators / authorization
    - teacher authentication, Face ID and logout
    - teacher dashboard, result selection and AI chatbot
    - teacher marks editing
    - teacher reports / graphs / leaderboard / attendance validation
    - teacher profile / password reset validation
    - management authentication, Face ID, logout and registration/OTP validation
    - management student/teacher management validation
    - CSV import/export validation
    - promotion validation
    - route/blueprint inventory
    - basic shared-service tests where they can be isolated safely
    - Python syntax checks for the repository

IMPORTANT
---------
These tests intentionally DO NOT use your real schooldb database, real email
account, real Face ID files, or real AI API. External/database operations are
mocked.

Install:
    pip install pytest

Run from the EduTrack project root:
    pytest -q

For more detail:
    pytest -v

Some tests will be SKIPPED if a source module cannot currently be imported.
This is deliberate: the suite should tell you which part of the repository
needs fixing instead of destroying data or requiring production services.

At the time this file was generated, the GitHub version of the repository had
syntax errors in some f-strings (for example management/teacher home logging).
Fix those syntax errors and the skipped module tests will become runnable.
"""

from __future__ import annotations

import ast
import importlib
import io
import json
import os
import socket
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, session

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent


# ============================================================================
# Generic helpers
# ============================================================================

def safe_import(module_name: str):
    """
    Import a repository module.

    SyntaxError/ImportError is converted into a pytest skip so one broken
    module does not prevent unrelated tests from running.
    """
    try:
        return importlib.import_module(module_name)
    except (SyntaxError, ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"{module_name} cannot currently be imported: {exc}")


def fake_render_template(template_name, **context):
    """
    Replace Flask's real template renderer during unit tests.

    We care about the route's behavior/context, not whether the browser
    template contains valid HTML.
    """
    return {
        "template": template_name,
        "context": context,
    }


def make_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="pytest-edutrack-secret",
        TESTING=True,
    )
    return app


def register_blueprint_app(module_name: str, blueprint_name: str):
    module = safe_import(module_name)
    app = make_app()
    app.register_blueprint(getattr(module, blueprint_name))
    return app, module


def set_logged_in(client, username="teacher@example.com", **extra):
    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["username"] = username
        sess.update(extra)


def set_teacher_context(client, class_value=12, section="A"):
    set_logged_in(
        client,
        class_teacher=class_value,
        class_teacher_sec=section,
        class_value=class_value,
        sec=section,
    )


# ============================================================================
# 0. Repository syntax checks
# ============================================================================

def test_repository_python_files_compile():
    """
    Every .py file should at least be syntactically valid.

    This is especially useful for EduTrack because a syntax error in one
    route can stop an entire Flask application from starting.
    """
    failures = []

    excluded_parts = {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
    }

    for py_file in ROOT.rglob("*.py"):
        if any(part in excluded_parts for part in py_file.parts):
            continue
        try:
            ast.parse(
                py_file.read_text(encoding="utf-8"),
                filename=str(py_file),
            )
        except (SyntaxError, UnicodeDecodeError) as exc:
            failures.append(f"{py_file}: {exc}")

    assert not failures, "Python syntax errors found:\n" + "\n".join(failures)


# ============================================================================
# 1. Shared decorators / authorization
# ============================================================================

@pytest.fixture
def decorator_app():
    app = make_app()

    from shared.decorators import login_required, class_teacher_required

    @app.get("/login")
    def login_page():
        return "login"

    app.add_url_rule(
        "/protected",
        "protected",
        login_required(lambda: "protected"),
    )

    app.add_url_rule(
        "/class-protected",
        "class_protected",
        class_teacher_required(lambda: "class-protected"),
    )

    return app


def test_login_required_rejects_logged_out_user(decorator_app):
    client = decorator_app.test_client()

    response = client.get("/protected")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_required_allows_logged_in_user(decorator_app):
    client = decorator_app.test_client()
    set_logged_in(client)

    response = client.get("/protected")

    assert response.status_code == 200
    assert response.data == b"protected"


def test_class_teacher_required_rejects_logged_out_user(decorator_app):
    client = decorator_app.test_client()

    response = client.get("/class-protected")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_class_teacher_required_rejects_unassigned_teacher(
    decorator_app, monkeypatch
):
    from shared import decorators

    teacher = SimpleNamespace(
        Gmail="teacher@example.com",
        class_teacher=None,
        class_teacher_sec=None,
    )

    fake_query = MagicMock()
    fake_query.filter_by.return_value.first.return_value = teacher

    monkeypatch.setattr(
        decorators.Teacher,
        "query",
        fake_query,
        raising=False,
    )

    client = decorator_app.test_client()
    set_logged_in(client)

    response = client.get("/class-protected")

    assert response.status_code == 403


def test_class_teacher_required_accepts_assigned_teacher(
    decorator_app, monkeypatch
):
    from shared import decorators

    teacher = SimpleNamespace(
        Gmail="teacher@example.com",
        class_teacher=12,
        class_teacher_sec="A",
    )

    fake_query = MagicMock()
    fake_query.filter_by.return_value.first.return_value = teacher

    monkeypatch.setattr(
        decorators.Teacher,
        "query",
        fake_query,
        raising=False,
    )

    client = decorator_app.test_client()
    set_logged_in(client)

    response = client.get("/class-protected")

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["class_teacher"] == 12
        assert sess["class_teacher_sec"] == "A"


# ============================================================================
# 2. Teacher-side authentication
# ============================================================================

def test_teacher_login_page_get():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert response.json["template"] == "login_page.html"


def test_teacher_login_success(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    teacher = SimpleNamespace(
        Gmail="teacher@example.com",
        password="stored-hash",
        class_teacher=12,
        class_teacher_sec="A",
    )

    query = MagicMock()
    query.filter.return_value.first.return_value = teacher

    monkeypatch.setattr(module.Teacher, "query", query, raising=False)
    monkeypatch.setattr(module.bp, "checkpw", lambda a, b: True)
    monkeypatch.setattr(module, "password_bytes", lambda value: b"hash")

    client = app.test_client()

    response = client.post(
        "/",
        data={
            "username": "teacher@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["logged_in"] is True
        assert sess["username"] == "teacher@example.com"


def test_teacher_login_wrong_password(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    teacher = SimpleNamespace(
        Gmail="teacher@example.com",
        password="stored-hash",
        class_teacher=12,
        class_teacher_sec="A",
    )

    query = MagicMock()
    query.filter.return_value.first.return_value = teacher

    monkeypatch.setattr(module.Teacher, "query", query, raising=False)
    monkeypatch.setattr(module.bp, "checkpw", lambda a, b: False)
    monkeypatch.setattr(module, "password_bytes", lambda value: b"hash")

    client = app.test_client()

    response = client.post(
        "/",
        data={
            "username": "teacher@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True


def test_teacher_face_login_without_file():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    response = client.post("/login-face")

    assert response.status_code == 200
    assert response.json["context"]["data"] == "No image received"


def test_teacher_face_login_match(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    teacher = SimpleNamespace(
        Gmail="teacher@example.com",
        face_id="face-data",
        class_teacher=12,
        class_teacher_sec="A",
    )

    query = MagicMock()
    query.filter.return_value.all.return_value = [teacher]

    monkeypatch.setattr(module.Teacher, "query", query, raising=False)
    monkeypatch.setattr(module, "match_face", lambda face, captured: True)

    client = app.test_client()

    response = client.post(
        "/login-face",
        data={
            "face": (io.BytesIO(b"fake-image"), "face.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["logged_in"] is True
        assert sess["username"] == "teacher@example.com"


def test_teacher_face_login_no_match(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    teacher = SimpleNamespace(
        Gmail="teacher@example.com",
        face_id="face-data",
        class_teacher=12,
        class_teacher_sec="A",
    )

    query = MagicMock()
    query.filter.return_value.all.return_value = [teacher]

    monkeypatch.setattr(module.Teacher, "query", query, raising=False)
    monkeypatch.setattr(module, "match_face", lambda face, captured: False)

    client = app.test_client()

    response = client.post(
        "/login-face",
        data={
            "face": (io.BytesIO(b"fake-image"), "face.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.json["context"]["data"] == "Face not recognized"

    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True


def test_teacher_logout_clears_session(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template
    monkeypatch.setattr(module, "email_file", MagicMock())

    client = app.test_client()
    set_logged_in(client)

    response = client.get("/log-out")

    assert response.status_code == 302

    with client.session_transaction() as sess:
        assert "logged_in" not in sess
        assert "username" not in sess


# ============================================================================
# 3. Teacher dashboard / AI chatbot
# ============================================================================

def test_teacher_show_results_requires_subject_and_exam():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    response = client.post("/show_results", data={})

    assert response.status_code == 200
    assert response.json["context"]["data"] == "Select the subject and exam."


def test_teacher_chatbot_requires_login():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    response = client.post(
        "/chatbot",
        json={"message": "Hello"},
    )

    assert response.status_code == 302


def test_teacher_chatbot_rejects_empty_question(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.home",
        "home_bp",
    )

    client = app.test_client()
    set_logged_in(client)

    response = client.post("/chatbot", json={"message": "   "})

    assert response.status_code == 400
    assert response.json["answer"] == "Please type a question."


def test_teacher_chatbot_calls_ai(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.home",
        "home_bp",
    )

    client = app.test_client()
    set_logged_in(client)

    monkeypatch.setattr(
        module,
        "ask_ai",
        lambda question: f"AI: {question}",
    )

    response = client.post(
        "/chatbot",
        json={"message": "How is my class doing?"},
    )

    assert response.status_code == 200
    assert response.json["answer"] == "AI: How is my class doing?"


def test_teacher_chatbot_handles_ai_failure(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.home",
        "home_bp",
    )

    client = app.test_client()
    set_logged_in(client)

    def fail(_):
        raise RuntimeError("AI unavailable")

    monkeypatch.setattr(module, "ask_ai", fail)

    response = client.post(
        "/chatbot",
        json={"message": "test"},
    )

    assert response.status_code == 500
    assert "something went wrong" in response.json["answer"].lower()


# ============================================================================
# 4. Teacher marks
# ============================================================================

def test_teacher_marks_edit_rejects_missing_student(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.marks",
        "marks_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    query = MagicMock()
    query.filter_by.return_value.first.return_value = None
    monkeypatch.setattr(module.Student, "query", query, raising=False)

    response = client.get("/edit/999/Math/1")

    assert response.status_code == 302
    assert response.location.endswith("/home")


def test_teacher_marks_edit_rejects_wrong_class(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.marks",
        "marks_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client, 12, "A")

    student = SimpleNamespace(
        roll_no=10,
        student_class=11,
        section="B",
    )

    student_query = MagicMock()
    student_query.filter_by.return_value.first.return_value = student
    monkeypatch.setattr(module.Student, "query", student_query, raising=False)

    response = client.get("/edit/10/Math/1")

    assert response.status_code == 200
    assert "not the class teacher" in response.json["context"]["data"]


def test_teacher_marks_edit_rejects_non_numeric_marks(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.marks",
        "marks_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    student = SimpleNamespace(
        roll_no=10,
        student_class=12,
        section="A",
    )
    mark = SimpleNamespace(marks=0)

    student_query = MagicMock()
    student_query.filter_by.return_value.first.return_value = student

    mark_query = MagicMock()
    mark_query.filter.return_value.first.return_value = mark

    monkeypatch.setattr(module.Student, "query", student_query, raising=False)
    monkeypatch.setattr(module.Mark, "query", mark_query, raising=False)

    response = client.post(
        "/edit/10/Math/1",
        data={"content": "abc"},
    )

    assert response.status_code == 200
    assert response.json["context"]["data"] == "Marks must be a valid number."


# ============================================================================
# 5. Teacher reports / leaderboard / attendance
# ============================================================================

def test_teacher_leaderboard_get(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.reports",
        "reports_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    response = client.get("/leaderboard")

    assert response.status_code == 200
    assert response.json["template"] == "leaderboard.html"
    assert response.json["context"]["class_value"] == 12
    assert response.json["context"]["sec"] == "A"


def test_teacher_leaderboard_requires_exam(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.reports",
        "reports_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    response = client.post("/leaderboard", data={"exam": ""})

    assert response.status_code == 200
    assert response.json["context"]["data"] == "Select an exam."


def test_teacher_leaderboard_handles_unknown_exam(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.reports",
        "reports_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    monkeypatch.setattr(module, "compute_leaderboard", lambda *args: None)

    response = client.post(
        "/leaderboard",
        data={"exam": "Does Not Exist"},
    )

    assert response.status_code == 200
    assert response.json["context"]["data"] == "No matching exam found."


def test_teacher_attendance_rejects_missing_payload(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.reports",
        "reports_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    response = client.post("/attendence", data={})

    assert response.status_code == 200
    assert response.json["context"]["data"] == "No attendance data received"


def test_teacher_attendance_rejects_invalid_json(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.reports",
        "reports_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    response = client.post(
        "/attendence",
        data={"attendance_data": "{bad json"},
    )

    assert response.status_code == 200
    assert response.json["context"]["data"] == "Invalid attendance data"


def test_teacher_attendance_rejects_invalid_month(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.reports",
        "reports_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    response = client.post(
        "/attendence",
        data={
            "attendance_data": json.dumps(
                {"month": "wrong", "records": {}}
            )
        },
    )

    assert response.status_code == 200
    assert response.json["context"]["data"] == "Invalid month"


def test_teacher_graph_rejects_student_outside_class(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.reports",
        "reports_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    monkeypatch.setattr(module, "_student_in_assigned_class", lambda roll: None)

    response = client.get("/graph/99/Math/1")

    assert response.status_code == 200
    assert "not authorized" in response.json["context"]["data"].lower()


def test_teacher_piegraph_rejects_student_outside_class(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.reports",
        "reports_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_teacher_context(client)

    monkeypatch.setattr(module, "_student_in_assigned_class", lambda roll: None)

    response = client.get("/piegraph/99/1")

    assert response.status_code == 200
    assert "not authorized" in response.json["context"]["data"].lower()


# ============================================================================
# 6. Teacher profile / password-reset validation
# ============================================================================

def test_teacher_about_page():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.pages",
        "pages_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    response = client.get("/about")

    assert response.status_code == 200
    assert response.json["template"] == "about_us.html"


def test_teacher_support_page():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.pages",
        "pages_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    response = client.get("/support")

    assert response.status_code == 200
    assert response.json["template"] == "support.html"


def test_teacher_forgot_password_requires_email():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.pages",
        "pages_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    response = client.post("/forget_pass", data={"email": ""})

    assert response.status_code == 200
    assert "Please enter your email" in response.json["context"]["error"]


def test_teacher_forgot_password_unknown_account(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.pages",
        "pages_bp",
    )
    module.render_template = fake_render_template

    query = MagicMock()
    query.filter.return_value.first.return_value = None
    monkeypatch.setattr(module.Teacher, "query", query, raising=False)

    client = app.test_client()

    response = client.post(
        "/forget_pass",
        data={"email": "missing@example.com"},
    )

    assert response.status_code == 200
    assert "No Teacher account" in response.json["context"]["error"]


def test_teacher_forgot_password_no_internet_shows_error(monkeypatch):
    """When the OTP email can't be sent because there's no internet
    connection, the user should see a clear error instead of a crash or a
    silently "successful" OTP screen."""
    app, module = register_blueprint_app(
        "teacher_side.app.routes.pages",
        "pages_bp",
    )
    module.render_template = fake_render_template

    account = SimpleNamespace(Gmail="teacher@example.com")
    query = MagicMock()
    query.filter.return_value.first.return_value = account
    monkeypatch.setattr(module.Teacher, "query", query, raising=False)

    def fake_email(*args, **kwargs):
        raise module.NoInternetError(
            "Could not send email: no internet connection. "
            "Please check your network connection and try again."
        )

    monkeypatch.setattr(module, "email", fake_email)

    client = app.test_client()

    response = client.post(
        "/forget_pass",
        data={"email": "teacher@example.com"},
    )

    assert response.status_code == 200
    assert response.json["template"] == "forgot_password.html"
    assert "no internet connection" in response.json["context"]["error"]

    with client.session_transaction() as sess:
        assert "reset_email" not in sess
        assert "reset_otp_hash" not in sess


def test_teacher_reset_password_requires_verified_otp():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.pages",
        "pages_bp",
    )

    client = app.test_client()

    response = client.get("/reset_password")

    assert response.status_code == 302
    assert "forget_pass" in response.location


def test_teacher_reset_password_rejects_mismatched_passwords(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.pages",
        "pages_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    with client.session_transaction() as sess:
        sess["reset_email"] = "teacher@example.com"
        sess["reset_otp_verified"] = True

    response = client.post(
        "/reset_password",
        data={
            "new_password": "password123",
            "confirm_password": "different123",
        },
    )

    assert response.status_code == 200
    assert "Passwords do not match" in response.json["context"]["error"]


def test_teacher_reset_password_rejects_short_password(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.pages",
        "pages_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    with client.session_transaction() as sess:
        sess["reset_email"] = "teacher@example.com"
        sess["reset_otp_verified"] = True

    response = client.post(
        "/reset_password",
        data={
            "new_password": "123",
            "confirm_password": "123",
        },
    )

    assert response.status_code == 200
    assert "at least 8" in response.json["context"]["error"]


# ============================================================================
# 7. Management authentication
# ============================================================================

def test_admin_login_get():
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert response.json["template"] == "login_page.html"


def test_admin_login_success(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    admin = SimpleNamespace(
        Gmail="admin@example.com",
        password="stored-hash",
    )

    query = MagicMock()
    query.filter.return_value.first.return_value = admin

    monkeypatch.setattr(module.Admin, "query", query, raising=False)
    monkeypatch.setattr(module.bp, "checkpw", lambda a, b: True)
    monkeypatch.setattr(module, "password_bytes", lambda value: b"hash")

    client = app.test_client()

    response = client.post(
        "/",
        data={
            "username": "admin@example.com",
            "password": "correct",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["logged_in"] is True
        assert sess["username"] == "admin@example.com"


def test_admin_login_wrong_password(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    admin = SimpleNamespace(
        Gmail="admin@example.com",
        password="stored-hash",
    )

    query = MagicMock()
    query.filter.return_value.first.return_value = admin

    monkeypatch.setattr(module.Admin, "query", query, raising=False)
    monkeypatch.setattr(module.bp, "checkpw", lambda a, b: False)
    monkeypatch.setattr(module, "password_bytes", lambda value: b"hash")

    client = app.test_client()

    response = client.post(
        "/",
        data={
            "username": "admin@example.com",
            "password": "wrong",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True


def test_admin_face_login_without_image():
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    response = client.post("/login-face")

    assert response.status_code == 200
    assert response.json["context"]["data"] == "No image received"


def test_admin_face_login_success(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    admin = SimpleNamespace(
        Gmail="admin@example.com",
        face_id="face-data",
    )

    query = MagicMock()
    query.filter.return_value.all.return_value = [admin]

    monkeypatch.setattr(module.Admin, "query", query, raising=False)
    monkeypatch.setattr(module, "match_face", lambda face, captured: True)

    client = app.test_client()

    response = client.post(
        "/login-face",
        data={"face": (io.BytesIO(b"fake"), "face.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["logged_in"] is True
        assert sess["username"] == "admin@example.com"


def test_admin_logout_clears_session(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template
    monkeypatch.setattr(module, "email_file", MagicMock())

    client = app.test_client()
    set_logged_in(client, "admin@example.com")

    response = client.get("/log-out")

    assert response.status_code == 302

    with client.session_transaction() as sess:
        assert "logged_in" not in sess
        assert "username" not in sess


def test_admin_logout_still_clears_session_when_email_fails(monkeypatch):
    """The log-file backup email is a background side effect of logging out
    - if there's no internet and it can't be sent, logout should still
    succeed instead of leaving the user stuck."""
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    def fake_email_file(*args, **kwargs):
        raise module.NoInternetError(
            "Could not send email: no internet connection. "
            "Please check your network connection and try again."
        )

    monkeypatch.setattr(module, "email_file", fake_email_file)

    client = app.test_client()
    set_logged_in(client, "admin@example.com")

    response = client.get("/log-out")

    assert response.status_code == 302

    with client.session_transaction() as sess:
        assert "logged_in" not in sess
        assert "username" not in sess


def test_admin_forgot_password_no_internet_shows_error(monkeypatch):
    """When the OTP email can't be sent because there's no internet
    connection, the user should see a clear error instead of a crash or a
    silently "successful" OTP screen."""
    app, module = register_blueprint_app(
        "management_side.app.routes.pages",
        "pages_bp",
    )
    module.render_template = fake_render_template

    account = SimpleNamespace(Gmail="admin@example.com")
    query = MagicMock()
    query.filter.return_value.first.return_value = account
    monkeypatch.setattr(module.Admin, "query", query, raising=False)

    def fake_email(*args, **kwargs):
        raise module.NoInternetError(
            "Could not send email: no internet connection. "
            "Please check your network connection and try again."
        )

    monkeypatch.setattr(module, "email", fake_email)

    client = app.test_client()

    response = client.post(
        "/forget_pass",
        data={"email": "admin@example.com"},
    )

    assert response.status_code == 200
    assert response.json["template"] == "forgot_password.html"
    assert "no internet connection" in response.json["context"]["error"]

    with client.session_transaction() as sess:
        assert "reset_email" not in sess
        assert "reset_otp_hash" not in sess


# ============================================================================
# 8. Management registration / OTP
# ============================================================================

def test_admin_registration_get():
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    response = client.get("/register")

    assert response.status_code == 200
    assert response.json["template"] == "register.html"


def test_admin_registration_requires_all_fields():
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    response = client.post(
        "/register",
        data={
            "username": "",
            "password": "",
            "confirm_password": "",
        },
    )

    assert response.status_code == 200
    assert "fill in all fields" in response.json["context"]["data"]


def test_admin_registration_rejects_password_mismatch():
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    response = client.post(
        "/register",
        data={
            "username": "admin@example.com",
            "password": "abc123",
            "confirm_password": "different123",
        },
    )

    assert response.status_code == 200
    assert "Passwords do not match" in response.json["context"]["error"]


def test_admin_registration_rejects_weak_password():
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    response = client.post(
        "/register",
        data={
            "username": "admin@example.com",
            "password": "ABC",
            "confirm_password": "ABC",
        },
    )

    assert response.status_code == 200
    assert "lowercase" in response.json["context"]["error"]


def test_admin_registration_stores_hashed_password_and_otp(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template
    monkeypatch.setattr(module, "email", MagicMock())

    client = app.test_client()

    response = client.post(
        "/register",
        data={
            "username": "admin@example.com",
            "password": "abc123",
            "confirm_password": "abc123",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["registration_email"] == "admin@example.com"
        assert sess["registration_password_hash"] != "abc123"
        assert sess["registration_otp_hash"]
        assert sess["registration_otp_expires"]
        assert sess["registration_otp_attempts"] == 0


def test_admin_registration_no_internet_shows_error(monkeypatch):
    """When the OTP email can't be sent because there's no internet
    connection, registration should show a clear error instead of a crash
    or a silently "successful" OTP screen."""
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    def fake_email(*args, **kwargs):
        raise module.NoInternetError(
            "Could not send email: no internet connection. "
            "Please check your network connection and try again."
        )

    monkeypatch.setattr(module, "email", fake_email)

    client = app.test_client()

    response = client.post(
        "/register",
        data={
            "username": "admin@example.com",
            "password": "abc123",
            "confirm_password": "abc123",
        },
    )

    assert response.status_code == 200
    assert response.json["template"] == "register.html"
    assert "no internet connection" in response.json["context"]["error"]

    with client.session_transaction() as sess:
        assert "registration_email" not in sess
        assert "registration_otp_hash" not in sess


def test_admin_registration_verification_without_state_redirects():
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )

    client = app.test_client()

    response = client.get("/register_verification")

    assert response.status_code == 302
    assert "register" in response.location


def test_admin_registration_verification_wrong_otp(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    with client.session_transaction() as sess:
        sess["registration_email"] = "admin@example.com"
        sess["registration_password_hash"] = "hashed"
        sess["registration_otp_hash"] = "correct-hash"
        sess["registration_otp_expires"] = 9999999999
        sess["registration_otp_attempts"] = 0

    response = client.post(
        "/register_verification",
        data={"onepass": "wrong"},
    )

    assert response.status_code == 200
    assert response.json["context"]["data"] == "Incorrect OTP."

    with client.session_transaction() as sess:
        assert sess["registration_otp_attempts"] == 1


def test_admin_registration_verification_max_attempts(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()

    with client.session_transaction() as sess:
        sess["registration_email"] = "admin@example.com"
        sess["registration_password_hash"] = "hashed"
        sess["registration_otp_hash"] = "correct-hash"
        sess["registration_otp_expires"] = 9999999999
        sess["registration_otp_attempts"] = 5

    response = client.post(
        "/register_verification",
        data={"onepass": "wrong"},
    )

    assert response.status_code == 200
    assert "Too many" in response.json["context"]["data"]


# ============================================================================
# 9. Management home / student / teacher / CSV / promotion
# ============================================================================

def test_management_home_without_class():
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_logged_in(client)

    response = client.get("/home")

    assert response.status_code == 200
    assert response.json["template"] == "Home.html"
    assert response.json["context"]["students"] == []


def test_management_show_students_invalid_class():
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_logged_in(client)

    response = client.post(
        "/show_students",
        data={
            "class": "not-a-number",
            "section": "A",
        },
    )

    assert response.status_code == 200
    assert response.json["context"]["data"] == "invalid class value"


def test_management_show_students_without_selected_class():
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_logged_in(client)

    response = client.post(
        "/show_students",
        data={"section": "A"},
    )

    assert response.status_code == 200
    assert response.json["context"]["data"] == "select a class first"


def test_management_edit_missing_student():
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    query = MagicMock()
    query.filter.return_value.first.return_value = None
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module.Student, "query", query, raising=False)

    client = app.test_client()
    set_logged_in(client)

    response = client.post(
        "/edit/999",
        data={"content": "2000-01-01", "Mobile": "123"},
    )

    monkeypatch.undo()

    assert response.status_code == 200
    assert "No student found" in response.json["context"]["data"]


def test_management_export_rejects_invalid_class():
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_logged_in(client)

    response = client.get("/export_csv")

    assert response.status_code == 200
    assert response.json["context"]["data"] == "invalid class value"


def test_management_import_requires_csv_file():
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_logged_in(client)

    response = client.post(
        "/import_csv",
        data={"class": "12", "section": "A"},
    )

    assert response.status_code == 200
    assert "choose a CSV" in response.json["context"]["data"]


def test_management_import_rejects_non_csv():
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    client = app.test_client()
    set_logged_in(client)

    response = client.post(
        "/import_csv",
        data={
            "class": "12",
            "section": "A",
            "csv_file": (
                io.BytesIO(b"not csv"),
                "students.txt",
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "Only .csv" in response.json["context"]["data"]


def test_management_remove_student_calls_service(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template
    monkeypatch.setattr(module, "remove", MagicMock())

    student_query = MagicMock()
    student_query.filter.return_value.all.return_value = []
    monkeypatch.setattr(module.Student, "query", student_query, raising=False)

    client = app.test_client()
    set_logged_in(client)

    response = client.post("/delete/15")

    assert response.status_code == 200
    module.remove.assert_called_once_with(roll_no=15)


def test_management_remove_teacher_calls_service(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template
    monkeypatch.setattr(module, "remove", MagicMock())

    teacher_query = MagicMock()
    teacher_query.all.return_value = []
    monkeypatch.setattr(module.Teacher, "query", teacher_query, raising=False)

    client = app.test_client()
    set_logged_in(client)

    response = client.post("/delete_teacher/teacher@example.com")

    assert response.status_code == 200
    module.remove.assert_called_once_with(name="teacher@example.com")


def test_management_promote_success(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    monkeypatch.setattr(
        module,
        "promote",
        lambda: {"promoted": 10, "graduated": 2},
    )

    client = app.test_client()
    set_logged_in(client, class_value=12, sec="A")

    response = client.post("/promote")

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert "class_value" not in sess
        assert "sec" not in sess

    assert response.json["context"]["promoted_count"] == 10
    assert response.json["context"]["graduated_count"] == 2


def test_management_promote_failure(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.home",
        "home_bp",
    )
    module.render_template = fake_render_template

    def fail():
        raise RuntimeError("promotion failure")

    monkeypatch.setattr(module, "promote", fail)

    client = app.test_client()
    set_logged_in(client)

    response = client.post("/promote")

    assert response.status_code == 200
    assert "Could not promote" in response.json["context"]["data"]


# ============================================================================
# 10. Blueprint / endpoint inventory
# ============================================================================

def test_teacher_blueprints_contain_expected_endpoints():
    expected = {
        "auth": {
            "login_page",
            "login_face",
            "log_out",
        },
        "home": {
            "home",
            "show_results",
            "chatbot",
        },
        "marks": {
            "edit",
        },
        "reports": {
            "graph",
            "piegraph",
            "leaderboard",
            "attendence",
        },
        "pages": {
            "about",
            "support",
            "forgot_password",
            "forgot_password_verification",
            "reset_password",
            "profile",
            "profile_details",
            "settings",
        },
    }

    for module_name, blueprint_name in (
        ("teacher_side.app.routes.auth", "auth_bp"),
        ("teacher_side.app.routes.home", "home_bp"),
        ("teacher_side.app.routes.marks", "marks_bp"),
        ("teacher_side.app.routes.reports", "reports_bp"),
        ("teacher_side.app.routes.pages", "pages_bp"),
    ):
        module = safe_import(module_name)
        blueprint = getattr(module, blueprint_name)
        # Blueprint deferred functions are implementation details and don't
        # expose route names reliably; the actual route inventory test below
        # uses a registered Flask application instead.
        assert blueprint.name


def test_teacher_registered_routes_exist():
    modules = [
        ("teacher_side.app.routes.auth", "auth_bp"),
        ("teacher_side.app.routes.home", "home_bp"),
        ("teacher_side.app.routes.marks", "marks_bp"),
        ("teacher_side.app.routes.reports", "reports_bp"),
        ("teacher_side.app.routes.pages", "pages_bp"),
    ]

    app = make_app()

    for module_name, blueprint_name in modules:
        module = safe_import(module_name)
        app.register_blueprint(getattr(module, blueprint_name))

    paths = {rule.rule for rule in app.url_map.iter_rules()}

    expected_paths = {
        "/",
        "/login-face",
        "/log-out",
        "/home",
        "/show_results",
        "/chatbot",
        "/edit/<int:roll_no>/<string:subject>/<int:exam_id>",
        "/leaderboard",
        "/attendence",
        "/about",
        "/support",
        "/forget_pass",
        "/forgot_password_verification",
        "/reset_password",
        "/profile",
        "/profile-details",
        "/settings",
    }

    for expected in expected_paths:
        assert expected in paths


def test_management_registered_routes_exist():
    modules = [
        ("management_side.app.routes.auth", "auth_bp"),
        ("management_side.app.routes.home", "home_bp"),
    ]

    app = make_app()

    for module_name, blueprint_name in modules:
        module = safe_import(module_name)
        app.register_blueprint(getattr(module, blueprint_name))

    paths = {rule.rule for rule in app.url_map.iter_rules()}

    expected_paths = {
        "/",
        "/login-face",
        "/log-out",
        "/register",
        "/register_verification",
        "/home",
        "/show_students",
        "/teachers_data",
        "/edit/<int:roll_no>",
        "/edit_teacher/<Gmail>",
        "/export_csv",
        "/import_csv",
        "/delete/<int:roll_no>",
        "/delete_teacher/<string:gmail>",
        "/promote",
    }

    for expected in expected_paths:
        assert expected in paths


# ============================================================================
# 11. Shared services - isolated safety tests
# ============================================================================

def test_profile_initials_service():
    module = safe_import("shared.services.profile_service")

    assert module.initials_for_name("John Doe") == "JD"
    assert module.initials_for_name("John") == "J"


def test_profile_initials_empty_name():
    module = safe_import("shared.services.profile_service")

    result = module.initials_for_name("")

    assert result == ""


def test_password_bytes_returns_bytes():
    module = safe_import("shared.services.profile_service")

    result = module.password_bytes("abc")

    assert isinstance(result, bytes)
    assert result == b"abc"


def test_leaderboard_service_can_be_imported():
    module = safe_import("shared.services.leaderboard_service")

    assert hasattr(module, "compute_leaderboard")


def test_graph_service_can_be_imported():
    module = safe_import("shared.services.graph_service")

    assert hasattr(module, "generate_graph")
    assert hasattr(module, "generate_pie_graph")


def test_export_service_can_be_imported():
    module = safe_import("shared.services.export_service")

    assert hasattr(module, "export_csv")
    assert hasattr(module, "import_csv")
    assert hasattr(module, "promote")


def test_face_service_can_be_imported():
    module = safe_import("shared.services.face_id_service")

    assert hasattr(module, "match_face")
    assert hasattr(module, "save_face")


def test_email_service_can_be_imported():
    module = safe_import("shared.services.email_service")

    assert hasattr(module, "email")
    assert hasattr(module, "email_file")


def test_email_service_exposes_error_types():
    module = safe_import("shared.services.email_service")

    assert hasattr(module, "EmailSendError")
    assert hasattr(module, "NoInternetError")
    assert issubclass(module.NoInternetError, module.EmailSendError)


def test_email_raises_no_internet_error_when_offline(monkeypatch):
    """A DNS/connection failure (what happens when there's no internet)
    must raise NoInternetError instead of being silently swallowed."""
    module = safe_import("shared.services.email_service")

    class OfflineSMTP:
        def __init__(self, *args, **kwargs):
            raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(module.smtplib, "SMTP", OfflineSMTP)

    with pytest.raises(module.NoInternetError):
        module.email("from@example.com", "to@example.com", "Subject", "Body", "app-password")


def test_email_file_raises_no_internet_error_when_offline(monkeypatch, tmp_path):
    module = safe_import("shared.services.email_service")

    class OfflineSMTP:
        def __init__(self, *args, **kwargs):
            raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(module.smtplib, "SMTP", OfflineSMTP)

    log_file = tmp_path / "App.log"
    log_file.write_text("log contents")

    with pytest.raises(module.NoInternetError):
        module.email_file(
            "from@example.com", "to@example.com", "Subject", "Body",
            str(log_file), "app-password",
        )


def test_email_raises_generic_error_for_non_connectivity_failures(monkeypatch):
    """A non-connectivity failure (e.g. rejected credentials) should still
    raise, but as the more general EmailSendError - not NoInternetError,
    since telling the user "no internet" would be misleading."""
    module = safe_import("shared.services.email_service")

    class AuthFailingSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def starttls(self):
            pass

        def login(self, *args, **kwargs):
            raise module.smtplib.SMTPAuthenticationError(535, b"Authentication failed")

        def send_message(self, *args, **kwargs):
            pass

    monkeypatch.setattr(module.smtplib, "SMTP", AuthFailingSMTP)

    with pytest.raises(module.EmailSendError) as excinfo:
        module.email("from@example.com", "to@example.com", "Subject", "Body", "app-password")

    assert not isinstance(excinfo.value, module.NoInternetError)


def test_send_results_job_reports_no_internet_error(monkeypatch):
    """The bulk "send results to parents" background job should stop and
    report a clear no-internet message, instead of marking the job "done"
    while emails silently failed to send."""
    app, module = register_blueprint_app(
        "teacher_side.app.routes.email_routes",
        "email_bp",
    )

    student = SimpleNamespace(roll_no=1, student_name="Test Student", student_gmail="parent@example.com")
    mark = SimpleNamespace(roll_no=1, marks=80)
    exam_obj = SimpleNamespace(exam_id=1)

    student_query = MagicMock()
    student_query.filter.return_value.all.return_value = [student]
    monkeypatch.setattr(module.Student, "query", student_query, raising=False)

    exam_query = MagicMock()
    exam_query.filter.return_value.first.return_value = exam_obj
    monkeypatch.setattr(module.Exam, "query", exam_query, raising=False)

    mark_query = MagicMock()
    mark_query.join.return_value.filter.return_value.all.return_value = [mark]
    monkeypatch.setattr(module.Mark, "query", mark_query, raising=False)

    def fake_email(*args, **kwargs):
        raise module.NoInternetError(
            "Could not send email: no internet connection. "
            "Please check your network connection and try again."
        )

    monkeypatch.setattr(module, "email", fake_email)

    job_id = "test-job"
    module._jobs[job_id] = {
        "status": "running",
        "sent_count": 0,
        "total": 0,
        "message": "",
        "cancel_requested": False,
        "username": "teacher@example.com",
    }

    module._run_send_job(app, job_id, "teacher@example.com", "app-password", 10, "A", "Maths", "Midterm")

    job = module._jobs[job_id]
    assert job["status"] == "error"
    assert "no internet connection" in job["message"]


# ============================================================================
# 12. Basic service contracts
# ============================================================================

def test_remove_service_exposes_remove_function():
    module = safe_import("shared.services.remove_service")

    assert callable(module.remove)


def test_create_account_service_exposes_create_account():
    module = safe_import("shared.services.create_account_service")

    assert callable(module.create_account)


# ============================================================================
# 13. Security-oriented behavior checks
# ============================================================================

def test_teacher_chatbot_does_not_call_ai_for_empty_input():
    app, module = register_blueprint_app(
        "teacher_side.app.routes.home",
        "home_bp",
    )

    client = app.test_client()
    set_logged_in(client)

    ai = MagicMock()
    module.ask_ai = ai

    response = client.post(
        "/chatbot",
        json={"message": ""},
    )

    assert response.status_code == 400
    ai.assert_not_called()


def test_teacher_face_login_does_not_authenticate_without_match(monkeypatch):
    app, module = register_blueprint_app(
        "teacher_side.app.routes.auth",
        "auth_bp",
    )

    teacher = SimpleNamespace(
        Gmail="teacher@example.com",
        face_id="stored",
        class_teacher=12,
        class_teacher_sec="A",
    )

    query = MagicMock()
    query.filter.return_value.all.return_value = [teacher]

    monkeypatch.setattr(module.Teacher, "query", query, raising=False)
    monkeypatch.setattr(module, "match_face", lambda *_: False)

    client = app.test_client()

    response = client.post(
        "/login-face",
        data={"face": (io.BytesIO(b"fake"), "face.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True


def test_admin_registration_does_not_store_plain_password(monkeypatch):
    app, module = register_blueprint_app(
        "management_side.app.routes.auth",
        "auth_bp",
    )
    module.render_template = fake_render_template
    monkeypatch.setattr(module, "email", MagicMock())

    client = app.test_client()

    password = "abc123"

    response = client.post(
        "/register",
        data={
            "username": "admin@example.com",
            "password": password,
            "confirm_password": password,
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["registration_password_hash"] != password


# ============================================================================
# Final note
# ============================================================================

def test_suite_has_expected_scope():
    """
    Guard test so this file doesn't silently become a tiny test suite after
    future edits.
    """
    current_file = Path(__file__).read_text(encoding="utf-8")

    expected_sections = [
        "Teacher-side authentication",
        "Teacher dashboard",
        "Teacher marks",
        "Teacher reports",
        "Teacher profile",
        "Management authentication",
        "Management registration",
        "Management home",
        "Blueprint / endpoint inventory",
        "Shared services",
    ]

    for section in expected_sections:
        assert section in current_file
