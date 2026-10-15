"""Run the management side:  python management_side/run_management.py   (default port 5000)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # makes `shared` importable

from shared import settings  # noqa: E402
from app import create_app, SIDE  # noqa: E402  (this side's own `app` package)

if __name__ == "__main__":
    create_app().run(
        host=settings.get("MANAGEMENT_HOST", "127.0.0.1"),
        port=settings.port(SIDE, 5000),
        debug=settings.debug_enabled(),
    )
