## Context

FastMCP builds each tool's description from its docstring, minus the
`Args:` and `Returns:` sections. The `Args:` line for a parameter becomes
that parameter's schema description, which is where "The input data value."
comes from. Every tool is registered through `ToolRegistrar.tool()`
(`tools/tool_boundary.py`), which already wraps it in the error boundary.

Measured on the registered tools (mock adapter), 2026-10-31:

| Measure | Count |
| --- | --- |
| Tools | 154 |
| Take a single `input_data` object | 144 |
| `input_data` described generically or not at all | 98 |
| Description restates the name ("Handle ...") | 5 |
| Description under 120 characters | 27 |
| `Args:` or `Returns:` text leaking into the description | 10 |
| MCP annotations | 0 |

The audit script is kept as the check (task 1.2).

## Goals / Non-Goals

**Goals:** a better description and parameter text for every tool; hints
on every tool; a check that keeps them.

**Non-Goals:**

- changing a tool's behaviour, name or input fields;
- a description of every nested field (they are already described; a
  missing one is fixed in passing).

## Decisions

- **Docstrings stay the source of descriptions.** There is no separate
  description registry. The description lives next to the code it
  describes, and FastMCP already reads it.
- **Description shape.** Plain sentences, not headings, in this order:
  1. what it does;
  2. "Use it to ..." and "For ..., use `other_tool`.";
  3. "Needs: an open drawing." (when it needs something);
  4. "Changes: ..." or "Read-only.";
  5. "Returns: ..." naming the main data fields.

  At most 1200 characters. The model reads every description on every turn,
  so concise matters.
- **The `input_data` line names the input model's purpose and its required
  fields**, e.g. "The extrusion to make: `sketch_name` and `depth` (mm) are
  required; the rest default to a blind boss."
- **Hints come from a table, not 154 decorators.** `tool_hints.py` maps a
  tool name to `(title, read_only, destructive, idempotent)`, and
  `ToolRegistrar.tool()` passes `annotations=` to FastMCP from it. One table
  is easy to review against the tool list, and the test requires it to match
  the registered tools exactly.

  Rejected: per-tool decorator arguments. That edits all 154 registrations,
  and the result is hard to review as a whole.
- **Which FastMCP description options we use.** FastMCP 3.4.9's
  `tool()` takes `title`, `description`, `tags`, `annotations` and `meta`,
  and reads parameter text from `Annotated[..., Field(description=...)]`.
  Checked against our tools on 2026-11-04:
  - *Docstring*: kept as the one source of each description (above).
  - *Field descriptions*: every one of the 493 fields inside our input
    models already has a `Field(description=...)`. Nothing to rewrite;
    the check now requires it, so a new field can't arrive undescribed.
  - *`title` and `annotations`*: passed by the registrar from the table.
  - *`tags`*: the registrar tags each tool with its family, the tool
    module's name (`modeling`, `vba_generation`, ...). It costs nothing now,
    and gives the toolsets of #176 something to filter on.
  - Rejected: `description=` overrides and descriptions built at run time.
    Both make a second source of truth, and nothing in a description depends
    on run-time state. `meta` has no consumer.
  - Not here: the server's `instructions` and a skill served over MCP.
    They are #175's, the next change. FastMCP 3.4.9 already serves a skill
    folder as `skill://` resources (`SkillProvider`), so that needs no
    upgrade to FastMCP 4.
- **What the check enforces.** For every registered tool:
  - no description starting "Handle ";
  - no generic parameter text;
  - a description on every field of its input model;
  - a length between 120 and 1200 characters;
  - a "Read-only." or "Changes:" sentence;
  - a hints entry, and a family tag.

  Usage guidance can't be checked mechanically, so it is reviewed per module
  in the PR.
- **Order: worst Glama scores first.** The drawing-analysis, VBA and
  automation modules come before modelling and sketching, which already
  score A/B.

## Risks / Trade-offs

- [A rewritten description promises behaviour the tool doesn't have] →
  Each description is written from the tool's code and its tests, not its
  old docstring. Where a mock-only or simulated tool is found, the
  description says so.
- [Hints are wrong (a "read-only" tool that changes the model)] → The table
  is reviewed against each tool's adapter calls; a tool that calls a write
  method is never read-only.
- [Glama may not rescore soon] → The check and the hints help agents
  either way. A rescan is requested after the release.
