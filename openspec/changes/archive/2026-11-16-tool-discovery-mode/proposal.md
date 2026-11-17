## Why

Every tool's schema is sent to the model on every turn. After the
honest-tool-list change the list is still about 125 tools, and the next
three items add about 20 more. Glama's review called the list "bloated
rather than scoped" (issue #176), and the internal assessment found that
the size of the list, not missing tools, is now the main cost of using
the server. Users who only model parts pay for VBA generators, API-help
lookup and drawing tools on every turn, and a client with a tool limit
can't load the server at all.

## What Changes

- **The tool list is measured.** A script reports the size of
  `tools/list`, in bytes and estimated tokens, overall and per family. The
  numbers go in the docs and are regenerated with the progress files.
- **Toolsets.** `SOLIDWORKS_MCP_TOOLSETS` picks which groups of families
  are registered as visible:
  - `core`: modelling, sketching, file management, analysis, engineering
    data, export, server admin;
  - `drawing`: drawing, drawing automation, drawing analysis;
  - `automation`: macros, automation, templates;
  - `vba`: the VBA generators;
  - `docs`: the API-help lookup tools;
  - `all` (the default): everything, as today.
  Several can be given, comma-separated (`core,drawing`).
- **Search mode.** `SOLIDWORKS_MCP_TOOL_MODE=search` replaces the list
  with FastMCP's search transform: `search_tools` (finds tools by a
  plain-language query and returns their schemas) and `call_tool`, plus a
  few always-visible tools (`get_model_info`, `reset_circuit_breaker`).
  `list` (the default) keeps today's full list. The two settings combine:
  search covers only the chosen toolsets.
- **The server's instructions and the agent skill** say which mode is on,
  and in search mode tell the agent to search before calling.
- **`--selftest`** reports the mode, the toolsets and the visible tool
  count.
- No breaking change: with neither setting, the server behaves as now.

## Capabilities

### New Capabilities

- `setup/toolsets`: choosing which tool families a client sees.
- `setup/tool-search-mode`: an opt-in search-and-call surface in place of
  the full list.

### Modified Capabilities

- `agents/server-instructions`: the instructions name the active mode and,
  in search mode, how to find tools.
- `setup/selftest`: the self-test reports the mode and the visible tool
  count.

## Impact

- **No COM or adapter code changes.** Visibility is applied after
  registration, with FastMCP 3.4.9's `enable(tags=..., only=True)` on the
  family tags `ToolRegistrar` already adds, and its `BM25SearchTransform`.
  Every tool is still registered, so the support-level and description
  checks see all of them.
- **Code:** `config.py` (two settings), `server.py` (apply them after
  registration), a toolset table beside `tool_hints.py`, the server
  instructions, `selftest`, a measuring script under
  `solidworks_mcp/progress/`.
- **Docs:** a "Choosing tools" section in the client setup page, the
  numbers, the skill's note, CHANGELOG.
- **Tests:** each mode and toolset reaches the same tool bodies; `all`
  equals today's list.
- Depends on the honest-tool-list change (queue item 10), which settles the
  families. Closes #176.
