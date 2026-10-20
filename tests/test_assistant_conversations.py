
from fastapi.testclient import TestClient

import app.main as main
from app.main import app


def test_assistant_saves_user_and_assistant_messages(monkeypatch):
    def fake_process_user_request(prompt, idempotency_key=None):
        return {
            "status": "tool_executed",
            "tool_name": "get_business_hours",
            "tool_result": {
                "success": True,
                "result": {"hours": "09:00–17:00"},
            },
            "answer": "Business hours are 09:00–17:00.",
        }

    monkeypatch.setattr(
        main, "process_user_request", fake_process_user_request
    )

    with TestClient(app) as client:
        response = client.post(
            "/assistant",
            json={"prompt": "What are the business hours on Monday?"},
        )

        assert response.status_code == 200
        result = response.json()
        conversation_id = result["conversation_id"]

        assert result["answer"] == "Business hours are 09:00–17:00."

        reopened = client.get(f"/conversations/{conversation_id}")
        assert reopened.status_code == 200

        messages = reopened.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == (
            "What are the business hours on Monday?"
        )
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == (
            "Business hours are 09:00–17:00."
        )
        assert messages[1]["details"]["tool_name"] == (
            "get_business_hours"
        )
        assert messages[1]["details"]["tool_result"]["success"] is True


def test_assistant_appends_to_existing_conversation(monkeypatch):
    monkeypatch.setattr(
        main,
        "process_user_request",
        lambda prompt, idempotency_key=None: {
            "status": "answered",
            "tool_name": None,
            "tool_result": None,
            "answer": "Mock reply",
        },
    )

    with TestClient(app) as client:
        created = client.post("/conversations")
        conversation_id = created.json()["id"]

        response = client.post(
            "/assistant",
            json={
                "prompt": "Follow-up question",
                "conversation_id": conversation_id,
            },
        )

        assert response.status_code == 200
        assert response.json()["conversation_id"] == conversation_id

        reopened = client.get(f"/conversations/{conversation_id}")
        messages = reopened.json()["messages"]

        assert len(messages) == 2
        assert messages[0]["content"] == "Follow-up question"
        assert messages[1]["content"] == "Mock reply"


def test_assistant_saves_prompt_if_ai_fails(monkeypatch):
    def fake_failure(prompt, idempotency_key=None):
        raise RuntimeError("Simulated AI failure")

    monkeypatch.setattr(main, "process_user_request", fake_failure)

    with TestClient(app) as client:
        response = client.post(
            "/assistant",
            json={"prompt": "Please answer this test prompt"},
        )

        assert response.status_code == 502

        conversations = client.get("/conversations").json()["conversations"]
        conversation = next(
            item
            for item in conversations
            if item["title"] == "Please answer this test prompt"
        )

        reopened = client.get(
            f"/conversations/{conversation['id']}"
        ).json()

        assert len(reopened["messages"]) == 1
        assert reopened["messages"][0]["role"] == "user"
        assert reopened["messages"][0]["content"] == (
            "Please answer this test prompt"
        )


def test_assistant_rejects_unknown_conversation(monkeypatch):
    def should_not_run(prompt, idempotency_key=None):
        raise AssertionError("Assistant should not be called")

    monkeypatch.setattr(main, "process_user_request", should_not_run)

    with TestClient(app) as client:
        response = client.post(
            "/assistant",
            json={
                "prompt": "This should be rejected",
                "conversation_id": 999999,
            },
        )

        assert response.status_code == 404
