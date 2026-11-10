## Why

Ten of the 156 tools are rated experimental: they are implemented but have
never been run against real SolidWorks. Item 7 (`beta-tool-faults`, 2.0.0)
showed that a tool which passes in the mock can still be wrong on SolidWorks;
three of its fixes were found only by the live runs. Reading these ten for
this proposal found two faults of that kind before any live run:
`pack_and_go_assembly` can close every open document without saving and
delete the contents of the folder it writes to, and `get_dimension` reports
an angle as a length. Item 8 in `openspec/queue.md` (reliability before new
features, 2026-11-09) is to check each of the ten live and promote it, or
fix it, or record why it stays where it is.

## What Changes

The ten tools fall into four groups.

**Faults found by reading the code (2 tools)**

- `pack_and_go_assembly`: never closes the user's documents. When the
  assembly is already open, Pack and Go uses the open copy instead of
  `CloseAllDocuments(False)`, which discarded unsaved work. With
  `overwrite`, it replaces only the files Pack and Go writes; it no longer
  deletes everything already in `target_dir`. `source_path` and
  `target_dir` become required (the input could be omitted, which turned
  into a "not found: ." error). A preview that can't be written gives a
  `warning` instead of a silent `null`.
- `get_dimension`: an angle dimension is reported in degrees with
  `units: "deg"`, a length in mm, and a count with no unit, from the
  dimension's own type (`IDimension.GetType`). The fallback that multiplied
  a document-unit value by 1000 is removed.

**Inputs that do nothing (2 tools)**

- **BREAKING** `compare_templates`: its six comparison switches
  (`comparison_type`, `comparison_depth`, `include_properties`,
  `include_dimensions`, `include_materials`, `generate_report`) are refused,
  as item 7 did for unused inputs; it compares the files, and says so.
- **BREAKING** `generate_vba_code`: `parameters` and `code_style` are
  refused (neither shapes the code). `target_document` is honoured: the
  macro stops when the active document is another type. The Sub name is
  made a valid VBA name, and the macro reports through `Debug.Print`
  instead of `MsgBox`, which would block SolidWorks when the macro runs.

**Smaller corrections (4 tools)**

- `compare_drawing_versions`: takes a typed input model like every other
  tool, instead of a bare mapping.
- `classify_feature_tree`: fails when the model can't be read, instead of
  classifying an empty model; dead `hasattr` branches go.
- `load_part` and `load_assembly`: report the configuration SolidWorks
  opened, or `null`, instead of assuming "Default"; a missing file is
  `not_found`.

**Checked live and promoted as they are (2 tools)**

- `get_file_properties` and `list_configurations`: no fault found in the
  code; the live test decides.

Each tool gets a live test in `tests/live/test_live_sw_experimental_tools.py`.
A tool that passes moves to `stable` in `support_levels.py`; one that fails
and can't be fixed in this change is recorded with its fault, at `beta`.

## Capabilities

### New Capabilities

- `tools/pack-and-go`: copying an assembly with its parts, without closing
  documents or deleting files that were already there.
- `tools/dimension-reading`: reading one dimension with the unit its type
  gives it.
- `tools/file-comparison`: comparing two drawing or template files on disk,
  and saying it compares the files only.
- `tools/vba-skeleton`: a macro skeleton that is valid VBA and runs without
  blocking SolidWorks.
- `tools/document-inspection`: file properties, configurations, feature-tree
  classification, and opening a part or assembly by type.

### Modified Capabilities

None. The input contract (refusing removed inputs) and the support levels
are reused unchanged.

## Impact

- **Tools:** `file_management.py`, `modeling.py` (`get_dimension`),
  `template_management.py`, `drawing_analysis.py`, `automation.py`, and
  `input_compat.REMOVED_INPUTS`.
- **COM and adapter code:** `adapters/solidworks/io.py` (Pack and Go and
  `get_dimension`), `adapters/base.py` (the `get_dimension` return shape),
  and `mock_adapter.py`. Pack and Go keeps its comtypes vtable path and stays
  on the connect thread; `get_dimension` adds one late-bound call
  (`IDimension.GetType`, flagged as a method).
- **Clients:** two breaking input removals (above). `get_dimension` replies
  gain a real `units`, which is "deg" for an angle.
- **Docs:** each tool's description, the skill's errors-and-limits page if a
  fault is recorded, the CHANGELOG, and the progress page.
- **Issue:** none filed; this is item 8 in `openspec/queue.md`.
