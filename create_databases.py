"""Manual, NON-destructive helper: registers a new, empty college.

    python create_databases.py "My College Name"

Every college has its own database. This creates the registry (if needed),
adds the college to it and creates its own database with all tables. Nothing
is ever dropped. People can also register a college from the management
side's Register page, which does the same thing.

The apps also create/upgrade the registry and each college's tables
themselves, so you normally never need this script.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import colleges


def main(argv):
    if len(argv) != 2 or argv[1].startswith("-"):
        sys.exit('Usage: python create_databases.py "College name"')
    colleges.init_registry()
    try:
        info = colleges.create_college(argv[1])
    except colleges.CollegeError as e:
        sys.exit(str(e))
    print(f"College '{info.name}' created (database: {info.db_name}).")
    print("Register its first administrator on the management side's Register page.")


if __name__ == "__main__":
    main(sys.argv)
