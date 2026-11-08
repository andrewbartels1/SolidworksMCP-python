## 1. Branch and adapter read

- [ ] 1.1 After PR #216 merges, rebase `feat/selftest` on main (face mates are needed by the assembly area)
- [ ] 1.2 Check `ISldWorks.GetCurrentLanguage`, `GetUserPreferenceStringValue` and the swDefaultTemplate* values against the API docs and `swconst.tlb`; note them in this design
- [ ] 1.3 Add `get_application_info` to `adapters/base.py` with its docstring and the "not implemented" default
- [ ] 1.4 Implement it in the pywin32 adapter (inside `_handle_com_operation`, each read through `_attempt`, file names only)
- [ ] 1.5 Implement it in `mock_adapter.py`, and add mock tests for both adapters' results, including an unreadable value becoming `None`
- [ ] 1.6 Add it to the circuit-breaker and connection-pool wrappers, with their wrapper tests

## 2. The selftest package

- [ ] 2.1 `expected.py`: the hand calculations from design §4, each with its formula in a comment
- [ ] 2.2 `documents.py`: `DocumentGuard` (baseline, temporary folder, close only its own, delete the folder); tests for a baseline document left open, an unsaved own document closed, cleanup after an exception
- [ ] 2.3 `areas.py`: the part, assembly, drawing and export areas, calling tools through an in-memory FastMCP client; tests with a stub client for pass, a wrong value, and a failed tool call
- [ ] 2.4 `runner.py`: run in order, skip dependents, always run the guard's cleanup; tests for skip propagation
- [ ] 2.5 `environment.py`: the environment section; tests with values missing
- [ ] 2.6 `report.py`: area lines, Markdown summary, prefilled link and its fallback past 8,000 characters; tests for both
- [ ] 2.7 `cli.py`: `selftest` options (`--year`, `--report`, `--config`), the precheck (Windows, installed, running) and exit codes 0/1/2; tests for each exit code
- [ ] 2.8 Route `selftest` and a leading `--selftest` in `server.cli_main`; tests for both spellings

## 3. Issue form and docs

- [ ] 3.1 `.github/ISSUE_TEMPLATE/compatibility.yml` with the `summary` field id the link fills, labelled `compatibility`; create the label
- [ ] 3.2 Point `feedback.yml` and the README's "Tested on" line at the form and the command
- [ ] 3.3 `docs/compatibility.md` (with the nav entry), seeded from the live run in 4.1; mention the command in the install docs
- [ ] 3.4 CHANGELOG, and mark #179 in `openspec/queue.md`

## 4. Live check and sign-off

- [ ] 4.1 Live test `tests/live/test_live_sw_selftest.py`: run the selftest on SolidWorks 2026 with a user-style unsaved part open first; assert every area passes and that part is still open, unsaved and unchanged
- [ ] 4.2 Run the command by hand for the user (live-demo sign-off), and paste its report into the compatibility page's first row
- [ ] 4.3 Full mock suite at 100% coverage, ruff, and `mkdocs build --strict`
