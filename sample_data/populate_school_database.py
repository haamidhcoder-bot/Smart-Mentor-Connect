try:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from datetime import date, timedelta
    import random
    from shared import settings
    import mysql.connector as sql
    from person_names_720 import person_names
    import bcrypt as bp

    # -------------------------
    # Database Configuration
    # -------------------------
    DB_CONFIG = settings.mysql_connect_kwargs(with_database=False)

    conn = sql.connect(**DB_CONFIG)
    cur = conn.cursor()

    import os

    schema_path = os.path.join(
        os.path.dirname(__file__),
        "school_database_schema.sql"
    )

    with open(schema_path) as f:
        data = f.read()

    statements = [stmt.strip() for stmt in data.split(";") if stmt.strip()]
    for statement in statements:
        cur.execute(statement)

    cur.execute(f"use {settings.mysql_database()}")

    # -------------------------
    # Exams
    # -------------------------
    exam_names = [
        "Unit Test 1",
        "Unit Test 2",
        "Quarterly Exam",
        "Half Yearly Exam",
        "Annual Exam"
    ]

    cur.executemany(
        """
        INSERT INTO exams(exam_name)
        VALUES(%s)
        """,
        [(exam,) for exam in exam_names]
    )

    conn.commit()

    # -------------------------
    # Get Exam IDs
    # -------------------------
    cur.execute("SELECT exam_id, exam_name FROM exams")

    exam_ids = {}

    for exam_id, exam_name in cur.fetchall():
        exam_ids[exam_name] = exam_id

    # -------------------------
    # Subjects
    # -------------------------
    subjects_1_10 = [
        "English",
        "Maths",
        "Science",
        "Social",
        "Tamil"
    ]

    subjects_11_12 = [
        "English",
        "Maths",
        "Physics",
        "Chemistry",
        "Computer"
    ]

    # -------------------------
    # Students
    # -------------------------

    sections = {
        "A":1,
        "B":2,
        "C":3
    }

    # -------------------------
    # Attendance settings
    # -------------------------
    attendance_start = date(2026, 6, 1)
    attendance_days = 20   # number of school days to generate per student

    status_choices = (
        ["present"] * 8 +
        ["absent"] +
        ["leave"]
    )

    random.shuffle(person_names)

    name_index = 0

    for cls in range(1,13):

        subjects = subjects_1_10 if cls <= 10 else subjects_11_12

        for section in sections:

            for roll in range(1,21):

                # Generate a random DOB
                start = date(2007, 1, 1)
                end = date(2019, 12, 31)
                days = (end - start).days

                dob = start + timedelta(days=random.randint(0, days))
                mobile_no = random.randint(6000000000, 9999999999)

                roll_no = int(f"{cls}{sections[section]}{roll:02d}")

                student_name = person_names[name_index]
                student_gmail=student_name.replace(" ", "")+"@gmail.com"
                name_index += 1

                cur.execute(
                    """
                    INSERT INTO students
                    (roll_no, student_name, class, section, student_gmail, DOB, mobile_no)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        roll_no,
                        student_name,
                        cls,
                        section,
                        student_gmail,
                        dob,
                        mobile_no
                    )
                )

                # -------------------------
                # Marks
                # -------------------------

                for exam in exam_names:

                    exam_id = exam_ids[exam]

                    for subject in subjects:
                        mark=random.randint(1,100)
                        cur.execute(
                            """
                            INSERT INTO marks
                            (roll_no,class,exam_id,subject,marks)
                            VALUES(%s,%s,%s,%s,%s)
                            """,
                            (
                                roll_no,
                                cls,
                                exam_id,
                                subject,
                                mark
                            )
                        )

                # -------------------------
                # Attendance
                # -------------------------

                for day_offset in range(attendance_days):
                    att_date = attendance_start + timedelta(days=day_offset)
                    status = random.choice(status_choices)

                    cur.execute(
                        """
                        INSERT INTO attendance
                        (roll_no, class_value, section, date, status, marked_by)
                        VALUES(%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            roll_no,
                            cls,
                            section,
                            att_date,
                            status,
                            "admin@school.com"
                        )
                    )

    password=bp.hashpw("pass@123".encode(), bp.gensalt()).decode("utf-8")
    cur.execute("INSERT INTO Admin (Gmail, name, password) VALUES('haamidh@gmail.com','Mohammed Hashim',%s)",(password,))

    conn.commit()
    conn.close()

    print("Database populated successfully!")

except Exception as e:
    print(f"ERROR:{e}")