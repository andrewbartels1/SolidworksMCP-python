# Work queue

The order the open issues are taken in. Each item becomes an OpenSpec
change under `openspec/changes/` ("spec, then execute"): its plan is
reviewed, then implemented, signed off live where it touches SolidWorks,
and archived after its PR merges. Update this file when an item is done
or the order changes.

Last updated 2026-11-14.

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
| 10 | An honest tool list: remove the 33 planned tools no item will build, deprecate the stable duplicates for one release, settle a verb list. Replaces the old items "the 40 planned tools" and "duplicate tools" | #174 | `honest-tool-list` | Planned 2026-11-12. Items 11-14 depend on it. It probes `manage_design_table` live before removing it (kept for item 13 if design tables work) |
| 11 | Part features the peers lead with: Hole Wizard holes, cosmetic threads, a linear feature pattern, shell, draft, rib, and sketch convert-entities | #105 | `part-feature-depth` | Planned 2026-11-12 |
| 12 | The drawing pack, where no peer goes: section and detail views, the title block and sheet format, drawing dimensions, and one drawing check | #102, #158 | `drawing-pack` | Planned 2026-11-12. Builds the 7 planned drawing tools item 10 leaves |
| 13 | Configurations: create, activate and delete one, and suppress a feature or set a dimension in one configuration only | none | `configuration-tools` | Planned 2026-11-12 |
| 14 | Optional toolsets and a discovery mode, to cut the tool list's size | #176 | `tool-discovery-mode` | Planned 2026-11-12. After item 10, which decides the families |
| 15 | Sheet metal: base flange, edge flange, sketched bend, flat pattern | #57 | not yet written | After item 11 |
| 16 | README: licence-tier tags | #79 (other half) | not yet written | |
| 17 | Remove the stale `validate_coverage.py`; decide whether mypy gates CI | #157 | not yet written | |
| 18 | Skills that improve the agent's results, measured on the U-joint prompt | #207 | not yet written | Tabled 2026-11-09: needs research first (what "better" means, a harness to run and score sessions). See `openspec/research/agent-skill-evaluation.md` |
## Tools that can't run yet (items 10 and 12)

Each one's description says "Not available yet ... planned for a future
release" (the wording is in `docs/agents/tool-description-standard.md`).
Found while rewriting the descriptions (39), plus `tutorial_simple_hole`
(40 in all). Their support level is `planned`. Item 10 removes 33 of them;
item 12 builds the seven drawing tools that are left (`add_dimension`,
`auto_dimension_view`, `create_section_view`, `create_detail_view`,
`update_title_block`, `update_sheet_format`, and `check_drawing_standards`
renamed `check_drawing`).

- **Drawing analysis (7):** `analyze_drawing_comprehensive`,
  `analyze_drawing_dimensions`, `analyze_drawing_annotations`,
  `check_drawing_compliance`, `analyze_drawing_views`,
  `generate_drawing_report`, `validate_drawing_completeness`.
- **Drawing (8):** `add_dimension` and `auto_dimension_view` (#102),
  `create_section_view`, `create_detail_view`, `update_sheet_format`,
  `update_title_block`, `add_annotation`, `check_drawing_standards`.
- **Automation (7):** `automation_start_macro_recording`,
  `automation_stop_macro_recording`, `batch_process_files`,
  `manage_design_table`, `execute_workflow`, `create_template`,
  `optimize_performance`.
- **Macro recording (6):** `start_macro_recording`,
  `stop_macro_recording`, `analyze_macro`, `batch_execute_macros`,
  `optimize_macro`, `create_macro_library`.
- **Templates (5):** `extract_template`, `apply_template`,
  `batch_apply_template`, `save_to_template_library`,
  `list_template_library`.
- **File management (3):** `manage_file_properties`, `convert_file_format`,
  `batch_file_operations`.
- **Export (1):** `batch_export`.
- **Analysis (2):** `analyze_geometry`, `get_material_properties`.
- **Sketching (1):** `tutorial_simple_hole`: its cut step fails on
  SolidWorks (it calls the adapter's `create_cut`, which only the mock has).

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
