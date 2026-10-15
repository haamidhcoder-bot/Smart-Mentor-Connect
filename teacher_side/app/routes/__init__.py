from .auth import auth_bp
from .home import home_bp
from .marks import marks_bp
from .reports import reports_bp
from .email_routes import email_bp
from .pages import pages_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(marks_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(email_bp)
    app.register_blueprint(pages_bp)
