from functools import wraps

from flask import abort, redirect, url_for, session
from werkzeug.routing.exceptions import BuildError

from shared.models import Teacher


def _login_redirect():
    """Redirect to the login page, whichever blueprint layout is in play.

    Production apps register the login route on an ``auth`` blueprint, so
    the endpoint is ``auth.login_page``. Isolated tests (and any consumer
    that mounts the route without a blueprint) may only have a bare
    ``login_page`` endpoint, so fall back to that instead of blowing up.
    """
    try:
        return redirect(url_for("auth.login_page"))
    except BuildError:
        pass

    try:
        return redirect(url_for("login_page"))
    except BuildError:
        # Last resort: no login endpoint is registered on this app at all
        # (e.g. a blueprint mounted in isolation for testing). Redirecting
        # to a fixed path is still safer than letting the request 500.
        return redirect("/login")


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("logged_in"):
            return func(*args, **kwargs)

        return _login_redirect()

    return wrapper


def class_teacher_required(func):
    """Allow access only to a logged-in teacher with an assigned class/section.

    The assignment is verified against the Teacher record and then cached in
    the session, so a user can never grant themselves a class/section just by
    posting a form value. Once verified, subsequent requests trust the
    session-cached assignment instead of re-hitting the database every time;
    the cache is repopulated from the Teacher record whenever it's missing.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return _login_redirect()

        if session.get("class_teacher") is not None and session.get("class_teacher_sec"):
            return func(*args, **kwargs)

        username = session.get("username", "")
        teacher = Teacher.query.filter_by(Gmail=username).first()

        if (
            teacher is None
            or teacher.class_teacher is None
            or not teacher.class_teacher_sec
        ):
            abort(403)

        # Keep the session synchronized with the authoritative Teacher record.
        session["class_teacher"] = teacher.class_teacher
        session["class_teacher_sec"] = teacher.class_teacher_sec

        return func(*args, **kwargs)

    return wrapper
