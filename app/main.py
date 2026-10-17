from app.gemini_agent import process_user_request
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.database import initialize_database
from app.registry import TOOL_DEFINITIONS, execute_tool


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
        default=None,
        min_length=1,
        max_length=200,
    )

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
def assistant(request: AssistantRequest):
    try:
        return process_user_request(
            prompt=request.prompt,
            idempotency_key=request.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail="The AI agent could not complete the request.",
        ) from exc
    except Exception as exc:
        # Keep internal exceptions out of the HTTP response.
        raise HTTPException(
            status_code=502,
            detail="The AI service or tool execution failed.",
        ) from exc
