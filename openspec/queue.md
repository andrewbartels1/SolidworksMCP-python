# Work queue

The order the open issues are taken in. Each item becomes an OpenSpec
change under `openspec/changes/` ("spec, then execute"): its plan is
reviewed, then implemented, signed off live where it touches SolidWorks,
and archived after its PR merges. Update this file when an item is done
or the order changes.

Last updated 2026-11-04.

| # | Item | Issue | OpenSpec change | State |
| --- | --- | --- | --- | --- |
| 1 | Tool descriptions agents can act on: one description standard, MCP hints and family tags, and a check that keeps them | #82 (docstring half) | `tool-descriptions-for-agents` | Plan approved 2026-11-04; three PRs: (1) standard, check and hints (merged, #202), (2) the eight worst-scoring modules (built, in review), (3) the other six |
| 2 | Guidance through MCP and an installable skill: the server's `instructions`, the skill served as `skill://` resources with FastMCP 3.4.9's `SkillProvider`, and the same skill installable into an agent | #175 | not yet written | Next |
| 3 | `--selftest` command and a compatibility-report issue template | #179 | not yet written | |
| 4 | README: COM API coverage audit and licence-tier tags | #79 | not yet written | |
| 5 | Remove the stale `validate_coverage.py`; decide whether mypy gates CI | #157 | not yet written | |
| 6 | Bracket demo GIF for the README: narrow the issue or close it | #147 | not yet written | |
| 7 | Clear out duplicate and overlapping tools: compare each cluster, keep one, settle a verb list, deprecate old names for one release | #174 | not yet written | Bottom of the queue, by request 2026-11-04 |
| 8 | Optional toolsets or a discovery mode, to cut the tool list's size | #176 | not yet written | After #174, which decides which families are core |
| 9 | Make the "not available yet" tools work, or retire them: each is registered but no adapter implements it, so every call returns `not_supported` (listed below) | not filed yet | not yet written | Added 2026-11-04. After #174, which may retire some of them as duplicates |
| 10 | Small faults found while describing the tools (listed below) | not filed yet | not yet written | Added 2026-11-04 |

## Tools that can't run yet (item 9)

Each one's description says "Not available yet ... planned for a future
release" (the wording is in `docs/agents/tool-description-standard.md`).
Found while rewriting the descriptions; part 3 of item 1 adds any in the
remaining modules.

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

## Small faults (item 10)

- `execute_macro` ignores `repeat_count`: it runs the macro once, but its
  message says "executed N times".
- `create_technical_drawing` ignores `template`, `sheet_size`, `title` and
  `output_path`; it only places three views on the active drawing.
- `add_drawing_view` takes an `operation` (add, update, remove) but only
  ever adds a view; it is the same code as `create_drawing_view`.

## Notes

- Until #174 lands, item 1's descriptions say which of two overlapping
  tools to use ("For ..., use `other_tool`."), so agents can pick
  correctly before any tool is removed.
- Item 1's family tags are what item 8's toolsets filter on.
- Parked: the intermittent SolidWorks error sound during
  `create_cut_extrude` in the chamfer live tests (#199, #201). Revisit if it
  causes failures; run `live_demo.ps1 -Trace` and read the "The hole cut"
  line.
