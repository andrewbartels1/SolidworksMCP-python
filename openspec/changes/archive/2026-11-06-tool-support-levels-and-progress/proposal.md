## Why

Nothing in the tool list tells you how far to trust a tool. A tool that has been checked on real SolidWorks and uses every input sits beside one that ignores half its inputs (the queue's small-faults list) or one that can't run at all (the 39 tools in the queue's not-available list). People landing on the repo also can't see how much of SolidWorks the project covers, or that it is two things at once: a Python library for scripting SolidWorks and an MCP server for agents. #79 asked for the coverage audit; the user asked on 2026-11-06 for it as a progress bar at the top of the README, kept up to date as tools are added.

## What Changes

- Every registered tool gets exactly one **support level**, kept in a single table:
  - `stable`: checked by a live test on real SolidWorks, every input used, no known fault;
  - `beta`: works on SolidWorks, but has a known fault or covers only part of its COM call (e.g. `get_material` reads the name and library only);
  - `experimental`: implemented, never checked on real SolidWorks;
  - `planned`: registered but not implemented (today's "Not available yet" tools).
- A tool's level shows in three places: its tags (`level:beta`, next to the family tag), the start of its description (beta and experimental tools say so first), and its results (a beta or experimental tool's success adds a short `warning`).
- A check fails when the table and the code disagree: a tool missing from the table, a `planned` tool whose description doesn't say "Not available yet" (or the reverse), or a `stable` tool with no live test.
- **COM coverage:** a committed snapshot of the SolidWorks type library (interface → method names, made on Windows with a small script) and a scan of the adapter code for the COM methods it calls. Coverage is counted for a fixed list of core interfaces (application, document, part, assembly, drawing, sketch, feature, selection) and for the whole API.
- **The progress bars:** a generator writes one SVG (two glossy, striped, rounded bars on a dark panel: the tools bar split by level colour, the core-COM bar filled red to green, the whole-API figure in small print) and the data behind it. A check fails when the committed SVG or data is out of date, so adding a tool means regenerating them.
- **An interactive page** on the docs site: the same bars, then every tool and every core interface, filterable by level and family, coloured by level, with each tool's description and the COM methods it reaches on hover.
- **README:** the bar at the top, linking to the page, and a short "two tools in one" section: a Python interface for scripting SolidWorks, and an MCP tool server on top of it.

## Capabilities

### New Capabilities
- `tools/support-levels`: one support level per tool, shown in its tags, description and results, and checked against the code.
- `docs/coverage-progress`: the COM snapshot, the coverage count, the generated progress SVG and interactive page, and the staleness check.

### Modified Capabilities
- `tools/tool-descriptions`: a beta or experimental tool's description opens with its level, as a "Not available yet" tool's already does.

## Impact

- New: `src/solidworks_mcp/tools/support_levels.py` (the table), a generator under `src/utils/`, `docs/assets/progress/` (SVG and data), a docs page with a small script, tests beside each module plus a cross-module check in `tests/integration/`.
- Changed: `tool_boundary.py` (adds the level tag and the `warning`), descriptions of the beta and experimental tools, README, mkdocs nav.
- No COM or adapter code changes: the adapter is only read, as text. The type-library snapshot script needs Windows with SolidWorks, but the check and the generator run anywhere from the committed snapshot.
- Addresses #79 (the coverage half; licence-tier tags are left for later). Feeds #174 (cleanup) and the queue's not-available and small-faults lists, which move tools between levels.
