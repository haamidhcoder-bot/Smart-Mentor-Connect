"""Roll / register numbers are alphanumeric (e.g. 21CS001, 912522104001).

They are stored upper-case and may contain letters, digits, '-' and '_'
(no '/', because the number is used inside URLs).
"""
import re

_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,19}$")


def normalise(value):
    """Upper-cased roll number, or None if it is empty or not valid."""
    value = (value or "").strip().upper()
    return value if _PATTERN.match(value) else None
