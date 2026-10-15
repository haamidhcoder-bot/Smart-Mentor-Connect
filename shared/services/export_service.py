import csv
import io
import mysql.connector as sql
from datetime import datetime

from shared import settings

def connect():
    cn= sql.connect(**settings.mysql_connect_kwargs())

    cur=cn.cursor()

    return cn,cur

def export_csv(class_value:int, sec:str):
    cn, cur = connect()

    try:
        cur.execute(
            "SELECT * FROM students WHERE class=%s AND section=%s",
            (class_value, sec)
        )

        output = io.StringIO()
        csv_writer = csv.writer(output)

        csv_writer.writerow(
            [
                "student_name",
                "student_gmail",
                "DOB",
                "mobile_no",
            ]
        )

        for row in cur.fetchall():
            csv_writer.writerow(
                [
                    row[1],
                    row[4],
                    row[5],
                    row[6],
                ]
            )
    finally:
        cur.close()
        cn.close()

    return output.getvalue()

SECTION_CODES = {"A": 1, "B": 2, "C": 3}


def import_csv(file, class_value:int, sec:str):
    cn, cur = connect()

    reader = csv.reader(io.TextIOWrapper(file, encoding="utf-8-sig"))

    # Skip the header row
    next(reader, None)

    cur.execute("DELETE FROM students WHERE class = %s", (class_value,))

    added = 0
    pending = []
    used_roll_numbers = set()

    try:
        for row in reader:
            row = [c.strip() for c in row]

            if not row:
                continue

            if not any(row):
                continue

            student_name = row[0].strip() if len(row) > 0 else ""

            student_gmail = (
                row[1].strip()
                if len(row) > 1 and row[1]
                else None
            )

            dob = (
                row[2].strip()
                if len(row) > 2 and row[2]
                else None
            )

            mobile_no = (
                row[3].strip()
                if len(row) > 3 and row[3]
                else None
            )

            if dob:
                try:
                    dob = datetime.strptime(dob, "%Y-%m-%d").date()

                except ValueError:
                    try:
                        dob = datetime.strptime(dob, "%d/%m/%Y").date()

                    except ValueError:
                        raise ValueError(
                            f"Invalid date '{dob}'. "
                            "Use YYYY-MM-DD or DD/MM/YYYY."
                        )

            row_class=class_value
            row_section=sec

            pending.append(
                (
                    student_name,
                    row_class,
                    row_section,
                    student_gmail,
                    dob,
                    mobile_no,
                )
            )

            added += 1

        groups = {}

        for student_name, row_class, row_section, student_gmail, dob, mobile_no in pending:
            groups.setdefault((row_class, row_section), []).append(
                (student_name, student_gmail, dob, mobile_no)
            )

        for (row_class, row_section), rows in groups.items():

            class_int = int(row_class)

            if row_section not in SECTION_CODES:
                raise ValueError(
                    f"'{row_section}' is not a valid section."
                )

            roll_prefix = class_int * 1000 + SECTION_CODES[row_section] * 100

            cur.execute(
                """
                SELECT roll_no
                FROM students
                WHERE class=%s AND section=%s
                """,
                (class_int, row_section)
            )

            used_roll_numbers.update(r[0] for r in cur.fetchall())

            next_roll_no = roll_prefix + 1

            while next_roll_no in used_roll_numbers:
                next_roll_no += 1

            rows.sort(key=lambda x: x[0].lower())

            for student_name, student_gmail, dob, mobile_no in rows:

                if next_roll_no > roll_prefix + 99:
                    raise ValueError(
                        f"No more roll numbers available for Class {row_class}-{row_section}."
                    )

                cur.execute(
                    """
                    INSERT INTO students
                    (roll_no, student_name, class, section,
                     student_gmail, DOB, mobile_no)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (next_roll_no, student_name, class_int,
                     row_section, student_gmail, dob, mobile_no)
                )

                used_roll_numbers.add(next_roll_no)
                added += 1

                next_roll_no += 1

                while next_roll_no in used_roll_numbers:
                    next_roll_no += 1

        cn.commit()
        return added

    except Exception:
        cn.rollback()
        raise

    finally:
        cur.close()
        cn.close()

def promote():
    cn, cur = connect()

    try:
        cur.execute("SELECT COUNT(*) FROM students WHERE class = 12")
        graduated = cur.fetchone()[0]

        cur.execute("SELECT * FROM students WHERE class = 12")

        data=cur.fetchall()

        year = datetime.now().year

        with open(f"Recycle_bin({year-1}-{year}).csv", "w", newline="") as f:
            f_write = csv.writer(f)
            f_write.writerows(data)
            

        cur.execute("DELETE FROM students WHERE class = 12")

        promoted = 0
        for cls in range(11, 0, -1):
            cur.execute("DELETE FROM marks WHERE class = %s", (cls,))
            cur.execute(
                """
                UPDATE students
                SET class = class + 1, roll_no = roll_no + 1000
                WHERE class = %s
                """,
                (cls,)
            )
            promoted += cur.rowcount

        cn.commit()
        return {"graduated": graduated, "promoted": promoted}
    except Exception:
        cn.rollback()
        raise
    finally:
        cur.close()
        cn.close()