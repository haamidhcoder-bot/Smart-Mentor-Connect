import pytest
from flask import Flask


@pytest.fixture(autouse=True)
def _flask_app_context():
    """Keep a Flask application context active for every test.

    Several tests monkeypatch SQLAlchemy model attributes (e.g.
    ``Teacher.query``) directly. Flask-SQLAlchemy's ``query`` descriptor
    needs a live application context just to be read (even before any
    query actually runs), so without this the monkeypatching itself
    raises "Working outside of application context" long before the
    test gets to exercise any real behavior.
    """
    app = Flask(__name__)
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _env_settings(monkeypatch):
    """Settings come from environment variables; give tests fake ones."""
    for key, value in {
        "MYSQL_PASSWORD": "test-password",
        "TEACHER_SECRET_KEY": "test-teacher-secret-key-0123456789",
        "MANAGEMENT_SECRET_KEY": "test-management-secret-key-0123456789",
        "GEMINI_API_KEY": "test-gemini-key",
        "ADMIN1_EMAIL": "admin1@example.com",
        "ADMIN1_APP_PASSWORD": "app-password-1",
        "ADMIN2_EMAIL": "admin2@example.com",
        "ADMIN2_APP_PASSWORD": "app-password-2",
        "CSRF_DISABLED": "1",
    }.items():
        monkeypatch.setenv(key, value)
