## Context

After 2.0.0 the server has 156 tools: 116 `stable`, 40 `planned`
(`tools/support_levels.py`). Planned tools are registered so their names
are reserved, and every call returns `not_supported`. Issue #174 lists the
overlapping clusters; Glama's review (2.3/5) says an agent can't pick the
intended tool. `ToolRegistrar` (`tools/tool_boundary.py`) already adds a
level tag, a description opening and a success `warning` from the levels
table, so a new level costs one table entry per tool.

Each overlapping cluster, compared in the code:

| Cluster | Finding | Decision |
| --- | --- | --- |
| `open_model`, `load_part`, `load_assembly` | Same adapter call; the two loaders only check the extension | keep `open_model` |
| `save_file`, `save_part`, `save_assembly`, `save_as` | `save_part`/`save_assembly` = `save_file` plus `_prepare_save_target`; `save_as` writes other formats | keep `save_file` (with the checks) and `save_as` |
| `get_mass_properties`, `calculate_mass_properties` | Same adapter call; one takes optional input | keep `get_mass_properties` |
| `get_model_info`, `get_file_properties` | Different fields: tree and rebuild vs size and dates | keep `get_model_info`, add size and dates |
| `create_drawing_view`, `add_drawing_view` | Same code; `add_drawing_view`'s description already says so | keep `create_drawing_view` |
| `create_technical_drawing` | Three views in one call: a different job | keep |
| `sketch_tutorial_simple_hole`, `tutorial_simple_hole` | Fixed examples; the second never worked | remove the planned one, deprecate the other |
| `generate_vba_code` and ten `generate_vba_*` | Offline text generators with different inputs | leave to item 14 (an optional toolset) |
| Seven drawing checks | All planned | remove six; `check_drawing_standards` becomes item 12's `check_drawing` |
| Macro recording (four) | All planned; the type-library index has no recorder start/stop member | remove |
| Templates (five, plus `create_template`) | All planned; `set_custom_property`/`set_material` cover applying settings | remove; keep `compare_templates` |

## Goals / Non-Goals

**Goals:**
- Every registered tool either works or is one of seven named drawing
  tools that item 12 builds.
- One tool per job, with a release in which old names still work.
- A verb list new tools follow.

**Non-Goals:**
- Renaming stable tools that break the verb list (`pattern_circular`,
  `mirror_feature`, `select_face_edges`, ...): renames break clients for no
  gain in function. They are listed as exceptions.
- Merging the VBA generators, or turning families off: item 14.
- Building any planned tool.

## Decisions

### 1. `deprecated` is a support level

`SupportLevel.DEPRECATED`, with `Support(level, reason)` where the reason
is "use `<tool>`" or "no replacement", and a new `since` field holding the
version it was deprecated in. `Support.warning()` returns
"Deprecated: use `<tool>`." for it, so `ToolRegistrar` adds the description
opening and the success `warning` exactly as it does for beta. The level
tag is `level:deprecated`. The progress page counts deprecated tools
separately and leaves them out of the coverage bars.

*Alternative:* a separate aliases table that re-registers the replacement
under the old name. Rejected: inputs differ (`load_part` checks the
extension), so each old tool must keep its own body for one release.

### 2. The removal check uses the package version

The support-level test reads `solidworks_mcp.version.__version__`. When its
major number is above a deprecated tool's `since` major, the test fails.
This forces the removal at 3.0.0 without a calendar.

### 3. Planned tools name their queue item

The planned reason becomes "planned in queue item 12 (the drawing pack)."
for the seven left. The test checks that every planned reason names a
queue item, so a planned tool can't be left without an owner again.

### 4. Removing a tool removes everything that names it

For each removed tool: its function and input model, its `tool_hints.py`
and `support_levels.py` entries, its tests, its catalog row, and any
"use `<tool>`" sentence in another description. A repo-wide grep for each
name, run in the tests (the existing description check already fails on a
backticked name that isn't registered), keeps this honest.

### 5. `save_file` and `get_model_info` gain what their duplicates had

`save_file` calls `_prepare_save_target` when `file_path` is given, with
the extension taken from the active document's type (the adapter's model
info already reports it), and gains `overwrite` (default off). This makes
`save_file` refuse an existing file where it overwrote before; the
CHANGELOG says so. `get_model_info` adds `size_bytes`, `created` and
`modified` with the same `os.stat` code `get_file_properties` uses, moved
into one helper.

### 6. The verb list lives with the description standard

The table goes into `docs/agents/tool-description-standard.md`, with the
exceptions listed under it, and CONTRIBUTING.md links to it. The existing
description-standard test gains a naming check.

### 7. Version 2.1.0

Removing tools that never worked is not a break for a working client, so
the release is 2.1.0. The CHANGELOG lists the removed names under
"Removed" and the deprecated ones under "Deprecated".

### 8. `manage_design_table` is checked before it goes (removed)

It is in the removal list because a design table needs Excel on the
machine, and item 13's configuration tools give agents the same variants
without it. That reason is not yet proven on the user's SolidWorks, so a
live probe (task 2.0) inserts a design table on a scratch part and reads it
back. If it works, the tool stays `planned` for item 13 and the planned
count is eight; if not, it is removed and the finding is recorded here.

**Finding (live, 2026-11-14, SolidWorks 2026, Excel installed):** a
two-row spreadsheet (`Default` 20 mm, `Tall` 30 mm on `D1@Boss-Extrude1`)
was written by Excel and inserted with `IModelDoc2.InsertFamilyTableOpen`.
`GetDesignTable` then returns a table, but `IDesignTable.Attach` returns
false, `GetTotalRowCount` and `GetTotalColumnCount` return -2, every cell
reads empty, and no `Tall` configuration is made. The insert call itself
raised in late binding. Design tables don't work through COM here, so the
tool is removed with the rest (33 in all) and the planned count is seven.
Item 13's configuration tools give agents variants without Excel.

### 9. Items 11 to 14 depend on this change

`part-feature-depth`, `drawing-pack`, `configuration-tools` and
`tool-discovery-mode` use the verb list, the `deprecated` level, the
planned-reason rule and the final family list from this change. None of
them starts until this change is merged.

## Risks / Trade-offs

- [A client scripted a planned tool's name] → it only ever got
  `not_supported`; the CHANGELOG lists every removed name.
- [`save_file` now refuses an existing file without `overwrite`] → this is
  what `save_as` and `save_part` already do; the error names `overwrite`.
- [Deprecation warnings add noise to replies] → one sentence, and only on
  the eight old names.
- [Removing a family empties a module] → `drawing_analysis.py` keeps
  `compare_drawing_versions`; `template_management.py` keeps
  `compare_templates`; `macro_recording.py` keeps `execute_macro`. No module
  is emptied.
