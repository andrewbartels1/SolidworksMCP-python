# TODO — OpenSpec adoption + assembly-aware `list_features`

Branch: `feat/issue-21-openspec-assembly-list-features`
Date: 2026-08-11

## Initial assessment

Two independent asks came in together:

1. Adopt an OpenSpec-style ("spec-driven development") workflow for this
   repo, as a repo-usability improvement in its own right.
2. Pick a good feature issue and implement it *using* that workflow, as the
   first real proof that the process works.
3. Validate PR #49 (`fix/save-file-data-loss`) before treating it as safe,
   since it's a data-loss bug fix and "very fundamental."

Repo already had informal versions of (1): `CONTRIBUTING.md` documents a
process, `docs/planning/` exists for roadmap docs, and issue #23 shows a
contributor (Pedro) writing an ad hoc planning doc in their fork before
starting a large multi-phase proposal. There was no shared, tool-enforced
convention for *how* a proposal → spec → design → tasks sequence should
look, so adopting OpenSpec formalizes something the repo was already
reaching for informally.

## Questions asked and answers received

**Q1: Lightweight in-repo convention vs. the real OpenSpec CLI?**
→ **Adopt the actual OpenSpec CLI** (`@fission-ai/openspec`). Not the
lightweight custom-template option.

**Q2: Which issue should be the first spec-driven change?**
→ **#21, assembly-aware `list_features`**. Chosen over #23 (a large,
multi-phase proposal better suited to being *its own* future OpenSpec
change, not a first example) for being self-contained, having clear
acceptance criteria, and directly improving usability for the most common
real document type (assemblies).

## OpenSpec setup

- Node.js wasn't installed (Python-only toolchain). Installed via
  `winget install OpenJS.NodeJS.LTS` with explicit confirmation first,
  since it's a machine-wide dependency add.
- Verified package identity before running anything: the bare `openspec`
  npm package is an unrelated 2019 placeholder (1.3 kB, v0.0.0, different
  GitHub repo). The real tool is `@fission-ai/openspec`
  (github.com/Fission-AI/OpenSpec), confirmed via `npm search` — GitHub
  Actions OIDC-published, current (v1.8.0 at time of writing).
- Ran `openspec init --tools claude`, which scaffolded `openspec/` and
  `.claude/commands/opsx/*` + `.claude/skills/openspec-*` (6 slash
  commands, 6 skills) for the spec-driven workflow.
- **Fixed `.gitignore`**: `.claude/` was fully ignored repo-wide, which
  would have made the new OpenSpec commands/skills invisible to every
  other contributor and to CI — silently defeating the point of adopting
  a *shared* workflow. Scoped the ignore so `.claude/commands/` and
  `.claude/skills/` are tracked while the rest of `.claude/` (personal
  settings, local session state) stays ignored.
- Populated `openspec/config.yaml` with real project context (adapter
  architecture, COM threading invariants, testing commands) so
  AI-generated proposals/specs/designs are grounded in this repo's actual
  constraints rather than generic boilerplate.

## Issue #21 change: `assembly-aware-list-features`

Full proposal/specs/design/tasks live at
`openspec/changes/assembly-aware-list-features/` and pass
`openspec validate --strict`.

**Important correction made during design, before any code was written**:
issue #21's literal acceptance criteria sketch a nested response shape
(`{"type", "components", "assembly_features"}`). Tracing actual callers of
`adapter.list_features().data` found **four** existing places that assume
it's a flat `list[dict]` unconditionally — the MCP tool's `count`/`features`
fields, `classify_feature_tree`, `soc_pickup.py`'s feature-tree diffing
(SolidWorks-as-Code pickup), and the UI's `model_service.py`. Shipping the
issue's literal shape would have silently broken SoC pickup diffing and the
UI feature panel for every assembly.

