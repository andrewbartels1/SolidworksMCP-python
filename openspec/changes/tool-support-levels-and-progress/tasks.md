## 1. Support levels

- [ ] 1.1 `src/solidworks_mcp/tools/support_levels.py`: the table, filled by the rules in design.md; tests in `tests/solidworks_mcp/tools/test_support_levels.py`
- [ ] 1.2 Review the first assignment with the user, tool by tool for the borderline ones; record the reasons
- [ ] 1.3 `tool_boundary.py`: add the `level:<level>` tag and the `warning` on beta/experimental successes; tests beside it
- [ ] 1.4 `tests/integration/test_support_levels.py`: every tool listed, no stale names, planned ⇔ "Not available yet", stable has a live test or is offline
- [ ] 1.5 Rewrite the opening sentence of every beta and experimental tool's description; extend the description check

## 2. COM coverage

- [ ] 2.1 `src/utils/snapshot_com_api.py` (Windows, by hand) and the committed `docs/assets/progress/com_snapshot.json`
- [ ] 2.2 The adapter scan and core-interface coverage, with tests on a small fixture

## 3. Progress image, data and page

- [ ] 3.1 `src/utils/generate_progress.py`: `progress.svg` and `progress.json`; tests
- [ ] 3.2 `tests/integration/test_progress_up_to_date.py`: fails when either is stale, naming the command
- [ ] 3.3 `docs/progress.md` with the no-script table and `docs/javascripts/progress.js` filters; mkdocs nav; `mkdocs build --strict`
- [ ] 3.4 Show the user the SVG and the page before wiring them into the README

## 4. README and docs

- [ ] 4.1 README: the progress image at the top linking to the page; a "two tools in one" section (Python interface for scripting SolidWorks, and an MCP server on it)
- [ ] 4.2 `docs/agents/tool-description-standard.md` and the agent skill: what the levels mean; the queue's small-faults list note: a fixed fault moves its tool up a level
- [ ] 4.3 CHANGELOG; `openspec/queue.md` (this change before #179; #79's coverage half done)

## 5. Ship

- [ ] 5.1 Full mock suite, ruff, 100 % coverage, `mkdocs build --strict`
