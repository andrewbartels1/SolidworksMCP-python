<!-- filepath: docs/user-guide/LOGGING_AND_AGENTS_SUMMARY.md -->

# Logging and Agent Invocation — Implementation Summary

This document summarizes the three components added to support full conversation and tool-event logging for reproducible SolidWorks design workflows.

## What Was Added

### 1. ConversationEvent Data Model and DB Layer

**File:** [src/solidworks_mcp/agents/history_db.py](../../src/solidworks_mcp/agents/history_db.py)

Added:

- `ConversationEvent` SQLModel table to store message and system events
- `insert_conversation_event(...)` function for recording messages, tool calls, and decisions
- `find_conversation_events(conversation_id, ...)` function to retrieve all events for a conversation
- `find_run_timeline(run_id, ...)` function to reconstruct a complete timeline for one run by joining `AgentRun`, `ToolEvent`, and `ConversationEvent` records

**Why:** Tool telemetry alone cannot capture the reasoning behind decisions. Conversation events let you see *why* a particular tool was chosen and what context the human provided.

### 2. Tests for New Functionality

**File:** [tests/test_agents_conversation_events.py](../../tests/test_agents_conversation_events.py)

Coverage:

- ✅ 13 tests, all passing
- Insert and query conversation events
- Timeline reconstruction and chronological ordering
- Edge cases (empty runs, missing conversations)

**Run tests:**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_agents_conversation_events.py -v
```

### 3. User Documentation

#### [logging-and-agent-invocation.md](./logging-and-agent-invocation.md)

Comprehensive reference covering:

- **Quick start** — 60-second setup with env vars
- **MCP tool telemetry** — what's captured, lifecycle phases, examples
- **Conversation event logging** — when and how to log decisions
- **Querying and reconstruction** — Python code patterns to replay sessions
- **Best practices** — meaningful IDs, boundaries, audit trails
- **Troubleshooting** — common issues and fixes

**Read this first if setting up logging.**

#### [agent-invocation-reference.md](./agent-invocation-reference.md)

Quick-reference guide with:

- **Copy-paste setup templates** for one-off, multi-turn, and batch scenarios
- **Use case examples:**
  - Classify and plan (no execution)
  - Execute direct-MCP build
  - VBA-backed workflow
  - 3D printing design with validation
- **Common agent patterns** — Inspect→Classify→Plan→Execute, multi-pass, assembly workflows
- **Debugging tips** — query last run, export for code review, verify active logging

**Use this to find your exact scenario and copy the pattern.**

---

## Architecture: Three-Layer Logging

```
┌─────────────────────────────────────────────────────────┐
│ Host / Editor / VS Code Copilot Chat                    │
│ (User interactions, chat turns, critiques)              │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ (optional, logged via insert_conversation_event)
                   ↓
┌─────────────────────────────────────────────────────────┐
│ Application Layer                                       │
│ - Your agent/worker scripts                            │
│ - Design session logic                                 │
│ - Insert ConversationEvent on decision boundaries      │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ (automatic via tool wrapper)
                   ↓
┌─────────────────────────────────────────────────────────┐
│ MCP Server Tool Wrapper                                 │
│ - Logs tool lifecycle (pre/post/error)                 │
│ - Automatic ToolEvent insertion                        │
│ - Guarded, non-blocking errors                         │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────────────────┐
│ SQLModel DB Layer                                       │
│ - AgentRun (session/run metadata)                       │
│ - ToolEvent (tool lifecycle + payload)                 │
│ - ConversationEvent (message + metadata)               │
│ - ErrorCatalog (failure modes + remediation)           │
│                                                         │
│ Location: .solidworks_mcp/agent_memory.sqlite3         │
└─────────────────────────────────────────────────────────┘
```

**Key insight:** Tool telemetry is automatic (thanks to server-side logging). Conversation events are optional but recommended for full audit trails.

---

## Environment Variables for Logging

| Variable | Purpose | Default |
|---|---|---|
| `SOLIDWORKS_MCP_ENABLE_DB_LOGGING` | Enable all DB logging | `false` |
| `SOLIDWORKS_MCP_CONVERSATION_ID` | Unique session identifier | auto-generated UUID |
| `SOLIDWORKS_MCP_RUN_ID_PREFIX` | Prefix for per-phase run IDs | `run` |
| `SOLIDWORKS_MCP_DB_PATH` | Override DB location | `.solidworks_mcp/agent_memory.sqlite3` |

**Set in PowerShell before starting MCP server:**

```powershell
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "my-design-session"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "my-design-session"

