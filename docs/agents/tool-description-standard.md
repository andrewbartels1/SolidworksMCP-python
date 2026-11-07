# Tool Description Standard

An agent picks a tool from its description and input schema alone, before it
has called anything. This page is the standard every MCP tool in this server
follows, so that what an agent reads is enough to choose the right tool,
call it correctly, and know what happened.

The mechanical parts are checked by
`tests/integration/test_tool_descriptions.py`; the rest is reviewed in the
pull request.

## Where the text comes from

| What the agent sees | Where it lives |
| --- | --- |
| The tool's description | The tool function's docstring, minus its `Args:` and `Returns:` sections |
| The `input_data` parameter's description | The `input_data` line in the docstring's `Args:` section |
| Each field inside `input_data` | `Field(description=...)` on the input model |
| The title and behaviour hints | `src/solidworks_mcp/tools/tool_hints.py` |
| The family tag | The name of the tool's module, added at registration |

Don't pass `description=` to `@mcp.tool()`. The docstring is the one source,
next to the code it describes.

## The description

Plain sentences, not headings, in this order:

1. **What it does**, in SolidWorks terms.
2. **When to use it**: "Use it to ...". Where another tool overlaps, say
   which to use: "For ..., use `other_tool`."
3. **What it needs**, when it needs something: "Needs: an open drawing."
   (a document type, a selection, a named sketch).
4. **What it changes**: "Changes: adds a feature to the active part." Or,
   when it changes nothing: "Read-only."
5. **What it returns**: "Returns: ..." naming the main fields of the
   success payload.

Keep it between 120 and 1200 characters. Every description is sent to the
model on every turn, so cut anything that doesn't help it choose or call the
tool. Never restate the name ("Handle analyze geometry.").

Write the description from what the code does, not from the old docstring.
If the tool can't do its job with the current adapter (it reports
`unsupported`), say so.

## The `input_data` line

Most tools take one `input_data` object. Its `Args:` line becomes that
parameter's description, so it says what the object holds and which fields
are required, never "The input data value.":

```text
input_data: The extrusion to make. `sketch_name` and `depth` (mm) are
    required; the rest default to a blind boss merged with the body.
```

Every field of the input model has its own `Field(description=...)`,
with units where there are any.

A tool with no parameters has no `Args:` or `Returns:` section: FastMCP
strips those sections only when there are parameters, so they would show up
in the description. Its "Returns: ..." sentence says what comes back.

## Tools that can't run yet

Some tools have no adapter implementation, so every call returns
`error_type: "not_supported"`. Say so plainly, right after the first
sentence: "Not available yet: no adapter implements it, so every call
returns an error with `error_type: "not_supported"`. It is planned for a
future release." Then point to the tool to use instead, if there is one, and
phrase what it would change or return as "once available". The list of these
tools is in `openspec/queue.md`.

## Support levels

Add one line to `SUPPORT_LEVELS` in `tools/support_levels.py` for every new
tool; registration fails without it. A tool is `stable` once a live test
calls it and it has no known fault, `beta` when it works on SolidWorks but
has a known fault or covers only part of its COM call, `experimental` when
no live test has checked it, and `planned` when nothing implements it (its
description says "Not available yet"). Below stable, give a one-sentence
reason.

Don't write the level into the docstring: the server opens a beta or
experimental tool's description with "Beta: <reason>" or "Experimental:
<reason>" from the table, adds the same sentence to its successful results as
`warning`, and tags every tool `level:<level>`. After changing a level, run
`python -m solidworks_mcp.progress.generate` so the README image and the
[progress page](../progress.md) follow; `tests/integration/test_support_levels.py`
and `test_progress_up_to_date.py` check both.

## Behaviour hints

Add one line to `TOOL_HINTS` in `tools/tool_hints.py` for every new tool;
registration fails without it. Pick the helper that fits:

| Helper | Read-only | Destructive | Idempotent | For tools that |
| --- | --- | --- | --- | --- |
| `_reads` | yes | no | yes | change nothing |
| `_adds` | no | no | no | add a feature, sketch entity, view or document |
| `_sets` | no | no | yes | set a value or state (a dimension, the active document) |
| `_overwrites` | no | yes | yes | write or replace a file or a stored value |
| `_discards` | no | yes | no | delete, close without saving, undo, or run a macro |

Choose from the tool's adapter calls: a tool that calls a write method is
never read-only.

## Two worked examples

A read-only tool:

```python
@mcp.tool()
async def list_features(input_data: ListFeaturesInput) -> dict[str, Any]:
    """List the feature tree of the active part or assembly, in order.

    Use it before editing a model, to find a feature's exact name for
    `delete_feature`, `suppress_feature` or `rename_feature`. Needs: an open
    part or assembly. Read-only. Returns: `features` (name and type of each
    entry), `count`, and for an assembly `assembly_tree`.

    Args:
        input_data: What to list. Nothing is required: `include_suppressed`
            and `max_assembly_depth` have defaults.

    Returns:
        dict[str, Any]: The feature list.
    """
```

A tool that changes the model:

```python
@mcp.tool()
async def create_extrusion(input_data: ExtrusionInput) -> dict[str, Any]:
    """Extrude a closed sketch profile into a solid boss.

    Use it after `exit_sketch` to turn a profile into material. To remove
    material, use `create_cut_extrude`. Needs: an open part with the named,
    closed sketch. Changes: adds a Boss-Extrude feature to the active part.
    Returns: the feature's name and parameters, and `measured_change` (volume
    and bounding box before and after).

    Args:
        input_data: The extrusion to make. `sketch_name` and `depth` (mm)
            are required; the rest default to a blind boss merged with the
            body.

    Returns:
        dict[str, Any]: The created feature.
    """
```
