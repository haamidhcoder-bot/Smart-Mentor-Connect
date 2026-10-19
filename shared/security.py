"""Security basics shared by the three sites: CSRF protection, safer cookies,
security headers, friendly error pages and a login-attempt throttle."""
import secrets
import threading
import time

from flask import jsonify, render_template, request, session, url_for
from markupsafe import Markup

from shared import settings


# ---- CSRF -------------------------------------------------------------------
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_token():
    """The per-session token every POST must send back (hidden form field
    ``csrf_token`` or the ``X-CSRF-Token`` header; shared/static/ui.js adds
    both automatically)."""
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def _wants_json():
    return request.is_json or "application/json" in request.headers.get("Accept", "")


def _csrf_failed(app):
    app.logger.warning(f"CSRF check failed for {request.method} {request.path}")
    message = (
        "Your session expired or this form is no longer valid. "
        "Please go back, refresh the page and try again."
    )
    if _wants_json():
        return jsonify({"success": False, "status": "error", "message": message}), 400
    return render_template("Error.html", data=message, location=_login_or_back()), 400


def _login_or_back():
    try:
        return url_for("auth.login_page")
    except Exception:  # no login endpoint registered (isolated tests)
        return "/"


def init_security(app):
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["SESSION_COOKIE_SECURE"] = settings.cookie_secure()
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["csrf_input"] = lambda: Markup(
        f'<input type="hidden" name="csrf_token" value="{csrf_token()}">'
    )

    @app.before_request
    def _check_csrf():
        if request.method in SAFE_METHODS or not settings.csrf_enabled():
            return None
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        expected = session.get("_csrf", "")
        if not expected or not sent or not secrets.compare_digest(str(sent), expected):
            return _csrf_failed(app)
        return None

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # The camera is only needed by the Face ID pages of this same site.
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if request.endpoint != "static" and not request.path.startswith("/shared-static/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _error_page(code, message):
        def handler(error):
            if _wants_json():
                return jsonify({"success": False, "status": "error", "message": message}), code
            return render_template("Error.html", data=message, location=_login_or_back()), code
        return handler

    app.register_error_handler(403, _error_page(403, "You do not have permission to open this page."))
    app.register_error_handler(404, _error_page(404, "That page could not be found."))
    app.register_error_handler(405, _error_page(405, "That action is not allowed here."))
    app.register_error_handler(413, _error_page(413, "That file is too large."))

    @app.errorhandler(500)
    def _server_error(error):
        app.logger.exception("Unhandled error")
        message = "Something went wrong on our side. Please try again; if it keeps happening, contact support."
        if _wants_json():
            return jsonify({"success": False, "status": "error", "message": message}), 500
        return render_template("Error.html", data=message, location=_login_or_back()), 500


# ---- login throttle ------------------------------------------------------
class LoginThrottle:
    """Lock a (college, account) pair for a while after repeated failures, so
    passwords (or dates of birth) can't be guessed. Kept in memory per process."""

    def __init__(self, max_failures=5, lock_seconds=300):
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self._failures = {}
        self._lock = threading.Lock()

    @staticmethod
    def key(college_slug, account):
        return (college_slug or "", (account or "").strip().lower())

    def locked_for(self, key):
        """Seconds still locked (0 if the account may try)."""
        with self._lock:
            count, since = self._failures.get(key, (0, 0))
            if count >= self.max_failures:
                remaining = self.lock_seconds - (time.time() - since)
                if remaining > 0:
                    return int(remaining) + 1
                self._failures.pop(key, None)
        return 0

    def record_failure(self, key):
        with self._lock:
            count, _ = self._failures.get(key, (0, 0))
            self._failures[key] = (count + 1, time.time())

    def clear(self, key):
        with self._lock:
            self._failures.pop(key, None)

    def reset(self):
        with self._lock:
            self._failures.clear()