.\dev-commands.ps1 dev-run
```

---

## Common Workflows

### Workflow 1: Inspect→Classify→Plan (No Execution)

```python
# Set env vars, then in Claude Code:
# 
# 1. open_model(...sample.SLDPRT)
# 2. get_model_info(), list_features(), classify_feature_tree()
# 3. Based on output, propose next steps (do NOT run yet)

# Later, query:
from src.solidworks_mcp.agents import find_run_timeline
timeline = find_run_timeline("my-run-id")
for evt in timeline['events']:
    print(f"{evt['timestamp']}: {evt['event_type']}")
```

### Workflow 2: Multi-Turn Interactive Build

```python
# Terminal 1: Start server with logging
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "baseball-bat-rebuild"
.\dev-commands.ps1 dev-run

# Terminal 2: Run design loop
for i in 1..5:
    $env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "bat-pass-$i"
    Write-Host "Pass $i: Use Claude Code to run tools"
    Read-Host "Press Enter when done"
    
    # Query progress:
    .\.venv\Scripts\python.exe -c "
from src.solidworks_mcp.agents import find_run_timeline
t = find_run_timeline('bat-pass-$i')
print(f'Pass $i: {len(t[\"events\"])} events')
    "
done
```

### Workflow 3: Full Session Audit

```python
import json
from pathlib import Path
from src.solidworks_mcp.agents import (
    find_conversation_events,
    find_run_timeline,
)

# Export everything
session_id = "my-session"
events = find_conversation_events(session_id)
run_ids = set(e.get('run_id') for e in events if e.get('run_id'))

audit = {
    "session_id": session_id,
    "event_count": len(events),
    "runs": {rid: find_run_timeline(rid) for rid in run_ids},
}

Path("session_audit.json").write_text(json.dumps(audit, indent=2))
print(f"Exported {len(events)} events from {len(run_ids)} runs")
```

---

## How to Log Conversation Events in Your Code

### From a Python Script

```python
from src.solidworks_mcp.agents import insert_conversation_event
import os

session_id = os.getenv("SOLIDWORKS_MCP_CONVERSATION_ID", "default")
run_id = os.getenv("SOLIDWORKS_MCP_RUN_ID_PREFIX", "run") + "-001"

# Log a user request
insert_conversation_event(
    conversation_id=session_id,
    run_id=run_id,
    event_type="user_message",
    role="user",
    content_snippet="Open the U-Joint pin sample and inspect it.",
)

# Log a classification result
insert_conversation_event(
    conversation_id=session_id,
    run_id=run_id,
    event_type="system_event",
    role="system",
    content_snippet="Classification: revolve family, confidence=high",
    metadata_json='{"family": "revolve", "confidence": "high", "next_action": "direct_mcp"}',
)

# Log the plan
insert_conversation_event(
    conversation_id=session_id,
    run_id=run_id,
    event_type="assistant_message",
    role="assistant",
    content_snippet="Plan: 1. create_part 2. create_sketch 3. add_centerline ...",
)
```

### From Claude Code (VS Code Copilot)

Logging is **automatic** for tool calls. To log decisions, in your agent prompt ask:

```
@solidworks-part-reconstructor

Before building, log your classification decision:

classification_result = {
    "family": "...",
    "confidence": "...",
    "evidence": "...",
    "recommended_workflow": "..."
}

Then show me the first 5 tool calls you'd use to rebuild this part.
```

(The tool calls are automatically logged to the DB. Decisions can be captured by you calling `insert_conversation_event` in your workflow.)

---

## Querying — Key Functions

### Find All Events for a Conversation

```python
from src.solidworks_mcp.agents import find_conversation_events

events = find_conversation_events("my-session-id")
for evt in events:
    print(f"{evt['created_at']} | {evt['role']}: {evt['content_snippet']}")
```

### Reconstruct Timeline for One Run

```python
from src.solidworks_mcp.agents import find_run_timeline

timeline = find_run_timeline("my-run-id")
print(f"Agent: {timeline['run_info']['agent_name']}")
print(f"Status: {timeline['run_info']['status']}")

for evt in timeline['events']:
    print(f"  {evt['timestamp']}: {evt['event_type']}")
    if evt['event_type'] == 'tool':
        print(f"    > {evt['tool_name']} ({evt['phase']})")
```

### Count Tool Calls by Name

```python
from src.solidworks_mcp.agents import find_run_timeline
from collections import Counter

timeline = find_run_timeline("run-id")
tools_used = Counter(
    evt['tool_name'] for evt in timeline['events'] 
    if evt['event_type'] == 'tool' and evt['phase'] == 'post'
)

