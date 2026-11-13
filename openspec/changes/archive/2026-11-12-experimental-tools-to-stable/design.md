## Context

`support_levels.py` rates ten tools `experimental` ("not yet checked by a
live test on real SolidWorks"). Item 7 (`beta-tool-faults`, archived
2026-11-09) set the pattern this change follows: honour or refuse every
advertised input, prove each tool with a live test in `tests/live/`, then
promote it. That change also showed the live runs find faults the mock
can't: three of its fixes (renaming an open sketch, deleting a used sketch,
the inertia fallback) came from them.

What reading the ten found, tool by tool:

| Tool | Calls SolidWorks | Found by reading |
| --- | --- | --- |
| `pack_and_go_assembly` | yes (comtypes vtable) | `CloseAllDocuments(False)` when `OpenDoc6` fails; deletes all of `target_dir` before copying; input optional, so omitting it gives "not found: ."; preview failure is a silent `null` |
| `get_dimension` | yes | every value is `SystemValue × 1000` labelled mm, so an angle (radians) is wrong; the `GetValue3` fallback is in document units, also × 1000 |
| `generate_vba_code` | no | `parameters` and `code_style` do nothing; Sub name is the description with spaces replaced, so punctuation gives invalid VBA; `MsgBox` blocks SolidWorks when run; its description says `execute_macro` runs only `.swp`, untrue since 2.0.0; an `adapter.generate_vba_code` branch no adapter implements |
| `compare_templates` | no | six comparison switches do nothing; an `adapter.compare_templates` branch no adapter implements |
| `compare_drawing_versions` | no | takes a bare `dict`, not a typed input model |
| `classify_feature_tree` | yes (reads) | a failed `get_model_info` is ignored and an empty model is classified; `hasattr` branches every adapter satisfies |
| `load_part`, `load_assembly` | yes | the reply's `configuration` falls back to an assumed "Default" |
| `get_file_properties`, `list_configurations` | yes (reads) | nothing |

## Goals / Non-Goals

**Goals:**

- Every one of the ten has a live test that proves what its description
  says, and is `stable` when it passes.
- No tool can lose the user's work: Pack and Go never closes documents or
  deletes files it didn't write.
- Every input is honoured or refused (the input contract from item 7).

**Non-Goals:**

- Comparing SolidWorks content (views, dimensions, template settings) in the
  two compare tools. They compare files; a content diff is new work.
- Merging `load_part` / `load_assembly` into `open_model`. That is #174's job
  (item 11); this change only makes them correct.
- The 40 `planned` tools (item 10).

## Decisions

### 1. Pack and Go uses the open document instead of closing everything

When `OpenDoc6` returns no model, the adapter today calls
`CloseAllDocuments(False)` and retries, which throws away unsaved work in
every open document. Instead, the adapter first looks for the assembly
among the open documents (`ISldWorks.GetOpenDocumentByName` with the path)
and packs that. If it is neither openable nor open, the call fails with the
`OpenDoc6` error codes and closes nothing. Alternative considered: close
only the source assembly. Rejected: it still discards unsaved changes, and
the user didn't ask for anything to close.

### 2. Overwrite replaces files, never the folder

The adapter renames `target_dir` aside and deletes it before packing, so
`overwrite: true` on a folder holding anything else deletes it. The rename
and delete go. Pack and Go writes into the existing folder, and
`SavePackAndGo` replaces the files it writes. The tool keeps refusing a
non-empty folder without `overwrite`. Risk (batch 2): `SavePackAndGo` may
refuse to replace a file SolidWorks still holds open from an earlier pack;
the per-file save statuses already in the reply show it, and the live test
packs twice into one folder to find out.

### 2a. Pack and Go copies the dependencies; SolidWorks' Pack and Go is dropped

Live batch 2 on SolidWorks 2026: `IPackAndGo.GetDocumentNames` listed only
the assembly, not its two parts, and `SavePackAndGo` wrote only the
assembly while reporting every file saved; on a second pack it refused the
file already there (`swPackAndGoSaveStatus_FileAlreadyExist`). The project
had already removed `save_assembly`'s native Pack and Go for never working
on 2026 (dead-code item 13); its dependency copy is proven live. So the
adapter asks the open assembly for `GetDependencies2(True, True, False)`
and copies the assembly and each listed file into `target_dir` under its
own name. SolidWorks looks for a referenced file in the assembly's own
folder before the stored path, so the copy opens with its own parts (demo
7 proves it). The copy is of the saved files: an open dependency with
unsaved changes is named in a `warning`. A file-name clash between two
dependencies fails the call, since renaming one would break the reference.
The comtypes vtable bridge, used only by Pack and Go, goes. The dependency
parsing moves to `utils/sw_dependencies.py`, shared with `save_assembly`.
Alternative considered: probe why `GetDocumentNames` misses the parts.
Rejected: the outcome was unknown, and overwrite would still need us to
delete the old copies.

