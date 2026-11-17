## Context

`ToolRegistrar` tags every tool with its family (the defining module's
name, `tool_family()` in `tools/tool_boundary.py`) and its level. The
families are: `analysis`, `automation`, `docs_discovery`, `drawing`,
`drawing_analysis`, `drawing_automation`, `engineering_data`, `export`,
`file_management`, `macro_recording`, `modeling`, `server_admin`,
`sketching`, `template_management`, `vba_generation`.

FastMCP 3.4.9, the pinned version, provides both pieces:

- `enable(tags=..., only=True)` on the server: an allowlist by tag, applied
  as a visibility transform;
- `fastmcp.server.transforms.search.BM25SearchTransform(max_results,
  always_visible, search_tool_name, call_tool_name)`: replaces the listed
  tools with `search_tools` and `call_tool`.

Settings are read from `SOLIDWORKS_MCP_*` variables in `config.py`.

## Goals / Non-Goals

**Goals:**
- A smaller tool list for users who want one, with no change for users
  who don't.
- Numbers that show what each choice saves.

**Non-Goals:**
- Changing the default list. A default of `core` would hide tools from
  current users without warning; the measured numbers can make the case
  for that later.
- Tools that turn toolsets on and off during a session (FastMCP's
  per-session visibility): clients cache the list, and few handle
  `list_changed`.
- Our own search ranking.

## Decisions

### 1. Toolsets map families, in one table

A `TOOLSETS: dict[str, frozenset[str]]` table beside the hints table:

| Toolset | Families |
| --- | --- |
| `core` | modeling, sketching, file_management, analysis, engineering_data, export, server_admin |
| `drawing` | drawing, drawing_automation, drawing_analysis |
| `automation` | macro_recording, automation, template_management |
| `vba` | vba_generation |
| `docs` | docs_discovery |

A test checks every family is in exactly one toolset. After registration,
`server.py` calls `mcp.enable(tags={<the chosen families>}, only=True)`
unless the choice is `all`. Tools stay registered, so the support-level
and description checks still see all of them.

### 2. Search mode is FastMCP's BM25 transform

With `search`, `server.py` adds `BM25SearchTransform(max_results=5,
always_visible=["get_model_info", "reset_circuit_breaker"])` after the
toolset filter, so the search covers only visible tools. BM25 needs no
model or network, and ranks on names and descriptions, which item 1's
description standard already made consistent. `call_tool` runs a tool
through the same registered function, so the error boundary, levels and
warnings apply unchanged.

*Alternative:* the regex transform. Rejected: agents search in plain
words, not patterns.

### 3. Settings fail fast

Both settings are validated in `config.py` at start. An unknown toolset or
mode raises a configuration error listing the valid values, and the server
doesn't start; a silently empty tool list would be worse.

### 4. Instructions are built from the mode

The server instructions are a constant today (`SERVER_INSTRUCTIONS`,
passed to FastMCP in `server.py`). They become a function of the two
settings, called at start. They gain one line naming the toolsets, the drawing paragraph only when `drawing` is on,
and, in search mode, a paragraph on `search_tools` and `call_tool`. The
skill gets a short "If you see `search_tools`" note.

### 5. Measuring with the real list

`python -m solidworks_mcp.progress.tool_list_size` starts the server
in-process with the mock adapter, reads `tools/list` per mode and toolset,
and writes bytes and an estimate of tokens (bytes ÷ 4, stated as an
estimate) to a docs table. It runs with the progress generator, so the
numbers can't go stale.

## Risks / Trade-offs

- [An agent in search mode can't find a tool] → BM25 on consistent
  descriptions; the live check runs the U-joint-style prompts' first
  steps in search mode; list mode stays the default.
- [`enable(only=True)` hides a tool another tool's description names] →
  descriptions name tools across families (for example "use
  `create_drawing_view`"); in a reduced set those pointers can name hidden
  tools. A test lists them for `core`; the description says "(drawing
  toolset)" where it points across toolsets.
- [FastMCP's transform API changes] → it is pinned at 3.4.9; the tests
  exercise both transforms through the real server object.

## What changed while building it (2026-11-16)

- **Settings** are the config fields `toolsets` and `tool_mode`, read from
  `SOLIDWORKS_MCP_TOOLSETS` and `SOLIDWORKS_MCP_TOOL_MODE` like every other
  setting. The table and `apply_tool_visibility` are in `tools/toolsets.py`.
- **The instructions** had no drawing paragraph to leave out; they gain a
  line naming the toolsets when some are off, and the search paragraph.
- **The self-test** runs its checks with every tool listed, since its areas
  call drawing and export tools directly; its report gains a "Tools listed"
  row giving what the user's settings list.
- **The numbers** (notes.md): 135 tools, about 55,000 tokens; `core` alone
  is two thirds of that, search mode about 900 tokens. The table is
  `docs/assets/progress/tool-list-size.md`, written with the progress files
  and included in the installation guide.
- **Live**, search mode with `core` built a filleted block through
  `call_tool`, and each search ranked the wanted tool first or second. It
  found a fault outside this change: `add_fillet` with no edge names (use
  the current selection) read the volume first, and that read's rebuild
  cleared the selection `select_face_edges` had made, so no fillet was
  built. `add_fillet` now skips the volume read in that case; the feature
  count still catches a fillet that builds nothing.
