## Why

An agent decides which tool to call from its description and schema alone.
Glama's automated Tool Definition Quality Score (TDQS) is the first number a
visitor to the listing sees, and it rates ours poorly. The low-scoring tools
share four faults, and the current code reproduces all of them:

- **Descriptions that only restate the name** ("Handle analyze drawing
  comprehensive."): 5 tools, plus 27 tools under 120 characters.
- **No usage guidance**: no "use this when", and no pointer to the sibling
  to use instead, where tools overlap (see #174).
- **Side effects not stated**: nothing says whether a call changes the
  model, saves files or only reads.
- **A generic parameter**: 144 of 154 tools take one `input_data` object,
  and 99 describe it only as "The input data value." The 493 fields inside
  are all described already, but nothing keeps them that way.

This implements the docstring half of #82 (audit every tool's docstring for
LLM usefulness). Guidance across tools (the server's `instructions` and an
agent skill) is #175, the change after this one.

## What Changes

- **One description standard** for every tool:
  - what it does;
  - when to use it, and which sibling to use instead;
  - what it needs (document type, selection);
  - what it changes, or that it is read-only;
  - what it returns.

  The standard is written down for contributors.
- **Every tool's description rewritten** to the standard, module by module,
  the worst-scoring first. Each `input_data` gets a specific description.
- **MCP behaviour hints on every tool**: `readOnlyHint`, `destructiveHint`,
  `idempotentHint` and a human `title`. They come from one table, which the
  registrar applies at registration, so clients and directories can see
  which tools change the model. The registrar also tags each tool with its
  family (its module), ready for the toolsets of #176.
- **A check in the test suite** that fails when a registered tool breaks
  the standard, has an undescribed input field, or has no hints entry, so
  new tools can't regress.

Out of scope:

- consolidating or renaming tools (#174);
- toolsets or discovery mode (#176);
- the error-message half of #82: the error boundary already gives
  `error_type` and `hint`, and the message content gets its own change.

No tool's name, input schema fields or response shape changes.

## Capabilities

### New Capabilities

- `tools/tool-descriptions`: every registered tool carries a description
  written to one standard, and MCP behaviour hints.

### Modified Capabilities

None.

## Impact

- Changed: the docstrings in every tool module under
  `src/solidworks_mcp/tools/` (154 tools in 14 modules), and
  `tools/tool_boundary.py` (the registrar applies the hints).
- New:
  - `src/solidworks_mcp/tools/tool_hints.py` (the hints table);
  - `tests/solidworks_mcp/tools/test_tool_hints.py`;
  - `tests/integration/test_tool_descriptions.py` (the check across all
    tools);
  - `docs/agents/tool-description-standard.md`.
- No COM or adapter code is touched; the mock and pywin32 paths are
  unchanged.
- Visible after merge as a Glama rescore. The listing still shows 112 tools,
  so it needs a rescan; claiming the listing is a maintainer action.
