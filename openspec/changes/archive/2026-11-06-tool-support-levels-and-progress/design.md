## Context

See proposal.md for why. Current state (counted 2026-11-06 on main):

- 154 registered tools. 39 say "Not available yet" (the queue's not-available list). Of the other 115, 81 are called by name in a `tests/live/` test and 34 are not. Some of the 34 are run only by demo scripts that live tests load (`save_part`, `export_stl` via `scripts/demo_monitor_stand.py`), and some never touch SolidWorks at all (the `generate_vba_*` tools, `search_solidworks_api_help`, `find_related_api_members`).
- `tool_boundary.with_tool_metadata` already adds the family tag (`tool_family`, the module name) and the MCP hints at registration; the level tag and the `warning` fit in the same place.
- The type library (`sw_type_info`, gen_py) has 418 interfaces and 9,282 methods (5,985 distinct names). A plain text scan finds about 199 of those names called in `src/solidworks_mcp/adapters/`. gen_py only exists on Windows with SolidWorks, so CI can't read it.
- The docs site is MkDocs Material, deployed to GitHub Pages on push to main (`deploy-docs.yml`).
- the queue's small-faults list lists the known faults; the agent skill's `references/errors-and-limits.md` repeats them.

## Goals / Non-Goals

**Goals:** a level for every tool that a check keeps honest; the level visible to agents (tags, description, `warning`) and people (README bar, docs page); COM coverage measured the same way every time; the README image and page regenerate from one command, and a check catches when they weren't.

**Non-Goals:**
- Fixing the faults or implementing planned tools (the queue's not-available and small-faults lists); this change only labels them.
- Licence-tier tags (#79's second half): a later change.
- Exact COM coverage. A name scan can't tell `IFeature.Name` from `IComponent2.Name`; the page says the figure is approximate.

## Decisions

### The table: `tools/support_levels.py`

A dict `tool name -> (level, reason)` in one module, beside `tool_hints.py`, so a level is changed in one line. Alternative, a decorator argument on each tool: rejected, the levels would be spread over 15 modules and harder to review as a set.

First assignment, by rule, then reviewed by hand with the user:
- `planned`: the 39 "Not available yet" tools;
- `beta`: a tool named in the queue's small-faults list or in `errors-and-limits.md` as having a fault, or known to cover only part of its COM call (`get_material`, `add_mate` without faces);
- `stable`: called by a live test or a demo script a live test runs, or a tool that never calls SolidWorks and is unit-tested (the VBA generators, the API lookups);
- `experimental`: the rest.

First assignment (2026-11-06, 155 tools): 81 stable, 24 beta, 10
experimental, 40 planned. Corrections to the rule, reviewed with the user:
- The rule's text match named three tools only because a fault's wording
  mentions them (`exit_sketch`, `create_cut_extrude`, `create_drawing_view`):
  stable.
- The five `export_*` file tools ignore `format_type` and `options` (a fault
  the rule's text match missed): beta. `export_image` has no such field:
  stable.
- `get_material` and `add_mate` cover only part of their COM call: beta.
- Tools that work on SolidWorks but ignore one optional input (`create_part`,
  `create_assembly`, `create_drawing`, `create_sketch`, `create_extrusion`,
  `create_revolve`, the `export_*` tools, ...): beta, the user's call. Each
  fix moves its tool up.
- `tutorial_simple_hole` always fails at its cut step on SolidWorks:
  planned, the user's call; its description now says "Not available yet".
- `generate_vba_code`, `compare_drawing_versions` and `compare_templates` go
  through the adapter but have no live test: experimental.

### "Stable needs a live test", checked by text

The check looks for the tool's name as a whole word in `tests/live/*.py` and in the `scripts/demo_*.py` files those tests load. Tools of the offline families (`vba_generation`, `type_library`, `docs_discovery`) are exempt. Alternative, recording which tools a live run actually called: rejected, live runs don't happen in CI.

### Level in the payload: one optional `warning` key

Added by the boundary to a successful result of a beta or experimental tool. It's additive, so existing clients and the stable payload shape (`status`, `message`, `execution_time`, data) are unaffected. Errors don't get it: they already carry `hint`.

### Level in the description: added by the registrar

`ToolRegistrar` opens a beta or experimental tool's description with the same
sentence as its `warning` ("Beta: <reason>"), followed by the docstring's text
(FastMCP's `parse_docstring`). Alternative, writing that sentence into ~35
docstrings by hand: rejected during implementation, the reason would live in
two places and go stale when a level changes. A tool's own `warning` (a cut
that removed nothing) and the level's are joined, the tool's first.

### COM snapshot: `docs/assets/progress/com_snapshot.json`

`{sw_version, interfaces: {name: [methods]}}`, written by `src/utils/snapshot_com_api.py` (Windows only, run by hand after a SolidWorks upgrade). Committed so the generator and the check run anywhere. About 150 KB, acceptable.

Core interfaces, fixed in the generator: `ISldWorks`, `IModelDoc2`, `IModelDocExtension`, `IPartDoc`, `IAssemblyDoc`, `IDrawingDoc`, `IFeatureManager`, `ISketchManager`, `ISelectionMgr`, `IComponent2`, `IFeature`, `ISketch`. Coverage of each = its method names called anywhere in the adapters, out of its methods.

### Where the code lives: `solidworks_mcp.progress`

Moved from `src/utils/` during implementation: `src/utils` is outside the
coverage run and has no tests, and the counting and drawing code should be
tested like the rest. The package has `com_coverage.py` (snapshot, scan,
counts), `snapshot.py` (`python -m solidworks_mcp.progress.snapshot`,
Windows), `svg.py` and `generate.py` (`python -m
solidworks_mcp.progress.generate`). `sw_type_info` gains two read-only
accessors, `all_interface_methods()` and `type_library_name()`, for the
snapshot. The scan counts names used as attributes or passed as strings
(`flag_members(obj, "EditDelete")`), across every file under `adapters/`.
The page's tables are a generated `tables.html` included with a snippet (a
`.md` under `docs/` would become a page of its own).

### Generator and check

`src/utils/generate_progress.py` writes `docs/assets/progress/progress.svg` and `progress.json` (per tool: name, family, level, reason, first sentence of its description; per core interface: covered and total). `tests/integration/test_progress_up_to_date.py` builds both in memory and compares them with the committed files; on a mismatch it prints the command to run. Alternative, regenerating in CI and committing: rejected, CI shouldn't push to branches.

### The SVG

Hand-built SVG, no new dependency. A dark rounded panel; each bar a rounded track with a gloss highlight and diagonal stripes (a pattern), a soft outline. Tools bar: green `stable`, amber `beta`, orange `experimental`, the `planned` part left as the empty track. Core COM bar: a red-to-yellow-to-green gradient fill to its percentage. A legend with counts, and the whole-API figure in small print. Inspired by the reference the user shared; drawn from scratch.

### The page: `docs/progress.md`

The SVG, then a table of every tool rendered from `progress.json` at build time (a small MkDocs hook or a generated Markdown include, so it works without JavaScript), then `docs/javascripts/progress.js` adding level and family filter chips and hover details. Colours as in the SVG, with a text label as well as colour on every row.

## Risks / Trade-offs

- [Levels get stale as tools change] → the checks above fail on the cases that can be detected; the queue's small-faults note says a fixed fault moves its tool up a level.
- [The COM figure reads as low] → the core-interface bar is the headline; the whole-API figure is small print with an explanation on the page.
- [Description openings change for ~20 tools] → agents see the change at the next connection; the description check covers it.

## Migration Plan

Additive. Clients ignoring tags and `warning` see no change apart from description openings. Rollback is removing the table and the boundary lines; the generated files can stay.

## Open Questions

- The hand review of the first assignment: the user decides the borderline tools (in tasks 1.2).
