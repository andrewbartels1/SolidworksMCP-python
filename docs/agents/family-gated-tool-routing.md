# Family-Gated Tool Routing for Interactive CAD Reconstruction

This page defines how the orchestration agent should shortlist tools by feature family, so the LLM does not reason over the full tool surface at every step.

## Why this exists

Large toolsets degrade agent precision. Family-gated routing keeps planning focused and makes failures easier to recover.

## Core loop

1. Inspect current state (`open_model`, `get_model_info`, `list_features`, `get_mass_properties`).
2. Classify family (`classify_feature_tree`) and confidence.
3. Select a restricted tool shortlist for the next checkpoint only.
4. Request human approval.
5. Execute one checkpoint.
6. Verify and store snapshot for rollback/diff.

## Family Routing Table

| Family | Confidence Gate | Primary Tools | Secondary Tools | Delegate / Fallback |
| --- | --- | --- | --- | --- |
| revolve | high/medium | `create_sketch`, `add_centerline`, `create_revolve` | `set_dimension`, `get_model_info` | if profile/axis ambiguous: inspect more + user confirmation |
| extrude | high/medium | `create_sketch`, `add_line`/`add_circle`/`add_rectangle`, `create_extrusion` | `set_dimension`, `list_features` | if downstream order unclear: pause and request accepted first feature |
| sheet_metal | any | inspect-only (`list_features`, `get_model_info`) | `get_mass_properties` | VBA-aware route (`generate_vba_part_modeling`) and preserve unfold/fold order |
| advanced_solid | medium/high | inspect-first + limited direct features | export/check tools | VBA-aware route when loft/sweep/surface operations exceed direct MCP support |
| assembly | high/medium | `list_components`, `list_mates`, part-level tools per component | `get_model_info` | decompose into per-part plans before editing assembly constraints |
| drawing | high/medium | drawing tools only | drawing analysis tools | do not run part modeling tools |
| unknown | low | inspect-only tools | docs-discovery + retrieval | no build execution until family is accepted |

## Checkpoint policy

- Keep each checkpoint to 1 intent (example: "create base profile", not "build whole part").
- Maximum 3-6 checkpoints presented at one time.
- Require approval before checkpoint execution.
- Persist every checkpoint decision and tool call in SQLite.

## Prompt template: classifier response

```text
Family: <family>
Confidence: <high|medium|low>
Evidence:
- <evidence 1>
- <evidence 2>
Warnings:
- <warning>
Recommended workflow: <direct-mcp-... | vba-... | inspect-more>
Next checkpoint options:
1) <option A>
2) <option B>
Ask user: approve, revise, or inspect more?
```

## Prompt template: orchestrator checkpoint handoff

```text
Goal: <user goal>
Accepted family: <family>
Accepted checkpoint index: <n>
Allowed tools for this checkpoint:
- <tool 1>
- <tool 2>
Disallowed tool families:
- <tool group>
Success criteria:
- <criterion>
Rollback target:
- checkpoint <n-1> snapshot_id=<id>
```

## SolidWorks-compatible edit workflow (human edits in-between)

This system works with SolidWorks, not in place of it.

1. Agent executes to an accepted checkpoint and stores state snapshot.
2. User opens/edits directly in SolidWorks.
3. User declares: "manual edits complete".
4. Agent performs diff pass:
   - refresh `get_model_info`, `list_features(include_suppressed=True)`, `get_mass_properties`
   - compare to last accepted snapshot
   - classify whether edits move toward or away from goal
5. Agent proposes reconciliation options:
   - accept manual changes and update plan
   - preserve goal and patch deltas
   - rollback to prior checkpoint

## Storage requirements

Store at minimum for each checkpoint:

- accepted family and confidence
- planned action + approved status
- executed tool calls with inputs/outputs
- verification artifacts (feature list/mass properties)
- rollback snapshot metadata
- evidence references used for planning

## Printability sub-agent handoff

After geometry checkpoints stabilize, invoke printability checks with explicit assumptions:

- printer model or bed size in mm
- material, nozzle, layer height
- target fit/joint type

Output must include:

- tolerance and clearance ranges by feature type
- orientation recommendation and rationale
- build-volume fit check and split strategy
- risk checklist (warping, weak axis, supports, overhangs)
