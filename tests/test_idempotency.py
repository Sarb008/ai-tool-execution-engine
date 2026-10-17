
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


def test_failed_idempotency_record_does_not_create_ticket(
    isolated_database,
    monkeypatch,
):
    import app.registry as registry

    arguments = {
        "customer_id": "C-203",
        "subject": "Account access issue",
        "description": "Unable to log in to my customer account.",
    }

    def fail_idempotency_insert(*args, **kwargs):
        raise RuntimeError("Simulated idempotency storage failure")

    monkeypatch.setattr(
        registry,
        "execute_idempotency_record",
        fail_idempotency_insert,
    )

    with pytest.raises(RuntimeError, match="Simulated idempotency"):
        execute_tool(
            "create_support_ticket",
            arguments,
            idempotency_key="ticket-failure-001",
        )

    with get_connection() as connection:
        ticket_count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert ticket_count == 0


def test_concurrent_retries_create_only_one_ticket(isolated_database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    arguments = {
        "customer_id": "C-204",
        "subject": "Concurrent retry test",
        "description": "Verify that concurrent requests do not create duplicates.",
    }
    start_together = Barrier(2)

    def submit_request():
        start_together.wait(timeout=5)
        return execute_tool(
            "create_support_ticket",
            arguments,
            idempotency_key="ticket-concurrent-001",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(submit_request)
        second_future = executor.submit(submit_request)
        first = first_future.result(timeout=10)
        second = second_future.result(timeout=10)

    assert first["result"]["ticket_id"] == second["result"]["ticket_id"]
    assert sorted([
        first["idempotent_replay"],
        second["idempotent_replay"],
    ]) == [False, True]

    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM support_tickets"
        ).fetchone()[0]

    assert count == 1
