"""Builds the Flask app for each side (teacher / management / student).

Every college has its own database; the request is routed to the right one.

The sides run as separate processes and only share the database and the
code in ``shared/``. Everything side-specific (secret key, cookie name, log
file) is derived from ``side`` so the two never interfere with each other.
"""
import os
from datetime import timedelta

from flask import Flask, g, send_from_directory, session
from jinja2 import ChoiceLoader, FileSystemLoader

from shared import colleges, db, settings
from shared.security import init_security
from shared.utils.logger import setup_logger


def _register_template_helpers(app):
    """Values and helpers every template can use (college structure, grading)."""
    from shared.services import grading
    from shared.services.course_service import course_name

    app.jinja_env.globals.update(
        DEPARTMENTS=settings.departments(),
        SECTIONS=settings.sections(),
        YEARS=list(range(1, settings.max_year() + 1)),
        pass_mark=grading.pass_mark(),
        min_attendance=settings.min_attendance(),
        course_name=course_name,
        grade_for=grading.grade_for,
        # Used by the login pages (dropdown) and the page header.
        college_options=colleges.list_colleges,
        current_college=colleges.active_college,
    )


def _register_college_selection(app):
    """Before every request, pick the database of the right college.

    A logged-in person always uses the college they logged in to. Everyone
    else (login, forgot-password, registration) uses the college chosen on
    that page, which those routes activate themselves for that request.
    """

    @app.before_request
    def _select_college():
        if session.get("logged_in"):
            slug = session.get("college")
            if not colleges.get_college(slug):
                # A session from before colleges existed (or a removed
                # college): ask the person to log in again.
                session.clear()
                slug = None
        else:
            slug = None
        g.college_slug = None
        if slug:
            colleges.activate(slug)


SHARED_STATIC = os.path.join(settings.PROJECT_ROOT, "shared", "static")
SHARED_TEMPLATES = os.path.join(settings.PROJECT_ROOT, "shared", "templates")


def _register_shared_assets(app, side):
    """Styles, scripts and icons used by all three sites live in shared/static
    and are served from /shared-static/; shared template snippets live in
    shared/templates."""
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(SHARED_TEMPLATES)])

    @app.route("/shared-static/<path:filename>", endpoint="shared_static")
    def shared_static(filename):
        response = send_from_directory(SHARED_STATIC, filename, max_age=3600)
        return response

    def shared_url(filename):
        """URL of a shared file with a version stamp so browsers pick up changes."""
        path = os.path.join(SHARED_STATIC, filename)
        version = int(os.path.getmtime(path)) if os.path.exists(path) else 0
        return f"/shared-static/{filename}?v={version}"

    app.jinja_env.globals.update(shared_url=shared_url, SIDE=side)


def create_app(side, side_dir, register_blueprints):
    """side: 'teacher' or 'management'; side_dir: that side's folder."""
    app = Flask(
        f"smartmentorconnect_{side}",
        template_folder=os.path.join(side_dir, "templates"),
        static_folder=os.path.join(side_dir, "static"),
    )

    app.secret_key = settings.secret_key(side)
    app.permanent_session_lifetime = timedelta(days=settings.remember_days())
    # Browsers share cookies between ports on the same host (localhost:8000
    # and localhost:5000), so each side needs its own cookie name or running
    # both at once keeps logging the other one out.
    app.config["SESSION_COOKIE_NAME"] = f"smartmentorconnect_{side}_session"
    app.config["SQLALCHEMY_DATABASE_URI"] = settings.sqlalchemy_uri()

    if settings.get("TRUST_PROXY", "0").lower() in ("1", "true", "yes", "on"):
        # Behind Render's HTTPS proxy: trust X-Forwarded-* so request.is_secure,
        # redirects and client IPs are correct.
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.route("/healthz", endpoint="healthz")
    def healthz():
        """Cheap liveness probe for Render (does not touch the database)."""
        return "ok", 200, {"Content-Type": "text/plain"}

    db.init_app(app)

    # The registry of colleges (each college's own database is created and
    # checked the first time it is used - see shared/colleges.py).
    colleges.init_registry()

    init_security(app)
    _register_shared_assets(app, side)
    _register_college_selection(app)
    _register_template_helpers(app)

    setup_logger(app, log_name=os.path.join(settings.PROJECT_ROOT, f"App_{side}.log"))
    register_blueprints(app)
    return app
