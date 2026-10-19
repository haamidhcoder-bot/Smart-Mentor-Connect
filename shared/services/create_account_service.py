import re
import bcrypt as bp

from shared import db

PASSWORD_PATTERN = r"^(?=.*[0-9])(?=.*[a-z]).+$"


def create_account(
    user,
    password=None,
    confirm_password=None,
    Table=None,
    face_id=None,
    advisor_dept=None,
    advisor_year=None,
    advisor_section=None,
    password_hash=None,
):
    """
    Creates an account for any model.

    A plaintext password is accepted for normal internal account creation.
    For multi-step registration flows, pass password_hash so the plaintext
    password never needs to be placed in a URL or stored in the session.

    Returns:
        True   -> Account created successfully.
        "pass" -> Password validation failed.
        ""     -> Database error.
    """

    if password_hash is None:
        if password is None or confirm_password is None:
            return "pass"
        if password != confirm_password or not re.match(PASSWORD_PATTERN, password):
            return "pass"
        password_hash = bp.hashpw(password.encode(), bp.gensalt()).decode("utf-8")

    data = {
        "Gmail": user,
        "password": password_hash,
    }

    if Table.__name__ == "Teacher":
        data["advisor_dept"] = advisor_dept
        data["advisor_year"] = advisor_year
        data["advisor_section"] = advisor_section
        data["face_id"] = face_id

    try:
        new_user = Table(**data)
        db.session.add(new_user)
        db.session.commit()
        return True

    except Exception as e:
        db.session.rollback()
        print(f"ERROR: {e}")
        return ""
