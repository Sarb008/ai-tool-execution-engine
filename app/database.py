
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


            CREATE TABLE IF NOT EXISTS assistant_request_records (
                idempotency_key TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('in_progress', 'completed')),
                response_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );


            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'New chat',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
            ON chat_messages(conversation_id, id);

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


def get_tool_executions(limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent tool execution records."""

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                tool_name,
                input_json,
                output_json,
                status,
                duration_ms,
                error_message,
                created_at
            FROM tool_executions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    executions = []

    for row in rows:
        execution = dict(row)

        # Convert stored JSON strings into normal Python objects.
        for column in ("input_json", "output_json"):
            value = execution.pop(column)
            try:
                execution[column.removesuffix("_json")] = (
                    json.loads(value) if value is not None else None
                )
            except (json.JSONDecodeError, TypeError):
                execution[column.removesuffix("_json")] = value

        executions.append(execution)

    return executions

def create_conversation() -> dict[str, Any]:
    """Create and return a new conversation."""

    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO conversations DEFAULT VALUES"
        )
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return dict(row)


def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent conversations, newest activity first."""

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_conversation(
    conversation_id: int,
) -> dict[str, Any] | None:
    """Return a conversation and its messages, or None if not found."""

    with get_connection() as connection:
        conversation_row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()

        if conversation_row is None:
            return None

        message_rows = connection.execute(
            """
            SELECT id, role, content, details_json, created_at
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

    messages = []

    for row in message_rows:
        message = dict(row)
        details_json = message.pop("details_json")

        try:
            message["details"] = (
                json.loads(details_json)
                if details_json is not None
                else None
            )
        except (json.JSONDecodeError, TypeError):
            message["details"] = None

        messages.append(message)

    conversation = dict(conversation_row)
    conversation["messages"] = messages
    return conversation


def add_chat_message(
    conversation_id: int,
    role: str,
    content: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save one message and update the conversation's activity."""

    if role not in {"user", "assistant"}:
        raise ValueError("role must be 'user' or 'assistant'")

    details_json = (
        json.dumps(details, sort_keys=True, default=str)
        if details is not None
        else None
    )

    with get_connection() as connection:
        conversation = connection.execute(
            "SELECT id, title FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

        if conversation is None:
            raise ValueError("Conversation not found")

        cursor = connection.execute(
            """
            INSERT INTO chat_messages (
                conversation_id, role, content, details_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, role, content, details_json),
        )

        if role == "user" and conversation["title"] == "New chat":
            title = " ".join(content.split())[:60] or "New chat"
            connection.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (title, conversation_id),
            )
        else:
            connection.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (conversation_id,),
            )

        row = connection.execute(
            """
            SELECT id, conversation_id, role, content,
                   details_json, created_at
            FROM chat_messages
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    message = dict(row)
    message.pop("details_json")
    message["details"] = details
    return message


def claim_assistant_request(
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    """Claim a new request, or report its existing state."""

    with get_connection() as connection:
        # Serialize claims so concurrent requests cannot both win.
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT request_hash, status, response_json
            FROM assistant_request_records
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()

        if row is None:
            connection.execute(
                """
                INSERT INTO assistant_request_records (
                    idempotency_key, request_hash, status
                )
                VALUES (?, ?, 'in_progress')
                """,
                (idempotency_key, request_hash),
            )
            return {"status": "claimed"}

        if row["request_hash"] != request_hash:
            return {"status": "conflict"}

        if row["status"] == "completed":
            return {
                "status": "replay",
                "response": json.loads(row["response_json"]),
            }

        return {"status": "in_progress"}


def complete_assistant_request(
    idempotency_key: str,
    response: dict[str, Any],
) -> None:
    """Store the response for future retries."""

    response_json = json.dumps(
        response,
        sort_keys=True,
        default=str,
    )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE assistant_request_records
            SET status = 'completed', response_json = ?
            WHERE idempotency_key = ? AND status = 'in_progress'
            """,
            (response_json, idempotency_key),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "Could not complete the assistant request record."
            )


def release_assistant_request(idempotency_key: str) -> None:
    """Remove an unfinished claim after a failed request."""

    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM assistant_request_records
            WHERE idempotency_key = ? AND status = 'in_progress'
            """,
            (idempotency_key,),
        )
