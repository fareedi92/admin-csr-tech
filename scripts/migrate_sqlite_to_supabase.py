#!/usr/bin/env python3
"""Migrate all data from the local SQLite database to Supabase PostgreSQL."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BASE_DIR / "schema" / "supabase_schema.sql"
DEFAULT_SQLITE_PATH = BASE_DIR / "instance" / "users.db"

TABLES_IN_ORDER = [
    "users",
    "admin_accounts",
    "tech_team_accounts",
    "ticket_statuses",
    "chat_conversations",
    "chat_assignment_events",
    "chat_messages",
    "tickets",
    "ticket_status_logs",
    "ticket_messages",
]

BOOLEAN_COLUMNS = {
    "users": {"is_active", "is_available", "unlimited_chats"},
    "tech_team_accounts": {"is_active"},
    "ticket_statuses": {"is_default", "is_resolved"},
}


def build_postgres_uri() -> str:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    db_password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    if not supabase_url or not db_password:
        raise RuntimeError("Set DATABASE_URL or SUPABASE_URL + SUPABASE_DB_PASSWORD in .env")

    project_ref = supabase_url.replace("https://", "").split(".")[0]
    encoded_password = quote_plus(db_password)
    pooler_host = os.environ.get("SUPABASE_POOLER_HOST", "").strip()
    if pooler_host:
        return (
            f"postgresql://postgres.{project_ref}:{encoded_password}"
            f"@{pooler_host}:6543/postgres"
        )
    return f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"


def sqlite_path() -> Path:
    configured = os.environ.get("SQLITE_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_SQLITE_PATH


def fetch_sqlite_rows(connection: sqlite3.Connection, table_name: str) -> tuple[list[str], list[tuple]]:
    cursor = connection.execute(f"SELECT * FROM {table_name}")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    return columns, rows


def apply_schema(engine) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [statement.strip() for statement in schema_sql.split(";") if statement.strip()]
    with engine.begin() as connection:
        for statement in statements:
            if statement.upper() in {"BEGIN", "COMMIT"}:
                continue
            connection.execute(text(statement))


def normalize_row(table_name: str, columns: list[str], row: tuple) -> dict:
    boolean_columns = BOOLEAN_COLUMNS.get(table_name, set())
    normalized = {}
    for column, value in zip(columns, row):
        if column in boolean_columns and value is not None:
            normalized[column] = bool(value)
        else:
            normalized[column] = value
    return normalized


def insert_rows(engine, table_name: str, columns: list[str], rows: list[tuple]) -> int:
    if not rows:
        return 0

    column_list = ", ".join(columns)
    placeholders = ", ".join(f":{column}" for column in columns)
    insert_sql = text(f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})")

    payload = [normalize_row(table_name, columns, row) for row in rows]
    with engine.begin() as connection:
        connection.execute(insert_sql, payload)
    return len(rows)


def reset_sequences(engine) -> None:
    sequence_updates = """
        SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE((SELECT MAX(id) FROM users), 1), true);
        SELECT setval(pg_get_serial_sequence('admin_accounts', 'id'), COALESCE((SELECT MAX(id) FROM admin_accounts), 1), true);
        SELECT setval(pg_get_serial_sequence('tech_team_accounts', 'id'), COALESCE((SELECT MAX(id) FROM tech_team_accounts), 1), true);
        SELECT setval(pg_get_serial_sequence('ticket_statuses', 'id'), COALESCE((SELECT MAX(id) FROM ticket_statuses), 1), true);
        SELECT setval(pg_get_serial_sequence('chat_conversations', 'id'), COALESCE((SELECT MAX(id) FROM chat_conversations), 1), true);
        SELECT setval(pg_get_serial_sequence('chat_assignment_events', 'id'), COALESCE((SELECT MAX(id) FROM chat_assignment_events), 1), true);
        SELECT setval(pg_get_serial_sequence('chat_messages', 'id'), COALESCE((SELECT MAX(id) FROM chat_messages), 1), true);
        SELECT setval(pg_get_serial_sequence('tickets', 'id'), COALESCE((SELECT MAX(id) FROM tickets), 1), true);
        SELECT setval(pg_get_serial_sequence('ticket_status_logs', 'id'), COALESCE((SELECT MAX(id) FROM ticket_status_logs), 1), true);
        SELECT setval(pg_get_serial_sequence('ticket_messages', 'id'), COALESCE((SELECT MAX(id) FROM ticket_messages), 1), true);
    """
    with engine.begin() as connection:
        for statement in sequence_updates.strip().split(";"):
            cleaned = statement.strip()
            if cleaned:
                connection.execute(text(cleaned))


def verify_counts(sqlite_connection: sqlite3.Connection, engine) -> None:
    print("\nVerification:")
    for table_name in TABLES_IN_ORDER:
        sqlite_count = sqlite_connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        with engine.connect() as connection:
            postgres_count = connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        status = "OK" if sqlite_count == postgres_count else "MISMATCH"
        print(f"  {table_name:24} sqlite={sqlite_count:4}  supabase={postgres_count:4}  [{status}]")
        if sqlite_count != postgres_count:
            raise RuntimeError(f"Row count mismatch for {table_name}")


def main() -> int:
    load_dotenv(BASE_DIR / ".env")

    sqlite_db_path = sqlite_path()
    if not sqlite_db_path.exists():
        print(f"SQLite database not found: {sqlite_db_path}")
        return 1

    postgres_uri = build_postgres_uri()
    postgres_engine = create_engine(postgres_uri, future=True)

    print(f"Source SQLite: {sqlite_db_path}")
    print(f"Target Supabase: {postgres_uri.split('@')[-1]}")
    print("Applying Supabase schema...")
    apply_schema(postgres_engine)

    sqlite_connection = sqlite3.connect(sqlite_db_path)
    sqlite_connection.row_factory = sqlite3.Row

    try:
        print("Migrating data...")
        for table_name in TABLES_IN_ORDER:
            columns, rows = fetch_sqlite_rows(sqlite_connection, table_name)
            migrated = insert_rows(postgres_engine, table_name, columns, rows)
            print(f"  {table_name:24} {migrated:4} rows")

        print("Resetting PostgreSQL ID sequences...")
        reset_sequences(postgres_engine)
        verify_counts(sqlite_connection, postgres_engine)
    finally:
        sqlite_connection.close()

    print("\nMigration completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