### 3. A dimension's unit comes from its type

The adapter reads `IDimension.GetType()` (`swDimensionParamType_e`, read
from swconst.tlb on 2026: 0 linear, 1 angular, 2 integer, -1 unknown) and
`SystemValue` (metres, radians, or a count). It returns `{value, units}`:
mm (× 1000), deg (radians to degrees), or the count with `units: None`. An
unknown type returns the system value with `units: None` rather than a
guess. The `GetValue3` fallback goes: it returns document units, which the
adapter can't convert without reading the document's unit system, and
`SystemValue` worked on every version measured. `base.py`'s `get_dimension`
return type changes from `float` to a dict; the tool already reads `value`
and `units` from a dict, so its reply shape is unchanged.

### 4. Inputs that do nothing are refused, as in item 7

`compare_templates`' six switches and `generate_vba_code`'s `parameters`
and `code_style` go into `input_compat.REMOVED_INPUTS`, each with a pointer
sentence. The tool boundary refuses them with `invalid_input`. This is
breaking, so it goes in the CHANGELOG under **Changed**.

### 5. The VBA skeleton is checked by running it

`generate_vba_code` never calls SolidWorks, so a unit test can only check
the text. The live test saves the macro as a `.swb` file and runs it with
`execute_macro` (which runs text macros since 2.0.0): the run completing
proves the VBA parses and that nothing blocks. The Sub name keeps letters,
digits and underscores, starts with a letter (prefix `Macro_` otherwise)
and is cut to VBA's 255-character limit. A `Sub main()` calls it: on
SolidWorks 2026 a `.swb` macro runs only through `main` (live batch 3), and
`main` is `execute_macro`'s default. `MsgBox` becomes `Debug.Print`.
The type check compares `swModel.GetType` with `swDocPART` (1),
`swDocASSEMBLY` (2) or `swDocDRAWING` (3) as literal numbers, so the macro
needs no type-library reference.

### 6. The compare tools stay file comparisons, said plainly

They never call SolidWorks, and a content diff is a different tool. Each
gets a typed input model (`compare_drawing_versions` from its bare dict), a
`not_found` for a missing path, and its existing `note` saying only the
files were compared. The live test uses files SolidWorks wrote: its own
templates, and a drawing saved twice. The dead `adapter.compare_templates`
branch is deleted.

### 7. Reads fail instead of guessing

`classify_feature_tree` raises when it has to read the model and
`get_model_info` fails, the same way it already does for `list_features`.
`load_part` and `load_assembly` report the configuration from the adapter,
or `null`, never an assumed "Default". The `hasattr` checks every adapter
satisfies are deleted (coverage is honest, so dead branches go).

### 8. Live batches

One live test file, `tests/live/test_live_sw_experimental_tools.py`, run
one test per process with the user's permission:

1. Reading: `get_file_properties`, `list_configurations` (a second
   configuration added in the test through COM, as item 7's hidden-component
   test did), `get_dimension` (a length and a revolve's angle),
   `classify_feature_tree` (a part and an assembly).
2. Files: `load_part` and `load_assembly` (save, close, reload, wrong type
   refused), `pack_and_go_assembly` (a two-part assembly, an unrelated file
   kept, a second pack into the same folder, a part left dirty stays dirty).
3. Off-line tools on SolidWorks files: `compare_templates` (the installed
   part and assembly templates), `compare_drawing_versions` (a drawing saved
   before and after adding a view), `generate_vba_code` (generated, saved as
   `.swb`, run on a part, then run on a drawing and stopping).

## Risks / Trade-offs

- [**The copy holds the saved files, not unsaved changes.**] Unlike
  Pack and Go in the SolidWorks UI. The reply's `warning` names each open
  dependency with unsaved changes, and the description says to save first.
- [**The copy's references still store the original paths.**] SolidWorks
  finds the same-named file in the assembly's folder first, so it opens
  from the copy (demo 7); a file-name clash fails instead of renaming.
- [**A saved drawing may differ byte-for-byte even when nothing changed**]
  (SolidWorks stamps save times). The compare tools would then call two
  equal drawings different. The live test records whether an unchanged
  re-save is identical; if not, the description says a re-save alone makes
  files differ.
- [**Breaking input removals right after 2.0.0.**] See Open Questions.

## Migration Plan

Removed inputs are listed in the CHANGELOG with what to use instead. No data
migration. Rollback is reverting the PR.

## Open Questions

None. **Version, settled 2026-11-10:** `v2.0.0` is not tagged (the last
release is `v1.5.0`), so this ships in 2.0.0 with item 7, and its breaking
items join the 2.0.0 CHANGELOG section under **Changed**. The maintainer
accepted the three refusals (`compare_templates`' switches,
`generate_vba_code`'s `parameters` and `code_style`, and
`classify_feature_tree` failing on an unreadable model) because none of them
worked before. `v2.0.0` is tagged after this merges.
