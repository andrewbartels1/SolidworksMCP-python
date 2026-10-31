## Context

See proposal.md for why. All new adapter methods follow the pattern set by
PR #68/#69: abstract method on `base.py`, real implementation dispatched
from `pywin32_adapter.py`, a mirrored `mock_adapter.py` implementation,
`AdapterResult`-shaped return, all COM calls on the existing `ComExecutor`
thread.

## Goals / Non-Goals

**Goals:** close the verified-remaining scope of each issue with minimal
new abstraction, keep mock and real adapters in lockstep, ship the batch
in the agreed order (tasks.md).

**Non-Goals:**
- Per-tool license-tier tags for #79 (`[Maker]`/`[Standard]`/etc.) — needs
  a live check against SolidWorks's current Maker-plan feature list,
  which isn't verifiable during planning; the COM-domain coverage table
  itself still ships in this batch. Tracked as a future backlog item.
- Broadening `create_axis` past x/y/z (general two-point / face / plane-pair
  axes). Real scope from #58's original ask, but a materially bigger COM
  surface than the rest of this batch — deferred to a future change.
- Any UI/dashboard work beyond `checkpoint_service.py`'s existing generic
  dispatch.
- The rest of the backlog (#13, #22, #23, #29, #30, #31, #42, #43,
  #44, #57, #75, #76–78, #80) — out of scope for this batch. (#12, formerly
  listed here, was closed 2026-08-27 — not the project's direction; see
  `docs/planning/roadmap.md`.)

## Decisions

**#6 — verify-then-land.** `origin/fix/issue-6-interference-check-dispatch`
(commit `ae37563`) claims passing tests but predates several merged PRs.
Try rebasing it onto `main` first; only reimplement by hand (a ~10-line
diff: drop `check_interference` from `_MOCKED_TOOLS`, add one dispatch
branch) if it no longer applies cleanly.

**#28 — render at write time, not read time.** `script_line` is computed
once on insert (`render_single()` in `soc_exporter.py`), so every row is
self-describing. Legacy rows stay `NULL`; export falls back to full
re-render only for those — a one-time bridge, not a permanent dual-path.

**#28 — schema change via a startup column check, not a migration
framework.** This repo has no migration tooling (`init_db()` only calls
`SQLModel.metadata.create_all()`, which does not alter an already-existing
table — confirmed via audit, see the proposal-auditor concern register).
Adding `script_line` to the SQLModel class alone would make every insert
on a pre-existing local DB fail with `no such column: script_line`.
`init_db()` gains a small startup check instead: query
`PRAGMA table_info(toolcallrecord)`, and if `script_line` isn't present,
run `ALTER TABLE toolcallrecord ADD COLUMN script_line TEXT`. No new
dependency (Alembic was considered and rejected as heavier than this
one-column change warrants); a fresh DB gets the column via `create_all()`
as normal and the check is a no-op.

**#58/#59 reuse the existing read-back discipline.** SolidWorks COM edit
calls (rename, suppress, delete) often don't report success through their
return value. Per `docs/agents/com-api-pitfalls.md` and PR #68's approach,
`rename_feature` and `create_reference_point` both verify by re-resolving
the feature/point by name after the call, before reporting success.

**#61 reads live COM state.** `list_open_documents` uses
`ISldWorks.GetDocuments` as the source of truth — nothing in the adapter
currently tracks "what's open" (an earlier draft of this doc claimed the
adapter already had internal session-doc tracking to build on; that
doesn't exist in the current codebase, confirmed by full-repo search, so
this is new state, not a wrapper around existing bookkeeping). This keeps
the answer correct even for documents opened outside this adapter's own
session. `ActivateDoc3` is already used internally elsewhere in `io.py`
(document-open flows), so `activate_document` reuses a call pattern
already proven against the live COM API rather than introducing a new one.

**#64 is purely additive.** `search_solidworks_api_help` and
`discover_solidworks_docs` are untouched; the four new lookups query
whatever indexed structure `docs_discovery.py` already builds, more
narrowly.

**#46/#79 have no adapter surface.** Docs-only — no spec deltas.

## Risks / Trade-offs

- The #6 branch may not cherry-pick cleanly onto current `main` → low
  effort either way; the fallback diff is small and well understood.
- `save_body_as_part`'s COM path (`CreatePartDocumentFromBody` vs. an
  "Insert > Features > Save Bodies" equivalent) is version-dependent per
  the issue's own notes → verify the live signature before implementing,
  as its own task rather than assumed upfront.
- `auto_center_marks`'s COM path is similarly version-dependent → same
  verify-first approach.

## Migration Plan

#28 requires the startup column check described above (`PRAGMA
table_info` + `ALTER TABLE` if missing) — the only schema change in this
batch. No backfill needed: legacy rows keep `script_line = NULL` and
export falls back to on-demand rendering for them. No breaking changes to
any existing tool. Each of the 12 items is independently mergeable in
tasks.md order; none blocks another outside this batch.
