## Context

- **Registration:** tools register per module through `register_<area>_tools(mcp,
  adapter, config)`, which decorates closures with `@mcp.tool()`. Each closure:
  1. normalises its input in its own `try` (`ValueError` -> `"Invalid input"`),
  2. awaits an adapter method returning `AdapterResult`,
  3. hand-builds a success or error dict,
  4. ends in `except Exception` -> `"Unexpected error: …"`.
- **Adapter-side boundaries already exist:**
  - `PyWin32Adapter._handle_com_operation` turns COM exceptions into
    `AdapterResult(ERROR, "COM error in <op>: (<hresult>, '<text>', …)")`.
  - `_attempt` is the best-effort accessor.
  - Adapter errors therefore reach tools as *strings*, not exceptions.
- **Verified on fastmcp 3.4.6:** a `functools.wraps` wrapper keeps the generated
  input schema intact, and `mcp.call_tool` / `list_tools()[i].fn` both go
  through the wrapper. Tool tests fetch `t.fn` from `list_tools()`.
- **Coverage today:** 97% (14,197 statements, 384 missed), measured with
  `honest.coveragerc` over unit + smoke + all six live files.

## Goals / Non-Goals

**Goals:**
- Tool closures contain business logic only. Error handling lives in one
  boundary plus one result-checking helper.
- Error classification is a pure, separately testable component that can be
  extended without editing tools (open/closed).
- 100% honest line coverage, or an explicit dead-code ledger for anything removed.
- Test files map 1:1 onto source modules.

**Non-Goals:**
- **Adapter `except` blocks:** `_handle_com_operation` *is* the adapter-level
  boundary, and `_attempt` is the deliberate best-effort helper. Each remaining
  adapter `except` is audited (task 3.4): kept, removed as redundant, or folded
  into those two. No new framework.
- **Success payloads:** they keep their per-tool content (see the spec).
- **#115** (circuit-breaker reset tool) is a separate change.

## Decisions

1. **The boundary is applied at registration, not by each tool.**
   - **How:** `register_tools` hands every `register_<area>_tools` a thin
     `ToolRegistrar` proxy around `FastMCP`. Its `.tool()` decorator wraps the
     function in the boundary before calling the real `mcp.tool()`, so no tool
     can forget it.
   - **Rejected:** a decorator on each tool (138 places to forget it), and
     FastMCP middleware. Middleware sits outside the payload contract: it would
     raise `ToolError` instead of returning our payload, and it never sees the
     tool's `AdapterResult`.
2. **Adapter errors become exceptions inside tools, payloads at the boundary.**
   - A helper `require_success(result)` raises `ToolOperationError(message,
     execution_time)` for non-success results. Tools stop building error dicts.
   - The boundary converts `ToolOperationError`, `ValueError`/`ValidationError`
     (invalid input) and anything else into the spec's payload.
   - Success dicts stay in the tool, since only the tool knows its success
     message and data.
3. **Classification is a separate, ordered rule table.**
   - **Where:** `ErrorClassifier` (its own module) holds an ordered list of rules
     `(predicate, error_type, hint)`.
   - **Inputs:** each predicate sees the exception and its message. HRESULTs are
     matched both from `com_error.args[0]` and from the
     `"COM error in …: (<hresult>,"` text, because adapter errors arrive as strings.
   - **Codes:**

     | HRESULT | Name | `error_type` |
     |---|---|---|
     | 0x80010108 | RPC_E_DISCONNECTED | `solidworks_unavailable` |
     | 0x800706BA | RPC_S_SERVER_UNAVAILABLE | `solidworks_unavailable` |
     | 0x800706BE | RPC_S_CALL_FAILED | `solidworks_unavailable` |
     | 0x80020003 | DISP_E_MEMBERNOTFOUND | `com_member_not_found` |
     | 0x80020005 | DISP_E_TYPEMISMATCH | `com_type_mismatch` |

     Plus the message rules: circuit breaker open, no active model/document,
     not found.
   - **Fallback:** `operation_failed` for adapter errors, `internal` for anything
     else.
   - **Why:** new categories are added by appending a rule (open/closed), and the
     table is unit-tested without MCP or adapters.
4. **Import-fallback lines are covered by importing in a clean subprocess.**
   - **How:** a helper runs `python -c` with the dependency blocked
     (`sys.modules[name] = None`) and imports the module, with the run measured
     through pytest-cov's subprocess support.
   - **Rejected:** `importlib.reload` in-process, which re-creates classes that
     other tests already hold.
   - **Fallback plan:** if subprocess measurement proves unreliable, an
     in-process reload inside a fixture that restores `sys.modules` afterwards.
5. **Dead code is decided by evidence, not opinion.**
   - **Test:** a branch is "unreachable" only when no input, fixture or fake can
     reach it.
   - **Record:** each removal goes in `dead-code.md` in this change, with
     `file:line`, the guarding condition, and why it can't be true.
   - **Not dead:** defensive branches for real COM behaviour (`None` returns,
     tuple-vs-scalar results) are reachable with fakes and get tests.
6. **Test layout rule.**
   - **Mapping:** `src/solidworks_mcp/<a>/<b>.py` ↔
     `tests/solidworks_mcp/<a>/test_<b>.py`. A module may have several files
     named `test_<b>_<topic>.py` in the same folder.
   - **Integration and live tests:** cross-module integration tests
     (`test_integration.py`, `test_all_endpoints_harness.py`,
     `test_real_solidworks_integration.py`, `test_demo_scripts_integration.py`)
     move to a new `tests/integration/`. Live tests stay in `tests/live/`.
   - **Scripts:** `tests/utils/` keeps mirroring `src/utils/`.
   - **Splitting buckets:** coverage-bucket files are split by the module each
     test imports and exercises.
   - **Moves:** done with `git mv` to keep history.
   - **Safeguard:** the collected test count is compared before and after the
     move.

## Risks / Trade-offs

- [Error-message wording changes break tests or prompts that match `"Unexpected error"`] → update those tests in the same commit; the payload keys and `status` are unchanged (spec).
- [A tool relied on its local `except` to return a partial success] → the audit in tasks 2.x reads every removed `except` body; any that does more than log-and-return is kept as explicit logic, not deleted.
- [Live COM behaviour of an adapter branch differs from its fake] → every adapter edit is followed by the live suite (one file per process, warm-up gate on).
- [Large mechanical diff makes review hard] → separate commits: (a) boundary + classifier, (b) per-area tool migration, (c) coverage tests, (d) dead-code removal, (e) test moves (pure renames).
- [pytest-cov does not record subprocess coverage on Windows] → Decision 4 fallback.

## Migration Plan

1. Land the boundary and classifier with tests, and wire the registrar. Existing tools still work unchanged: the boundary is additive.
2. Migrate tool modules one area at a time, removing their per-tool handlers. Run the unit suite after each module.
3. Coverage tests and dead-code removal.
4. Test-layout moves as a final pure-rename commit.
5. Live suite, docs, then the #106 PR.

Rollback: each step is its own commit and can be reverted on its own.
