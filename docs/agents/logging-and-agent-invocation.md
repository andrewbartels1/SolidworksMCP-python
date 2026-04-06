# Logging Configuration and Agent Invocation Guide

This guide explains how to enable, configure, and use the logging infrastructure for SolidWorks MCP tool execution and multi-turn conversational design workflows.

## Overview

The logging system has **two layers**:

| Layer | Purpose | Capture Source | Scope |
|---|---|---|---|
| **MCP Tool Telemetry** | Log every SolidWorks tool call, phase transition, and error | MCP server wrapper | Tool lifecycle: pre → execution → post / error |
| **Conversation Events** | Log chat messages, system events, and decision points | Host/editor or external caller | Full message flow between human and LLM |

**For reproducible CAD work, you need both layers.** The tool telemetry ensures you can replay and debug every SolidWorks action. The conversation events let you reconstruct why a particular tool was chosen and what context the human provided.

---

## Quick Start: Enable Logging in 60 Seconds

### Step 1 — Set Environment Variables

```powershell
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "my-design-session-001"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "bracket-rebuild"
```

### Step 2 — Start the Server

```powershell
.\dev-commands.ps1 dev-run
```

The server uses the variables above for every tool call.

### Step 3 — Use the Agent

Work with Claude Code or VS Code Copilot as normal. Every tool call is logged.

### Step 4 — Query What Happened

```python
from src.solidworks_mcp.agents import find_run_timeline, find_conversation_events

# See all events in one run
timeline = find_run_timeline("bracket-rebuild-001")
print(timeline)

# See all conversation events linked to that session
events = find_conversation_events("my-design-session-001")
for event in events:
    print(f"[{event['created_at']}] {event['role']}: {event['content_snippet']}")
```

---

## Environment Variables Reference

### Logging Control

| Variable | Values | Effect | Default |
|---|---|---|---|
| `SOLIDWORKS_MCP_ENABLE_DB_LOGGING` | `"true"` / `"false"` | Enable/disable all DB logging | `"false"` |
| `SOLIDWORKS_MCP_CONVERSATION_ID` | any string | Conversation context ID (e.g., "baseball-bat-rebuild") | auto-generated |
| `SOLIDWORKS_MCP_RUN_ID_PREFIX` | any string | Prefix for per-tool-batch run IDs (e.g., "sketch-pass-1") | `"run"` |
| `SOLIDWORKS_MCP_DB_PATH` | file path | Override default DB location | `.solidworks_mcp/agent_memory.sqlite3` |

### Example Full Setup

```powershell
# Long-running design session — log everything
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "u-joint-yoke-design-session"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "yoke-feature-pass"
$env:SOLIDWORKS_MCP_DB_PATH = "c:\temp\design_telemetry.sqlite3"

# Run server and agent
.\dev-commands.ps1 dev-run
```

---

## MCP Tool Telemetry — What Gets Logged

### Automatic Logging on Tool Wrapper

Every call to an MCP tool is wrapped with logging. You get this for free once `SOLIDWORKS_MCP_ENABLE_DB_LOGGING=true`.

#### What is captured

```json
{
  "run_id": "yoke-feature-pass-001",
  "tool_name": "create_sketch",
  "phase": "pre",
  "payload_json": {"plane": "Front"},
  "created_at": "2026-04-04T23:52:23.759570+00:00"
}
```

**Phases:**

- `pre` — input validation and pre-execution setup
- `execution` — tool running (usually empty payload, just a marker)
- `post` — success, output captured
- `error` — exception caught, error details in payload

#### Example — Complete Tool Lifecycle

```
tool_event: run_id=sketch-pass-001, tool=create_sketch, phase=pre, payload={plane: "Front"}
tool_event: run_id=sketch-pass-001, tool=create_sketch, phase=execution
tool_event: run_id=sketch-pass-001, tool=create_sketch, phase=post, payload={sketch_id: "Sketch1"}

tool_event: run_id=sketch-pass-001, tool=add_circle, phase=pre, payload={...}
tool_event: run_id=sketch-pass-001, tool=add_circle, phase=post, payload={...}

tool_event: run_id=sketch-pass-001, tool=exit_sketch, phase=pre
tool_event: run_id=sketch-pass-001, tool=exit_sketch, phase=post
```

---

## Conversation Event Logging — Your Layer

You (or the host editor) log conversation events when you want to record:

- User questions or critiques
- LLM planning steps and reasoning
- Classification results and branch decisions
- Human-bot interaction patterns

### Adding Conversation Events from Your Prompt

In Claude Code or a custom agent script:

