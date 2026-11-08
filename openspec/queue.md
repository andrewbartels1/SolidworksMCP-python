# Work queue

The order the open issues are taken in. Each item becomes an OpenSpec
change under `openspec/changes/` ("spec, then execute"): its plan is
reviewed, then implemented, signed off live where it touches SolidWorks,
and archived after its PR merges. Update this file when an item is done
or the order changes.

Last updated 2026-11-06.

| # | Item | Issue | OpenSpec change | State |
| --- | --- | --- | --- | --- |
| 0 | Hotfix: the monitor-stand GIF looked empty in the README and Demos grids (its first 8 frames were SolidWorks' blank start screen, and GitHub shows only the first frame to readers with reduced motion) | none | none (asset fix) | Fixed 2026-11-06 on `fix/monitor-stand-gif-poster`: the GIF opens on the finished stand for 2 s, then plays the build. Awaiting push approval |
| 1 | Tool descriptions agents can act on: one description standard, MCP hints and family tags, and a check that keeps them | #82 (docstring half) | `tool-descriptions-for-agents` (archived) | Done 2026-11-05 (#202, #203, #204). Left: after the next release, ask Glama for a rescan and record the score in the internal assessment |
| 2 | Guidance through MCP and an installable skill: the server's `instructions`, the skill served as `skill://` resources with FastMCP 3.4.9's `SkillProvider`, and the same skill installable into an agent | #175 | `agent-skill-and-instructions` (archived) | Done 2026-11-06 (#205, #211; #147 closed as superseded) |
| 3 | The circuit breaker locks a tool out after a success and never reopens; a reset tool | #208 | `circuit-breaker-recovery` (archived) | Done 2026-11-06 (#213) |
| 4 | Support levels for every tool, and COM coverage progress bars at the top of the README with an interactive docs page | #79 (coverage half) | `tool-support-levels-and-progress` (archived) | Done 2026-11-06 (#214). #79's licence-tier half is item 8 |
| 5 | Tool gaps found building the U-joint: face mates, fixed parts and flexible sub-assemblies, angled planes, angled chamfers, `both_directions`, a stale interference result, thin extrudes | #209 | `ujoint-tool-gaps` | Implemented 2026-11-06 on `feat/ujoint-tool-gaps`; live-checked; awaiting push approval |
| 6 | `--selftest` command and a compatibility-report issue template | #179 | not yet written | |
| 7 | Skills that improve the agent's results, measured on the U-joint prompt (Opus 5.5 at medium effort: the first skill changed how the agent worked, not what it built) | #207 | not yet written | |
| 8 | README: licence-tier tags | #79 (other half) | not yet written | |
| 9 | Remove the stale `validate_coverage.py`; decide whether mypy gates CI | #157 | not yet written | |
| 10 | Monitor stand demo follow-ups | #206 | not yet written | |
| 11 | Clear out duplicate and overlapping tools: compare each cluster, keep one, settle a verb list, deprecate old names for one release | #174 | not yet written | Bottom of the queue, by request 2026-11-04 |
| 12 | Optional toolsets or a discovery mode, to cut the tool list's size | #176 | not yet written | After #174, which decides which families are core |
| 13 | Make the "not available yet" tools work, or retire them: each is registered but no adapter implements it, so every call returns `not_supported` (listed below) | not filed yet | not yet written | After #174, which may retire some of them as duplicates |
| 14 | Small faults found while describing the tools (listed below) | not filed yet | not yet written | Fixing one moves its tool up a support level (item 4) |

## Tools that can't run yet (item 13)

Each one's description says "Not available yet ... planned for a future
release" (the wording is in `docs/agents/tool-description-standard.md`).
Found while rewriting the descriptions (39), plus `tutorial_simple_hole`
(40 in all). Their support level is `planned`.

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

## Small faults (item 14)

When one is fixed, remove it from the agent skill's
`src/solidworks_mcp/skills/solidworks-mcp/references/errors-and-limits.md`
in the same change, and move its tool up a level in
`src/solidworks_mcp/tools/support_levels.py` (beta tools list the fault as
their reason), then run `python -m solidworks_mcp.progress.generate`.

- `execute_macro` ignores `repeat_count`: it runs the macro once, but its
  message says "executed N times".
- `create_technical_drawing` ignores `template`, `sheet_size`, `title` and
  `output_path`; it only places three views on the active drawing.
- `add_drawing_view` takes an `operation` (add, update, remove) but only
  ever adds a view; it is the same code as `create_drawing_view`.
- `create_extrusion` ignores `sketch_name` and `direction`, and
  `create_revolve` ignores `sketch_name` and `axis_entity`: both use the
  sketch `exit_sketch` closed (the revolve its centreline). `create_cut_extrude`
  does honour `sketch_name`.
- `create_part` ignores `material`, `create_assembly` ignores `components`,
  `create_drawing` ignores `model_path` and `sheet_format`, and
  `create_sketch` echoes `sketch_name` back as the sketch's name without
  applying it, so the reply can name a sketch that doesn't exist.
- `pattern_circular` and `mirror_feature` fail unless the volume grows, so
  patterning or mirroring a cut (a ring of holes) is reported as an error.
- `calculate_mass_properties` labels the moments of inertia kg·mm², but they
  are SolidWorks' kg·m² (a factor of a million); its input fields are unused.
- `delete_feature` reads `removed_features`, but the real adapter returns
  `features_removed` (a count), so on SolidWorks its message never mentions
  the dependent features that went too.
- `sketch_tutorial_simple_hole` suggests a negative-depth extrusion for the
  hole instead of `create_cut_extrude`.
- `save_as` ignores `overwrite` (an existing file is replaced) and
  `save_file` ignores `force_save`; the `export_*` file tools ignore
  `options` (`format_type` is optional since #209: the extension decides);
  `ExportSTEPInput`, `ExportIGESInput` and `ExportSTLInput` are unused.
- `check_interference` passes `include_hidden` where the adapter reads
  `ignore_hidden`, so it has no effect.

## Notes

- Until #174 lands, item 1's descriptions say which of two overlapping
  tools to use ("For ..., use `other_tool`."), so agents can pick
  correctly before any tool is removed.
- Item 1's family tags are what item 12's toolsets filter on.
- Parked: the intermittent SolidWorks error sound during
  `create_cut_extrude` in the chamfer live tests (#199, #201). Revisit if it
  causes failures; run `live_demo.ps1 -Trace` and read the "The hole cut"
  line.
