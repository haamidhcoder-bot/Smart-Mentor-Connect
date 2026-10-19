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


def advisor_required(func):
    """Allow access only to a logged-in teacher who is class advisor of a
    department / year / section.

    The assignment is verified against the Teacher record and then cached in
    the session, so a user can never grant themselves a group just by
    posting a form value. Once verified, subsequent requests trust the
    session-cached assignment instead of re-hitting the database every time;
    the cache is repopulated from the Teacher record whenever it's missing.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return _login_redirect()

        if (
            session.get("advisor_dept")
            and session.get("advisor_year") is not None
            and session.get("advisor_section")
        ):
            return func(*args, **kwargs)

        username = session.get("username", "")
        teacher = Teacher.query.filter_by(Gmail=username).first()

        if (
            teacher is None
            or not teacher.advisor_dept
            or teacher.advisor_year is None
            or not teacher.advisor_section
        ):
            abort(403)

        # Keep the session synchronized with the authoritative Teacher record.
        session["advisor_dept"] = teacher.advisor_dept
        session["advisor_year"] = teacher.advisor_year
        session["advisor_section"] = teacher.advisor_section

        return func(*args, **kwargs)

    return wrapper
