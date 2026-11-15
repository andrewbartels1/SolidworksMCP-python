## Why

The server registers 156 tools, but 40 of them are `planned`: every call
returns `not_supported`. A client still pays for their schemas on every
turn, and an agent can pick one and fail. Among the 116 that work, several
do the same job under different names (`load_part` and `open_model`,
`get_mass_properties` and `calculate_mass_properties`), so an agent can't
reliably pick the intended one. Glama's tool-quality review scored the
server 2.3/5 for exactly this (issue #174). The fix is a list where every
tool works, does one job, and is named by one verb list.

## What Changes

- **33 planned tools are removed.** Each either duplicates a working tool,
  is a loop an agent can run itself, or has no SolidWorks API behind it:
  - analysis: `analyze_geometry`, `get_material_properties`;
  - automation: `automation_start_macro_recording`,
    `automation_stop_macro_recording`, `batch_process_files`,
    `create_template`, `execute_workflow`, `manage_design_table`,
    `optimize_performance`;
  - drawing: `add_annotation`;
  - drawing analysis: `analyze_drawing_annotations`,
    `analyze_drawing_comprehensive`, `analyze_drawing_dimensions`,
    `analyze_drawing_views`, `check_drawing_compliance`,
    `generate_drawing_report`, `validate_drawing_completeness`;
  - export: `batch_export`;
  - file management: `batch_file_operations`, `convert_file_format`,
    `manage_file_properties`;
  - macros: `analyze_macro`, `batch_execute_macros`,
    `create_macro_library`, `optimize_macro`, `start_macro_recording`,
    `stop_macro_recording`;
  - sketching: `tutorial_simple_hole`;
  - templates: `apply_template`, `batch_apply_template`,
    `extract_template`, `list_template_library`,
    `save_to_template_library`.
- **The seven planned drawing tools stay planned** for the drawing pack
  (queue item 12): `add_dimension`, `auto_dimension_view`,
  `create_section_view`, `create_detail_view`, `update_title_block`,
  `update_sheet_format`, `check_drawing_standards`. Their reason names that
  item.
- **A new support level, `deprecated`**, for a working tool replaced by
  another. It keeps working for one minor release. Its description opens
  "Deprecated: use `<tool>`.", and a successful result carries the same
  sentence as `warning`. It is removed in 3.0.0.
- **Eight stable tools are deprecated**, after their replacement gains what
  they did:
  - `load_part`, `load_assembly` → `open_model`;
  - `save_part`, `save_assembly` → `save_file`, which gains the new-path
    checks (folder exists, extension matches the document, no overwrite
    unless asked). `save_assembly`'s `include_references` copy is
    `pack_and_go_assembly`'s job;
  - `calculate_mass_properties` → `get_mass_properties`;
  - `get_file_properties` → `get_model_info`, which gains the file's size
    and dates;
  - `add_drawing_view` → `create_drawing_view`;
  - `sketch_tutorial_simple_hole` → none; it is a fixed example, and its
    description already points to the real tools.
- **One verb list**, in CONTRIBUTING.md and the description standard, that
  new tools follow. Stable tools that break it are listed as exceptions,
  not renamed.
- **BREAKING (for clients that call them):** the 33 removed tool names
  disappear. They never did anything but return `not_supported`, so this
  ships in 2.1.0. The eight deprecated names keep working until 3.0.0.

## Capabilities

### New Capabilities

- `tools/tool-deprecation`: a deprecated tool keeps working, names its
  replacement in its description and its results, and is removed at the
  next major release.
- `tools/tool-naming`: one verb per meaning, checked for new tools.

### Modified Capabilities

- `tools/support-levels`: a fifth level, `deprecated`; the levels check
  allows only the seven drawing tools to be `planned`, each naming the
  queue item that builds it.
- `tools/file-saving`: `save_file` checks a new path the way `save_part`
  did.
- `tools/document-inspection`: `get_model_info` reports the file's size and
  dates.

## Impact

- **No COM or adapter code changes.** Removed tools have no adapter
  method; deprecated tools already call the adapter method their
  replacement calls. `get_model_info`'s size and dates come from the file
  on disk (`os.stat`), as `get_file_properties` reads them today.
- **Tools:** `analysis.py`, `automation.py`, `drawing.py`,
  `drawing_analysis.py`, `export.py`, `file_management.py`,
  `macro_recording.py`, `sketching.py`, `template_management.py` lose the
  removed tools and their input models. `support_levels.py`,
  `tool_hints.py` and `tool_boundary.py` gain `deprecated`.
- **Docs:** the tool catalog pages, the README's counts and progress bars
  (regenerated), the agent skill's tool list, CHANGELOG, CONTRIBUTING.md.
- **Tests:** each removed tool's tests go; the support-level and description
  checks gain the new rules. No live run is needed for removals; the two
  replacements that gain behaviour (`save_file`, `get_model_info`) get a
  live check in one bundle.
- Issue #174 closes with this change. The VBA generators are left to
  item 14's optional toolsets, not merged here.
