## 1. Measure first

- [x] 1.1 `progress/tool_list_size.py`: `tools/list` bytes and estimated tokens, overall and per family, through the in-process server with the mock adapter; tests
- [x] 1.2 Record today's numbers in the change's notes before anything else changes

## 2. Toolsets

- [x] 2.1 The `TOOLSETS` table; a test that every family is in exactly one toolset
- [x] 2.2 `config.py`: `tool_toolsets` from `SOLIDWORKS_MCP_TOOLSETS`, validated, default `all`; tests for a list, `all`, unset and a typo
- [x] 2.3 `server.py`: `enable(tags=..., only=True)` after registration unless `all`; tests that `core` and `core,drawing` list the right tools and that unset equals today's list
- [x] 2.4 Cross-toolset pointers in descriptions: list those that name a tool outside `core`, and add "(drawing toolset)" or similar; test

## 3. Search mode

- [x] 3.1 `config.py`: `tool_mode` from `SOLIDWORKS_MCP_TOOL_MODE`, `list` or `search`, validated; tests
- [x] 3.2 `server.py`: `BM25SearchTransform` with the always-visible tools, after the toolset filter; tests that search finds `add_fillet` for "fillet edges", `call_tool` gives a direct call's result, and a tool outside the toolsets is refused

## 4. Instructions, skill and self-test

- [x] 4.1 Server instructions name the toolsets, leave out the drawing paragraph without `drawing`, and explain search mode; tests
- [x] 4.2 The agent skill's note for search mode
- [x] 4.3 `--selftest` reports mode, toolsets and visible count; tests

## 5. Docs

- [x] 5.1 "Choosing tools" in the client setup page: the two settings, examples per client, and the size table
- [x] 5.2 The size table generated with the progress files
- [x] 5.3 CHANGELOG (Added)

## 6. Live bundle (one set, run together, then fixes one by one)

- [x] 6.1 (passed 2026-11-16: the search-mode build after the add_fillet fix in design "What changed"; selftest with core in search mode, 4 of 4 areas) Live tests: in search mode with `core`, an agent-style sequence (search, open a part, extrude, fillet) through `call_tool`; `--selftest` with `core`
- [x] 6.2 Hand the user the bundle; fix each failure afterwards, one at a time

## 7. Finish

- [x] 7.1 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`
- [x] 7.2 Sign-off, PR (no attribution) closing #176, archive, the queue updated
