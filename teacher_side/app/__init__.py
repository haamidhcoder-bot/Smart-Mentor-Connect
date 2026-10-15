"""Teacher side application factory (config comes from environment variables)."""
import os

from shared.app_factory import create_app as _create_app

SIDE = "teacher"
SIDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app():
    from .routes import register_blueprints

    return _create_app(SIDE, SIDE_DIR, register_blueprints)
