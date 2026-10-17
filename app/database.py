
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", "ai_tool_engine.db")
)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Open a database connection and always close it."""

    connection = sqlite3.connect(DATABASE_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    """Create the required tables if they do not exist."""

    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS demo_bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                requested_day TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tool_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT,
                status TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS idempotency_records (
                idempotency_key TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                output_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            """
        )


def record_tool_execution(
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    duration_ms: float,
    output: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Persist one tool execution attempt."""

    input_json = json.dumps(
        arguments,
        sort_keys=True,
        default=str,
    )

    output_json = (
        json.dumps(output, sort_keys=True, default=str)
        if output is not None
        else None
    )

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO tool_executions (
                tool_name,
                input_json,
                output_json,
                status,
                duration_ms,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tool_name,
                input_json,
                output_json,
                status,
                duration_ms,
                error_message,
            ),
        )
