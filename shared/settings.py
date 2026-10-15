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
    # Fixed: sample_data/school_database_schema.sql also uses this name.
    return "schooldb"


def sqlalchemy_uri():
    """DATABASE_URL overrides everything (handy for tests); otherwise the
    MySQL connection is built from the MYSQL_* variables."""
    override = get("DATABASE_URL")
    if override:
        return override
    from urllib.parse import quote_plus

    return (
        f"mysql+pymysql://{quote_plus(mysql_user())}:{quote_plus(mysql_password())}"
        f"@{mysql_host()}/{mysql_database()}"
    )


def mysql_connect_kwargs(with_database=True):
    kwargs = {"host": mysql_host(), "user": mysql_user(), "password": mysql_password()}
    if with_database:
        kwargs["database"] = mysql_database()
    return kwargs


# ---- Flask ------------------------------------------------------------
def secret_key(side):
    """side is 'teacher' or 'management' -> TEACHER_SECRET_KEY / MANAGEMENT_SECRET_KEY."""
    return get(f"{side.upper()}_SECRET_KEY", required=True)


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
