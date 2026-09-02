## Why

A feature-parity review filed a batch of small tool gaps (#58–#64) alongside
one bug (#6), one DB feature (#28), two docs issues (#46, #79), and a repo
housekeeping item found during triage (#81) — 12 issues total, none big
enough to deserve its own change, all cluttering the backlog. Auditing them
against `main` also found #6, #58, and #59 partly shipped already (PRs #66,
#68, #69) without the issues being closed, so their real remaining scope is
smaller than filed. This change bundles the actual remaining work into one
plan instead of 12 one-off PRs.

## What Changes

| # | Change |
|---|--------|
| #6 | `checkpoint_service.py` still mocks `check_interference` even though the adapter/tool support it (PR #66). Wire it up. |
| #59 | Add `rename_feature` — the one gap left after suppress/delete/undo (PR #68). |
| #58 | Add `create_reference_point` — the one gap left after plane/axis (PR #69). Broadening `create_axis` past x/y/z is deferred (see design.md). |
| #60 | Add `set_units`; wire it into `create_part`'s currently-ignored `units` param. |
| #61 | Add `list_open_documents` and `activate_document`. |
| #62 | Add `save_body_as_part` (multibody → standalone part). |
| #63 | Add `auto_center_marks` for drawing views. |
| #64 | Split `search_solidworks_api_help` into granular lookups (method/interface/enum/related). Lowest priority in this batch. |
| #28 | Add a `script_line` column to `ToolCallRecord`, rendered at write time. |
| #46 | Fix broken doc links/orphaned pages; pin `mkdocs-material` `<10`. |
| #79 | Add a COM-API coverage table (`docs/api-coverage.md`, wired into the docs build, plus a concise version in `README.md`), once the above tools exist to audit. License-tier tags are deferred to a future change (see design.md). |
| #81 | Remove three ad-hoc debug scripts from repo root (`test_*.py`, never collected by pytest — clutter, not a test-suite defect). |

Every item except #28/#46/#79/#81 adds real COM calls, so each gets its own
`mock_adapter.py` counterpart and runs on the adapter's existing
`ComExecutor` thread — no new threading, no new dependencies, no breaking
changes to existing tools.

## Capabilities

**New:** `tools/feature-rename` (#59) · `tools/reference-point` (#58) ·
`tools/document-units` (#60) · `tools/document-session-management` (#61) ·
`tools/multibody-part-export` (#62) · `tools/drawing-center-marks` (#63) ·
`tools/api-help-lookup` (#64) · `soc/script-line-capture` (#28)

**Modified:** none — #6 is a routing fix with no change to
`check_interference`'s documented behavior; #46/#79 are docs-only.

## Impact

- Adapters: `base.py` (new method signatures), `pywin32_adapter.py` +
  `adapters/solidworks/{features,io}.py` (real implementations),
  `mock_adapter.py` (mirrored mocks)
- Tools: `modeling.py`, `file_management.py`, `drawing.py`,
  `docs_discovery.py` (new registrations)
- `ui/services/checkpoint_service.py` (#6, #28), `history_db.py` +
  `soc_exporter.py` (#28)
- `docs/`, `mkdocs.yml`, `README.md`, new `docs/api-coverage.md` (#46, #79)
- `tests/` — new mock-backed unit tests per tool; nothing existing changes
  behavior
- Repo root — remove or relocate `test_api_response.py`,
  `test_docs_discovery_run.py`, `test_workflow_fields.py` (#81)
