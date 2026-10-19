"""Colleges: one registry + one database per college.

* The **registry** (a small "master" database) only lists the colleges: their
  display name, a URL-safe slug and the name of their own database.
* Every college has its **own database** with the usual tables (students,
  teachers, Admin, courses, exams, marks, attendance). Nothing is shared
  between colleges, so roll numbers and e-mail addresses can repeat.
* The college a person picked on the login page is kept in their session;
  ``before_request`` (see app_factory) activates it, and ``CollegeSession``
  (shared/extensions.py) then sends all queries to that college's database.
"""
import re
import threading
from collections import namedtuple
from datetime import datetime, timezone

from flask import g, has_app_context
from sqlalchemy import Column, DateTime, Integer, String, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session as PlainSession
from sqlalchemy.orm import declarative_base

from shared import settings

CollegeInfo = namedtuple("CollegeInfo", "slug name db_name")

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,&'()\-]{2,99}$")
_DB_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")

Base = declarative_base()


class College(Base):
    __tablename__ = "colleges"

    id = Column(Integer, primary_key=True)
    slug = Column(String(40), unique=True, nullable=False)
    name = Column(String(120), unique=True, nullable=False)
    db_name = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class CollegeError(ValueError):
    """Raised with a message that is safe to show to the user."""


_lock = threading.RLock()
_engines = {}          # uri -> Engine
_ready = set()         # uris whose schema has been created/checked
_cache = {}            # (master uri, slug) -> CollegeInfo


# ---- engines ---------------------------------------------------------------
def _ensure_mysql_database(uri):
    """CREATE DATABASE IF NOT EXISTS - never drops anything."""
    url = make_url(uri)
    if not url.drivername.startswith("mysql"):
        return
    if not _DB_NAME_PATTERN.match(url.database or ""):
        raise CollegeError("Invalid database name.")
    server = create_engine(url.set(database=None), isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{url.database}`"))
    finally:
        server.dispose()


def _engine(uri):
    with _lock:
        engine = _engines.get(uri)
        if engine is None:
            _ensure_mysql_database(uri)
            engine = create_engine(uri, pool_pre_ping=True, pool_recycle=1800)
            _engines[uri] = engine
        return engine


def master_engine():
    uri = settings.master_uri()
    engine = _engine(uri)
    with _lock:
        if ("master", uri) not in _ready:
            Base.metadata.create_all(engine)
            _ready.add(("master", uri))
    return engine


def init_college_schema(engine):
    """Create any missing tables/columns/default exams in one college database.
    Never drops or overwrites existing data."""
    from shared import models  # noqa: F401  (registers all tables)
    from shared.extensions import db
    from shared.services.course_service import ensure_default_exams
    from shared.services.profile_schema import ensure_profile_columns

    db.metadata.create_all(engine)
    ensure_profile_columns(engine)
    with PlainSession(engine) as session:
        ensure_default_exams(session)


def engine_for(info):
    """Engine of a college's own database (schema is checked on first use)."""
    uri = settings.college_uri(info.db_name)
    engine = _engine(uri)
    with _lock:
        if ("college", uri) not in _ready:
            init_college_schema(engine)
            _ready.add(("college", uri))
    return engine


# ---- registry --------------------------------------------------------------
def _info(row):
    return CollegeInfo(row.slug, row.name, row.db_name)


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40].strip("_")
    return slug


def list_colleges():
    try:
        with PlainSession(master_engine()) as session:
            rows = session.execute(select(College).order_by(College.name)).scalars().all()
            return [_info(r) for r in rows]
    except OperationalError:
        return []


def get_college(slug):
    """CollegeInfo for a slug, or None. Looked up in the registry once and
    then remembered (colleges are never renamed or deleted by the app)."""
    slug = (slug or "").strip().lower()
    if not slug or len(slug) > 40:
        return None
    key = (settings.master_uri(), slug)
    cached = _cache.get(key)
    if cached:
        return cached
    with PlainSession(master_engine()) as session:
        row = session.execute(select(College).where(College.slug == slug)).scalars().first()
        if row is None:
            return None
        info = _info(row)
    _cache[key] = info
    return info


def validate_name(name):
    name = " ".join((name or "").split())
    if not NAME_PATTERN.match(name):
        raise CollegeError(
            "College name must be 3-100 characters (letters, numbers, spaces and . , & ' ( ) - only)."
        )
    if not slugify(name):
        raise CollegeError("College name must contain letters or numbers.")
    return name


def create_college(name):
    """Register a new college: add it to the registry and create its own
    database with all tables. Returns its CollegeInfo."""
    name = validate_name(name)
    slug = slugify(name)
    db_name = f"smc_{slug}"
    with PlainSession(master_engine()) as session:
        taken = session.execute(
            select(College).where((College.slug == slug) | (College.name == name))
        ).scalars().first()
        if taken:
            raise CollegeError("A college with this name is already registered.")
        session.add(College(slug=slug, name=name, db_name=db_name))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise CollegeError("A college with this name is already registered.")
    info = CollegeInfo(slug, name, db_name)
    engine_for(info)  # creates the database and its tables
    return info


def register_existing(name, db_name, slug=None):
    """Add an already existing database to the registry (used for the legacy
    single-college database and by the sample-data script)."""
    name = validate_name(name)
    slug = slug or slugify(name)
    if not _DB_NAME_PATTERN.match(db_name):
        raise CollegeError("Invalid database name.")
    with PlainSession(master_engine()) as session:
        row = session.execute(select(College).where(College.slug == slug)).scalars().first()
        if row is None:
            session.add(College(slug=slug, name=name, db_name=db_name))
            session.commit()
    return CollegeInfo(slug, name, db_name)


def init_registry():
    """Called at app start: make sure the registry exists, and if this
    installation used the old single database ("collegedb"), register it as a
    college so the existing data keeps working."""
    engine = master_engine()
    if engine.dialect.name != "mysql":
        return
    with PlainSession(engine) as session:
        if session.execute(select(College.id).limit(1)).first():
            return
    legacy = settings.mysql_database()
    with engine.connect() as conn:
        found = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = :db AND table_name = 'students'"
            ),
            {"db": legacy},
        ).scalar()
    if found:
        register_existing("Default College", legacy, slug="default")


# ---- the college of the current request -----------------------------------
def activate(slug):
    """Use this college's database for the rest of the current request
    (or app context). Returns its CollegeInfo, or None if unknown."""
    info = get_college(slug)
    g.college_slug = info.slug if info else None
    return info


def active_slug():
    return g.get("college_slug") if has_app_context() else None


def active_college():
    slug = active_slug()
    return get_college(slug) if slug else None


def active_engine():
    info = active_college()
    return engine_for(info) if info else None


def reset_caches():
    """Forget engines and cached lookups (used by tests)."""
    with _lock:
        for engine in _engines.values():
            engine.dispose()
        _engines.clear()
        _ready.clear()
        _cache.clear()
