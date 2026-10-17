
import hashlib
import json
import sqlite3
import time
from typing import Any, Callable

from pydantic import BaseModel

from app.database import get_connection, record_tool_execution
from app.schemas import (
    BookDemoArgs,
    CheckOrderStatusArgs,
    CreateSupportTicketArgs,
    GetBusinessHoursArgs,
    StrictToolArguments,
)
from app.tools.handlers import (
    book_demo,
    check_order_status,
    create_support_ticket,
    get_business_hours,
)


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

TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "check_order_status": check_order_status,
    "get_business_hours": get_business_hours,
    "create_support_ticket": create_support_ticket,
    "book_demo": book_demo,
}

WRITE_TOOLS = {"create_support_ticket", "book_demo"}


def validate_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
) -> StrictToolArguments:
    """Validate arguments for an explicitly registered tool."""

    definition = TOOL_DEFINITIONS.get(tool_name)

    if definition is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    return definition.arguments_model.model_validate(arguments)


def execute_idempotency_record(
    connection: sqlite3.Connection,
    idempotency_key: str,
    tool_name: str,
    input_hash: str,
    output_json: str,
) -> None:
    """Store an idempotency result inside the caller's transaction."""

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
        (idempotency_key, tool_name, input_hash, output_json),
    )


def _record_execution_in_transaction(
    connection: sqlite3.Connection,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    duration_ms: float,
    output: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Write an audit entry using the caller's transaction."""

    connection.execute(
        """
        INSERT INTO tool_executions (
            tool_name,
            input_json,
            output_json,
            status,
            duration_ms,
            error_message
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tool_name,
            json.dumps(arguments, sort_keys=True, default=str),
            (
                json.dumps(output, sort_keys=True, default=str)
                if output is not None
                else None
            ),
            status,
            duration_ms,
            error_message,
        ),
    )


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Validate, execute, and audit a tool invocation."""

    started_at = time.perf_counter()
    validated_args: StrictToolArguments | None = None

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

        handler = TOOL_HANDLERS[tool_name]

        # Keyed calls hold a SQLite write lock while checking the key,
        # executing the write, and storing the result.
        if idempotency_key is not None:
            with get_connection() as connection:
                connection.execute("BEGIN IMMEDIATE")

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

                    result = json.loads(existing["output_json"])
                    return {
                        "tool_name": tool_name,
                        "status": "success",
                        "result": result,
                        "idempotent_replay": True,
                    }

                if tool_name in WRITE_TOOLS:
                    result = handler(validated_args, connection=connection)
                else:
                    result = handler(validated_args)

                duration_ms = round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                )
                output_json = json.dumps(result, sort_keys=True)

                execute_idempotency_record(
                    connection,
                    idempotency_key,
                    tool_name,
                    input_hash,
                    output_json,
                )

                _record_execution_in_transaction(
                    connection,
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

        # Calls without an idempotency key retain the normal execution path.
        result = handler(validated_args)
        duration_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
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

        # Best-effort failure audit. If a keyed transaction is rolling
        # back, this audit is deliberately recorded separately.
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
