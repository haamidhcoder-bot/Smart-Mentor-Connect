import re

from google import genai
from flask import session
from sqlalchemy import text

from shared import settings
from shared.extensions import db


_client = None


def _get_client():
    """Create the Gemini client on first use, so the app can start (and the
    GEMINI_API_KEY variable is only required) until the AI feature is used."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key())
    return _client


SCHEMA = """
students
(
    roll_no,          -- text, e.g. '21CS001'
    student_name,
    department,       -- e.g. 'CSE', 'ECE'
    year,             -- year of study, 1-4
    section,
    student_gmail,
    DOB,
    mobile_no
)

marks
(
    roll_no,
    year,
    exam_id,
    subject,          -- course code, joins to courses.code
    marks             -- out of 100, 0 means not entered yet
)

courses
(
    code,
    name,
    department,       -- 'ALL' = common to every department
    semester,         -- 1-8
    credits
)

attendance
(
    id,
    roll_no,
    department,
    year,
    section,
    date,
    status            -- 'present', 'absent' or 'leave'
)

exams
(
    exam_id,
    exam_name,        -- e.g. 'Sem 3 - Internal 1'
    semester
)
"""


FORBIDDEN = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE"
]


def generate_sql(question):

    teacher_dept = session.get("advisor_dept")
    teacher_year = session.get("advisor_year")
    teacher_section = session.get("advisor_section")

    pass_mark = settings.pass_mark()
    min_attendance = settings.min_attendance()

    prompt = f"""
You are a MySQL expert for an engineering college database.

Database schema:

{SCHEMA}

The logged-in teacher is the class advisor of:

Department: {teacher_dept}
Year: {teacher_year}
Section: {teacher_section}

Rules:

1. Generate ONLY SELECT queries.

2. Never generate INSERT, UPDATE, DELETE,
DROP, ALTER, TRUNCATE or CREATE statements.

3. If the user does not specify a department,
assume department = '{teacher_dept}'.

4. If the user does not specify a year,
assume year = {teacher_year}.

5. If the user does not specify a section,
assume section = '{teacher_section}'.

6. A mark of 0 means "not entered yet"; ignore those rows when
averaging. Pass mark is {pass_mark} out of 100. A student is short
of attendance when present days / marked days is below
{min_attendance} percent.

7. Return ONLY SQL.

Question:

{question}
"""

    response = _get_client().models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    sql = response.text.strip()

    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")

    return sql.strip()


def validate_sql(sql):

    upper_sql = sql.upper()

    if not upper_sql.startswith("SELECT"):
        return False

    for keyword in FORBIDDEN:

        if re.search(rf"\b{keyword}\b", upper_sql):
            return False

    return True


def ask_ai(question):

    try:

        sql = generate_sql(question)

        print("Generated SQL:")
        print(sql)

        if not validate_sql(sql):
            return "Invalid query."

        result = db.session.execute(
            text(sql)
        )

        rows = result.mappings().all()

        rows = [dict(row) for row in rows]

        if not rows:
            return "No matching records were found."

        response = _get_client().models.generate_content(
            model="gemini-3.6-flash",
            contents=f"""
Question:

{question}

Database result:

{rows}

Answer the question naturally.
"""
        )

        return response.text

    except Exception as e:

        print(e)

        return f"Error: {e}"