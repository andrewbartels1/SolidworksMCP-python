# Agent Invocation Reference — Quick Patterns

This is a reference guide showing exactly how to invoke agents with full logging, including copy-paste command templates.

## Quick Copy-Paste Setup

### Template 1: One-Off Design Session

```powershell
# Step 1: Set env vars
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "SESSION_NAME_HERE"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "SESSION_NAME_HERE"

# Example:
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "baseball-bat-rebuild"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "bat-initial"

# Step 2: Start server
.\dev-commands.ps1 dev-run

# Step 3: In VS Code Copilot Chat, ask:
# @solidworks-part-reconstructor: Open the Baseball Bat sample, 
# classify the feature family, and show me the first 10 tool calls 
# needed to rebuild it.
```

### Template 2: Multi-Turn Interactive Session

```powershell
# Terminal 1: Start server with logging
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "u-joint-assembly"
.\dev-commands.ps1 dev-run

# Terminal 2: Run interactive script
.\.venv\Scripts\python.exe .\scripts\interactive_design.py
```

**interactive_design.py:**

```python
import os
from src.solidworks_mcp.agents import (
    insert_conversation_event,
    find_run_timeline,
)

session_id = "u-joint-assembly"
os.environ["SOLIDWORKS_MCP_ENABLE_DB_LOGGING"] = "true"
os.environ["SOLIDWORKS_MCP_CONVERSATION_ID"] = session_id

for pass_num in range(1, 3):
    run_id = f"ujoint-pass-{pass_num}"
    os.environ["SOLIDWORKS_MCP_RUN_ID_PREFIX"] = run_id
    
    print(f"\n=== Pass {pass_num} ===")
    print("Use Claude Code to run tool calls.")
    print(f"Session ID: {session_id}")
    print(f"Run ID: {run_id}")
    
    input("Press Enter when done with this pass...")
    
    timeline = find_run_timeline(run_id)
    print(f"Logged {len(timeline['events'])} events in pass {pass_num}.")
```

### Template 3: Batch Test of Sample Parts

```powershell
# Test all sample parts with logging
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"

@("Paper Airplane", "Baseball Bat", "U-Joint\pin") | ForEach-Object {
    $part_name = $_
    $env:SOLIDWORKS_MCP_CONVERSATION_ID = "batch-test-$part_name"
    $env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "classify-$part_name"
    
    Write-Host "Testing: $part_name"
    .\.venv\Scripts\python.exe -c `
        "from src.solidworks_mcp.agents import find_conversation_events; `
         print(f'Logged: {len(find_conversation_events(\"batch-test-$part_name\"))} events')"
}
```

---

## Agent Invocation by Use Case

### Use Case 1: Classify and Plan (No Execution)

**Goal:** Inspect a part, classify it, and get a step-by-step plan *without* executing.

**Prompt in Claude Code:**

```
@solidworks-part-reconstructor

I have a part file open: C:\path\to\my_part.SLDPRT

1. Run: open_model, get_model_info, list_features, get_mass_properties, classify_feature_tree
2. Based on the classification result, tell me the recommended workflow (direct-mcp, vba-backed, or assembly-planning)
3. Propose the first 5–10 reconstruction steps
4. Do NOT execute any modeling commands yet.
```

**Logging context:**

```powershell
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "classify-my-part"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "classify-phase"
```

**Query results:**

```python
from src.solidworks_mcp.agents import find_run_timeline

timeline = find_run_timeline("classify-phase-001")
for evt in timeline['events']:
    if evt['event_type']  == 'tool':
        print(f"{evt['tool_name']}: {evt['phase']}")
# Output:
# open_model: pre
# open_model: post
# get_model_info: pre
# get_model_info: post
# list_features: pre
# list_features: post
# classify_feature_tree: pre
# classify_feature_tree: post
```

### Use Case 2: Execute Direct-MCP Build (Simple Parts)

**Goal:** Rebuild Baseball Bat (revolve family) using direct MCP tools.

**Logging setup:**

```powershell
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "baseball-bat-rebuild-v2"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "bat-rebuild"
```

**Prompt in Claude Code:**

```
@solidworks-part-reconstructor

I want to rebuild the Baseball Bat sample part using classifier-backed workflow.

