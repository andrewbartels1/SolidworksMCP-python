## Purpose

An opt-in mode in which the client sees a small search-and-call surface
instead of every tool's schema.

## ADDED Requirements

### Requirement: Search mode replaces the list
With `SOLIDWORKS_MCP_TOOL_MODE=search`, `tools/list` SHALL hold
`search_tools`, `call_tool` and the always-visible tools
(`get_model_info`, `reset_circuit_breaker`) only. `search_tools` SHALL
take a plain-language query and return up to five matching tools with
their full input schemas. `call_tool` SHALL run any tool the active
toolsets allow, by name, with the same result as calling it directly.

#### Scenario: Finding and calling a tool
- **WHEN** the agent searches "fillet edges" and calls the returned
  `add_fillet` through `call_tool`
- **THEN** the search's results include `add_fillet` with its schema, and
  the fillet result is the same as a direct call's

#### Scenario: A tool outside the toolsets
- **WHEN** toolsets are `core` and the agent calls `generate_vba_extrusion`
  through `call_tool`
- **THEN** the call fails and says the tool is not in the active toolsets

### Requirement: List mode is the default
With `SOLIDWORKS_MCP_TOOL_MODE` unset or `list`, the server SHALL list the
toolsets' tools directly, with no `search_tools` or `call_tool`. Any other
value SHALL stop the server at start with an error naming `list` and
`search`.

#### Scenario: Unset
- **WHEN** the mode is unset
- **THEN** `tools/list` holds no `search_tools`

### Requirement: The list's size is measured
A script SHALL report `tools/list`'s size in bytes and estimated tokens,
overall and per family, for list mode and for search mode, and the docs
SHALL show the latest numbers.

#### Scenario: Regenerating
- **WHEN** the progress files are regenerated
- **THEN** the docs' size table matches the registered tools
