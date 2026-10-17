from app.database import record_tool_execution
import time
from typing import Any

from pydantic import BaseModel

from app.schemas import (
    BookDemoArgs,
    CheckOrderStatusArgs,
    CreateSupportTicketArgs,
    GetBusinessHoursArgs,
    StrictToolArguments,
)

import hashlib
import json

from app.database import get_connection, record_tool_execution

class ToolDefinition(BaseModel):
    """Metadata connecting a public tool name to its argument schema."""

    name: str
    description: str
    arguments_model: type[StrictToolArguments]


TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    "check_order_status": ToolDefinition(
        name="check_order_status",
        description="Look up the status of an order using its order ID.",
        arguments_model=CheckOrderStatusArgs,
    ),
    "get_business_hours": ToolDefinition(
        name="get_business_hours",
        description="Get the business opening hours for a weekday.",
        arguments_model=GetBusinessHoursArgs,
    ),
    "create_support_ticket": ToolDefinition(
        name="create_support_ticket",
        description="Create a support ticket for a customer.",
        arguments_model=CreateSupportTicketArgs,
    ),
    "book_demo": ToolDefinition(
        name="book_demo",
        description="Record a demo booking request.",
        arguments_model=BookDemoArgs,
    ),
}


def validate_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
) -> StrictToolArguments:
    """Validate arguments for an explicitly registered tool."""

    definition = TOOL_DEFINITIONS.get(tool_name)

    if definition is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    return definition.arguments_model.model_validate(arguments)


from app.tools.handlers import (
    book_demo,
    check_order_status,
    create_support_ticket,
    get_business_hours,
)


TOOL_HANDLERS = {
    "check_order_status": check_order_status,
    "get_business_hours": get_business_hours,
    "create_support_ticket": create_support_ticket,
    "book_demo": book_demo,
}




def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Validate, execute, and audit a tool invocation."""

    started_at = time.perf_counter()

    try:
        validated_args = validate_tool_arguments(tool_name, arguments)

        canonical_input = json.dumps(
            validated_args.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        input_hash = hashlib.sha256(
            canonical_input.encode("utf-8")
        ).hexdigest()

        # Return a previous successful result for an identical retry.
        if idempotency_key is not None:
            with get_connection() as connection:
                existing = connection.execute(
                    """
                    SELECT tool_name, input_hash, output_json
                    FROM idempotency_records
                    WHERE idempotency_key = ?
                    """,
                    (idempotency_key,),
                ).fetchone()

            if existing is not None:
                if (
                    existing["tool_name"] != tool_name
                    or existing["input_hash"] != input_hash
                ):
                    raise ValueError(
                        "Idempotency key was already used "
                        "for a different request."
                    )

                return {
                    "tool_name": tool_name,
                    "status": "success",
                    "result": json.loads(existing["output_json"]),
                    "idempotent_replay": True,
                }

        handler = TOOL_HANDLERS[tool_name]
        result = handler(validated_args)

        duration_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        if idempotency_key is not None:
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO idempotency_records (
                        idempotency_key,
                        tool_name,
                        input_hash,
                        output_json
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        idempotency_key,
                        tool_name,
                        input_hash,
                        json.dumps(result, sort_keys=True),
                    ),
                )

        record_tool_execution(
            tool_name=tool_name,
            arguments=arguments,
            status="success",
            duration_ms=duration_ms,
            output=result,
        )

        return {
            "tool_name": tool_name,
            "status": "success",
            "duration_ms": duration_ms,
            "result": result,
            "idempotent_replay": False,
        }

    except Exception as exc:
        duration_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        try:
            record_tool_execution(
                tool_name=tool_name,
                arguments=arguments,
                status="failed",
                duration_ms=duration_ms,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            pass

        raise
