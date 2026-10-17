
import pytest

from app.database import get_connection, initialize_database
import app.database as database
from app.registry import execute_tool


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    test_database = tmp_path / "idempotency.db"
    monkeypatch.setattr(database, "DATABASE_PATH", test_database)
    initialize_database()


def test_retry_does_not_create_duplicate_ticket(isolated_database):
    arguments = {
        "customer_id": "C-200",
        "subject": "Account access issue",
        "description": "Unable to log in to my customer account.",
    }

    first = execute_tool(
        "create_support_ticket",
        arguments,
        idempotency_key="ticket-request-001",
    )
    second = execute_tool(
        "create_support_ticket",
        arguments,
        idempotency_key="ticket-request-001",
    )

    assert first["result"]["ticket_id"] == second["result"]["ticket_id"]
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True

    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert count == 1


def test_key_cannot_be_reused_with_different_arguments(isolated_database):
    execute_tool(
        "create_support_ticket",
        {
            "customer_id": "C-201",
            "subject": "Account access issue",
            "description": "Unable to log in to my customer account.",
        },
        idempotency_key="ticket-request-002",
    )

    with pytest.raises(ValueError, match="different request"):
        execute_tool(
            "create_support_ticket",
            {
                "customer_id": "C-202",
                "subject": "Payment issue",
                "description": "My payment was processed but not reflected.",
            },
            idempotency_key="ticket-request-002",
        )

    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert count == 1
