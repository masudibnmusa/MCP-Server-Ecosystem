# MCP Server Ecosystem

Custom **Model Context Protocol (MCP)** servers that expose your own systems (a database, a calendar, internal tools) in a standard way, plus a **client agent** that discovers those servers' capabilities at runtime and composes them to complete multi-step tasks.

> Adding a new capability means adding a server, not changing the agent.

---

## Overview

[MCP](https://modelcontextprotocol.io) is an open protocol that standardizes how LLM applications connect to tools and data. Any MCP-compatible client can use an MCP server without custom integration code.

This project has two halves:

1. **Servers** — each wraps one system and exposes:
   - **Tools**: actions the LLM can invoke (e.g. `run_query`, `create_event`)
   - **Resources**: read-only data (e.g. database schema, working hours)
   - **Prompts**: reusable workflow templates (e.g. "Analyze table X")
2. **Agent** — connects to several servers, lists their capabilities, hands the tool definitions to Claude, and routes each tool call to the server that owns it.

**Example request**

```
"Find my top 3 customers by revenue, book a review meeting with each,
 and open a ticket to track the follow-up."
```

The agent plans across servers: query the database, find free calendar slots, create events, and create a ticket, pausing for your approval before anything that writes.

---

## Features

- **Three focused MCP servers**: database, calendar, internal tools
- **Dynamic discovery**: tools, resources, and prompts are listed at runtime
- **Namespaced tools** (e.g. `calendar__create_event`) to avoid collisions
- **Two transports**: stdio for local servers, streamable HTTP for remote/shared ones
- **Planner**: drafts a cross-server plan, executes step by step, re-plans on failure
- **Approval gate**: servers *declare* tool annotations (`readOnlyHint`, `destructiveHint`); the agent *enforces* approval
- **Defense in depth for SQL**: read-only connection, `sqlglot` AST validation, row limits, timeouts
- **Prompt-injection hygiene**: tool results are treated as untrusted data
- **Graceful degradation**: health checks, reconnects with backoff, and fallback behavior when a server is down
- **Full call tracing**: every tool call logged with server, arguments, result, and latency
- **Declarative registry**: add or remove servers via `registry/servers.json`, no code changes

---

## Architecture

```
User request
     ↓
planner.py          drafts a cross-server plan
     ↓
agent_loop.py       Claude sees filtered tools from all servers (tool_selector.py)
     ↓
approval_gate.py    pauses on write/destructive tools (reads server annotations)
     ↓
tool_router.py      namespaced tool name → owning server
     ↓
┌──────────────────┬──────────────────────┬─────────────────────────┐
│ database_server  │   calendar_server    │  internal_tools_server  │
│ (stdio)          │   (stdio)            │  (streamable HTTP)      │
└──────────────────┴──────────────────────┴─────────────────────────┘
     ↓
injection_guard.py  wraps results as untrusted data
     ↓
Claude → final response + call_logger.py trace
```

### Example flow

| Step | Tool | Type | Approval |
|---|---|---|---|
| 1 | `database__run_query` | read-only | automatic |
| 2 | `calendar__find_free_slots` | read-only | automatic |
| 3 | `calendar__create_event` | write | **required** |
| 4 | `tickets__create_ticket` | write | **required** |

---

## Project Structure

```
mcp-ecosystem/
│
├── servers/
│   ├── database_server/
│   │   ├── __init__.py
│   │   ├── server.py                  # Entry point; supports stdio AND streamable HTTP
│   │   ├── tools.py                   # run_query (read-only), describe_table, list_tables
│   │   ├── write_tools.py             # insert_record, annotated destructive
│   │   ├── resources.py               # Schema as a resource, sample rows
│   │   ├── prompts.py                 # "Analyze table X" prompt template
│   │   ├── query_guard.py             # sqlglot AST validation, row limits, timeouts
│   │   ├── connection.py              # Opens SQLite with ?mode=ro; separate RW connection
│   │   └── config.py
│   │
│   ├── calendar_server/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── tools.py                   # list_events, find_free_slots, create_event (annotated)
│   │   ├── resources.py               # Working hours, calendar list
│   │   ├── prompts.py                 # "Schedule review meeting" template
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── ics_provider.py        # Start here: local ICS file, no OAuth
│   │   │   └── google_provider.py     # Later: real OAuth calendar
│   │   ├── auth.py                    # OAuth flow and token storage (google_provider)
│   │   └── config.py
│   │
│   ├── internal_tools_server/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── tools.py                   # create_ticket, search_wiki, post_to_chat (annotated)
│   │   ├── resources.py               # Ticket templates, team list
│   │   └── config.py
│   │
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── stdio_runner.py
│   │   ├── http_runner.py             # Streamable HTTP app, session handling
│   │   └── http_auth.py               # Bearer token / OAuth validation for remote servers
│   │
│   └── shared/
│       ├── __init__.py
│       ├── schemas.py                 # Common input/output models
│       ├── errors.py                  # Consistent, LLM-readable error messages
│       └── annotations.py             # Servers DECLARE readOnlyHint / destructiveHint /
│                                      #   idempotentHint; the agent ENFORCES approval
│
├── agent/
│   ├── __init__.py
│   ├── main.py                        # CLI/chat entry point
│   ├── config.py                      # Which servers to connect to
│   │
│   ├── mcp_client/
│   │   ├── __init__.py
│   │   ├── connection_manager.py      # Start/connect/reconnect with backoff
│   │   ├── health.py                  # Heartbeat, timeouts, mark server up/down
│   │   ├── capability_loader.py       # List tools/resources/prompts from each server
│   │   ├── tool_router.py             # Namespaced name -> owning server; handles server-down
│   │   └── namespace.py               # Splits on FIRST separator only; validates tool names
│   │
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── agent_loop.py              # LLM tool-use loop across all servers
│   │   ├── planner.py                 # Cross-server plan, step-by-step execution, re-plan on failure
│   │   ├── tool_selector.py           # Filter tools per task to keep context small
│   │   ├── approval_gate.py           # Reads server annotations; pauses on write/destructive
│   │   └── degradation.py             # What to do when a server is down (skip, retry, tell user)
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── llm_client.py              # Claude API with native tool use
│   │   └── prompts.py
│   │
│   └── observability/
│       ├── __init__.py
│       ├── call_logger.py             # Every tool call: server, args, result, latency
│       └── trace_viewer.py
│
├── registry/
│   ├── servers.json                   # Declarative: name, transport, command/URL, permissions
│   ├── servers.schema.json            # Validates the registry file
│   └── registry_loader.py
│
├── security/
│   ├── __init__.py
│   ├── permissions.py                 # Per-server, per-tool allow/deny rules
│   ├── secrets_manager.py             # Load credentials from env/vault, never hardcode
│   └── injection_guard.py             # Treat tool results as untrusted data
│
├── data/
│   ├── sample_db/                     # SQLite demo database
│   ├── sample_calendar.ics            # Mock calendar for the ICS provider
│   └── logs/
│
├── tests/
│   ├── fixtures/
│   │   └── mock_mcp_server.py         # Fake server for agent tests (incl. crash/hang modes)
│   ├── servers/
│   │   ├── test_database_tools.py
│   │   ├── test_query_guard.py        # Bypass attempts: comments, multi-statement, CTEs
│   │   ├── test_readonly_connection.py # Writes fail even if guard is bypassed
│   │   └── test_annotations.py
│   ├── agent/
│   │   ├── test_namespace.py          # Edge cases: underscores, empty names, collisions
│   │   ├── test_tool_router.py
│   │   ├── test_approval_gate.py
│   │   ├── test_planner.py
│   │   ├── test_degradation.py        # Server crashes mid-call, timeouts
│   │   └── test_agent_integration.py
│   └── security/
│       ├── test_injection_guard.py
│       └── test_permissions.py
│
├── docs/
│   ├── server_catalog.md              # What each server exposes
│   ├── threat_model.md                # Malicious tool output, over-broad scopes, token leaks
│   └── demo/                          # Recording/script + sample trace output
│
├── scripts/
│   ├── run_inspector.sh               # Launch MCP Inspector against a single server
│   └── run_demo.sh                    # Scripted end-to-end walkthrough
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── run.sh
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- An Anthropic API key
- Node.js (optional, only needed for MCP Inspector)

### Installation

```bash
git clone https://github.com/masudibnmusa/MCP-Server-Ecosystem.git
cd mcp-ecosystem

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Environment setup

```bash
cp .env.example .env
```

Then edit `.env` (see [Configuration](#configuration)).

### Seed the demo data

```bash
python -m data.seed              # creates data/sample_db/demo.sqlite
```

The calendar server uses `data/sample_calendar.ics` by default, so no OAuth setup is needed to get started.

---

## Configuration

### `.env`

| Variable | Description | Example |
|---|---|---|
| `ANTHROPIC_API_KEY` | API key for Claude | `sk-ant-...` |
| `CLAUDE_MODEL` | Model used by the agent | `claude-sonnet-5-5` |
| `DB_PATH` | SQLite database path | `data/sample_db/demo.sqlite` |
| `CALENDAR_PROVIDER` | `ics` or `google` | `ics` |
| `ICS_PATH` | Local calendar file | `data/sample_calendar.ics` |
| `HTTP_SERVER_TOKEN` | Bearer token for remote servers | `change-me` |
| `LOG_DIR` | Where call traces are written | `data/logs` |

Never commit `.env`. Credentials are loaded through `security/secrets_manager.py`.

### `registry/servers.json`

Servers are declared, not hardcoded:

```json
{
  "servers": [
    {
      "name": "database",
      "transport": "stdio",
      "command": "python",
      "args": ["-m", "servers.database_server.server"],
      "permissions": {
        "allow": ["run_query", "describe_table", "list_tables"],
        "deny": ["insert_record"]
      }
    },
    {
      "name": "calendar",
      "transport": "stdio",
      "command": "python",
      "args": ["-m", "servers.calendar_server.server"]
    },
    {
      "name": "tickets",
      "transport": "http",
      "url": "http://localhost:8080/mcp",
      "auth": { "type": "bearer", "env": "HTTP_SERVER_TOKEN" }
    }
  ]
}
```

To add a capability, add an entry here and restart the agent. The registry is validated against `registry/servers.schema.json`.

---

## Running

### Start the agent

```bash
./run.sh
# or
python -m agent.main
```

The agent starts the stdio servers itself and connects to any HTTP servers listed in the registry.

### Start the HTTP server (if used)

```bash
python -m servers.transport.http_runner --server internal_tools --port 8080
```

### Run the scripted demo

```bash
./scripts/run_demo.sh
```

### Example session

```
> Find my top 3 customers by revenue and book a review meeting with each

Plan:
  1. Query top 3 customers by revenue          (database)
  2. Find free 30-min slots this week          (calendar)
  3. Create 3 review events                    (calendar)  needs approval
  4. Create a follow-up ticket                 (tickets)   needs approval

[approval] calendar__create_event
  title: "Acme Corp: Account Review"
  time:  Tue 14:00-14:30
  Approve? [y/N/a(ll)]
```

---

## Server Catalog

Full details live in [`docs/server_catalog.md`](docs/server_catalog.md). Summary:

### Database server

| Kind | Name | Notes |
|---|---|---|
| Tool | `run_query` | Read-only; AST-validated; row limit and timeout enforced |
| Tool | `describe_table` | Columns and types |
| Tool | `list_tables` | |
| Tool | `insert_record` | **Write**; annotated destructive; requires approval |
| Resource | `schema://main` | Full schema |
| Resource | `sample://{table}` | Sample rows |
| Prompt | `analyze_table` | "Analyze table X" template |

### Calendar server

| Kind | Name | Notes |
|---|---|---|
| Tool | `list_events` | Read-only |
| Tool | `find_free_slots` | Read-only |
| Tool | `create_event` | **Write**; requires approval |
| Resource | `calendar://working-hours` | |
| Resource | `calendar://list` | |
| Prompt | `schedule_review_meeting` | |

### Internal tools server

| Kind | Name | Notes |
|---|---|---|
| Tool | `create_ticket` | **Write**; requires approval |
| Tool | `search_wiki` | Read-only |
| Tool | `post_to_chat` | **Write**; requires approval |
| Resource | `tickets://templates` | |
| Resource | `team://members` | |

---

## How the Agent Works

1. **Connect**: `connection_manager.py` starts or connects to each server in the registry, with reconnect and backoff.
2. **Discover**: `capability_loader.py` lists tools, resources, and prompts from every server.
3. **Namespace**: `namespace.py` prefixes each tool with its server name (`calendar__create_event`). It splits on the **first** `__` only and validates names against LLM tool-name rules.
4. **Select**: `tool_selector.py` filters the tool list per task to keep the context small.
5. **Plan**: `planner.py` drafts a cross-server plan, then executes it step by step and re-plans on failure.
6. **Gate**: `approval_gate.py` checks each tool's annotations and pauses for your OK on write or destructive calls.
7. **Route**: `tool_router.py` sends the call to the owning server.
8. **Sanitize**: `injection_guard.py` marks results as untrusted data before they reach the model.
9. **Log**: `call_logger.py` records the call.
10. **Degrade gracefully**: if a server is down, `degradation.py` decides whether to skip, retry, or tell you.

---

## Security Model

| Layer | Protection |
|---|---|
| **SQL safety** | SQLite opened with `mode=ro`; `sqlglot` parses queries and rejects non-`SELECT` statements, multi-statement input, and unsafe constructs; row limits and timeouts at the connection level |
| **Write isolation** | `insert_record` lives in `write_tools.py` with a separate read-write connection and a destructive annotation |
| **Single source of truth for approvals** | Servers declare `readOnlyHint` / `destructiveHint` / `idempotentHint`; only `approval_gate.py` enforces |
| **Permissions** | Per-server, per-tool allow/deny rules in `security/permissions.py` |
| **Secrets** | Loaded from environment or a vault; never hardcoded or logged |
| **Prompt injection** | Tool results are treated as untrusted data and never as instructions |
| **Remote servers** | Bearer-token or OAuth validation in `servers/transport/http_auth.py` |

See [`docs/threat_model.md`](docs/threat_model.md) for malicious tool output, over-broad scopes, and token-leak scenarios.

> Treat annotations from servers you don't control as hints, not guarantees. Only trust them for servers you operate.

---

## Observability

Every tool call is written to `data/logs/` with:

- Timestamp
- Namespaced tool name and owning server
- Arguments
- Result (truncated) or error
- Latency
- Approval decision (auto, approved, denied)

View a trace:

```bash
python -m agent.observability.trace_viewer data/logs/<session>.jsonl
```

---

## Testing

```bash
pytest
```

| Area | What's covered |
|---|---|
| `tests/servers/` | Database tools, `query_guard` (including bypass attempts via comments, multi-statement input, and CTEs), read-only connection, annotations |
| `tests/agent/` | Namespacing edge cases, tool router, approval gate, planner, degradation (crash and timeout), end-to-end integration |
| `tests/security/` | Injection guard, permissions |
| `tests/fixtures/` | `mock_mcp_server.py`, a fake server with crash and hang modes |

---

## Debugging with MCP Inspector

Test any server in isolation, without the agent:

```bash
./scripts/run_inspector.sh database
# equivalent to:
npx @modelcontextprotocol/inspector python -m servers.database_server.server
```

---

## Troubleshooting

| Problem | Likely cause / fix |
|---|---|
| `Tool name invalid` from the API | Tool names must match `^[a-zA-Z0-9_-]{1,64}$`. Check `namespace.py` output. |
| Server shows as down | Run it alone with the Inspector and check stderr. Stdio servers must never print to stdout. |
| `attempt to write a readonly database` | Expected for `run_query`. Use `insert_record` (requires approval). |
| HTTP server returns 401 | `HTTP_SERVER_TOKEN` mismatch between server and registry entry. |
| Agent picks the wrong tool | Improve the tool's name, description, and input schema; the LLM selects by these. |
| Too many tools in context | Tune `tool_selector.py` or narrow the registry. |

---

## Contributing

1. Fork the repo and create a feature branch
2. Add or update tests
3. Run `pytest`
4. Open a pull request describing the change

To add a new server: create it under `servers/`, annotate every tool, document it in `docs/server_catalog.md`, and add it to `registry/servers.json`.

---

## License

MIT