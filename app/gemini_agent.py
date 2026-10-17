import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.registry import TOOL_DEFINITIONS, execute_tool


load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    """Create the Gemini client only when it is first needed."""
    global _client

    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        _client = genai.Client(api_key=api_key)

    return _client


def build_function_declarations() -> list[dict[str, Any]]:
    """Build Gemini-compatible declarations from the Pydantic tool schemas."""
    declarations = []

    for definition in TOOL_DEFINITIONS.values():
        schema = definition.arguments_model.model_json_schema()
        properties = {}

        for field_name, field_schema in schema.get("properties", {}).items():
            property_schema: dict[str, Any] = {
                "type": field_schema.get("type", "string")
            }

            if field_schema.get("description"):
                property_schema["description"] = field_schema["description"]

            if field_schema.get("enum"):
                property_schema["enum"] = field_schema["enum"]

            properties[field_name] = property_schema

        declarations.append(
            {
                "name": definition.name,
                "description": definition.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": schema.get("required", []),
                },
            }
        )

    return declarations


def process_user_request(
    prompt: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Ask Gemini whether a registered tool is needed, execute it safely,
    and ask Gemini to explain the result.
    """
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Prompt must not be empty.")

    client = get_gemini_client()
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    declarations = build_function_declarations()
    tool = types.Tool(function_declarations=declarations)
    config = types.GenerateContentConfig(tools=[tool])

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    candidate = response.candidates[0] if response.candidates else None
    model_content = candidate.content if candidate else None

    function_call = None
    if model_content and model_content.parts:
        for part in model_content.parts:
            if part.function_call:
                function_call = part.function_call
                break

    if function_call is None:
        return {
            "status": "answered",
            "tool_name": None,
            "tool_result": None,
            "answer": response.text or "I couldn't generate a response.",
        }

    tool_name = function_call.name

    # Never execute a name that is not in our application registry.
    if tool_name not in TOOL_DEFINITIONS:
        raise RuntimeError("Gemini requested an unregistered tool.")

    arguments = dict(function_call.args or {})

    try:
        execution = execute_tool(
            tool_name,
            arguments,
            idempotency_key=idempotency_key,
        )
        tool_result = {"success": True, "result": execution}
        status = "tool_executed"
    except Exception as exc:
        # Do not expose a traceback or internal database details to the model.
        tool_result = {
            "success": False,
            "error": f"Tool execution failed: {type(exc).__name__}",
        }
        status = "tool_failed"

    function_response = types.Part.from_function_response(
        name=tool_name,
        response={"result": tool_result},
    )

    history = [prompt]
    if model_content:
        history.append(model_content)

    history.append(
        types.Content(
            role="user",
            parts=[function_response],
        )
    )

    final_response = client.models.generate_content(
        model=model,
        contents=history,
        config=config,
    )

    return {
        "status": status,
        "tool_name": tool_name,
        "tool_result": tool_result,
        "answer": final_response.text or "The tool ran, but I couldn't summarize its result.",
    }
