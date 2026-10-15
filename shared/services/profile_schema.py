from sqlalchemy import text


def ensure_profile_columns(db):
    """Add the profile name column to existing databases if it is missing."""
    if db.engine.dialect.name != "mysql":
        return  # uses information_schema; tables come from db.create_all()

    statements = [
        ("teachers", "name", "ALTER TABLE teachers ADD COLUMN name VARCHAR(100) NULL"),
        ("Admin", "name", "ALTER TABLE Admin ADD COLUMN name VARCHAR(100) NULL"),
        ("Admin", "face_id", "ALTER TABLE Admin ADD COLUMN face_id VARCHAR(200) NULL"),
    ]

    for table_name, column_name, alter_sql in statements:
        exists = db.session.execute(
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
            db.session.execute(text(alter_sql))

    db.session.commit()
