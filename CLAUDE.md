# SolidWorks MCP Server (Python)

This file is the quick orientation guide for contributors and coding agents.

## Platform and Runtime

- Primary runtime is Python 3.13+.
- Real COM automation requires Windows + SolidWorks installed.
- Cross-platform development is possible in mock/test mode.

## Build and Development Commands

Use either micromamba environment commands or local virtualenv commands.

### Preferred PowerShell workflow

```powershell
# Show command help
.\dev-commands.ps1

# Full install in micromamba env
.\dev-commands.ps1 dev-install

# Fast test pass (no SolidWorks-required tests)
.\dev-commands.ps1 dev-test

# Full test run including real SolidWorks integration
.\dev-commands.ps1 dev-test-full

# Lint and format
.\dev-commands.ps1 dev-lint
.\dev-commands.ps1 dev-format

# Docs build/serve
.\dev-commands.ps1 dev-docs-build
.\dev-commands.ps1 dev-docs-strict
.\dev-commands.ps1 dev-docs-audit
.\dev-commands.ps1 dev-docs
```

### Virtualenv direct workflow

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs]"

# Run server
.\.venv\Scripts\python.exe -m solidworks_mcp.server

# Lint/tests/docs
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m pytest tests -m "not solidworks_only"
.\.venv\Scripts\python.exe -m mkdocs build --clean
```

## Architecture

- Server entrypoint: `src/solidworks_mcp/server.py`
- CLI entrypoint: `src/solidworks_mcp/server_cli_fixed.py`
- Adapters: `src/solidworks_mcp/adapters/`
  - `pywin32_adapter.py`: real SolidWorks COM adapter (Windows)
  - `mock_adapter.py`: mock adapter for tests and CI-like runs
  - `factory.py`: adapter selection/routing logic
- Tools: `src/solidworks_mcp/tools/` (modeling, sketching, drawing, export, analysis, automation, templates, VBA, docs discovery)
- Agent harness: `src/solidworks_mcp/agents/` (prompt schemas, smoke test CLI, run/error persistence)

## Key Patterns

### COM and Adapter Safety

- Prefer adapter abstraction, not direct COM calls from tool modules.
- Keep Windows/COM behavior behind adapter boundaries.
- Use mock adapter for tests unless a test explicitly requires real SolidWorks.

### Logging and Output

- Use project logging utilities (`loguru`/configured helpers).
- Avoid ad-hoc print statements in runtime server paths.

### Validation and Tool Contracts

- Keep tool input schemas strict and explicit.
- Maintain stable response payload shapes (`status`, `message`, `execution_time`, plus data payload).

## Testing Guidance

- Default local path: run non-`solidworks_only` tests first.
- Real integration path: run `dev-test-full` on Windows with SolidWorks available.
- Harness and generated report artifacts may write under `tests/.generated/` and `.solidworks_mcp/`.

## Documentation Guidance

- Build docs before commit when touching docs pages:
  - `.\dev-commands.ps1 dev-docs-build`
  - `.\dev-commands.ps1 dev-docs-strict`
- For local preview:
  - `.\dev-commands.ps1 dev-docs`

## Agent and Model Notes

- VS Code Copilot subscription is suitable for chat-based workflows.
- Local Python smoke tests require explicit provider credentials:
  - GitHub Models: `GH_TOKEN` or `GITHUB_API_KEY`
  - OpenAI: `OPENAI_API_KEY`
  - Anthropic: `ANTHROPIC_API_KEY`

## Troubleshooting Runbook

When the bridge misbehaves, walk this list in order. Compiled from SolidWorks
forum threads, pywin32 issues, and observed failures on this install. Last
updated 2026-04-24.

### 1. `OpenDoc6` HRESULT failure — pass-by-ref params

- **Cause:** pywin32 `makepy`/`gencache` marks SW's pass-by-ref `errors` and
  `warnings` parameters as non-optional inputs. Calls fail unless
  `pythoncom.Missing` is passed explicitly.
- **Check:** grep server code for `OpenDoc6(`; every callsite should pass
  `pythoncom.Missing` for the last two params.
- **Fix:**
  `model, errors, warnings = sw.OpenDoc6(path, type, opts, '', pythoncom.Missing, pythoncom.Missing)`
- **Error codes:** warning=128 = already open (not fatal); error=1024 = generic
  open failure. S_OK with null return is also possible.

### 2. `Member not found` / `NoneType not callable` — stale gencache

- **Cause:** pywin32 caches SW type-library wrappers under `%TEMP%\gen_py\`.
  SW upgrades (e.g. 2024 → 2025) or patches leave wrappers pointing at the
  old TLB.
- **Fix:** delete `%TEMP%\gen_py\`, restart the MCP server. Rebuilds on first
  call.

### 3. `No active model` AND `OpenDoc6` errors together — stale COM handle

- **Cause:** MCP server process grabbed a COM pointer at startup; user has
  since quit and reopened SolidWorks. Pointer is dangling.
- **Check:** compare MCP server start time (Claude `main.log` →
  `Launching MCP Server: solidworks`) to current `SLDWORKS.exe` start time.
- **Fix:** restart Claude Desktop (respawns MCP server, which grabs a fresh
  SW handle). Restarting SolidWorks alone will NOT fix this.

### 4. `Circuit breaker is open for <tool>`

- **Cause:** server-side resilience library trips after N failures in a
  window. Subsequent calls fail fast even when the underlying issue is fixed.
- **Fix:** wait for breaker timeout (~30–60s) or restart the server.

### 5. COM apartment / threading mismatch — FastMCP async workers

- **Cause:** SolidWorks COM is STA (single-threaded apartment). An IDispatch
  proxy obtained on thread A cannot be invoked from thread B. FastMCP runs
  tool handlers on worker threads distinct from where `connect()` ran.
- **Signature (critical):** pywin32 late-binding surfaces this as
  ``AttributeError: SldWorks.Application.<method>`` at attribute lookup —
  **NOT** as ``pywintypes.com_error``. The `except com_error` branch in
  ``_handle_com_operation`` therefore misses it, and the generic handler
  flattens the message to the source+method name with no traceback.
- **Fix (applied 2026-04-24, revised same day):** dedicated STA worker
  thread. See "COM threading architecture" section below. The earlier
  thread-local fix (`_tls` / `_swapp_for_thread`) was a band-aid that was
  replaced by the proper executor-based design.

### 6. PDM vault files

- **Cause:** `OpenDoc6` on a file under a PDM working folder fails when the
  file isn't checked out or cached locally.
- **Check:** target path has PDM vault metadata / is under a PDM working
  folder.
- **Fix:** check the file out in PDM, or test with a copy outside the vault.

### 7. Silent-mode UI leak

- `swOpenDocOptions_Silent` still pops the UI on some SW-2025 SP levels.
  Cosmetic only; not a failure.

### 8. SW 2025 SP0 drawing crashes

- SP0 has reported `.slddrw` open crashes. If the target is a drawing,
  suggest upgrading to SP1+.

### 9. MCP log silence

- FastMCP banner output (emoji-prefixed lines to stdout) is misparsed as
  JSON-RPC by the Claude host — noise, not errors.
- Actual tool-call tracebacks go to **stderr** and are NOT captured in
  `%APPDATA%\Claude\logs\mcp-server-solidworks.log`. Check the
  `%LOCALAPPDATA%\solidworks_mcp\logs\` directory and the FastMCP install
  dir for a separate Python log.

### 9a. Server exits right after `initialize` — stdout pollution + crash-on-close (fixed 2026-08-23)

- **Symptom:** Claude Desktop's `main.log` shows `Message from client:
  method="initialize"` followed within ~1-2s by `Server transport closed
  unexpectedly, this is likely due to the process exiting early` and
  `Couldn't start this server for Cowork and Code sessions ... Connection
  closed`.
- **Root cause:** `src/utils/start_local_server.py` (the script `run-mcp.ps1`
  invokes) is a local dev/demo harness — before item 9's banner noise was
  even understood to be more than cosmetic, it turned out to compound with a
  real crash. `main()` used bare `print()` for startup banners, the printed
  Claude Desktop config sample, and post-startup status — all going to real
  stdout, which an MCP stdio host treats as a pure JSON-RPC channel from the
  moment it spawns the process. Separately, `create_local_config()` hardcodes
  `DeploymentMode.LOCAL`, so `server.start()` always blocks for the entire
  stdio session and only returns once the client disconnects (for any
  reason, including a parse error from the stdout pollution above). Code
  after that point assumed HTTP/remote mode — it called `test_server_health()`
  against a `/health` endpoint that was never started, and printed more
  status text. By then `mcp.server.stdio.stdio_server()`'s teardown had
  already closed the wrapped stdout stream, so every subsequent `print()`
  raised `ValueError: I/O operation on closed file`, cascading through the
  `except`/`finally` blocks (each handler's own `print()` re-raised the same
  error) until the process died with a confusing multi-traceback dump.
- **Fix:** all decorative/status output in `start_local_server.py` now goes
  through an `eprint()` helper that writes to `stderr`, never `stdout`.
  Routine startup/shutdown status uses `logger.info`/`logger.error` (already
  stderr-bound via loguru) instead of `print()`. The HTTP-health-check /
  demo-workflow code path (`test_server_health`, `demonstrate_tools`,
  `run_example_workflow`) is now gated on `config.deployment_mode !=
  DeploymentMode.LOCAL`, so it can no longer run after a stdio session ends.
- **Verify:** run
  `.\.venv\Scripts\python.exe src\utils\start_local_server.py --real --year 2026 < NUL`
  (simulates a client that connects then immediately disconnects) — stdout
  must be completely empty and the process must exit 0 with only stderr log
  lines.

### 9b. Server never starts at all under an MCP host, even though `run-mcp.ps1` works fine from a terminal (fixed 2026-08-23)

- **Symptom:** identical to 9a's (`Server transport closed unexpectedly ...
  process exiting early`, ~0.3-1.5s after `initialize`), but **no output at
  all** appears anywhere - not `mcp-server-solidworks.log`
  (`%LOCALAPPDATA%\Claude\Logs\`), not a boot-trace file written as the very
  first statement of `start_local_server.py`, not even one written as the
  very first statement of `run-mcp.ps1` itself, anchored to the script's own
  directory (so it can't be a missing/unwritable `%TEMP%`). Every manual
  reproduction of the *exact same* `powershell -NoProfile -ExecutionPolicy
  Bypass -File run-mcp.ps1 --real --year 2026` command, run from an
  interactive terminal, works perfectly.
- **Root cause:** `run-mcp.ps1`'s `Test-PythonExecutable` function ran `&
  $PythonPath -c "import sys" | Out-Null` to sanity-check the venv before
  using it. Piping a native executable's output makes it a pipeline stage,
  and Windows PowerShell 5.1 throws `Cannot run a document in the middle of
  a pipeline` for that specific pattern when the host process has no real
  console attached - exactly the case when an MCP client (Claude Desktop,
  VS Code, LM Studio) spawns a server over raw stdio pipes with no pty. An
  interactive terminal always provides a console (directly, or via a pty),
  so the bug never reproduces there. `Test-PythonExecutable` caught the
  exception and returned `$false`, so `run-mcp.ps1` silently fell through to
  its `uv run` fallback path - which also doesn't work for this project (it
  isn't `uv`-managed) and exits in milliseconds without ever touching
  `start_local_server.py`, hence zero output from it anywhere. A first fix
  attempt (redirecting with `*> $null` instead of piping to `Out-Null`,
  which avoids constructing a pipeline) stopped the exception but was
  observed, under a real MCP-host spawn, to leave `$LASTEXITCODE` silently
  unset instead - a quieter failure in the same family. `Start-Process` was
  also tried and initially got the arguments wrong: `-ArgumentList @('-c',
  'import sys')` gets joined into a command line where `import sys` isn't
  quoted, so Windows' argument parser splits it into two separate argv
  entries and `python -c import` fails with a syntax error on a truncated
  program.
- **Fix:** `Test-PythonExecutable` now uses `Start-Process -NoNewWindow
  -Wait -PassThru` with `-RedirectStandardOutput`/`-RedirectStandardError`
  pointed at real temp files (not `$null`) and reads `$proc.ExitCode`, which
  bypasses PowerShell's pipeline/redirection engine entirely and goes
  straight to Win32 `CreateProcess` - the class of bug above doesn't apply
  to it. The `-ArgumentList` array quotes the `-c` payload explicitly
  (`'"import sys"'`) so Windows' command-line parser keeps it as one
  argument. **However:** the config change that was actually confirmed
  working end-to-end in this environment's live Claude Desktop was
  sidestepping PowerShell entirely - pointing the MCP host directly at
  `.venv\Scripts\python.exe` with `src\utils\start_local_server.py` as the
  script argument (see the README's MCP client configuration section, now
  documented as the recommended approach for every host). Prefer that form
  for any MCP client config; `run-mcp.ps1` remains available (with the
  `Start-Process` hardening above) for people who want its automatic
  venv/`uv` detection, e.g. manual terminal use.
- **Diagnostic technique used:** dependency-free "boot trace" helpers
  (stdlib-only, anchored to a known-writable directory next to the script,
  never `%TEMP%`/cwd since an MCP host's environment is not guaranteed to
  set either - see the MCP spec's debugging guide) were added to both
  `start_local_server.py` and `run-mcp.ps1`, each appending one flushed
  line per checkpoint. Getting a trace to fire *at all* under the real
  failing launch - as opposed to every local reproduction, which always
  worked - is what isolated the bug to `run-mcp.ps1`'s PowerShell layer
  instead of anything in the Python server itself.

### 10. Claude Code `settings.json` UTF-8 BOM (host-side, not SW)

- A BOM on `~/.claude/settings.json` makes Claude Code silently drop **all**
  user settings (`[SettingsIo] Failed to read ... Unexpected token '﻿'`).
  Strip the BOM; write plain UTF-8.

### 11. `SelectByID2` Callout type mismatch — use `VT_DISPATCH` null, not `None`

- **Signature:** `(-2147352571, 'Type mismatch.', None, 8)` on any `SelectByID2` call.
- **Cause:** The `Callout` parameter (8th arg) is typed `VT_DISPATCH`. Python `None`
  marshals as `VT_NULL` which SW rejects. Must pass an explicit COM null pointer:

  ```python
  import pythoncom, win32com.client as _win32com
  null_callout = _win32com.VARIANT(pythoncom.VT_DISPATCH, None)
  model.Extension.SelectByID2("", "EDGE", x, y, z, append, mark, null_callout, 0)
  ```

- **Applies to:** Every `SelectByID2` / `SelectByID` call with no real callout.

### 12. `InsertFeatureChamfer` is on `IFeatureManager`, not `IModelDocExtension`

- **Signature:** `<unknown>.InsertFeatureChamfer` when calling via `model.Extension`.
- **Cause:** `InsertFeatureChamfer` (DISPID 83) is on `IFeatureManager`.
  Routing through `model.Extension` (IModelDocExtension) causes `DISP_E_MEMBERNOTFOUND`.
- **Fix:** `fm = model.FeatureManager; fm.InsertFeatureChamfer(1, 1, width_m, pi/4, 0, 0, 0, 0)`
- **More detail:** See `docs/agents/com-api-pitfalls.md` for the full pattern catalogue.

### 13. `ForceRebuild3(True)` required before coordinate-based edge/face selection

- **Signature:** `SelectByID2("", "EDGE", x, y, z, ...)` returns `False` on a freshly
  created feature.
- **Cause:** New feature edges are not tessellated until an explicit rebuild.
  `SelectByID2` uses the tessellated mesh to resolve coordinates.
- **Fix:** Call `model.ForceRebuild3(True)` once before the first `SelectByID2` in a
  feature operation.

> **Full COM pitfall catalogue for LLM agents:** `docs/agents/com-api-pitfalls.md`

### Decision order when starting a debug session

1. Read recent `%APPDATA%\Claude\logs\main.log` entries for
   `Launching MCP Server: solidworks` and note the timestamp.
2. Compare to current `SLDWORKS.exe` process start (Task Manager). If SW is
   newer than the server → **#3**, restart Claude Desktop first.
3. If SW is older or same, try a trivial call (`get_model_info`). If it
   returns a circuit-breaker error, wait 60s and retry → **#4**.
4. If real error text surfaces, map to #1/#2/#5/#6 via the error signature
   above.
5. Only then read server source to confirm.

## COM threading architecture

Invariants every new COM-touching code path must respect. Written 2026-04-24
after the Phase 1+2 rewrite landed.

### 1. All COM calls run on the adapter's ComExecutor thread

The adapter owns a single dedicated worker thread (``PyWin32Adapter._com``,
instance of ``com_executor.ComExecutor``). COM is initialized on that thread
once via ``pythoncom.CoInitialize()``. All COM work — ``connect()``, every
``_handle_com_operation`` closure, every ``disconnect()`` cleanup — is
submitted to that executor and awaited via ``Future``.

Consequences:

- ``self.swApp`` and ``self.currentModel`` are **only** valid when touched
  from inside an executor job. Reading them from an async tool function
  or an HTTP handler thread directly will raise the cross-thread
  ``AttributeError`` described in runbook item #5.
- Do NOT call ``pythoncom.CoInitialize()`` anywhere else in the adapter
  code. The executor owns the apartment.
- Do NOT cache IDispatch references outside instance attributes that are
  only read from executor jobs.

### 2. Late binding is forced, always

``_do_connect`` uses ``win32com.client.dynamic.Dispatch`` instead of
``win32com.client.Dispatch``. Rationale: when the makepy-generated
``gen_py`` wrapper is loaded (it is, as soon as ``sw_type_info`` is
imported), plain ``Dispatch`` would auto-upgrade to an early-bound wrapper.
Early-bound wrappers reject the VARIANT-based pass-by-ref out-parameters
used by ``OpenDoc6`` and many other SW calls; migrating to ``pythoncom.Missing``
for every such call is a much larger change than we want.

If you add a new COM-touching function: call ``dynamic.Dispatch`` if you
need to acquire a fresh IDispatch, **not** ``EnsureDispatch``.

### 3. Method flagging via sw_type_info

``sw_type_info.flag_methods(obj, *interfaces)`` tells pywin32's late
binding to resolve specific names as methods (``Invoke`` with method
flags) rather than properties. Without flagging, zero-arg SW methods like
``GetTitle()`` raise ``TypeError: 'str' object is not callable`` because
the dispatch returns the string *value*, which Python then tries to call.

Apply flagging:

- On ``swApp`` after acquiring it → ``flag_methods(app, "ISldWorks")``
- On a newly-opened document → ``flag_doc(model, doc_type)`` (infers from
  doc type: Part=1, Assembly=2, Drawing=3)
- On any intermediate dispatch returned from a SW call →
  ``sw_type_info.flagged(x, "IInterfaceName")`` inline-style

Interface names come from the gen_py wrapper (run
``python -m win32com.client.makepy "C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\sldworks.tlb"``
to regenerate after a SW version upgrade).

### 4. Properties are still properties

Not every zero-arg accessor is a method. ``IConfiguration.Name``,
``ModelDoc2.Visible``, etc. are genuine properties — read them without
``()``. If you flag them as methods you'll get the opposite TypeError.
When in doubt, check the gen_py wrapper: methods live in the class body
as regular defs; properties use ``_prop_map_get_`` / ``_prop_map_put_``.

### 5. Regression tests

See ``tests/test_live_sw_regression.py`` for the safety net:

- ComExecutor start/stop/exception semantics
- flag_methods incrementality + per-interface correctness
- Late-bound ``swApp`` acquisition
- ``get_model_info`` fields populate correctly
- ``get_model_info`` works from a worker thread (the cross-thread bug
  reproducer)

Run these after any change to ``pywin32_adapter.py``, ``com_executor.py``,
or ``sw_type_info.py``::

    $env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1
    .\.venv\Scripts\python.exe -m pytest tests/test_live_sw_regression.py -v

### Reference sources

- [Problem with OpenDoc6 — SW Forums](https://forum.solidworks.com/thread/19519)
- [OpenDoc6 error — SW Forums](https://forum.solidworks.com/thread/100254)
- [Opendoc6/7 silent open — SW Forums](https://forum.solidworks.com/thread/245676)
- [pywin32 #337 SW pass-by-reference bug](https://sourceforge.net/p/pywin32/bugs/337/)
- [pywin32 #1585 strange issues with SW](https://github.com/mhammond/pywin32/issues/1585)
- [CodeStack SW macros troubleshooting](https://www.codestack.net/solidworks-api/troubleshooting/macros/)
- [SW 2025 SP0 drawing crash thread](https://forum.solidworks.com/forum-solidworks/MYfrK4r0RF6Fnd8tf5tAMA/solidworks-2025-sp0-crashes-when-opening-a-drawing-file)
- [pythoncom CoInitializeEx docs](https://timgolden.me.uk/pywin32-docs/pythoncom__CoInitializeEx_meth.html)
