
import hashlib
import json

from fastapi.testclient import TestClient

from app import main
from app.database import get_conversation, list_conversations


def test_retry_reuses_saved_response_without_calling_agent(monkeypatch):
    calls = []

    def fake_process_user_request(prompt, idempotency_key=None):
        calls.append(prompt)
        return {
            "status": "success",
            "tool_name": "create_support_ticket",
            "tool_result": {"ticket_id": 123},
            "answer": "Ticket created.",
        }

    monkeypatch.setattr(
        main, "process_user_request", fake_process_user_request
    )

    with TestClient(main.app) as client:
        payload = {
            "prompt": "Create a support ticket",
            "idempotency_key": "retry-test-001",
        }

        first = client.post("/assistant", json=payload)
        second = client.post("/assistant", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json() == first.json()
        assert len(calls) == 1

        conversation_id = first.json()["conversation_id"]
        conversation = get_conversation(conversation_id)

        # Only one user message and one assistant message were saved.
        assert len(conversation["messages"]) == 2
        assert [m["role"] for m in conversation["messages"]] == [
            "user", "assistant"
        ]

        # The retry did not create another conversation.
        assert len(list_conversations()) == 1


def test_reusing_key_with_different_prompt_returns_conflict(monkeypatch):
    calls = []

    def fake_process_user_request(prompt, idempotency_key=None):
        calls.append(prompt)
        return {
            "status": "answered",
            "tool_name": None,
            "tool_result": None,
            "answer": "Mock answer.",
        }

    monkeypatch.setattr(
        main, "process_user_request", fake_process_user_request
    )

    with TestClient(main.app) as client:
        first = client.post(
            "/assistant",
            json={
                "prompt": "First prompt",
                "idempotency_key": "retry-test-002",
            },
        )
        second = client.post(
            "/assistant",
            json={
                "prompt": "Different prompt",
                "idempotency_key": "retry-test-002",
            },
        )

        assert first.status_code == 200
        assert second.status_code == 409
        assert len(calls) == 1
        assert len(list_conversations()) == 1


def test_in_progress_request_is_not_executed_twice(monkeypatch):
    calls = []

    def fake_process_user_request(prompt, idempotency_key=None):
        calls.append(prompt)
        return {
            "status": "answered",
            "tool_name": None,
            "tool_result": None,
            "answer": "Mock answer.",
        }

    monkeypatch.setattr(
        main, "process_user_request", fake_process_user_request
    )

    payload = {
        "prompt": "A request already being processed",
        "conversation_id": None,
    }
    canonical_request = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_hash = hashlib.sha256(
        canonical_request.encode("utf-8")
    ).hexdigest()

    from app.database import claim_assistant_request

    claim = claim_assistant_request(
        "retry-test-003", request_hash
    )
    assert claim["status"] == "claimed"

    with TestClient(main.app) as client:
        response = client.post(
            "/assistant",
            json={
                "prompt": payload["prompt"],
                "idempotency_key": "retry-test-003",
            },
        )

    assert response.status_code == 409
    assert len(calls) == 0
    assert len(list_conversations()) == 0
