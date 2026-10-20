
import sqlite3

import pytest

from app.database import (
    add_chat_message,
    create_conversation,
    get_conversation,
    list_conversations,
)


def test_create_conversation():
    conversation = create_conversation()

    assert conversation["id"] > 0
    assert conversation["title"] == "New chat"
    assert conversation["created_at"]
    assert conversation["updated_at"]


def test_save_and_reopen_conversation():
    conversation = create_conversation()
    conversation_id = conversation["id"]

    add_chat_message(
        conversation_id,
        "user",
        "What are the business hours on Monday?",
    )
    add_chat_message(
        conversation_id,
        "assistant",
        "The business hours are 09:00–17:00.",
        details={
            "tool_name": "get_business_hours",
            "status": "success",
        },
    )

    reopened = get_conversation(conversation_id)

    assert reopened is not None
    assert reopened["id"] == conversation_id
    assert reopened["title"] == "What are the business hours on Monday?"
    assert len(reopened["messages"]) == 2

    assert reopened["messages"][0]["role"] == "user"
    assert reopened["messages"][0]["content"] == (
        "What are the business hours on Monday?"
    )

    assistant_message = reopened["messages"][1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == (
        "The business hours are 09:00–17:00."
    )
    assert assistant_message["details"] == {
        "tool_name": "get_business_hours",
        "status": "success",
    }


def test_list_conversations():
    first = create_conversation()
    second = create_conversation()

    add_chat_message(first["id"], "user", "First conversation")
    add_chat_message(second["id"], "user", "Second conversation")

    conversations = list_conversations()

    conversation_ids = {item["id"] for item in conversations}
    assert first["id"] in conversation_ids
    assert second["id"] in conversation_ids


def test_get_missing_conversation_returns_none():
    assert get_conversation(999999) is None


def test_cannot_add_message_to_missing_conversation():
    with pytest.raises(ValueError, match="Conversation not found"):
        add_chat_message(999999, "user", "This should not be saved")


def test_invalid_message_role_is_rejected():
    conversation = create_conversation()

    with pytest.raises(ValueError, match="role must be"):
        add_chat_message(conversation["id"], "system", "Invalid role")
