# AI Tool Execution Engine

A Python-based tool execution gateway for AI agents, built with FastAPI, Pydantic, SQLite, and Google's Gemini API.

The project connects natural-language requests to a controlled set of application tools. Gemini can select a tool and propose its arguments, while the application validates those arguments, dispatches the request to an allowlisted handler, and records execution details.

## Features

- **Gemini function calling:** Translate natural-language requests into structured tool calls.
- **Validated arguments:** Use Pydantic schemas to validate tool inputs before execution.
- **Allowlisted tool registry:** Only registered application tools can be executed.
- **REST API:** Expose the engine through FastAPI endpoints.
- **SQLite persistence:** Store support tickets, demo bookings, execution records, and idempotency records.
- **Execution auditing:** Record successful and failed tool executions.
- **Idempotency support:** Recognize repeated write requests using a supplied idempotency key.
- **Automated tests:** Test validation, execution, API behavior, auditing, idempotency, and mocked AI interactions without requiring live Gemini calls.

## Architecture

```text
Client
  |
  v
FastAPI
  |
  +---- /health
  +---- /tools
  +---- /tools/execute
  +---- /assistant
                |
                v
          Gemini API
                |
          Proposed tool call
                |
                v
         Tool Registry
                |
         Pydantic Validation
                |
                v
         Tool Handlers
                |
                v
             SQLite
                |
                v
       Tool result returned
       to Gemini for a reply
```

The application—not the language model—controls the available tools and executes their handlers.

## Available tools

| Tool | Purpose |
|---|---|
| `check_order_status` | Look up an order in sample order data |
| `get_business_hours` | Retrieve business hours for a weekday |
| `create_support_ticket` | Create a support ticket in SQLite |
| `book_demo` | Record a demo booking request in SQLite |

The order-status and business-hours tools currently use sample data. Ticket creation and demo booking persist records in the local database.

## Technology stack

- Python
- FastAPI
- Pydantic
- Google GenAI SDK (`google-genai`)
- SQLite
- pytest
- HTTPX / FastAPI TestClient

## Getting started

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd ai-tool-execution-engine
```

### 2. Create a virtual environment

Windows PowerShell:

```powershell
py -m venv .venv
```

Install the dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" "pydantic>=2,<3" google-genai python-dotenv pytest httpx
```

### 3. Configure environment variables

Create a local `.env` file from the template:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and provide your Google AI Studio API key:

```dotenv
GEMINI_API_KEY=your_actual_api_key
GEMINI_MODEL=gemini-3.8-flash
```

Keep `.env` private. Never commit API keys or other credentials to Git.

### 4. Start the API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The service runs at `http://127.0.0.1:8000`.

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## API endpoints

### Health check

```http
GET /health
```

Checks that the application is responding.

### List available tools

```http
GET /tools
```

Returns the registered tool names and descriptions.

### Execute a tool directly

```http
POST /tools/execute
Content-Type: application/json
```

Example:

```json
{
  "tool_name": "check_order_status",
  "arguments": {
    "order_id": "ORD-1002"
  }
}
```

### Send a natural-language request

```http
POST /assistant
Content-Type: application/json
```

Example:

```json
{
  "prompt": "Check the status of order ORD-1002"
}
```

Gemini can select the appropriate registered tool, after which the application validates and executes the request. The tool result is sent back to Gemini to produce a natural-language response.

A write request may also supply an idempotency key:

```json
{
  "prompt": "Create a support ticket for customer CUST-100",
  "idempotency_key": "support-request-001"
}
```

Use a unique key for each logical write operation. The engine uses SQLite transactions to atomically execute supported write operations, store idempotency records, and record successful executions. Repeated requests with the same key and input replay the original result; reusing a key with different inputs is rejected. Concurrent retries are covered by automated tests.

## Running tests

Run the test suite from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The current test suite contains 26 passing tests. Gemini interactions in the automated agent tests are mocked, so the tests do not require live model calls.

## Project structure

```text
ai-tool-execution-engine/
├── app/
│   ├── main.py           # FastAPI application and routes
│   ├── schemas.py        # Strict argument validation schemas
│   ├── registry.py       # Tool registry, validation and dispatch
│   ├── database.py       # SQLite connections and audit persistence
│   ├── gemini_agent.py   # Gemini function-calling integration
│   └── tools/
│       └── handlers.py   # Registered tool implementations
├── tests/
│   ├── test_health.py
│   ├── test_registry.py
│   ├── test_execution.py
│   ├── test_audit.py
│   ├── test_idempotency.py
│   ├── test_api.py
│   └── test_gemini_agent.py
├── .env.example
├── .gitignore
└── README.md
```

## Current limitations and future improvements

- Order and business-hour data are examples rather than integrations with a real business system.
- The application uses a local SQLite database.
- Authentication, authorization, rate limiting, and production deployment configuration have not yet been implemented.
- Tool execution is currently a single-tool interaction per assistant request.

Potential next steps include authentication and authorization, rate limiting, structured logging, configurable tool permissions, production deployment, and integration tests.

## License

Choose and add an appropriate open-source license before publishing the repository publicly.