```python
from src.solidworks_mcp.agents import insert_conversation_event
import os

conversation_id = os.getenv("SOLIDWORKS_MCP_CONVERSATION_ID", "default-session")
run_id = os.getenv("SOLIDWORKS_MCP_RUN_ID_PREFIX", "run") + "-001"

# Log the user's request
insert_conversation_event(
    conversation_id=conversation_id,
    run_id=run_id,
    event_type="user_message",
    role="user",
    content_snippet="Open the U-Joint pin sample and classify it first.",
)

# Log the classification result
insert_conversation_event(
    conversation_id=conversation_id,
    run_id=run_id,
    event_type="system_event",
    role="system",
    content_snippet="Classification: revolve family, confidence=high, workflow=direct-mcp-revolve",
    metadata_json='{"family": "revolve", "confidence": "high"}',
)

# Log the plan the LLM proposes
insert_conversation_event(
    conversation_id=conversation_id,
    run_id=run_id,
    event_type="assistant_message",
    role="assistant",
    content_snippet="1. create_part(name=pin_rebuild) 2. create_sketch(plane=Front) ...",
)
```

### When to Log Conversation Events

| When | What | Why |
|---|---|---|
| After receiving a user prompt | User request snippet | Understand user intent |
| After classifier runs | Classification result + evidence | Know why a workflow was chosen |
| Before presenting a plan | Plan summary | Replay the decision process |
| After user feedback | Critique or correction | Learn from human input |
| On tool error | Error message + remediation | Capture failure context |

---

## Querying and Reconstructing Sessions

### Query 1 — Get the Timeline for One "Work Session"

```python
from src.solidworks_mcp.agents import find_run_timeline
import json

run_id = "bracket-rebuild-001"
timeline = find_run_timeline(run_id)

print(f"Run: {timeline['run_info']['agent_name']}")
print(f"Status: {timeline['run_info']['status']}")
print(f"Model: {timeline['run_info']['model_name']}")
print(f"\nEvents ({len(timeline['events'])} total):")

for evt in timeline['events']:
    print(f"  [{evt['timestamp']}] {evt['event_type']}: {evt.get('tool_name') or evt.get('role')}")
```

**Output:**

```
Run: solidworks-print-architect.agent.md
Status: success
Model: github:openai/gpt-4.1

Events (47 total):
  [2026-04-04T23:52:10.000+00:00] message: user
  [2026-04-04T23:52:11.000+00:00] tool: create_part
  [2026-04-04T23:52:12.000+00:00] tool: create_sketch
  [2026-04-04T23:52:13.000+00:00] tool: add_circle
  ...
```

### Query 2 — Get All Conversation Events in a Session

```python
from src.solidworks_mcp.agents import find_conversation_events

conversation_id = "my-design-session-001"
events = find_conversation_events(conversation_id)

for evt in events:
    role = evt['role'] or evt['event_type']
    snippet = evt['content_snippet'][:80]
    print(f"[{evt['created_at']}] {role}: {snippet}...")
```

### Query 3 — Export Full Log for Audit or Training

```python
import json
from pathlib import Path
from src.solidworks_mcp.agents import find_conversation_events, find_run_timeline

conversation_id = "u-joint-rebuild"
events = find_conversation_events(conversation_id)
run_ids = set(e.get('run_id') for e in events if e.get('run_id'))

full_log = {
    "conversation_id": conversation_id,
    "event_count": len(events),
    "run_count": len(run_ids),
    "runs": {}
}

for run_id in run_ids:
    full_log['runs'][run_id] = find_run_timeline(run_id)

output_file = Path("design_session_audit.json")
output_file.write_text(json.dumps(full_log, indent=2))
print(f"Exported to {output_file}")
```

---

## Agent Invocation — How to Invoke with Logging Enabled

### Pattern 1 — Simple Script with Source of Truth

Use this for reproducible, auditable design workflows.

```python
# File: rebuild_baseball_bat.py
import os
from src.solidworks_mcp.agents import (
    insert_conversation_event,
    find_run_timeline,
)

# Setup logging context
conversation_id = "baseball-bat-rebuild-session"
run_id = "bat-initial-build"

os.environ["SOLIDWORKS_MCP_ENABLE_DB_LOGGING"] = "true"
os.environ["SOLIDWORKS_MCP_CONVERSATION_ID"] = conversation_id
os.environ["SOLIDWORKS_MCP_RUN_ID_PREFIX"] = run_id

# Log your intent
insert_conversation_event(
    conversation_id=conversation_id,
    run_id=run_id,
    event_type="user_message",
    role="user",
    content_snippet="Rebuild Baseball Bat from the sample library using revolve.",
)

# Now invoke the agent (or have the user interact via Claude Code)
# Tool calls are automatically logged thanks to the env vars above

# Later, reconstruct what happened
print("\n=== Build Timeline ===")
timeline = find_run_timeline(run_id)
for evt in timeline["events"]:
    print(f"  {evt['timestamp']}: {evt['event_type']}")
```

### Pattern 2 — Multi-Turn Interactive Loop

Use this when human feedback and correction happen in cycles.

