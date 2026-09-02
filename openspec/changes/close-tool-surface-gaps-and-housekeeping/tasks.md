## 1. #6 — check_interference dispatch

- [x] 1.1 Rebase/cherry-pick `ae37563` from
      `fix/issue-6-interference-check-dispatch` onto `main`; if it doesn't
      apply cleanly or its tests fail, reimplement by hand (drop
      `check_interference` from `_MOCKED_TOOLS`, add a dispatch branch
      matching the existing pattern). Done 2026-08-30: cherry-pick hit 8
      real conflicts (branch predates a lot of merged work), aborted and
      reimplemented by hand in `checkpoint_service.py` per the documented
      fallback. Also fixed a stale "check_interference [mocked until
      wired]" mention in `llm_service.py`'s local-agent tool-catalog prompt
      text, found while checking for other references.
- [ ] 1.2 Run the mock-only suite; confirm a checkpoint exercising
      `check_interference` reports a real result, not `status: "mocked"`;
      open a PR closing #6. Suite run + new/updated tests done (7 stale
      "check_interference is mocked" test assertions found and fixed
      across `test_checkpoint_service.py`, `test_service_coverage_push.py`,
      `test_service_helpers.py`, `test_session_service.py`; 2 new dedicated
      dispatch tests added). PR not yet opened — pending commit/PR strategy
      decision.

## 2. #59 — rename_feature

- [ ] 2.0 Check prior art before implementing from scratch: contributor
      `@pedropaulovc`'s fork (`github.com/pedropaulovc/SolidworksMCP-python`,
      branch `claude/nameplate-dxf-import-bb1ywj`, commit `bde0ff1`, their
      PR #73) already has a `rename_feature` adapter method, using the
      settable `IFeature.Name` property rather than a COM method call. That
      fork has diverged substantially (434 commits vs. this repo's 367 at
      a shared ancestor, its own README claims 156 tools) — review the
      specific commit for correctness and fit with this repo's current
      conventions (read-back discipline, mock_adapter parity, COM
      threading rules) before adapting it; do not merge wholesale
- [ ] 2.1 Verify the live rename signature, implement `rename_feature`
      (`base.py`/`pywin32_adapter.py`) with read-back verification, and
      register it in `modeling.py`
- [ ] 2.2 Add the matching `mock_adapter.py` implementation
- [ ] 2.3 Add tests for successful rename, unresolvable feature, and name
      collision (`specs/tools/feature-rename`); verify `dev-test` passes

## 3. #58 — create_reference_point

- [ ] 3.1 Verify the live vertex/curve/sketch-point signatures, implement
      `create_reference_point` with read-back verification, and register
      it in `modeling.py`
- [ ] 3.2 Add the matching `mock_adapter.py` implementation
- [ ] 3.3 Add tests for all three placement modes and an unresolvable
      reference (`specs/tools/reference-point`); verify `dev-test` passes

## 4. #60 — set_units

- [ ] 4.1 Verify the live unit-preference API, implement `set_units`,
      register it in `modeling.py`, and wire `create_part`'s `units`
      parameter through it
- [ ] 4.2 Add the matching `mock_adapter.py` implementation
- [ ] 4.3 Add tests for unit application, no-active-document failure, and
      `create_part(units=...)` (`specs/tools/document-units`); verify
      `dev-test` passes

## 5. #61 — list_open_documents + activate_document

- [ ] 5.1 Implement both using `ISldWorks.GetDocuments` as source of
      truth, and register them in `file_management.py`
- [ ] 5.2 Add the matching `mock_adapter.py` implementations
      (multi-document fixture)
- [ ] 5.3 Add tests for enumeration (multiple/zero open), successful
      activation, and activating a document that isn't open
      (`specs/tools/document-session-management`); verify `dev-test` passes

## 6. #62 — save_body_as_part

- [ ] 6.1 Verify the live body-extraction COM path, implement
      `save_body_as_part` reusing the existing `save_as` write path, and
      register it in `modeling.py`
- [ ] 6.2 Add the matching `mock_adapter.py` implementation (multibody
      fixture)
- [ ] 6.3 Add tests for successful extraction, unresolvable body name, and
      an unaffected source part (`specs/tools/multibody-part-export`);
      verify `dev-test` passes

## 7. #63 — auto_center_marks

- [ ] 7.1 Verify the live center-mark COM path, implement
      `auto_center_marks` returning the inserted count, and register it in
      `drawing.py`
- [ ] 7.2 Add the matching `mock_adapter.py` implementation
- [ ] 7.3 Add tests for a view with holes, a view with none, and an
      unresolvable view name (`specs/tools/drawing-center-marks`); verify
      `dev-test` passes

