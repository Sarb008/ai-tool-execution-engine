
import pytest
from pydantic import ValidationError

from app.registry import validate_tool_arguments


def test_valid_order_arguments_are_accepted() -> None:
    result = validate_tool_arguments(
        "check_order_status",
        {"order_id": "ORD-1001"},
    )

    assert result.order_id == "ORD-1001"


def test_invalid_order_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_tool_arguments(
            "check_order_status",
            {"order_id": "not-an-order"},
        )


def test_unexpected_argument_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_tool_arguments(
            "check_order_status",
            {
                "order_id": "ORD-1001",
                "admin": True,
            },
        )


def test_missing_required_argument_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_tool_arguments(
            "check_order_status",
            {},
        )


def test_wrong_argument_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_tool_arguments(
            "check_order_status",
            {"order_id": 1001},
        )


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        validate_tool_arguments(
            "delete_everything",
            {},
        )


def test_support_ticket_rejects_short_description() -> None:
    with pytest.raises(ValidationError):
        validate_tool_arguments(
            "create_support_ticket",
            {
                "customer_id": "C-1",
                "subject": "Help me",
                "description": "Short",
            },
        )
