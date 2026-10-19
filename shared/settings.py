"""All configuration comes from environment variables (no config.py).

Set them in your shell, or put them in a ``.env`` file in the project root
(``KEY=value`` per line). Real environment variables always win over ``.env``.
See ``.env.example`` for the full list.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class MissingSettingError(RuntimeError):
    """A required environment variable is not set."""


def _load_dotenv(path=os.path.join(PROJECT_ROOT, ".env")):
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)


_load_dotenv()


def get(name, default=None, required=False):
    value = os.environ.get(name)
    if value is None or value == "":
        if required:
            raise MissingSettingError(
                f"Environment variable {name} is not set. "
                "See .env.example for the list of required settings."
            )
        return default
    return value


# ---- Database ---------------------------------------------------------
def mysql_host():
    return get("MYSQL_HOST", "127.0.0.1")


def mysql_user():
    return get("MYSQL_USER", "root")


def mysql_password():
    return get("MYSQL_PASSWORD", required=True)


def mysql_database():
    # Legacy single-college database. Colleges registered through the app get
    # their own database (see shared/colleges.py); an existing "collegedb" is
    # registered automatically as a college on first start.
    return "collegedb"


def master_database():
    """Small registry database that only lists the colleges (their name and
    database). Student/teacher/admin data never lives here."""
    return get("MASTER_DATABASE", "smartmentor_master")


def _base_url():
    """SQLAlchemy URL of the database server (database part replaced per use)."""
    from sqlalchemy.engine import URL, make_url

    override = get("DATABASE_URL")
    if override:
        return make_url(override)
    return URL.create(
        "mysql+pymysql",
        username=mysql_user(),
        password=mysql_password(),
        host=mysql_host(),
        database=mysql_database(),
    )


def _url_for_database(name):
    """Same server as the base URL but a different database. For SQLite
    (used by the tests) every database is a sibling file: <stem>_<name>.db"""
    url = _base_url()
    if url.drivername.startswith("sqlite"):
        base = url.database
        if not base or base == ":memory:":
            raise MissingSettingError(
                "DATABASE_URL must point at a SQLite file (not :memory:) "
                "because every college has its own database."
            )
        stem, ext = os.path.splitext(base)
        return url.set(database=f"{stem}_{name}{ext or '.db'}")
    return url.set(database=name)


def master_uri():
    return _url_for_database(master_database()).render_as_string(hide_password=False)


def college_uri(db_name):
    return _url_for_database(db_name).render_as_string(hide_password=False)


def legacy_college_uri():
    """URI of the old single-college database ("collegedb"), if any."""
    return college_uri(mysql_database())


def sqlalchemy_uri():
    """Default URI handed to Flask-SQLAlchemy. Real queries are routed to the
    logged-in college's database (shared/colleges.py), so this only has to be
    a valid URL; it points at the registry database."""
    return master_uri()


def mysql_connect_kwargs(with_database=True):
    kwargs = {"host": mysql_host(), "user": mysql_user(), "password": mysql_password()}
    if with_database:
        kwargs["database"] = mysql_database()
    return kwargs


# ---- College structure and academic rules ---------------------------------
def _csv_setting(name, default):
    raw = get(name, default)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def departments():
    """Department codes offered by the college (DEPARTMENTS, comma separated)."""
    return _csv_setting("DEPARTMENTS", "CSE,IT,AIDS,ECE,EEE,MECH,CIVIL")


def sections():
    """Section letters used inside a department/year (SECTIONS)."""
    return _csv_setting("SECTIONS", "A,B,C,D")


def max_year():
    """Length of the degree in years (4 for B.E./B.Tech)."""
    return int(get("MAX_YEAR", "4"))


def pass_mark():
    """Minimum marks (out of 100) needed to pass a course."""
    return int(get("PASS_MARK", "50"))


def min_attendance():
    """Minimum attendance percentage before a student is flagged (shortage)."""
    return int(get("MIN_ATTENDANCE", "75"))


# ---- Flask ------------------------------------------------------------
def secret_key(side):
    """side is 'teacher', 'management' or 'student' -> TEACHER_SECRET_KEY / ..."""
    return get(f"{side.upper()}_SECRET_KEY", required=True)


def remember_days():
    """How long "Remember me" keeps someone logged in (REMEMBER_DAYS, default 7)."""
    return max(1, int(get("REMEMBER_DAYS", "7")))


def csrf_enabled():
    """CSRF protection is always on; CSRF_DISABLED=1 exists only for automated tests."""
    return get("CSRF_DISABLED", "0").lower() not in ("1", "true", "yes", "on")


def cookie_secure():
    """Set SESSION_COOKIE_SECURE=1 when the site is served over HTTPS (recommended in production)."""
    return get("SESSION_COOKIE_SECURE", "0").lower() in ("1", "true", "yes", "on")


def debug_enabled():
    return get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes", "on")


def port(side, default):
    return int(get(f"{side.upper()}_PORT", default))


# ---- AI ---------------------------------------------------------------
def gemini_api_key():
    return get("GEMINI_API_KEY", required=True)


# ---- Email (Gmail app passwords) -------------------------------------
def administrator1():
    return get("ADMIN1_EMAIL", required=True)


def administrator2():
    return get("ADMIN2_EMAIL", required=True)


def email_credentials():
    """{email: app_password} for the two administrator sender accounts."""
    return {
        administrator1(): get("ADMIN1_APP_PASSWORD", required=True),
        administrator2(): get("ADMIN2_APP_PASSWORD", required=True),
    }


def app_password_for(address):
    return email_credentials().get(address)
