"""Manual, DESTRUCTIVE helper: (re)creates the schooldb database from
sample_data/school_database_schema.sql.

The apps no longer call this automatically - they create any missing
database/tables on startup without touching existing data. Only run this if
you really want an empty, fresh database:

    python create_databases.py --yes
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import settings


def create_database():
    import mysql.connector as sql

    schema_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "sample_data",
        "school_database_schema.sql",
    )
    with open(schema_path, encoding="utf-8") as f:
        data = f.read()

    conn = sql.connect(**settings.mysql_connect_kwargs(with_database=False))
    try:
        cur = conn.cursor()
        for statement in (s.strip() for s in data.split(";")):
            if statement:
                cur.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        sys.exit("This DROPS and recreates schooldb. Re-run with --yes to confirm.")
    create_database()
    print("schooldb recreated (empty).")
