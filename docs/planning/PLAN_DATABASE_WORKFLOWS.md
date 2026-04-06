# Database & Workflow Catalog Planning

## Current MVP Baseline (April 2026)

An initial local SQLite implementation is now available via `src/solidworks_mcp/agents/history_db.py`.

Implemented tables:

- `agent_runs`
- `tool_events`
- `error_catalog`

This provides immediate value for provenance and troubleshooting by capturing where failures originated and recommended remediation, before adding full template/replay orchestration.

**Objective**: Create a stateful workflow system that catalogs all SolidWorks MCP operations, enables workflow reuse, supports undo/redo, and provides crash recovery. This is a TODO and just planning.

## Problem Statement

Current limitations:
1. No persistent record of executed commands
2. Difficult to replay/reuse successful workflows
3. No undo capability without manual intervention
4. Server crash loses context; hard to resume
5. No way to build reusable scripts from ad-hoc AI commands

## Vision

Enable users to:
- Record successful design sequences as templates
- Replay workflows on new parts
- Branch workflows at any step
- Undo/redo individual or batch operations
- Resume interrupted sessions from state snapshot
- Export workflows as Python/VBA scripts

## Core Data Model

### Database Schema (SQLModel + SQLite)

```python
# Core entities
class Workflow(Base):
    """A named sequence of operations"""
    id: UUID
    name: str
    description: str
    tags: list[str]  # for categorization
    created_at: datetime
    updated_at: datetime
    is_template: bool  # if True, available for reuse
    icon_class: str  # for UI representation
    
class Operation(Base):
    """A single MCP tool invocation"""
    id: UUID
    workflow_id: UUID  # foreign key
    sequence_num: int  # order within workflow
    tool_name: str  # e.g., "create_part", "add_constraint"
    input_params: dict  # full input JSON
    output_result: dict  # full result JSON
    status: str  # "pending", "running", "success", "error"
    error_message: str | None
    duration_ms: int
    timestamp: datetime
    
class WorkflowSnapshot(Base):
    """Recovery point / state snapshot"""
    id: UUID
    workflow_id: UUID
    operation_id: UUID  # after which operation
    solidworks_file: dict  # {path, hash, metadata}
    session_state: dict  # server state at this point
    created_at: datetime
    is_checkpoint: bool  # user-created or auto
    
class WorkflowTemplate(Base):
    """Reusable workflow template"""
    id: UUID
    source_workflow_id: UUID  # derived from this workflow
    template_name: str
    parameter_mappings: dict  # input placeholders
    description: str
    category: str  # "bracket", "assembly", "drawing", etc.
    difficulty: str  # "beginner", "intermediate", "advanced"
    
class ExecutionHistory(Base):
    """Track all historical executions for audit/learning"""
    id: UUID
    workflow_template_id: UUID
    execution_time: datetime
    success: bool
    notes: str | None
    output_files: list[str]  # generated files
    performance_metrics: dict
```

### Database Location
```
project_root/
  .solidworks_mcp/
    data.db  # Main SQLite database
    workflows/  # Exported workflow files
      template_1.json
      template_2.json
    snapshots/  # Recovery snapshots
      snapshot_xyz_001.json
      snapshot_xyz_002.json
```

## Feature Roadmap

### Phase 1: Basic Recording & Replay (Weeks 1-2)
**Goal**: Record all MCP operations, enable simple replay

**Implementation**:
1. Create SQLModel database schema
2. Add operation logging to MCP tool handler
3. Create `replay_workflow(workflow_id)` tool
4. Add basic UI for workflow list

**Not included**:
- State snapshots
- Undo/redo
- Template parameterization

### Phase 2: State Management & Recovery (Weeks 3-4)
**Goal**: Support crash recovery and state awareness

**Implementation**:
1. Create operation/workflow snapshots after each step
2. Add `resume_from_checkpoint(workflow_id, operation_id)` tool
3. Store SolidWorks file hash as checkpoint
4. Implement state mismatch detection

**Features**:
- Auto-checkpoint every 5 operations
- Manual checkpoint creation
- Recovery wizard on server restart

### Phase 3: Workflow Templating (Weeks 5-6)
**Goal**: Convert workflows into reusable templates

**Implementation**:
1. Add parameter mapping system (Jinja2 templates)
2. Create `create_template_from_workflow()` tool
3. Add template marketplace/catalog
4. Implement `execute_template_with_params()` tool

**Example**:
```json
{
  "workflow": "create_bracket",
  "parameters": {
    "width": 80.0,
    "height": 60.0,
    "material": "Steel AISI 1020",
    "output_format": "STEP"
  }
}
```

### Phase 4: Undo/Redo System (Weeks 7-8)
**Goal**: Enable operation-level undo/redo

**Implementation**:
1. Add operation reversibility metadata
2. Implement inverse operations for reversible tools
3. Create undo/redo stack management
4. Add UI for undo tree visualization

**Reversible operations**:
- Create → Delete (with file save before delete)
- Add Feature → Rollback (suppress feature)
- Modify Property → Store original value

**Non-reversible** (logged but not undoable):
- Export operations
- Complex macro executions
- Third-party integrations

### Phase 5: Batch Scripting (Weeks 9-10)
**Goal**: Export workflows as executable scripts

**Implementation**:
1. Add Python script generator
2. Add VBA macro script generator
3. Create git-friendly workflow format (YAML?)
4. Implement dry-run mode

