# ToolPilot — AI Tool Execution Engine

ToolPilot is a full-stack AI tool execution engine that converts natural-language requests into validated application actions. It combines Google's Gemini function calling with a controlled Python backend, persistent SQLite storage, and a React + TypeScript chat interface.

Rather than allowing an AI model to execute arbitrary operations, ToolPilot exposes an allowlisted set of tools. The application validates proposed arguments, dispatches registered handlers, persists relevant results, and records execution history.

## Features

- **AI-powered tool selection:** Use Gemini function calling to map natural-language requests to registered application tools.
- **Validated inputs:** Validate tool arguments with Pydantic schemas before execution.
- **Controlled execution:** Dispatch only registered tools through an allowlisted tool registry.
- **REST API:** Expose health, tool discovery, execution, assistant, and conversation endpoints through FastAPI.
- **Persistent conversations:** Save chat messages and reopen previous conversations after refreshing the frontend.
- **Execution history:** Persist tool execution records and display relevant tool details alongside assistant responses.
- **Idempotency:** Use request keys to prevent duplicate processing of repeated assistant requests and supported write operations.
- **SQLite persistence:** Store support tickets, demo bookings, conversations, execution records, and idempotency records.
- **Automated testing:** Test API behavior, validation, persistence, retries, and failure scenarios without requiring live Gemini calls for the mocked tests.
- **Full-stack interface:** Interact with the backend through a React + TypeScript frontend with Markdown-formatted assistant responses.

## Architecture

```text
React + TypeScript Frontend
          |
          v
      FastAPI API
          |
          +---- Health / Tool Discovery
          +---- Direct Tool Execution
          +---- Conversation Management
          +---- Assistant Requests
                     |
                     v
                  Gemini
              Function Calling
                     |
                     v
              Tool Registry
                     |
                     v
             Pydantic Validation
                     |
                     v
               Tool Handlers
                     |
                     v
                  SQLite
          /          |           \
   Business Data  Conversations  Execution &
                                 Idempotency
                     |
                     v
             Tool Result / Reply
```

**Design principle:** The model proposes an action; the application validates and executes it. The model is not given unrestricted access to application operations.

## Available tools

| Tool | Purpose |
|---|---|
| `check_order_status` | Look up an order in sample data |
| `get_business_hours` | Retrieve business hours for a weekday |
| `create_support_ticket` | Create a support ticket in SQLite |
| `book_demo` | Record a demo booking request in SQLite |

Order-status and business-hours lookups currently use sample data. Support tickets and demo bookings are persisted in the local database.

## Technology stack

**Backend**
- Python
- FastAPI
- Pydantic
- Google GenAI SDK (`google-genai`)
- SQLite
- pytest

**Frontend**
- React
- TypeScript
- Vite
- React Markdown

## Getting started

### Prerequisites

- Python installed and available through the Windows Python launcher (`py`)
- Node.js and npm
- A Google AI Studio API key for live Gemini-powered requests

### 1. Clone the repository

```powershell
git clone https://github.com/Sarb008/ai-tool-execution-engine.git
cd ai-tool-execution-engine
```

### 2. Set up the backend

Create a virtual environment:

```powershell
py -m venv .venv
```

Install the dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" "pydantic>=2,<3" google-genai python-dotenv pytest httpx
```

### 3. Configure Gemini

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and configure your own API key and model:

```dotenv
GEMINI_API_KEY=your_actual_api_key
GEMINI_MODEL=gemini-3.8-flash
```

Use a model available to your account. Never commit `.env` or expose API keys in source code, screenshots, logs, or public repositories.

### 4. Start the backend

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URLs:

- API: `http://127.0.0.1:8000`
- Interactive API documentation: `http://127.0.0.1:8000/docs`

### 5. Set up and start the frontend

Open a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open the local URL printed by Vite, usually `http://localhost:5173`.

Keep the backend and frontend terminals running while using the application.

## API overview

### Health check

```http
GET /health
```

Check whether the API is responding.

### Discover available tools

```http
GET /tools
```

Retrieve registered tool names and descriptions.

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

### Submit an assistant request

```http
POST /assistant
Content-Type: application/json
```

Example:

```json
{
  "prompt": "What are the business hours on Monday?"
}
```

The backend sends the request to Gemini, processes a proposed registered tool call when appropriate, and returns the result and a natural-language response.

Assistant requests can include an idempotency key and a conversation ID:

```json
{
  "prompt": "Create a support ticket for customer CUST-100",
  "idempotency_key": "support-request-001",
  "conversation_id": 1
}
```

The conversation ID is optional. The idempotency key is also optional, but should be supplied when safe retries are required.

### Conversation management

| Endpoint | Purpose |
|---|---|
| `POST /conversations` | Create a conversation |
| `GET /conversations` | List saved conversations |
| `GET /conversations/{conversation_id}` | Retrieve a conversation and its messages |

The frontend uses these endpoints to restore saved chats and start new conversations.

## Idempotency and reliability

ToolPilot implements database-backed idempotency at both the tool-execution layer and the assistant-request layer.

- Repeating a completed assistant request with the same key and request payload returns the stored response rather than executing the request again.
- Reusing a key with a different request payload is rejected.
- A request already marked `in_progress` is rejected rather than immediately executed a second time.
- Supported write operations use SQLite transactions to coordinate data changes, idempotency records, and execution records.
- Automated tests cover repeated requests, conflicting keys, concurrent retries, and in-progress requests.

**Current limitation:** Crash recovery for abandoned `in_progress` assistant requests has not yet been implemented. A process crash at the wrong point can leave a request blocked until recovery is added. The project should not be considered production-ready.

## Running the tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests -q
```

The latest verified result is **41 passing tests**.

The mocked agent and API tests avoid unnecessary live Gemini requests. A successful test run does not require consuming Gemini API quota for every test.

## Building the frontend

From the frontend directory:

```powershell
npm.cmd run build
```

This runs TypeScript compilation and creates a production build using Vite.

The latest verified production build completed successfully.

## Project structure

```text
ai-tool-execution-engine/
├── app/
│   ├── main.py
│   ├── schemas.py
│   ├── registry.py
│   ├── database.py
│   ├── gemini_agent.py
│   └── tools/
│       └── handlers.py
├── tests/
│   ├── test_health.py
│   ├── test_registry.py
│   ├── test_execution.py
│   ├── test_audit.py
│   ├── test_idempotency.py
│   ├── test_api.py
│   ├── test_gemini_agent.py
│   ├── test_conversations.py
│   ├── test_assistant_conversations.py
│   └── test_assistant_idempotency.py
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── .env.example
├── .gitignore
└── README.md
```

## Limitations and future improvements

- Business hours and order status use sample data rather than live external integrations.
- The backend currently uses local SQLite storage.
- Authentication, authorization, rate limiting, and production deployment configuration are not implemented.
- Assistant requests currently support a single tool interaction rather than multi-step workflows.
- Safe recovery of abandoned in-progress requests remains future work.

Potential improvements include authenticated access, configurable tool permissions, observability, crash recovery, external business-system integrations, and deployment.

## License

No open-source license has been added yet. Add an appropriate license before distributing the project under an open-source license.
