"""Builds the Flask app for either side (teacher / management).

The two sides run as separate processes and only share the database and the
code in ``shared/``. Everything side-specific (secret key, cookie name, log
file) is derived from ``side`` so the two never interfere with each other.
"""
import os
from datetime import timedelta

from flask import Flask
from sqlalchemy.engine import make_url

from shared import db, settings
from shared.utils.logger import setup_logger
from shared.services.profile_schema import ensure_profile_columns


def _ensure_database_exists(uri):
    """CREATE DATABASE IF NOT EXISTS - never drops anything."""
    url = make_url(uri)
    if not url.drivername.startswith("mysql"):
        return
    import mysql.connector as sql

    conn = sql.connect(
        host=url.host or "127.0.0.1",
        port=url.port or 3306,
        user=url.username,
        password=url.password,
    )
    try:
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{url.database}`")
        conn.commit()
    finally:
        conn.close()


def create_app(side, side_dir, register_blueprints):
    """side: 'teacher' or 'management'; side_dir: that side's folder."""
    app = Flask(
        f"smartmentorconnect_{side}",
        template_folder=os.path.join(side_dir, "templates"),
        static_folder=os.path.join(side_dir, "static"),
    )

    app.secret_key = settings.secret_key(side)
    app.permanent_session_lifetime = timedelta(hours=1)
    # Browsers share cookies between ports on the same host (localhost:8000
    # and localhost:5000), so each side needs its own cookie name or running
    # both at once keeps logging the other one out.
    app.config["SESSION_COOKIE_NAME"] = f"smartmentorconnect_{side}_session"
    app.config["SQLALCHEMY_DATABASE_URI"] = settings.sqlalchemy_uri()

    db.init_app(app)

    _ensure_database_exists(app.config["SQLALCHEMY_DATABASE_URI"])
    with app.app_context():
        from shared import models  # noqa: F401  (registers all tables)
        db.create_all()
        ensure_profile_columns(db)

    setup_logger(app, log_name=os.path.join(settings.PROJECT_ROOT, f"App_{side}.log"))
    register_blueprints(app)
    return app