```python
# File: interactive_design_session.py
import os
from pathlib import Path
from src.solidworks_mcp.agents import (
    insert_conversation_event,
    find_run_timeline,
    find_conversation_events,
)

session_id = "u-joint-interactive"
os.environ["SOLIDWORKS_MCP_ENABLE_DB_LOGGING"] = "true"
os.environ["SOLIDWORKS_MCP_CONVERSATION_ID"] = session_id

for iteration in range(1, 4):
    run_id = f"u-joint-iteration-{iteration}"
    os.environ["SOLIDWORKS_MCP_RUN_ID_PREFIX"] = run_id

    # Phase 1: Inspect
    insert_conversation_event(
        conversation_id=session_id,
        run_id=run_id,
        event_type="user_message",
        role="user",
        content_snippet=f"Iteration {iteration}: Inspect U-Joint pin and classify.",
    )

    # User interacts via Claude Code here
    # MCP auto-logs tool calls

    # Phase 2: Get feedback
    user_feedback = input(f"Iteration {iteration} feedback: ").strip()
    
    if user_feedback:
        insert_conversation_event(
            conversation_id=session_id,
            run_id=run_id,
            event_type="user_message",
            role="user",
            content_snippet=user_feedback,
        )

    # Phase 3: Show summary
    timeline = find_run_timeline(run_id)
    print(f"\n  Iteration {iteration}: {len(timeline['events'])} events logged")

# Final: Export the full session log
print("\n=== Full Session Log ===")
all_events = find_conversation_events(session_id)
print(f"Total events: {len(all_events)}")
for evt in all_events[-5:]:  # Show last 5
    print(f"  {evt['role']}: {evt['content_snippet'][:60]}...")
```

### Pattern 3 — VS Code Copilot Chat Integration

When using Claude Code or VS Code Copilot, logging is automatic if you set env vars in your terminal before starting SolidWorks MCP server.

**Setup:**

```powershell
# Terminal where you'll run the MCP server
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "copilot-session-1"

# Start MCP server
.\dev-commands.ps1 dev-run
```

**In VS Code Copilot Chat:**

```
@Claude, I want to rebuild the Baseball Bat sample.

1. First, inspect the original sample and classify the feature family.
2. Tell me the recommended workflow.
3. Show the first 5 tool calls we should make.
```

All tool calls are automatically logged to the database with:

- `conversation_id = "copilot-session-1"`
- `run_id = auto-generated`
- `phase = pre/post/error`

**Later, query:**

```python
from src.solidworks_mcp.agents import find_conversation_events

events = find_conversation_events("copilot-session-1")
print(f"Copilot session captured {len(events)} events.")
```

---

## Best Practices

### 1. Always Set CONVERSATION_ID

```powershell
# ✅ Good
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "u-joint-assembly-design"

# ❌ Bad — defaults to UUID, hard to find later
# (don't set it at all)
```

### 2. Use Meaningful RUN_ID_PREFIX

```powershell
# ✅ Good — each phase is traceable
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "ujoint-yoke-features"

# ❌ Bad — generic, no context
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "run"
```

### 3. Log Conversation Events at Boundaries

```python
# ✅ Good — mark decision points
insert_conversation_event(
    conversation_id=conversation_id,
    event_type="system_event",
    content_snippet="classify_feature_tree returned: family=revolve, confidence=high",
)

# ❌ Bad — log everything (too noisy)
# (log at every line of reasoning)
```

### 4. Query Incrementally During Long Sessions

```python
# ✅ Good — check progress frequently
for i in range(1, 10):
    timeline = find_run_timeline(f"my-run-{i:02d}")
    print(f"Pass {i}: {len(timeline['events'])} events")

# ❌ Bad — wait until the end to query (harder to debug)
```

### 5. Export Logs After Each Major Workflow

```python
# ✅ Good — build an audit trail
import json
from pathlib import Path

events = find_conversation_events("my-session")
Path("session_log.json").write_text(json.dumps(events, indent=2))

# ❌ Bad — keep logs only in database (risk data loss)
```

---

## Troubleshooting

### Logs Are Not Being Written

**Check:**

```powershell
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING
$env:SOLIDWORKS_MCP_CONVERSATION_ID

# Should both be set
```

**Then verify the DB path:**

```powershell
ls -Path ".solidworks_mcp\agent_memory.sqlite3"
```

**If still nothing, check server startup:**

```powershell
.\dev-commands.ps1 dev-run 2>&1 | Select-String "logging"
```

### Can't Query Events

**Verify the database exists and has data:**

```python
from pathlib import Path
from src.solidworks_mcp.agents import init_db, find_conversation_events

db = Path(".solidworks_mcp") / "agent_memory.sqlite3"
if db.exists():
    print(f"DB exists: {db.stat().st_size} bytes")
    init_db(db)
    events = find_conversation_events("your-conversation-id", db_path=db)
    print(f"Found {len(events)} events")
else:
    print("DB not found — check SOLIDWORKS_MCP_DB_PATH env var")
```

### Performance: DB Locked

If you see "database is locked":

```python
# Add a short backoff
import time
from src.solidworks_mcp.agents import find_conversation_events

for attempt in range(5):
    try:
        events = find_conversation_events("my-conv")
        break
    except Exception as e:
        if "locked" in str(e):
            time.sleep(0.5 * (attempt + 1))
        else:
            raise
```

---

## See Also

- [Agents and Testing](agents-and-testing.md) — Agent CLI and schema reference
- [Worked Examples](./worked-examples.md) — Inspect-classify-delegate examples with logging context
- [Prompting Best Practices](../user-guide/prompting-best-practices.md) — How to structure prompts so logging captures good decisions