## 8. #64 — Granular API lookup tools

- [ ] 8.1 Confirm the existing indexed API-doc structure in
      `docs_discovery.py` supports method/interface/enum-keyed lookups
      without re-indexing
- [ ] 8.2 Implement `lookup_api_method`, `lookup_api_interface`,
      `lookup_api_enum`, and a related-members lookup in
      `docs_discovery.py`; register them as MCP tools
- [ ] 8.3 Add tests for a known/unknown case per lookup, plus a regression
      test confirming `search_solidworks_api_help` is unchanged
      (`specs/tools/api-help-lookup`); verify `dev-test` passes

## 9. #28 — script_line column

- [ ] 9.1 Add the nullable `script_line` column to `ToolCallRecord` in
      `history_db.py`; add a startup check in `init_db()` (`PRAGMA
      table_info(toolcallrecord)`, `ALTER TABLE ... ADD COLUMN
      script_line TEXT` if missing) so existing local DBs pick up the
      column without Alembic; add `render_single()` to `soc_exporter.py`
- [ ] 9.2 Wire `script_line` through `insert_tool_call_record` and its
      call sites (`checkpoint_service.py`)
- [ ] 9.3 Update `export_session` to join stored `script_line` with a
      fallback re-render for legacy rows
- [ ] 9.4 Add tests for a new record's stored line, a session export
      mixing legacy/new records, and `init_db()` against a fixture DB file
      created without the `script_line` column (confirms the `ALTER
      TABLE` check adds it without error) (`specs/soc/script-line-capture`);
      verify `dev-test` passes

## 10. #46 — Docs housekeeping

- [ ] 10.1 Fix the broken links and orphaned pages listed in the issue;
       verify with `dev-docs-build`. Fully resolved ahead of implementation
       (2026-08-27) for the 7 orphaned pages found beyond the issue's own
       list: 4 with real inbound links from in-nav content were added to
       `mkdocs.yml` nav (`agent-memory-and-recovery.md`,
       `agent-ui-workflows.md`, `screenshot-equivalence.md`,
       `solidworks-ui-llm-tutorial.md`); 3 with zero inbound links anywhere
       in the repo were deleted (`agent-invocation-reference.md`,
       `ai-assisted-design-workflow.md`, `docs-discovery-tool-design.md`).
       `dev-docs-build` confirms zero orphaned pages remain. Still open:
       the issue's own original broken-links table (Part 1)
- [ ] 10.2 Fix the docstring/mkdocstrings warnings, pin `mkdocs-material`
       to `<10` in `pyproject.toml`, and record the theme-migration
       decision (even "stay pinned, revisit later")
- [ ] 10.3 Run `dev-docs-build` and `dev-docs-strict`; verify a clean run

## 11. #79 — API coverage audit

- [ ] 11.1 Re-audit COM-domain-vs-MCP-tool coverage against the surface as
       it stands after tasks 1–8, write `docs/api-coverage.md`, and add it
       to `mkdocs.yml`'s `nav:` so it builds automatically through the
       existing `deploy-docs.yml` workflow (already runs on every push/PR
       to `main` — no new CI wiring needed)
- [ ] 11.2 Add a "SolidWorks API Coverage" section to `README.md`: a
       concise summary table inline (not just a link) plus a link to the
       full `docs/api-coverage.md` page; while touching it, fix
       `mkdocs.yml`'s `site_description` stale tool count to match the
       audited total
- [ ] 11.3 Run `dev-docs-build` and `dev-docs-strict`; verify both the new
       page and the README section render cleanly

**Deferred to a future change:** per-tool license-tier tags
(`[Maker]`/`[Standard]`/`[Professional]`/`[Simulation]`/`[PDM]`) — needs a
live check against SolidWorks's current Maker-plan feature list, which
isn't verifiable during planning and is more scope than this housekeeping
batch warrants. Tracked as a backlog item in `SWChecklist.md`.

## 12. #81 — Remove root-level debug scripts

- [ ] 12.1 Decide per-file: delete `test_api_response.py` and
       `test_workflow_fields.py` (historical template-literal check, no
       open issue references it), or port the check into a real
       `tests/`-based assertion test if still wanted
- [ ] 12.2 Delete `test_docs_discovery_run.py` or relocate it to
       `tests/scripts/` (renamed off the `test_` prefix) if the manual
       live-SolidWorks smoke run still has value
- [ ] 12.3 Verify no `test_*.py` files remain in repo root and `dev-test`
       still passes
