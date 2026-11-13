## Why

23 of the 156 tools are rated beta. Each one works but has a known fault: it
ignores an input it advertises, reports a wrong value, or fails on a valid
model. Each fault is written down in the tool's description and in the agent
skill's workaround table, which makes it honest, but an agent still has to read
around it. Some faults give a wrong answer with no warning: the moments of
inertia are off by a factor of a million, and a ring of holes made with
`pattern_circular` is reported as a failure. The maintainer chose
reliability before new features (2026-11-09): fix the beta tools first, then
work up the support levels.

## What Changes

The 23 tools fall into four groups.

**Wrong results (4 tools)**

- `calculate_mass_properties`: moments of inertia are converted from kg·m² to
  kg·mm², so the label is true. Its four unused inputs are removed.
- `pattern_circular` and `mirror_feature`: succeed when the volume changes in
  either direction, so patterning or mirroring a cut works. They still fail
  when the volume doesn't change.
- `delete_feature`: names the dependent features it removed, found by comparing
  the feature tree before and after.

**Inputs that are now honoured (8 tools)**

- `create_extrusion`: `sketch_name` picks the sketch, the same way
  `create_cut_extrude` already does.
- `create_revolve`: `sketch_name` picks the sketch, and `axis_entity`, when it
  names a reference axis, is the axis.
- `create_sketch`: `sketch_name` renames the new sketch. The reply always
  carries the real name.
- `create_part`: `material` is applied.
- `check_interference`: `include_hidden` reaches the adapter.
- `save_as`: refuses to replace an existing file unless `overwrite` is on.
- `execute_macro`: runs `repeat_count` times, pausing `pause_between_runs`
  between runs.
- `get_material`: also returns the density.

**Inputs that are removed (10 tools)**

- `create_extrusion`'s `direction`, which duplicates `end_condition`, and
  `create_revolve`'s `direction`, which duplicates `both_directions`. The
  revolve reply also stops echoing `direction`.
- `create_assembly`'s `components`. Use `insert_component` instead.
- `create_drawing`'s `model_path` and `sheet_format`.
- `create_technical_drawing`'s `template`, `sheet_size`, `title` and
  `output_path`.
- `save_file`'s `force_save`.
- `options` on the five `export_*` tools, and the unused `ExportSTEPInput`,
  `ExportIGESInput` and `ExportSTLInput` classes.
- `add_drawing_view` now refuses an `operation` other than `add`.

**BREAKING:** a call that still sends a removed input gets an `invalid_input`
error that names the tool to use instead. Today the input is silently ignored.

**Wrong guidance (1 tool)**

- `sketch_tutorial_simple_hole` tells the agent to use `create_cut_extrude` for
  the hole, not a negative-depth extrusion.

**For every tool**

- A live SolidWorks test proves the fix.
- The tool moves to `stable` in `support_levels.py`.
- Its row is removed from the skill's known-faults table.
- Its description no longer mentions the fault.
- The progress page is regenerated.

## Capabilities

### New Capabilities

- `tools/input-contract`: a tool either honours each input it advertises or
  refuses it. A removed input is refused with a pointer to the right tool.
- `tools/mass-properties`: the units and values `calculate_mass_properties`
  reports.
- `tools/feature-patterns`: when `pattern_circular` and `mirror_feature`
  succeed, including for cuts.
- `tools/feature-deletion`: what `delete_feature` reports about the dependent
  features it removed.
- `tools/document-creation`: what `create_part`, `create_sketch`,
  `create_assembly` and `create_drawing` apply.
- `tools/file-saving`: `save_as` and `overwrite`.
- `tools/macro-execution`: `execute_macro` repeats.

### Modified Capabilities

- `tools/extrusion`: `sketch_name` picks the sketch, and the same applies to
  `create_revolve`.

`tools/support-levels` is not modified. Its existing rule, that a stable tool
is called by a live test, is what each promotion here has to meet.

## Impact

- **Tools:** `modeling.py`, `sketching.py`, `analysis.py`, `drawing.py`,
  `export.py`, `file_management.py`, `macro_recording.py`,
  `engineering_data.py`, and their input models.
- **Adapters (COM risk):** `adapters/solidworks/features.py` (shared sketch
  resolution for extrude and revolve, the revolve axis, the pattern and mirror
  checks, delete's before/after names), `sketch.py` (renaming the new sketch),
  `documentation.py` (density), and `pywin32_adapter.py` (macro repeats).
  All COM work stays inside `_handle_com_operation` on the connect thread.
  The mock adapter changes to match.
- **Skill:** `skills/solidworks-mcp/references/errors-and-limits.md` loses 11
  rows. `add_mate`'s edge row stays.
- **Docs:** the support levels in `support_levels.py`, the generated progress
  page, and the CHANGELOG.
- **Tests:** unit tests beside each module. A new
  `tests/live/test_live_sw_beta_tools.py` holds one live test per tool,
  run in batches with the user's permission.
- **Issue:** none filed yet. This is item 7 in `openspec/queue.md`.
