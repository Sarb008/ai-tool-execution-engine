
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import gemini_agent


def make_response(text=None, function_call=None):
    parts = []
    if function_call is not None:
        parts.append(SimpleNamespace(function_call=function_call))

    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=parts)
    )

    return SimpleNamespace(
        candidates=[candidate],
        text=text,
    )


def test_build_function_declarations_contains_all_tools():
    declarations = gemini_agent.build_function_declarations()

    names = {item["name"] for item in declarations}

    assert names == {
        "check_order_status",
        "get_business_hours",
        "create_support_ticket",
        "book_demo",
    }

    order_tool = next(
        item for item in declarations
        if item["name"] == "check_order_status"
    )
    assert "order_id" in order_tool["parameters"]["properties"]


def test_empty_prompt_is_rejected():
    with pytest.raises(ValueError, match="Prompt must not be empty"):
        gemini_agent.process_user_request("   ")


def test_process_request_executes_registered_tool(monkeypatch):
    function_call = SimpleNamespace(
        name="check_order_status",
        args={"order_id": "ORD-1002"},
        id="call-123",
    )

    first_response = make_response(function_call=function_call)
    final_response = make_response(
        text="Order ORD-1002 has shipped."
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        first_response,
        final_response,
    ]

    monkeypatch.setattr(gemini_agent, "_client", mock_client)

    expected_execution = {
        "tool_name": "check_order_status",
        "status": "success",
        "result": {
            "found": True,
            "order_id": "ORD-1002",
            "status": "Shipped",
        },
    }

    execute_mock = MagicMock(return_value=expected_execution)
    monkeypatch.setattr(gemini_agent, "execute_tool", execute_mock)

    result = gemini_agent.process_user_request(
        "Check order ORD-1002"
    )

    execute_mock.assert_called_once_with(
        "check_order_status",
        {"order_id": "ORD-1002"},
        idempotency_key=None,
    )

    assert result["status"] == "tool_executed"
    assert result["tool_name"] == "check_order_status"
    assert result["tool_result"]["success"] is True
    assert result["answer"] == "Order ORD-1002 has shipped."
    assert mock_client.models.generate_content.call_count == 2


def test_process_request_returns_direct_answer_without_tool(monkeypatch):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = make_response(
        text="Hello! How can I help?"
    )

    monkeypatch.setattr(gemini_agent, "_client", mock_client)

    execute_mock = MagicMock()
    monkeypatch.setattr(gemini_agent, "execute_tool", execute_mock)

    result = gemini_agent.process_user_request("Say hello")

    assert result["status"] == "answered"
    assert result["tool_name"] is None
    assert result["tool_result"] is None
    assert result["answer"] == "Hello! How can I help?"

    execute_mock.assert_not_called()
    mock_client.models.generate_content.assert_called_once()
