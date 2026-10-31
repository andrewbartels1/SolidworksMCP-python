## Why

Every MCP tool hand-rolls the same error handling: about 169 `try:` blocks across
138 tools, each ending in a catch-all that returns `"Unexpected error: <str(e)>"`.
That breaks single responsibility, and it hides the useful part of a failure.
An LLM receiving `COM error in add_line: (-2147023174, 'The RPC server is
unavailable.', None, None)` gets no hint that SolidWorks crashed and must be
restarted.

Separately, honest line coverage (no `pragma: no cover`, `ui/` included, live
phase included) is 97% with 384 lines missed. About 18 test files are
"coverage buckets" that test many modules at once, so failures and gaps don't map
back to the source they belong to.

This lands on the #106 branch before it merges, at the user's request:
coverage, then a feature review, then fixes, then merge.

## What Changes

- **One tool error boundary.**
  - **What it does:** a single wrapper, applied where tools are registered, owns
    input validation failures, adapter `AdapterResult` errors and unexpected
    exceptions.
  - **What tools keep:** only their business logic, with no per-tool `try/except`.
  - **What callers get:** error payloads that keep the existing shape (`status`,
    `message`, `execution_time`) and add a machine-readable `error_type` plus a
    `hint` saying what to do next. Known COM failures get named:
    - SolidWorks crashed or disconnected (`RPC_E_DISCONNECTED`, RPC server unavailable)
    - member not found / stale type cache
    - type mismatch
    - circuit breaker open
- **One success/error payload builder** for `AdapterResult`, replacing the
  repeated hand-built dicts.
- **100% honest line coverage.**
  - **How:** real tests with fixtures and fakes, including the
    "pywin32 not installed" import fallbacks and a live pack-and-go test.
  - **Unreachable code:** lines that no input, fixture or mock can reach are
    listed in a dead-code ledger and deleted.
  - **No shortcuts:** no `pragma: no cover` and no `noqa` to dodge coverage.
- **Tests mirror `src/`.**
  - **Layout:** `tests/solidworks_mcp/<package>/<module>/test_*.py` or
    `tests/solidworks_mcp/<package>/test_<module>.py` for each source module.
  - **Splits:** the coverage-bucket files are split by the module they actually test.
  - **Unchanged:** live tests stay in `tests/live/`.
- **BREAKING (message text only):** generic error messages change wording. The
  `"Unexpected error: "` prefix is replaced by a categorised message. Payload keys
  and `status` values do not change.

## Capabilities

### New Capabilities
- `tools/error-boundary`: how every MCP tool reports invalid input, adapter
  failures and unexpected exceptions, including the `error_type` / `hint`
  contract and the named COM failure categories.

### Modified Capabilities
<!-- none: coverage and test layout are quality gates, not runtime behavior -->

## Impact

- **Code:**
  - `src/solidworks_mcp/tools/*.py`: all tool modules lose per-tool exception handling.
  - New boundary/payload module under `src/solidworks_mcp/tools/`.
  - `tools/__init__.py`: registration wiring.
- **Adapters:** `pywin32_adapter.py`, `solidworks/*.py`, `mock_adapter.py` and
  `base.py` are touched only for coverage tests and dead-code removal. That still
  carries COM/late-binding risk per CLAUDE.md, so every adapter edit is
  re-verified with the live suite.
- **Tests:** most test files move or split. Test count and assertions are
  preserved, apart from tests that pin the old `"Unexpected error"` wording,
  which get updated.
- **Docs:**
  - Tool response contract (`error_type`, `hint`) in the tool-catalog docs.
  - CLAUDE.md "Validation and Tool Contracts".
  - The stale CLAUDE.md COM-threading section (no `ComExecutor` in the adapter).
- **Issues:** follows #106. Also covers the coverage-to-100% request from the
  #106 review. The circuit-breaker reset tool (#115) stays a separate change.