1. Open the original and run all inspect tools (list_features, get_mass_properties, classify_feature_tree)
2. Based on the classifier output, confirm it's a revolve family
3. Generate a complete tool-call sequence to rebuild it from scratch
4. Execute each step and confirm success before continuing
5. Export an image and compare to the original
```

**Query the build log:**

```python
from src.solidworks_mcp.agents import find_run_timeline

timeline = find_run_timeline("bat-rebuild-001")
print(f"Total events: {len(timeline['events'])}")

# Count tool phases
phases = {}
for evt in timeline['events']:
    if evt['event_type'] == 'tool':
        phase = evt['phase']
        phases[phase] = phases.get(phase, 0) + 1

print(f"Tool call phases: {phases}")
```

### Use Case 3: VBA-Backed Workflow (Complex Parts)

**Goal:** Rebuild Paper Airplane (sheet metal) using VBA-aware delegation.

**Logging setup:**

```powershell
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "paper-airplane-vba-session"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "airplane-vba"
```

**Prompt in Claude Code:**

```
@solidworks-part-reconstructor

The Paper Airplane is a sheet metal part. I want to rebuild it preserving the sheet metal workflow.

1. Open the original and classify it
2. Verify the classifier says: family=sheet_metal, workflow=vba-sheet-metal
3. Generate a VBA-aware reconstruction plan that preserves:
   - The base-flange root feature
   - All bend and edge-flange dependencies
   - Unfold/Fold state transitions
4. Use generate_vba_part_modeling for any unsupported direct-MCP operations
5. Do NOT simplify this into a flat plate extrusion
```

**Query for VBA calls:**

```python
from src.solidworks_mcp.agents import find_run_timeline

timeline = find_run_timeline("airplane-vba-001")

# Find all VBA-related tool calls
for evt in timeline['events']:
    if evt['event_type'] == 'tool' and 'vba' in evt['tool_name'].lower():
        print(f"{evt['tool_name']}: {evt['phase']}")
```

### Use Case 4: Print-Ready Design (3D Printing Workflow)

**Goal:** Design a snap-fit enclosure cover from scratch with printability validation.

**Logging setup:**

```powershell
$env:SOLIDWORKS_MCP_ENABLE_DB_LOGGING = "true"
$env:SOLIDWORKS_MCP_CONVERSATION_ID = "snapfit-cover-design"
$env:SOLIDWORKS_MCP_RUN_ID_PREFIX = "cover-design"
```

**Prompt in Claude Code:**

```
@solidworks-print-architect

I want to design a snap-fit battery cover for a 3D printer.

Dimensions:
- Base: 80 mm × 60 mm
- Height: 20 mm (including 2 mm wall thickness)
- Snap tabs: four corners, 2 mm thick, 3 mm high
- Material: PETG (bridge friendly, 0.2 mm layers)

1. Create the part geometry using direct MCP (extrude, fillets)
2. Check printability: wall thickness, overhangs, bridge length
3. If any issue is detected, propose a design modification
4. Export STL ready for slicing

Do not execute yet — show me the plan first.
```

**Query the tool sequence:**

```python
from src.solidworks_mcp.agents import find_run_timeline

timeline = find_run_timeline("cover-design-001")

print("=== Tool Sequence ===")
for i, evt in enumerate(timeline['events'], 1):
    if evt['event_type'] == 'tool' and evt['phase'] == 'post':
        print(f"{i:2d}. {evt['tool_name']}")
```

---

## Common Agent Patterns

### Pattern A: Inspect → Classify → Plan Approval → Execute

Used for high-confidence workflows where classification is the decision gate.

```python
session_id = "my-workflow"
os.environ["SOLIDWORKS_MCP_CONVERSATION_ID"] = session_id

# Phase 1: Inspect
run_id = "phase-1-inspect"
insert_conversation_event(
    conversation_id=session_id,
    run_id=run_id,
    event_type="user_message",
    role="user",
    content_snippet="Inspect and classify the part.",
)
# User/agent runs: open_model, get_model_info, list_features, classify_feature_tree

timeline = find_run_timeline(run_id)
# Extract classification result from payload_json

# Phase 2: Plan (use classification output)
run_id = "phase-2-plan"
insert_conversation_event(
    conversation_id=session_id,
    run_id=run_id,
    event_type="user_message",
    role="user",
    content_snippet="Based on revolve classification, propose the build sequence.",
)
# Agent reads classifier result and generates a plan

