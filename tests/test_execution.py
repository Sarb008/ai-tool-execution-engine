
import pytest
from pydantic import ValidationError

from app.registry import execute_tool


def test_order_status_tool_executes_successfully() -> None:
    result = execute_tool(
        "check_order_status",
        {"order_id": "ORD-1001"},
    )

    assert result["status"] == "success"
    assert result["tool_name"] == "check_order_status"
    assert result["result"]["found"] is True
    assert result["result"]["status"] == "Processing"
    assert result["duration_ms"] >= 0


def test_business_hours_tool_executes_successfully() -> None:
    result = execute_tool(
        "get_business_hours",
        {"day": "Monday"},
    )

    assert result["status"] == "success"
    assert result["result"]["hours"] == "09:00–17:00"


def test_invalid_arguments_never_reach_execution() -> None:
    with pytest.raises(ValidationError):
        execute_tool(
            "check_order_status",
            {"order_id": "INVALID"},
        )


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        execute_tool("delete_database", {})
