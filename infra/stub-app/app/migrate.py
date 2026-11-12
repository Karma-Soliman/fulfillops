import os

import psycopg


def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)"
        )


if __name__ == "__main__":
    main()
