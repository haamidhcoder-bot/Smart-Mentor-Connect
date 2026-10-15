from datetime import date
from calendar import monthrange

from flask import Blueprint, redirect, render_template, request, url_for

from shared import login_required
from shared.services import student_service as svc
from .home import current_student

attendance_bp = Blueprint("attendance", __name__)


@attendance_bp.route("/attendance", endpoint="attendance")
@login_required
def attendance():
    student = current_student()
    if student is None:
        return redirect(url_for("auth.login_page"))

    today = date.today()
    try:
        year, month = [int(p) for p in request.args.get("month", "").split("-")]
        date(year, month, 1)
    except ValueError:
        year, month = today.year, today.month

    by_day, counts = svc.attendance_month(student.roll_no, year, month)
    first_weekday = date(year, month, 1).weekday()        # Monday = 0
    days_in_month = monthrange(year, month)[1]
    cells = [None] * first_weekday + list(range(1, days_in_month + 1))
    while len(cells) % 7:
        cells.append(None)

    total_counts, marked, pct = svc.attendance_overall(student.roll_no)
    return render_template(
        "attendance.html",
        student=student,
        month_value=f"{year:04d}-{month:02d}",
        month_label=date(year, month, 1).strftime("%B %Y"),
        weeks=[cells[i:i + 7] for i in range(0, len(cells), 7)],
        by_day=by_day,
        counts=counts,
        total_counts=total_counts,
        marked=marked,
        pct=pct,
    )
