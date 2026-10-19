"""Production entry point:  gunicorn --chdir management_side -w 1 --threads 4 -b 0.0.0.0:PORT wsgi:app

Use a single worker process (threads are fine): background e-mail job status is kept in memory.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # makes `shared` importable

from app import create_app  # noqa: E402

app = create_app()