# Phase 3: User approval
user_approval = input("Approve plan? (y/n): ")
if user_approval.lower() == "y":
    # Phase 4: Execute
    run_id = "phase-4-execute"
    # Agent runs all tool calls
```

### Pattern B: Multi-Pass Refinement

Used when geometry needs iteration or error recovery.

```python
session_id = "multi-pass-rebuild"

for pass_num in range(1, 4):
    run_id = f"pass-{pass_num}"
    os.environ["SOLIDWORKS_MCP_RUN_ID_PREFIX"] = run_id
    
    insert_conversation_event(
        conversation_id=session_id,
        run_id=run_id,
        event_type="user_message",
        role="user",
        content_snippet=f"Pass {pass_num}: Refine geometry based on feedback.",
    )
    
    # User interacts via Claude Code
    
    timeline = find_run_timeline(run_id)
    if timeline['events']:  # Check what happened
        error_count = sum(1 for e in timeline['events'] if e['event_type'] == 'error')
        if error_count > 0:
            print(f"Pass {pass_num}: {error_count} errors detected.")
        else:
            print(f"Pass {pass_num}: Success.")
```

### Pattern C: Assembly + Part Reconstruction

Used when both part and assembly steps are needed.

```python
session_id = "u-joint-assembly"

# Part 1: Build individual parts
for part_name in ["pin", "yoke", "cross"]:
    run_id = f"part-{part_name}"
    os.environ["SOLIDWORKS_MCP_RUN_ID_PREFIX"] = run_id
    
    insert_conversation_event(
        conversation_id=session_id,
        run_id=run_id,
        event_type="user_message",
        role="user",
        content_snippet=f"Build U-Joint {part_name} part.",
    )

# Part 2: Assemble
run_id = "assembly-build"
os.environ["SOLIDWORKS_MCP_RUN_ID_PREFIX"] = run_id

insert_conversation_event(
    conversation_id=session_id,
    run_id=run_id,
    event_type="user_message",
    role="user",
    content_snippet="Insert parts into assembly and add mates.",
)

# Query entire session
all_events = find_conversation_events(session_id)
print(f"Full session: {len(all_events)} events across {len(set(e['run_id'] for e in all_events if e['run_id']))} runs.")
```

---

## Debugging Tips

### See What Happened in the Last Run

```python
from src.solidworks_mcp.agents import find_run_timeline
import os

run_id = os.getenv("SOLIDWORKS_MCP_RUN_ID_PREFIX", "run") + "-001"
timeline = find_run_timeline(run_id)

for evt in timeline['events']:
    evt_str = f"{evt['timestamp']}: {evt['event_type']}"
    if evt['event_type'] == 'tool':
        evt_str += f" | {evt['tool_name']} ({evt['phase']})"
    print(evt_str)
```

### Export Session for Code Review

```python
import json
from pathlib import Path
from src.solidworks_mcp.agents import find_conversation_events

session_id = "hockey-stick-design"
events = find_conversation_events(session_id)

output = Path(f"{session_id}_audit.json")
output.write_text(json.dumps(events, indent=2))
print(f"Exported {len(events)} events to {output}")
```

### Verify Logging is Active

```python
from pathlib import Path
from src.solidworks_mcp.agents import init_db

db = Path(".solidworks_mcp/agent_memory.sqlite3")
if db.exists():
    init_db(db)
    print(f"✅ DB exists: {db.stat().st_size} bytes")
    
    from sqlmodel import Session, create_engine, select
    from src.solidworks_mcp.agents.history_db import ConversationEvent
    
    engine = create_engine(f"sqlite:///{db}")
    with Session(engine) as session:
        count = len(session.exec(select(ConversationEvent)).all())
    print(f"✅ ConversationEvent rows: {count}")
else:
    print("❌ DB not found. Set SOLIDWORKS_MCP_ENABLE_DB_LOGGING=true")
```

---

## Next Steps

- [Logging Configuration Guide](./logging-and-agent-invocation.md) — Full reference for all env vars and query patterns
- [Worked Examples](./worked-examples.md) — End-to-end examples with logging context
- [Prompting Best Practices](../user-guide/prompting-best-practices.md) — How to write clear, audit-friendly prompts
