from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session


class NoCollegeSelected(RuntimeError):
    """A database query was attempted before a college was chosen."""


class CollegeSession(Session):
    """Sends every query to the database of the college the current request
    belongs to (each college has its own database - see shared/colleges.py)."""

    def get_bind(self, mapper=None, clause=None, bind=None, **kwargs):
        if bind is not None:
            return bind
        from shared import colleges

        engine = colleges.active_engine()
        if engine is None:
            raise NoCollegeSelected(
                "No college is selected for this request, so there is no database to use."
            )
        return engine


db = SQLAlchemy(session_options={"class_": CollegeSession})