**Generated Script**:
```python
# Generated from workflow: simple_bracket_v2
from solidworks_mcp.client import MCP

async def create_bracket_workflow():
    # Step 1: Create part
    await mcp.create_part(template="Part Template", ...)
    
    # Step 2: Create sketch
    await mcp.create_sketch(plane="Front Plane", ...)
    
    # ... more operations
```

## Data Flow Architecture

```
User Action in Dashboard
     ↓
LLM Request via Copilot  ← → VS Code (prompting)
     ↓
MCP Tool Handler
     ↓
Operation Logger (new)
     ├─ Store in database
     ├─ Create checkpoint (if needed)
     └─ Emit event to UI
     ↓
SolidWorks COM Call
     ↓
Result + State Update
     ↓
Dashboard & History View Update
```

## API Additions

### New MCP Tools

```
Workflow Management:
- list_workflows(filter: "all" | "templates" | "recent")
- get_workflow_detail(workflow_id)
- delete_workflow(workflow_id)
- rename_workflow(workflow_id, new_name)

Replay & Recovery:
- replay_workflow(workflow_id, skip_steps: list[int])
- resume_from_checkpoint(workflow_id, checkpoint_id)
- get_workflow_status(workflow_id)
- list_recovery_points(workflow_id)

Templating:
- create_template_from_workflow(workflow_id, template_name, params)
- list_templates(category: str)
- execute_template(template_id, parameters: dict)
- export_template_as_yaml(template_id)

Batch/Script:
- export_workflow_as_python(workflow_id)
- export_workflow_as_vba(workflow_id)
- export_workflow_as_yaml(workflow_id)
- validate_workflow(workflow_id, dry_run: bool)
```

## UI/UX Integration

### Workflow Browser Panel
```
┌─ Workflows (sidebar panel in VS Code)
├─ Recent
│  ├─ ✓ bracket_v2 (1h ago)
│  ├─ ✓ assembly_test (3h ago)
│  └─ ✗ failed_export (6h ago)
├─ Templates
│  ├─ 📋 L-Bracket (beginner)
│  ├─ 📋 Box Assembly (intermediate)
│  └─ 📋 Drawing Package (advanced)
└─ Recovery
   └─ 🔄 Resume last interrupted (2 steps ago)
```

### Workflow Detail View
```
Workflow: bracket_v2
Created: 2026-03-20 14:32
Steps: 8
Success Rate: 87.5% (7/8)

History:
[1] ✓ 0.32s  create_part(template="Part")
[2] ✓ 0.18s  create_sketch(plane="Front Plane")
[3] ✓ 0.25s  sketch_line(...)
[4] ✓ 0.41s  create_extrusion(depth=15.0)
[5] ✗ 2.15s  create_revolve(...) - Error: COM exception
[6] ℹ        SKIPPED (on user request)
[7] ✓ 0.18s  create_fillet(radius=3.0)
[8] ⏳       PENDING

Actions:
[↷] Undo   [↶] Redo   [⏸] Pause   [⏹] Stop   [💾] Save as Template
```

### Undo/Redo Visualization
```
Timeline View:
○─ create_part
├─○─ create_sketch
│  ├─○─ sketch_line
│  ├─○─ sketch_line
│  └─○─ create_extrusion
└─○─ create_fillet
   └─→ (current: can redo to ✗ create_revolve)

Undo Stack: [...], create_fillet, create_extrusion
Redo Stack: create_revolve, ...
```

## Implementation Priorities

### Must Have (MVP)
- [x] SQLModel schema design
- [ ] Operation logging middleware
- [ ] Basic replay_workflow tool
- [ ] Simple navigation UI
- [ ] Auto-checkpoint logic

### Should Have (v1)
- [ ] State snapshots
- [ ] Resume from checkpoint
- [ ] Template creation from workflow
- [ ] Export to Python script

### Nice to Have (v2+)
- [ ] Full undo/redo system
- [ ] Collaborative workflow editing
- [ ] Workflow marketplace
- [ ] Performance analytics

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Large DB size if many operations | Implement archival strategy, compress old workflows |
| State divergence on crash | Regular checksums, validation on restore |
| Complex undo dependencies | Pre-analyze reversibility, document limitations |
| Replay failure due to part changes | State validation, branching instead of replay |

## Success Metrics

✅ **MVP** (4 weeks)
- [ ] All MCP operations logged to DB
- [ ] Can replay simple 3-4 step workflow
- [ ] Can recover from checkpoint
- [ ] DB file < 10MB for 1000 operations

✅ **V1** (8 weeks)
- [ ] Create template from workflow works
- [ ] Execute template with parameters
- [ ] Export as Python script works
- [ ] Undo/redo for basic operations

✅ **V2** (12 weeks)
- [ ] Full undo tree visualization
- [ ] Workflow marketplace
- [ ] Performance profiling per operation
- [ ] Collaborative features

## Integration Points

### With GUI Dashboard (Plan_GUI_Visualization.md)
- Workflow list in side panel
- Execution history display
- One-click template creation from running workflow

### With Pydantic-AI Agent (Plan_PydanticAI_Integration.md)
- Agent auto-creates workflow from multi-step tasks
- Agent suggests template reuse
- Agent learns from workflow success rate

### With VBA Generation
- Export workflow as VBA macro
- Run macro directly in SolidWorks
- Bi-directional: import recorded VBA as workflow

## Timeline

```
Week 1-2: Database schema + operation logging
Week 3-4: State snapshots + recovery
Week 5-6: Template system
Week 7-8: Undo/redo
Week 9-10: Batch scripting + export
Week 11-12: Integration + polish
```

Estimated total effort: **12 developer-weeks**