**Resolution** (recorded in `design.md`): keep the response a flat list for
every document type. Each feature descriptor gains two new optional keys,
`component` and `component_path` (both `None` for a document's own
features, matching today's Part behavior exactly). Assembly features get
flattened into the same list, tagged by which component they came from,
recursing into sub-assemblies up to a new optional `max_assembly_depth`
parameter (default 2). This satisfies the issue's actual goal
(component-scoped feature visibility) without an API shape that breaks
working code.

## Implementation status: done, pending one live-SolidWorks check

All `tasks.md` items implemented and checked off except 2.6/6.2 (verifying
the `IComponent2.GetModelDoc2` accessor against a live SolidWorks session —
impossible in this environment, no SolidWorks installed). Full suite:
1898 passed, 0 failed, 40 skipped, 73 `solidworks_only` deselected,
coverage 99.98%. `ruff check` clean on every changed file (one pre-existing,
unrelated `UP046` in `base.py`, confirmed identical on `main`).

One self-inflicted detour worth recording: an early `ruff check src tests
--fix` (scoped too broadly) auto-removed imports in `ui/service.py` and
`ui/services/llm_service.py` that looked unused to static analysis but are
actually re-exports test code monkeypatches by module-attribute name —
broke 9 unrelated UI tests. Caught it by re-running the full suite,
reverted both files, confirmed green again. Lesson: scope `ruff --fix` to
the files actually being touched, not the whole tree.

## Text-to-cad integration (#43) — investigated, not started

Looked at #43 and its prerequisite #42 (skill-routing layer) at your
request, to see where the OpenSpec commands/skills just set up could plug
in. Finding: **no direct code-level overlap** — two different meanings of
"skill" collide in name only:

- OpenSpec's `.claude/commands/opsx/*` + `.claude/skills/openspec-*` are
  Claude Code dev-tooling: they help *me* (or any contributor using Claude
  Code) plan changes to *this repo's own source*.
- The `#42`/`#43` "skill family" router (`solidworks-native` /
  `text-to-cad` / `mesh-concept`) is *runtime* orchestration code
  (`src/solidworks_mcp/ui/services/skill_router.py`, per #42's proposed
  shape) that routes an end-user's MCP tool calls — it sits above the
  existing `IntelligentRouter`/`ComplexityAnalyzer` COM/VBA routing and is
  unrelated to Claude Code's own skill-loading.
- The `cad` skill from `earthtojake/text-to-cad` (#43) *is* a Claude Code
  plugin skill (`claude plugin install cad@text-to-cad`), so it lives in
  the same `.claude/` namespace as OpenSpec's skills, but that's a shared
  install location, not a shared code path.

Where OpenSpec *does* apply directly: #43 is already written almost
exactly like an OpenSpec proposal (Summary/Research/Non-goals/Acceptance
criteria) and depends on #42 landing first. It's a strong candidate for a
second `openspec/changes/` entry once you want to start it — but that's
new, unstarted scope (new external dependency, new tool, router wiring)
well beyond this branch's issue #21 work, so I stopped short of drafting
it without checking first.

## Live SolidWorks verification (2026-08-11, later same session)

A real SolidWorks 2026 instance turned out to be running on this machine
after all — closed task 2.6's gap for real instead of leaving it
theoretical:

- Connected to the live session, ran the actual `SolidWorksDocsDiscovery`
  tool (the "read docs" MCP tooling) to cross-check `GetComponents`/
  `IComponent2`/`GetModelDoc2` against the installed SW 2026 (build
  34.3.0) type library before trusting the implementation.
- Exercised `list_features` against the built-in U-Joint sample —
  `UJoint.SLDASM`, which conveniently already contains a nested
  sub-assembly (`crank sub.SLDASM`) — and found **two real bugs neither
  the mock adapter nor any unit test could have caught**, both late-binding
  property-vs-method ambiguities: `document.GetType()` failing on a
  freshly-fetched `ActiveDoc`, and `IComponent2.GetModelDoc2` needing
  explicit `flag_methods` before it resolves. Fixed both; documented as
  `docs/agents/com-api-pitfalls.md` items #11/#12. After the fix, a live
  run resolved all 11 real components across 2 levels of nesting (271
  features total) with zero `UnresolvedComponent` rows.
- **Design refinement from your feedback**: the flat list-with-tags shape
  was right for backward compatibility, but didn't capture actual
  parent/child structure between components. Added a `component_parent`
  tag (still additive/backward-compatible) plus
  `build_component_tree()` — a pure function that reconstructs the real
  nested tree from the flat list — exposed additively as `assembly_tree`
  on the `list_features` MCP tool response. Verified live: `crank sub-1`'s
  three child parts now nest correctly under it instead of sitting flat
  alongside its top-level siblings.
- Added a runnable demo script,
  `docs/getting-started/tutorial-parts/list_features_assembly_demo.py`,
  matching this repo's existing tutorial-script conventions.
- Ran the full mock-only suite again (1903 passed, 0 failed, coverage
  99.96%) and `dev-test-full` against the live SolidWorks session (1925
  passed, 42 skipped, 49 failed, coverage 99.91% — gate passed). Every
  `list_features`/assembly test passed. The 49 failures are all
  `create_part: Failed to create new part` and are **confirmed
  pre-existing and unrelated** to this change — they reproduce identically
  with this branch's commits `git stash`-ed, and persist even with every
  document closed, so it's not a too-many-open-docs issue either. Looks
  like degraded state in the long-running `SLDWORKS.exe` process itself
  after hours of automation churn this session. Flagging for you — a
  SolidWorks restart is the likely fix, but I didn't restart your live
  application unprompted.

## Next steps

1. Open the PR for `assembly-aware-list-features` referencing issue #21
   and this OpenSpec change. Task 2.6 is now fully closed (verified live,
   not just theoretical).
2. Separately: `create_part` is currently failing in your live SolidWorks
   session for reasons unrelated to this branch — worth a SolidWorks
   restart before your next real-integration test run.
3. Decide whether to draft a second OpenSpec change for #43 now or later
   (separate branch either way, since #42 is its prerequisite).
