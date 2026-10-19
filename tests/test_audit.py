
import json

import pytest

import app.database as database
from app.database import get_connection, initialize_database
from app.registry import execute_tool


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    test_database = tmp_path / "test_engine.db"
    monkeypatch.setattr(database, "DATABASE_PATH", test_database)
    initialize_database()


def test_successful_execution_is_audited(isolated_database):
    result = execute_tool(
        "check_order_status",
        {"order_id": "ORD-1001"},
    )

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM tool_executions ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert row["status"] == "success"
    assert row["tool_name"] == "check_order_status"
    assert json.loads(row["input_json"]) == {"order_id": "ORD-1001"}
    assert json.loads(row["output_json"]) == result["result"]


def test_invalid_arguments_are_audited(isolated_database):
    with pytest.raises(Exception):
        execute_tool("check_order_status", {"order_id": "INVALID"})

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM tool_executions ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert row["status"] == "failed"
    assert "ValidationError" in row["error_message"]


def test_failure_audit_does_not_store_sensitive_exception_details(
    isolated_database, monkeypatch
):
    import app.registry as registry

    secret = "SECRET_DATABASE_PASSWORD"

    def crash_handler(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setitem(
        registry.TOOL_HANDLERS,
        "check_order_status",
        crash_handler,
    )

    with pytest.raises(RuntimeError):
        execute_tool(
            "check_order_status",
            {"order_id": "ORD-1001"},
        )

    with get_connection() as connection:
        row = connection.execute(
            "SELECT error_message FROM tool_executions "
            "WHERE status = 'failed' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert row is not None
    assert secret not in row["error_message"]
