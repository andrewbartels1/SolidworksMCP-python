# Agent Memory and Recovery (SQLite MVP)

This documents a simple local SQLite strategy to help agents avoid repeated failures and recover from broken design states.

## Goal

Capture enough execution history to answer:

1. What failed?
2. Where did it fail (tool + stage)?
3. What is the likely root cause?
4. What should we do next?
5. Should we roll back before retrying?

## Local Storage

Database path:

- `.solidworks_mcp/agent_memory.sqlite3`

Core tables:

- `agent_runs`
- `tool_events`
- `error_catalog`

## Error-Centric Recovery Loop

1. Query `error_catalog` for similar failures by `tool_name` + `error_type`.
2. Present the top remediation options to the user.
3. Prefer rollback/recovery actions before blind retries.
4. Re-run with constrained parameters and capture outcome.

## Example Troubleshooting Prompt

"Based on recent `create_extrusion` failures in the local SQLite catalog, suggest rollback-first recovery using existing MCP tools and avoid repeating known bad states."

## Rollback-First Tooling Pattern

When a step fails:

1. Capture snapshot metadata.
2. Inspect recent feature-tree changes.
3. Roll back/suppress latest risky feature.
4. Re-run prerequisite validation tools.
5. Retry only after preconditions pass.

## Why This Helps

- Fewer repeated failures
- Faster root-cause diagnosis
- Better agent recommendations over time
- Better handoff between human and agent sessions