for tool, count in tools_used.most_common(10):
    print(f"{tool}: {count} calls")
```

---

## Troubleshooting

| Issue | Check | Fix |
|---|---|---|
| Logs not being written | `$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING` | Set to `"true"` |
| Can't find conversation | `$env:SOLIDWORKS_MCP_CONVERSATION_ID` | Use same ID in queries |
| DB file doesn't exist | DB path permissions | Ensure `.solidworks_mcp/` is writable |
| Query returns empty | Logging was disabled during run | Restart server with logging enabled |

---

## Next Steps

1. **Set env vars and try it:** Follow the Quick Start in [logging-and-agent-invocation.md](./logging-and-agent-invocation.md)
2. **Pick your use case:** Find it in [agent-invocation-reference.md](./agent-invocation-reference.md) and copy the template
3. **Query your session:** Use `find_conversation_events()` and `find_run_timeline()` to see what happened
4. **Export for audit:** Use the JSON export pattern for compliance or training data

---

## Files Changed / Added

| Path | Type | Purpose |
|---|---|---|
| `src/solidworks_mcp/agents/history_db.py` | Modified | Added ConversationEvent table and query functions |
| `src/solidworks_mcp/agents/__init__.py` | Modified | Exported new conversation event functions |
| `tests/test_agents_conversation_events.py` | New | 13 comprehensive tests (all passing) |
| `docs/user-guide/logging-and-agent-invocation.md` | New | Full reference guide |
| `docs/user-guide/agent-invocation-reference.md` | New | Quick-reference patterns and use cases |

---

## API Summary

### Database Schema

```python
# Tables in .solidworks_mcp/agent_memory.sqlite3

class AgentRun(SQLModel, table=True):
    """Metadata for one agent run."""
    run_id: str
    agent_name: str
    prompt: str
    status: str
    output_json: str | None
    model_name: str | None
    created_at: str

class ToolEvent(SQLModel, table=True):
    """One tool lifecycle event."""
    run_id: str
    tool_name: str
    phase: str  # "pre", "execution", "post", "error"
    payload_json: str | None
    created_at: str

class ConversationEvent(SQLModel, table=True):
    """One message or system event."""
    conversation_id: str
    run_id: str | None
    event_type: str  # "user_message", "assistant_message", "system_event", "tool_call"
    role: str | None  # "user", "assistant", "system"
    content_snippet: str  # truncated for privacy
    metadata_json: str | None
    created_at: str

class ErrorCatalog(SQLModel, table=True):
    """Persisted error records for recovery."""
    run_id: str | None
    source: str
    tool_name: str
    error_type: str
    error_message: str
    root_cause: str
    remediation: str
    created_at: str
```

### Key Functions

```python
# Insert events
insert_conversation_event(
    conversation_id: str,
    event_type: str,
    content_snippet: str,
    role: str | None = None,
    run_id: str | None = None,
    metadata_json: str | None = None,
    db_path: Path | None = None,
) -> None

# Query events
find_conversation_events(
    conversation_id: str,
    db_path: Path | None = None,
) -> list[dict[str, Any]]

# Reconstruct timeline
find_run_timeline(
    run_id: str,
    db_path: Path | None = None,
) -> dict[str, Any]
```

---

## Design Rationale

### Why Separate Layers?

1. **MCP tool telemetry** is automatic and reliable — you get it just by enabling logging.
2. **Conversation events** are optional and intentional — you log when a decision matters.
3. Together they form a complete audit trail: *what* was done and *why*.

### Why ConversationEvent?

- Preserves *context* alongside tool calls (message role, reasoning, feedback).
- Links to both conversation and run for flexible querying.
- Supports privacy: you can truncate content_snippet and store full text elsewhere.
- Extensible: metadata_json field allows per-event custom data.

### Why Timestamps and Chronological Ordering?

- Reproducible sessions require causality: "did the user feedback come before or after the tool error?"
- Chronological ordering lets you replay events as a narrative instead of a list.
- Helps with debugging: "at what point did things diverge?"

---

## For More Information

- **[Logging and Agent Invocation](./logging-and-agent-invocation.md)** — Full reference with all env vars, query patterns, and best practices
- **[Agent Invocation Reference](./agent-invocation-reference.md)** — Copy-paste templates for your use case
- **[Worked Examples](./worked-examples.md)** — Inspect-classify-delegate patterns (next step: add logging context)
- **[Agents and Testing](../getting-started/agents-and-testing.md)** — Schema validation and agent harness docs
