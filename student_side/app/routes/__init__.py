from .auth import auth_bp
from .home import home_bp
from .reports import reports_bp
from .attendance import attendance_bp
from .pages import pages_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(pages_bp)
