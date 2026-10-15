import re


def initials_for_name(name):
    """Return up to two initials for a profile avatar."""
    cleaned = " ".join((name or "").strip().split())
    if not cleaned:
        return ""
    parts = re.findall(r"[A-Za-z0-9]+", cleaned)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def password_bytes(password):
    """Accept password hashes stored as str or bytes and return bytes."""
    if isinstance(password, bytes):
        return password
    return (password or "").encode("utf-8")
