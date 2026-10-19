
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_list_tools_returns_registered_tools():
    response = client.get("/tools")

    assert response.status_code == 200

    names = {
        tool["name"]
        for tool in response.json()["tools"]
    }

    assert names == {
        "check_order_status",
        "get_business_hours",
        "create_support_ticket",
        "book_demo",
    }


def test_execute_order_status_through_api():
    response = client.post(
        "/tools/execute",
        json={
            "tool_name": "check_order_status",
            "arguments": {"order_id": "ORD-1001"},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["result"]["status"] == "Processing"


def test_invalid_tool_arguments_return_422():
    response = client.post(
        "/tools/execute",
        json={
            "tool_name": "check_order_status",
            "arguments": {"order_id": "INVALID"},
        },
    )

    assert response.status_code == 422


def test_unknown_tool_returns_400():
    response = client.post(
        "/tools/execute",
        json={
            "tool_name": "delete_database",
            "arguments": {},
        },
    )

    assert response.status_code == 400


def test_unexpected_tool_error_does_not_leak_internal_details(monkeypatch):
    import app.main as main

    def crash_tool(*args, **kwargs):
        raise RuntimeError("SECRET_DATABASE_PASSWORD")

    monkeypatch.setattr(main, "execute_tool", crash_tool)

    response = client.post(
        "/tools/execute",
        json={
            "tool_name": "check_order_status",
            "arguments": {"order_id": "ORD-1001"},
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Tool execution failed."
    assert "SECRET_DATABASE_PASSWORD" not in response.text
