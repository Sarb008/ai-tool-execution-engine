from app.gemini_agent import process_user_request
from contextlib import asynccontextmanager
from typing import Any
import logging
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

import hashlib
import json
import threading

from app.database import (
    initialize_database,
    get_tool_executions,
    create_conversation,
    list_conversations,
    get_conversation,
    add_chat_message,
    claim_assistant_request,
    complete_assistant_request,
    release_assistant_request,
    add_chat_message_for_assistant_request,
    renew_assistant_request,
)
from app.registry import TOOL_DEFINITIONS, execute_tool

from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="AI Tool Execution Engine",
    description="A validated tool execution gateway for AI agents.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://localhost:5173",
        "https://ai-tool-execution-engine.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)


class ToolExecutionRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

class AssistantRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=200
    )
    conversation_id: int | None = Field(default=None, ge=1)

@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ai-tool-execution-engine",
    }


@app.get("/tools")
def list_tools() -> dict[str, list[dict[str, str]]]:
    return {
        "tools": [
            {
                "name": definition.name,
                "description": definition.description,
            }
            for definition in TOOL_DEFINITIONS.values()
        ]
    }


@app.get("/executions")
def list_executions(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    return {
        "executions": get_tool_executions(limit),
    }


@app.post("/conversations", status_code=201)
def new_conversation() -> dict[str, Any]:
    """Create a new, empty conversation."""
    return create_conversation()


@app.get("/conversations")
def get_conversations(
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """List recent conversations."""
    return {"conversations": list_conversations(limit)}


@app.get("/conversations/{conversation_id}")
def read_conversation(conversation_id: int) -> dict[str, Any]:
    """Load a conversation and its saved messages."""
    conversation = get_conversation(conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    return conversation


@app.post("/tools/execute")
def run_tool(request: ToolExecutionRequest) -> dict[str, Any]:
    try:
        return execute_tool(
            tool_name=request.tool_name,
            arguments=request.arguments,
            idempotency_key=request.idempotency_key,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_input=False),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Tool execution failed.",
        ) from exc



@app.post("/assistant")
def assistant(request: AssistantRequest) -> dict[str, Any]:
    conversation_id = request.conversation_id
    idempotency_key = request.idempotency_key
    owner_token: str | None = None
    request_claimed = False

    heartbeat_stop = threading.Event()
    heartbeat_lost = threading.Event()
    heartbeat_thread: threading.Thread | None = None

    def stop_heartbeat() -> None:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join()

    def renew_lease() -> None:
        while not heartbeat_stop.wait(30):
            try:
                renewed = renew_assistant_request(
                    idempotency_key, owner_token
                )
            except Exception:
                logger.exception("Could not renew assistant request lease")
                heartbeat_lost.set()
                return

            if not renewed:
                heartbeat_lost.set()
                return

    def save_message(
        role: str,
        content: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if heartbeat_lost.is_set():
            raise RuntimeError("Assistant request ownership was lost.")

        if request_claimed and idempotency_key and owner_token:
            add_chat_message_for_assistant_request(
                idempotency_key=idempotency_key,
                owner_token=owner_token,
                conversation_id=conversation_id,
                role=role,
                content=content,
                details=details,
            )
        else:
            add_chat_message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                details=details,
            )

    # Claim before creating conversations or saving messages.
    if idempotency_key:
        request_data = {
            "prompt": request.prompt,
            "conversation_id": conversation_id,
        }
        canonical_request = json.dumps(
            request_data,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_hash = hashlib.sha256(
            canonical_request.encode("utf-8")
        ).hexdigest()

        claim = claim_assistant_request(
            idempotency_key,
            request_hash,
        )

        if claim["status"] == "replay":
            return claim["response"]

        if claim["status"] == "conflict":
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used for a different request.",
            )

        if claim["status"] == "in_progress":
            raise HTTPException(
                status_code=409,
                detail="This request is already in progress. Retry shortly.",
                headers={"Retry-After": "2"},
            )

        request_claimed = claim["status"] == "claimed"
        owner_token = claim.get("owner_token")

        if request_claimed and not owner_token:
            raise RuntimeError(
                "Request was claimed without an ownership token."
            )

        if request_claimed:
            heartbeat_thread = threading.Thread(
                target=renew_lease,
                name="assistant-request-lease",
                daemon=True,
            )
            heartbeat_thread.start()

    try:
        if conversation_id is None:
            conversation = create_conversation()
            conversation_id = conversation["id"]
        elif get_conversation(conversation_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

        save_message(
            role="user",
            content=request.prompt,
        )

        result = process_user_request(
            prompt=request.prompt,
            idempotency_key=idempotency_key,
        )

        save_message(
            role="assistant",
            content=result["answer"],
            details={
                "status": result.get("status"),
                "tool_name": result.get("tool_name"),
                "tool_result": result.get("tool_result"),
            },
        )

        response = {
            **result,
            "conversation_id": conversation_id,
        }

        if request_claimed and idempotency_key and owner_token:
            stop_heartbeat()

            if heartbeat_lost.is_set():
                raise RuntimeError(
                    "Assistant request ownership was lost before completion."
                )

            complete_assistant_request(
                idempotency_key,
                owner_token,
                response,
            )

        return response

    except HTTPException:
        if request_claimed and idempotency_key and owner_token:
            stop_heartbeat()
            release_assistant_request(idempotency_key, owner_token)
        raise

    except ValueError as exc:
        if request_claimed and idempotency_key and owner_token:
            stop_heartbeat()
            release_assistant_request(idempotency_key, owner_token)

        logger.warning(
            "Assistant request rejected: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        if request_claimed and idempotency_key and owner_token:
            stop_heartbeat()
            release_assistant_request(idempotency_key, owner_token)

        logger.exception("Assistant agent failed")
        raise HTTPException(
            status_code=502,
            detail="The AI agent could not complete the request.",
        ) from exc

    except Exception as exc:
        if request_claimed and idempotency_key and owner_token:
            stop_heartbeat()
            release_assistant_request(idempotency_key, owner_token)

        logger.exception(
            "Unexpected assistant endpoint failure (%s)",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The AI service or tool execution failed.",
        ) from exc

    finally:
        stop_heartbeat()