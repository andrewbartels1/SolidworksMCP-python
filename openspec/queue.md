# Work queue

The order the open issues are taken in. Each item becomes an OpenSpec
change under `openspec/changes/` ("spec, then execute"): its plan is
reviewed, then implemented, signed off live where it touches SolidWorks,
and archived after its PR merges. Update this file when an item is done
or the order changes.

Last updated 2026-11-16.

| # | Item | Issue | OpenSpec change | State |
| --- | --- | --- | --- | --- |
| 0 | Hotfix: the monitor-stand GIF looked empty in the README and Demos grids (its first 8 frames were SolidWorks' blank start screen, and GitHub shows only the first frame to readers with reduced motion) | none | none (asset fix) | Fixed 2026-11-06 on `fix/monitor-stand-gif-poster`: the GIF opens on the finished stand for 2 s, then plays the build. Done (#215) |
| 1 | Tool descriptions agents can act on: one description standard, MCP hints and family tags, and a check that keeps them | #82 (docstring half) | `tool-descriptions-for-agents` (archived) | Done 2026-11-05 (#202, #203, #204). Left: after the next release, ask Glama for a rescan and record the score in the internal assessment |
| 2 | Guidance through MCP and an installable skill: the server's `instructions`, the skill served as `skill://` resources with FastMCP 3.4.9's `SkillProvider`, and the same skill installable into an agent | #175 | `agent-skill-and-instructions` (archived) | Done 2026-11-06 (#205, #211; #147 closed as superseded) |
| 3 | The circuit breaker locks a tool out after a success and never reopens; a reset tool | #208 | `circuit-breaker-recovery` (archived) | Done 2026-11-06 (#213) |
| 4 | Support levels for every tool, and COM coverage progress bars at the top of the README with an interactive docs page | #79 (coverage half) | `tool-support-levels-and-progress` (archived) | Done 2026-11-06 (#214). #79's licence-tier half is item 13 |
| 5 | Tool gaps found building the U-joint: face mates, fixed parts and flexible sub-assemblies, angled planes, angled chamfers, `both_directions`, a stale interference result, thin extrudes | #209 | `ujoint-tool-gaps` (archived) | Done 2026-11-07 (#216), signed off live |
| 6 | `--selftest` command and a compatibility-report issue template | #179 | `selftest-and-compatibility-report` (archived) | Done 2026-11-09 (#217), signed off live |
| 7 | Beta tools to stable: fix each beta tool's known fault (the small faults listed below), prove it live, and move it up a level | not filed yet | `beta-tool-faults` (archived) | Done 2026-11-09 (#219, 2.0.0): 23 tools promoted, signed off live |
| 8 | Experimental tools to stable: a live test for each of the 10, then promote it or record its fault | not filed yet | `experimental-tools-to-stable` (archived) | Done 2026-11-12 (2.0.0, tagged `v2.0.0`): all 10 promoted, signed off live. Pack and Go now copies the files `GetDependencies2` lists (SolidWorks 2026's own Pack and Go copied only the assembly); `comtypes` dropped |
| 9 | Monitor stand demo follow-ups: feature order, `verify_model`'s planes, dimension listing, STL export, `create_sketch` on a face, the demo's camera | #206 | `monitor-stand-follow-ups` (archived) | Done 2026-11-14: all five live tests pass, GIF re-recorded; PR open |
| 10 | An honest tool list: remove the 33 planned tools no item will build (the design table among them, after its live check), deprecate the stable duplicates for one release, settle a verb list. Replaces the old items "the 40 planned tools" and "duplicate tools" | #174 | `honest-tool-list` (archived) | Done 2026-11-14 (#229): 33 removed (the design table after its live check failed), 8 deprecated until 3.0.0, the verb list. Items 11-14 can start |
| 19 | Our own `llms.txt`, and every link checked. A script builds `llms.txt` from the mkdocs nav: each entry's title and summary are copied word for word from the page they link to, and nothing is written by hand. A check follows EVERY link in `llms.txt`, the README and the docs (internal pages, anchors and external URLs), and fails on a dead link, a redirect off this repo, or an `llms.txt` line that doesn't match its page. Security review of the result: only this repo's own pages, no third-party links, no hidden text or instructions. PR #225's file is not used as a starting point; the user is closing that PR | #225 (closed, not merged) | `own-llms-txt` | Done 2026-11-16 (#232) |
| 11 | Part features the peers lead with: Hole Wizard holes, cosmetic threads, a linear feature pattern, shell, draft, rib, and sketch convert-entities | #105 | `part-feature-depth` (archived) | Done 2026-11-16: 7 tools, all stable after the live bundle passed; `create_hole` takes `positions`; the holes demo is in the docs. PR with item 13's first part |
| 22 | The Hole Wizard library: a read-only `list_hole_sizes` tool (standards, hole types, sizes and dimensions, read from the installed Toolbox library), and `create_hole` refusing sizes that don't exist, with `M6` on a simple hole meaning a screw clearance hole. Adding sizes or standards from a config file is a later change | none | `hole-wizard-library` (archived) | Done 2026-11-16: `list_hole_sizes` and the size check, checked live. Adding sizes from a config is a later change |
| 12 | The drawing pack, where no peer goes: section and detail views, the title block and sheet format, drawing dimensions, and one drawing check | #102, #158 | `drawing-pack` (archived) | Done 2026-11-16 (#235): the 7 tools stable after the live demo (a section through the hole, a 3:1 detail of the bore, revision B on A2, the 60 mm and Ø6 dimensions, auto-dimension, the check). The BOM on the A3 format (#158) is still open |
| 13 | Configurations: create, activate and delete one, and suppress a feature or set a dimension in one configuration only | none | `configuration-tools` (archived) | Done 2026-11-16: create, activate, delete (#233); changes in chosen configurations, all checked live |
| 20 | Elastic material properties: `get_material` (or a sibling) also reads the assigned material's elastic modulus, Poisson's ratio, yield and tensile strength, with units, so an agent can size a part without leaving the server. Found by item 10's ledger: `get_material_properties` was removed and only name and density are read today | none | `material-elastic-properties` (archived) | Done 2026-11-16: `get_material` returns the modulus, strengths and thermal properties in SI units from the material's library entry, and reads any library material by name; checked live |
| 21 | Save the active document as a template (.prtdot, .asmdot, .drwdot), so a part set up once (units, material, properties) can start the next one through `create_part`'s `template`. Found by item 10's ledger: `create_template` and `save_to_template_library` were removed and nothing saves a template today | none | `save-as-template` (archived) | Done 2026-11-16: `save_as_template`, checked live. SolidWorks has the template open in place of the document afterwards (the copy option doesn't change it); the reply says so |
| 14 | Optional toolsets and a discovery mode, to cut the tool list's size | #176 | `tool-discovery-mode` (archived) | Done 2026-11-16: `SOLIDWORKS_MCP_TOOLSETS` and `SOLIDWORKS_MCP_TOOL_MODE=search` (4 tools, about 900 tokens a turn instead of about 55,000), checked live; the size table is in the installation guide |
| 15 | Sheet metal: base flange, edge flange, sketched bend, flat pattern | #57 | `sheet-metal` (archived) | Done 2026-11-16: `create_base_flange`, `add_edge_flange`, `create_sketched_bend`, `set_flat_pattern`, checked live (the blank 78.7124 mm against 78.712 by hand). A sketched bend's fixed side can't be chosen through the API (#239) |
| 16 | README: licence-tier tags | #79 (other half) | `tool-requirements` (archived) | Done 2026-11-16: no tool needs more than the licence that runs SolidWorks, so each tool is tagged with what it needs instead: `needs:nothing` (14), `needs:installed` (6) or `needs:running` |
| 17 | Remove the stale `validate_coverage.py`; decide whether mypy gates CI | #157 | not yet written | |
| 18 | Skills that improve the agent's results, measured on the U-joint prompt | #207 | not yet written | Tabled 2026-11-09: needs research first (what "better" means, a harness to run and score sessions). See `openspec/research/agent-skill-evaluation.md` |
## Removed tools (item 10, release 2.1.0)

33 tools were registered but never implemented: every call returned
`not_supported`. Item 10 removed them (#174). Each row says why, and whether
the job is done elsewhere or is a real gap that should come back as a queue
item. Re-adding a name needs a working implementation and a live test, not a
placeholder.

Why, in short:

- **duplicate**: another working tool already does it;
- **loop**: the agent runs it by calling a working tool once per file;
- **no API**: SolidWorks' type library has no member for it, or the job
  isn't defined well enough to build;
- **replaced**: a queue item builds a better-defined tool for it.

| Tool | Why | Done today by, or comes back as |
| --- | --- | --- |
| `analyze_geometry` | no API (curvature, draft and thickness in one call) | `measure_entities`, `verify_model`; a draft check could come with item 11's `add_draft` |
| `get_material_properties` | duplicate, in part | `get_material` (name, database, density). **Gap:** elastic properties; queue item 20 |
| `automation_start_macro_recording` | no API (no recorder start member) | SolidWorks' own Tools > Macro > Record; `generate_vba_code` |
| `automation_stop_macro_recording` | no API | as above |
| `start_macro_recording` | no API | as above |
| `stop_macro_recording` | no API | as above |
| `batch_process_files` | loop | `open_model`, then the operation, per file |
| `batch_export` | loop | `export_*` per file |
| `batch_file_operations` | loop | `open_model`, `save_as` per file |
| `batch_execute_macros` | loop | `execute_macro` per macro |
| `batch_apply_template` | loop | per file (see templates) |
| `execute_workflow` | loop | the agent's own sequence of calls |
| `manage_design_table` | no API that works here: checked live 2026-11-14 on SolidWorks 2026, `InsertFamilyTableOpen` adds the table but SolidWorks can't open it in Excel (`Attach` false, counts -2) and makes no configurations | configurations, queue item 13 |
| `optimize_performance` | no API (not defined) | none needed |
| `create_template` | no API, as specified | `create_part` / `create_assembly` take `template`. **Gap:** saving a document as a template; queue item 21 |
| `extract_template` | no API, as specified | as above |
| `apply_template` | duplicate | `set_custom_property`, `set_material`, `set_units` |
| `list_template_library` | no API (a folder listing, not SolidWorks) | none needed |
| `save_to_template_library` | no API | as `create_template` |
| `add_annotation` | duplicate | `add_note`, `add_gtol`, `add_datum_tag` |
| `analyze_drawing_annotations` | replaced | item 12's `check_drawing` |
| `analyze_drawing_comprehensive` | replaced | item 12's `check_drawing` |
| `analyze_drawing_dimensions` | replaced | item 12's `check_drawing` |
| `analyze_drawing_views` | replaced | `list_drawing_views`; item 12's `check_drawing` |
| `check_drawing_compliance` | replaced | item 12's `check_drawing` |
| `generate_drawing_report` | replaced | item 12's `check_drawing` |
| `validate_drawing_completeness` | replaced | item 12's `check_drawing` |
| `convert_file_format` | duplicate | `save_as`, `export_*` |
| `manage_file_properties` | duplicate | `get_custom_properties`, `set_custom_property` |
| `analyze_macro` | no API (VBA text review, not SolidWorks) | none needed |
| `optimize_macro` | no API (as above) | none needed |
| `create_macro_library` | no API (a folder of files) | none needed |
| `tutorial_simple_hole` | never worked | the sketching and feature tools; item 11's `create_hole` (Hole Wizard) |

The two gaps marked above are queued: elastic material properties as item
20, saving a template as item 21.

Still planned (7): the drawing tools item 12 builds (`add_dimension`,
`auto_dimension_view`, `create_section_view`, `create_detail_view`,
`update_title_block`, `update_sheet_format`, `check_drawing_standards`
renamed `check_drawing`).

Deprecated (8, removed in 3.0.0): `load_part`, `load_assembly` (use
`open_model`); `save_part`, `save_assembly` (use `save_file`);
`calculate_mass_properties` (use `get_mass_properties`);
`get_file_properties` (use `get_model_info`); `add_drawing_view` (use
`create_drawing_view`); `sketch_tutorial_simple_hole` (no replacement).

How the list is kept honest: the support-level table
(`tools/support_levels.py`) gives every tool one level, and its checks fail
when a planned tool names no queue item, a deprecated tool outlives its
major version, or a stable tool has no live test. The counts are on the
[progress page](../docs/progress.md), regenerated from the code.

## Small faults (item 7)

When one is fixed, remove it from the agent skill's
`src/solidworks_mcp/skills/solidworks-mcp/references/errors-and-limits.md`
in the same change, and move its tool up a level in
`src/solidworks_mcp/tools/support_levels.py` (beta tools list the fault as
their reason), then run `python -m solidworks_mcp.progress.generate`.

- `create_drawing_view` and `add_drawing_view` place a view wherever
  `position` says, even off the sheet, and report success (seen in the beta
  live tests, 2026-11-09). They could read the sheet size (`_sheet_bounds`
  in `adapters/solidworks/documentation.py`) and refuse or warn.

## Notes

- Items 11 and 12 come from the internal assessment: match the closest
  peer on part depth, and lead on drawings, which it leaves out.
- Until #174 lands, item 1's descriptions say which of two overlapping
  tools to use ("For ..., use `other_tool`."), so agents can pick
  correctly before any tool is removed.
- Item 1's family tags are what item 14's toolsets filter on.
- Parked: the intermittent SolidWorks error sound during
  `create_cut_extrude` in the chamfer live tests (#199, #201). Revisit if it
  causes failures; run `live_demo.ps1 -Trace` and read the "The hole cut"
  line.
