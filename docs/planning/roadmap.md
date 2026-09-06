# Roadmap

**Last updated:** 2026-09-06

This page tracks the order the open backlog gets worked in. It replaces the
old `docs/planning/ROADMAP_2026_2027.md`, which described a GUI-dashboard-first,
PydanticAI-agent-first strategy that was superseded on 2026-05-17 when the
project pivoted to [SolidWorks-as-Code](../getting-started/solidworks-as-code.md)
and deleted along with the rest of `docs/planning/`. That plan's dated,
quarter-by-quarter phases (`Phase 1A`, `Phase 2C`, etc.) no longer describe
where this project is headed, so this page doesn't reuse them — issues are
grouped by what actually blocks what, not by calendar quarter.

For per-tool SolidWorks COM API coverage (what's implemented vs. missing at
the interface/method level), see
[SolidWorks API Coverage](solidworks-api-coverage.md).

## In progress

**[`close-tool-surface-gaps-and-housekeeping`](https://github.com/andrewbartels1/SolidworksMCP-python/tree/main/openspec/changes/close-tool-surface-gaps-and-housekeeping)**
— 12 small issues bundled into one OpenSpec change: #6, #28, #46, #58, #59,
#60, #61, #62, #63, #64, #79, #81. Full ordering, task breakdown, and
rationale live in that change's `tasks.md` — not duplicated here to avoid
the two going out of sync.

## Backlog: what's ready to start now

No blockers. Can be picked up in any order, based on priority:

| Issue | What | Why it's unblocked |
|---|---|---|
| [#29](https://github.com/andrewbartels1/SolidworksMCP-python/issues/29) | SoC: wire rewind's DB revert + feature suppression | `revert_tool_call_records()` already exists, just unwired |
| [#30](https://github.com/andrewbartels1/SolidworksMCP-python/issues/30) | SoC: pickup reads live dimension values | Extends existing `pickup_changes()` diffing, no new deps |
| [#75](https://github.com/andrewbartels1/SolidworksMCP-python/issues/75) | Portable, installable MCP server setup | Prerequisite #74 already merged |
| [#57](https://github.com/andrewbartels1/SolidworksMCP-python/issues/57) | Sheet metal feature support | Fully uncovered area, no dependency on other backlog items |
| [#77](https://github.com/andrewbartels1/SolidworksMCP-python/issues/77) | `sketch_from_face_loop` + `thin_extrude` | Standalone tools; see note on #76 synergy below |
| [#42](https://github.com/andrewbartels1/SolidworksMCP-python/issues/42) | CAD-generation skill-routing layer | Foundational — gates #43 and #44, itself has no blocker |
| [#78](https://github.com/andrewbartels1/SolidworksMCP-python/issues/78) | SolidWorks Simulation COM API wrapper | Foundational for #76's paid-Simulation path, no blocker itself |
| [#22](https://github.com/andrewbartels1/SolidworksMCP-python/issues/22) | Context and glossary injection engine (TAG-style domain context) | Confirmed direction (2026-08-27) — #12, the overlapping alternative, was closed in favor of this. Gates #13, see below |

## Backlog: gated, in dependency order

Each arrow means "must land first." Citations are to the dependent issue's
own text, not inferred.

```
#29 ─┐
     ├─→ #31 (SoC tutorial/docs) ─→ #80 (prompt-to-SW tutorials)
#30 ─┘
     "Builds on #31" — #80's own body

#42 (routing layer) ─→ #43 (text-to-cad integration)
                    └─→ #44 (CADAM live-render UI)
     #43: "connective-tissue piece for #43 ... and #44" — #42's own body
     #44: "visualization layer for the mesh-concept/general chat path
           in #42's router" — #44's own body

#22 (context/glossary injection engine) ─→ #13 (end-to-end agent test)
     #13 tests "prompt construction, context assembly, RAG retrieval,
     planning output, MCP tool awareness" together — the deliverable
     of #22 — per #13's own body. (#12 described the same
     context-assembly problem from a different angle; closed 2026-08-27
     in favor of #22 as the confirmed direction — see note below.)
```

`#76` (cheapo topology-optimization loop) has two real dependencies, both
stated in its own issue body, plus one unresolved contradiction with #78
— see [Open scoping questions](#open-scoping-questions-before-scheduling)
below before treating it as sequenced.

## Open scoping questions before scheduling

These aren't mine to resolve — each needs a maintainer decision that would
change scope, approach, or order if answered differently.

### #23 — awaiting a response, and the fork is much bigger than the issue says

[#23](https://github.com/andrewbartels1/SolidworksMCP-python/issues/23) is a
community contributor's (`@pedropaulovc`) proposal for ~31 new tools across
8 phases (assembly mates, reference geometry, parametric variants, BOM,
measurement), with a plan doc linked in their fork. The issue asks the
maintainer three direct questions (does the plan look reasonable, what PR
cadence, thoughts on the plan's own "open questions" section) that haven't
been answered yet.

**2026-08-27 investigation** (`git fetch` from
`github.com/pedropaulovc/SolidworksMCP-python`, all 8 branches inspected):
the fork has diverged far past what #23's text describes. `pedro/personal`
alone has 434 commits vs. this repo's 367 at their shared ancestor, with
its own independent PR numbering (their PR #92-94 range, unrelated to this
repo's issue numbers) covering things #23 never mentions: DXF/DWG import,
motion-study video export, a 3DEXPERIENCE-connector start/stop/recover
path, SolidWorks crash/hung-window health probes, and — directly relevant
to this repo's current batch — **a `rename_feature` adapter method**
(commit `bde0ff1`, their PR #73) already implementing what this repo's #59
task 2 is about to build from scratch (see that task's prior-art note).
Their fork's own README claims 156 tools, well past this repo's 122.

This changes the recommended next step: a re-audit of #23 as originally
scoped (the same pattern used for #6/#58/#59) would miss most of what's
actually available.

**2026-08-30 review findings** (real diff, not commit-message skimming —
`_generated/sldworks_2026.py`, a 102,444-line auto-generated COM typelib
wrapper, was inflating the raw diff stats; excluding it, `pedro/personal`'s
real diff is ~38k lines across 80 files):

| Finding | Action taken |
|---|---|
| `rename_feature` (commit `bde0ff1`) already implements #59's task 2 | **Done** — implemented fresh on the same `IFeature.Name` setter approach, wired through every adapter layer with mock + live tests, verified against real SW; shipped with #60/#61 in the Wave 2 PR |
| `create_reference_plane` negative-offset bug (commit `3c091fd`) — `InsertRefPlane`'s Distance constraint clamps a negative value to 0 instead of erroring, silently collapsing the plane onto its base | **Fixed directly** — filed as [#84](https://github.com/andrewbartels1/SolidworksMCP-python/issues/84), ported the sign-resolution fix (credited to `@pedropaulovc`) into `features.py`, added direct unit coverage, `dev-test`-verified |
| Motion Study support (`motion.py`, `assembly.py` extensions, ~1200 lines, live-demo-verified) — matches this repo's own "Motion Study ❌ Missing" finding from the #79 audit | Confirmed we have **zero** existing Motion Study code to conflict with. Substantial enough (tested adapter + tools + mock parity + a working live demo) that it's a real candidate for its own future OpenSpec change, not a quick port |
| DXF/DWG import, 3DEXPERIENCE-connector start/stop/recover, SolidWorks crash/hung-window health probes, `swdimxpert` auxiliary-typelib plumbing, `add_fillet` propagate option, a `SetEntitiesToMate` COM-typing fix | Catalogued, not yet reviewed for convention-fit or mergeability |

**Recommended next step:** the two small, self-contained, already-verified
items (`rename_feature`, the offset fix) are actioned or ready to action
without needing a whole new OpenSpec change. The larger items (Motion
Study especially) still warrant their own scoped OpenSpec change before
touching Pedro's cadence/scope questions on #23 itself.

### #12 vs. #22 — resolved 2026-08-27

[#12](https://github.com/andrewbartels1/SolidworksMCP-python/issues/12)
("simple context layer so UI RAG actually drives agent context") and
[#22](https://github.com/andrewbartels1/SolidworksMCP-python/issues/22)
("context and glossary injection engine — TAG-style domain context") both
described a layer between retrieval and prompt construction that decides
what the model actually sees — #12 framed around the UI/RAG path, #22
framed around a structured glossary/domain-knowledge injection pattern.
**Maintainer decision:** #12 isn't the direction the project is headed —
closed, with #22 confirmed as the actual scope for this work (now listed
in "ready to start now" above). #13 tests #22's deliverable specifically.

### #76 vs. #78 — confirmed, not a contradiction: Option B needs re-scoping

**Update 2026-08-27, confirmed against SolidWorks's own API docs:**
SimulationXpress genuinely has no COM API of its own — this is settled, not
in dispute between #76 and #78. What #78 found (and SolidWorks's docs
confirm) is the actual automatable path: *"To automate tasks that mimic
SimulationXpress functionality (such as setting up fixtures, applying
loads, meshing, and running a static analysis on a single part), you must
use the `SldWorks` and `CosmosWorks` interfaces within a VBA Macro, C#, or
C++ environment."* `CosmosWorks` is the **paid** Simulation add-in's COM
interface (matches #78's own finding: `CWAddincallback` → `CWModelDoc` →
`CWStudyManager` → `CWStudy` → `CWMesh`/`CWLoads`/`CWFixt...`) — it can
reproduce SimulationXpress-equivalent results, but only through the paid
add-in, not through free SimulationXpress itself.

Net effect on #76 Option B ("native SW only... SimulationXpress COM
automation... no paid add-in required"): the *automation* half is
achievable via `CosmosWorks`, but the *no paid add-in* half isn't — those
two goals can't both hold. #76 needs Option B re-scoped as "paid Simulation
add-in via CosmosWorks" (drops the free-tier promise) before it's
schedulable, or the issue commits to Option A (FreeCAD + CalculiX,
genuinely free, external to SolidWorks) as the only free-tier path.

#76 also has an explicit, undisputed dependency: *"Phase 2 and 3 require
global variable read/write via MCP"* — tracked in #23, not yet built (see
above). #77 (`sketch_from_face_loop`/`thin_extrude`) isn't a stated
dependency of #76, but both describe "topology-robust" cutting/sketching
against face geometry — worth building #77 first as a foundation even
though nothing requires it.

## Not yet triaged into this roadmap

Everything above accounts for every open issue except the 12 already in
`close-tool-surface-gaps-and-housekeeping`. If a new issue is filed, add it
to one of the three sections above (ready now / gated / needs a decision)
rather than leaving it off this page — an untracked issue is exactly the
kind of drift this page exists to prevent.
