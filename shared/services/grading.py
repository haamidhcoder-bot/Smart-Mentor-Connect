"""Grading rules in one place, so a college can match its own regulations.

Marks are out of 100 per course. A course is passed with PASS_MARK or more
(default 50, override with the PASS_MARK environment variable). Grades and
grade points follow a common 10-point scale; edit GRADE_SCALE to match your
university's table.
"""
import math

from shared import settings

DEFAULT_CREDITS = 3

# (minimum marks, grade, grade point), highest first.
GRADE_SCALE = [
    (90, "O", 10),
    (80, "A+", 9),
    (70, "A", 8),
    (60, "B+", 7),
    (55, "B", 6),
    (50, "C", 5),
]
PASS_GRADE = ("P", 4)   # passing marks that fall below the lowest scale row
FAIL_GRADE = ("F", 0)


def pass_mark():
    return settings.pass_mark()


def is_pass(marks):
    return marks is not None and marks >= pass_mark()


def grade_for(marks):
    """(grade, grade_point) for a mark out of 100."""
    if marks is None or marks < pass_mark():
        return FAIL_GRADE
    for minimum, grade, point in GRADE_SCALE:
        if marks >= minimum:
            return grade, point
    return PASS_GRADE


def gpa(items):
    """Credit-weighted grade point average.

    items: iterable of (marks, credits). A failed course counts with 0 grade
    points. Returns None when there are no credits.
    """
    total_credits = 0
    weighted = 0
    for marks, credits in items:
        credits = credits or DEFAULT_CREDITS
        total_credits += credits
        weighted += grade_for(marks)[1] * credits
    if not total_credits:
        return None
    return round(weighted / total_credits, 2)


def attendance_status(present, marked):
    """Attendance summary against the minimum percentage (default 75).

    Returns a dict: pct, required, shortage (bool), and either
    ``need`` (consecutive classes to attend to get back to the minimum) or
    ``can_miss`` (classes that can still be missed). pct is None when no
    attendance has been marked yet.
    """
    required = settings.min_attendance()
    if not marked:
        return {"pct": None, "required": required, "shortage": False,
                "need": 0, "can_miss": 0}
    pct = round(present / marked * 100, 1)
    ratio = required / 100
    if present / marked >= ratio:
        can_miss = max(0, math.floor(present / ratio - marked)) if ratio else 0
        return {"pct": pct, "required": required, "shortage": False,
                "need": 0, "can_miss": can_miss}
    need = math.ceil((ratio * marked - present) / (1 - ratio)) if ratio < 1 else 0
    return {"pct": pct, "required": required, "shortage": True,
            "need": need, "can_miss": 0}
