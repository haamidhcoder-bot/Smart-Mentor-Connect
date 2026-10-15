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
    roll_no,
    student_name,
    class,
    section,
    student_gmail,
    DOB,
    mobile_no
)

marks
(
    roll_no,
    class,
    exam_id,
    subject,
    marks
)

attendance
(
    id,
    roll_no,
    class_value,
    section,
    date,
    status
)

exams
(
    exam_id,
    exam_name
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

    teacher_class = session.get("class_teacher")
    teacher_section = session.get("class_teacher_sec")

    prompt = f"""
You are a MySQL expert.

Database schema:

{SCHEMA}

The logged-in teacher teaches:

Class: {teacher_class}
Section: {teacher_section}

Rules:

1. Generate ONLY SELECT queries.

2. Never generate INSERT, UPDATE, DELETE,
DROP, ALTER, TRUNCATE or CREATE statements.

3. If the user does not specify a class,
assume class = {teacher_class}.

4. If the user does not specify a section,
assume section = '{teacher_section}'.

5. Return ONLY SQL.

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