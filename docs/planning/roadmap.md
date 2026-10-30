# Roadmap

**Last updated:** 2026-10-30

This page tracks the order the open backlog gets worked in. It replaces the
old `docs/planning/ROADMAP_2026_2027.md`, which described a GUI-dashboard-first,
PydanticAI-agent-first strategy that was superseded on 2026-05-17 when the
project pivoted to [SolidWorks-as-Code](../getting-started/solidworks-as-code.md)
and deleted along with the rest of `docs/planning/`. That plan's dated,
quarter-by-quarter phases (`Phase 1A`, `Phase 2C`, etc.) no longer describe
where this project is headed, so this page doesn't reuse them — issues are
ranked by priority and by what blocks what, not by calendar quarter.

For per-tool SolidWorks COM API coverage (what's implemented vs. missing at
the interface/method level), see
[SolidWorks API Coverage](solidworks-api-coverage.md).

## How work is ordered

Open issues are ranked in four tiers, then by order within each tier:

- **P0 — first impression:** what a new user sees and installs.
- **P1 — trust and quality:** claims backed by evidence, bugs, agent ergonomics.
- **P2 — capability gaps:** new or deeper tools.
- **P3 — research and long horizon.**

Sizes are rough: **S** about a day, **M** 2–4 days, **L** 1–2 weeks, **XL**
several weeks. Each issue becomes an OpenSpec change under
[`openspec/changes/`](https://github.com/andrewbartels1/SolidworksMCP-python/tree/main/openspec/changes)
before it is built; finished changes are archived under
`openspec/changes/archive/`, and their specs merge into
[`openspec/specs/`](https://github.com/andrewbartels1/SolidworksMCP-python/tree/main/openspec/specs),
which describes what the server does today.

**Done recently:** the 12-issue `close-tool-surface-gaps-and-housekeeping`
batch (#79 moved out), the unwired adapter tools (#106), one error boundary
and honest coverage (PR #118), the drawing-package tools (#117), repo
clean-up (PR #177), and the release pipeline (PR #178, which superseded #75).

## P0 — first impression

| Order | Issue | What | Size | Note |
|---|---|---|---|---|
| 1 | [#171](https://github.com/andrewbartels1/SolidworksMCP-python/issues/171) | Repo clean-up: description, topics, community files, tidy root | S | Mostly done in PR #177; social-preview image and `good first issue` labels left |
| 2 | [#172](https://github.com/andrewbartels1/SolidworksMCP-python/issues/172) | Publish to PyPI, GitHub Releases and the MCP Registry | M | Pipeline merged in PR #178; first release is 1.5.0, after #173 |
| 3 | [#173](https://github.com/andrewbartels1/SolidworksMCP-python/issues/173) | `verify_model`: check a part or assembly against expected values, plus measured change on extrude, revolve and cut | M | **In progress** (change `verify-model-against-expectations`): built, live tests next. The demo's final step |
| 4 | [#147](https://github.com/andrewbartels1/SolidworksMCP-python/issues/147) | Bracket-assembly demo: one prompt to an assembly, read back and verified, ending in a drawing package with BOM | M–L | The README's demo GIF; the gaps it finds become issues |
| 5 | — | README rewrite: demo first, three-line install, only claims the status matrix backs, specific "not yet supported" list | M | Issue to be filed; after #172 and #147 |

## P1 — trust and quality

| Order | Issue | What | Size | Note |
|---|---|---|---|---|
| 6 | [#79](https://github.com/andrewbartels1/SolidworksMCP-python/issues/79) | Per-tool status: verified live / pilot / simulated | M | Prerequisite for any public tool-count claim |
| 7 | [#179](https://github.com/andrewbartels1/SolidworksMCP-python/issues/179) | `--selftest` command and a compatibility-report issue template | M | Feeds #79 with real results from other SolidWorks versions |
| 8 | [#174](https://github.com/andrewbartels1/SolidworksMCP-python/issues/174) | Consolidate duplicate and overlapping tools | S–M | Honest count, smaller tool list |
| 9 | [#175](https://github.com/andrewbartels1/SolidworksMCP-python/issues/175) | Agent skill and server guidance for using the tools well | M | Builds on #82 and the COM pitfall catalogue |
| 10 | [#82](https://github.com/andrewbartels1/SolidworksMCP-python/issues/82) | Audit tool docstrings and error messages for LLM usefulness | L | Runtime-error half done in PR #118; feeds #175 and #176 |
| 11 | [#156](https://github.com/andrewbartels1/SolidworksMCP-python/issues/156) | Tool catalog pages drift from the generator | S | Add a check |
| 12 | [#155](https://github.com/andrewbartels1/SolidworksMCP-python/issues/155) | `docs_discovery` can launch a hidden SolidWorks; misleading hint | S | Bug |
| 13 | [#101](https://github.com/andrewbartels1/SolidworksMCP-python/issues/101) | `save_body_as_part` leaves a linked assembly open | S | Bug |
| 14 | [#23](https://github.com/andrewbartels1/SolidworksMCP-python/issues/23) | Reply to the contributor's tool-expansion proposal | S | An active outside contributor; see [scoping notes](#open-scoping-questions-before-scheduling) |

## P2 — capability gaps

| Order | Issue | What | Size | Note |
|---|---|---|---|---|
| 15 | [#176](https://github.com/andrewbartels1/SolidworksMCP-python/issues/176) | Optional tool-discovery mode to cut schema context | M | Measure the tool-list size first |
| 16 | [#83](https://github.com/andrewbartels1/SolidworksMCP-python/issues/83) | Real startup banner and better logging | S | First-run impression |
| 17 | [#157](https://github.com/andrewbartels1/SolidworksMCP-python/issues/157) | Remove stale `validate_coverage.py`; decide on mypy in CI | S |  |
| 18 | [#115](https://github.com/andrewbartels1/SolidworksMCP-python/issues/115) | `reset_circuit_breaker` tool | S | Follow-up from PR #118 |
| 19 | [#97](https://github.com/andrewbartels1/SolidworksMCP-python/issues/97) | `execute_macro` hangs on a modal macro | M | Issue text predates the COM threading change; refresh it |
| 20 | [#158](https://github.com/andrewbartels1/SolidworksMCP-python/issues/158) | Drawing-tool follow-ups from the live sign-off | M |  |
| 21 | [#102](https://github.com/andrewbartels1/SolidworksMCP-python/issues/102) | Live COM for `add_dimension` / `auto_dimension_view` | M | Check overlap with `insert_model_dimensions` (#146) first; may close |
| 22 | [#105](https://github.com/andrewbartels1/SolidworksMCP-python/issues/105) | `sketch_convert_entities` tool | M |  |
| 23 | [#77](https://github.com/andrewbartels1/SolidworksMCP-python/issues/77) | `sketch_from_face_loop` + `thin_extrude` | M | Foundation for #76 |
| 24 | [#57](https://github.com/andrewbartels1/SolidworksMCP-python/issues/57) | Sheet metal features | L |  |

## P3 — research and long horizon

| Order | Issue | What | Size | Note |
|---|---|---|---|---|
| 25 | [#95](https://github.com/andrewbartels1/SolidworksMCP-python/issues/95) | `lookup_api_enum` enum value lookup | S | Needs the swconst enums indexed |
| 26 | #29 · #30 · #31 | SolidWorks-as-Code: rewind, pickup, tutorial | M each | #31 is gated on #29 and #30 (below) |
| 27 | [#96](https://github.com/andrewbartels1/SolidworksMCP-python/issues/96) | Generate a runnable binary `.swp` from VBA source | L |  |
| 28 | [#80](https://github.com/andrewbartels1/SolidworksMCP-python/issues/80) | Prompt-to-SolidWorks tutorials | L | Rescope: SimulationXpress has no COM API (see #76 notes) |
| 29 | [#13](https://github.com/andrewbartels1/SolidworksMCP-python/issues/13) | End-to-end agent test | L | Gated on #22 |
| 30 | [#22](https://github.com/andrewbartels1/SolidworksMCP-python/issues/22) | Context and glossary injection engine | L | Partly overlaps #175 |
| 31 | #78 · #76 | Simulation COM wrapper; topology-optimisation loop | XL | See scoping notes below |
| 32 | #42 · #43 · #44 | Generation-intent router, text-to-CAD branch, live render panel | XL | Long horizon |

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
Their fork's own README claims 156 tools, well past this repo's 122 at the time (152 as of 2026-10-30).

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
closed, with #22 confirmed as the actual scope for this work (now ranked in
P3 above). #13 tests #22's deliverable specifically.

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

## Keeping this page current

The four tiers above account for every open issue as of 2026-10-30. When an
issue is filed, give it a tier, an order and a size here rather than leaving
it off this page; an untracked issue is exactly the drift this page exists to
prevent.
