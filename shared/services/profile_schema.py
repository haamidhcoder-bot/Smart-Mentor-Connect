from sqlalchemy import text


def ensure_profile_columns(engine):
    """Add the profile name column to an existing college database if it is
    missing. ``engine`` is that college's SQLAlchemy engine."""
    if engine.dialect.name != "mysql":
        return  # uses information_schema; tables come from db.create_all()

    statements = [
        ("teachers", "name", "ALTER TABLE teachers ADD COLUMN name VARCHAR(100) NULL"),
        ("Admin", "name", "ALTER TABLE Admin ADD COLUMN name VARCHAR(100) NULL"),
        ("Admin", "face_id", "ALTER TABLE Admin ADD COLUMN face_id VARCHAR(200) NULL"),
    ]

    with engine.begin() as conn:
        _apply(conn, statements)


def _apply(conn, statements):
    for table_name, column_name, alter_sql in statements:
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar()

        if not exists:
            conn.execute(text(alter_sql))
