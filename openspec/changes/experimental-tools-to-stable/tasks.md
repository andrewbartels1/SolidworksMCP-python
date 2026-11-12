## 1. Shared pieces

- [x] 1.1 `input_compat.REMOVED_INPUTS`: `TemplateComparisonInput` (six switches) and `GenerateVBAInput` (`parameters`, `code_style`), each with a pointer sentence; tests that each is refused and that `operation_type` (an alias that is used) is still accepted
- [x] 1.2 `tests/live/test_live_sw_experimental_tools.py`: the tool registry helper and the scratch fixture, reused from `test_live_sw_beta_tools.py` where they fit

## 2. Reading (live batch 1)

- [x] 2.1 `get_dimension`: adapter returns `{value, units}` from `IDimension.GetType` (mm, deg, or `None` for a count or unknown type); remove the `GetValue3` fallback; `base.py` and the mock match; tests for a length, an angle, a count, an unknown type and an unreadable value
- [x] 2.2 `classify_feature_tree`: raise when `get_model_info` fails and the model must be read; delete the `hasattr` branches; tests
- [x] 2.3 `get_file_properties` and `list_configurations`: no code change expected; tests stay as they are
- [x] 2.4 Live batch 1: file properties (saved, then edited), two configurations, a length and a 270° revolve angle, a part and an assembly classified; run with the user's permission

## 3. Files (live batch 2)

- [x] 3.1 `load_part` and `load_assembly`: report the adapter's configuration or `null`; a missing file is `not_found`; tests
- [x] 3.2 `pack_and_go_assembly` adapter: use the open document when `OpenDoc6` returns none, never `CloseAllDocuments`; no rename-and-delete of `target_dir`; tests with a stubbed comtypes path
- [x] 3.3 `pack_and_go_assembly` tool: `PackAndGoInput` required; missing source `not_found`; a failed preview gives a `warning`; description says the copy holds what is open, saved or not; tests
- [x] 3.5 `pack_and_go_assembly` copies the saved files `GetDependencies2` lists (design 2a): shared parsing in `utils/sw_dependencies.py`, a `warning` for unsaved changes, a name clash or missing file fails; the comtypes bridge goes; tests
- [x] 3.4 Live batch 2: save, close and reload a part and an assembly, wrong types refused; pack a two-part assembly into a folder holding `notes.txt` (kept), pack again into the same folder, and pack while a part is dirty (still dirty after)

## 4. Off-line tools on SolidWorks files (live batch 3)

- [x] 4.1 `compare_templates`: delete the `adapter.compare_templates` branch; missing path `not_found`; description; tests
- [x] 4.2 `compare_drawing_versions`: a typed input model with both paths required; missing path `not_found`; tests
- [x] 4.3 `generate_vba_code`: valid Sub name, `Debug.Print` for `MsgBox`, the `target_document` type check, delete the adapter branch, fix the `.swp`-only sentence; tests for the name rules and each document type
- [x] 4.4 Live batch 3: the installed part template against itself and against the assembly template; a drawing saved before and after adding a view, and an unchanged re-save (record whether it is byte-identical); a generated macro run on a part, then on a drawing

## 5. Promote and document

- [x] 5.1 `support_levels.py`: each tool whose batch passed moves to `stable`; any that can't be fixed here goes to `beta` with its fault as the reason; `python -m solidworks_mcp.progress.generate`
- [x] 5.2 Each tool's description matches what it now does; the skill's `errors-and-limits.md` gains a row for any fault recorded
- [x] 5.3 CHANGELOG: **Fixed** (Pack and Go, angles), **Changed** (the removed inputs; `get_dimension` units)
- [x] 5.4 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`
- [ ] 5.5 Live-demo sign-off with the user before the PR; settle the version question in design.md

## Notes from the implementation

- `open_model` (stable) and `list_configurations` had the same fault as the
  load tools: they called `IConfiguration.GetName()`, which doesn't exist
  (the type library has only the `Name` property), so on SolidWorks the
  call always failed and the reply fell back to "Default". Both now read
  `Name`. `open_model` also checks the file exists before `OpenDoc6`, so a
  missing file is `not_found` for all three open tools.
- `OpenDoc6`'s error 65536 is `swFileWithSameTitleAlreadyOpen`: another
  document with the same file name is open. Pack and Go now says so and
  closes nothing, where it used to close every document.
- `pack_and_go_assembly`'s `export_preview` defaulted to on, though its
  description said off; it is now off.
- `classify_feature_tree` keeps `require_capability` for an adapter without
  `get_model_info` or `list_features` (the house pattern), replacing the
  `hasattr` branches.
- `generate_vba_code`'s macro is late-bound (`As Object`), so it runs as a
  `.swb` text macro without a type-library reference; its reply gains
  `sub_name`, the Sub that `Sub main()` calls.
- Live batch 1: `classify_feature_tree` called a plain extruded part an
  assembly. Its assembly check matched "mate" anywhere in a feature name,
  and every real part's tree has "Material <not specified>". The mock's
  parts have no Material entry, so no unit test saw it. Now a known
  document type (part, assembly, drawing) decides, feature names only
  count when the type is unknown, and the mate check skips "material".
- The rerun then called the same part sheet metal: every real tree has
  folders ("HistoryFolder", "SensorFolder", ...), and the sheet-metal word
  "fold" is inside "folder". The classifier now skips rows whose type ends
  in "Folder", and the live test expects `extrude`.
- Live batch 2: `close_model` (stable) only closed the document the
  adapter tracked, and forgot it after closing. SolidWorks makes another
  open document active, so a second close in a row failed with "No active
  model to close". It now reads `ActiveDoc` first, as `list_features` does.
- Live batch 3: a drawing saved again with no change is not byte-identical
  to the earlier save (SolidWorks 2026). `compare_drawing_versions` now says
  that identical files mean nothing changed, but different files may not.
- Live batch 3: the generated macro failed on SolidWorks: `RunMacro2`
  returned false with error 0 (no reason), on the part and the drawing. A
  `.swb` macro ran in the beta batch, so `test_which_macro_text_runs_from_a_swb`
  runs one-change variants of it to find the construct the `.swb` runner
  rejects. Until that passes, `generate_vba_code` stays experimental; the
  other nine tools are stable (5.1), and the skill's limits page has rows
  for Pack and Go's saved files and drawing re-saves (5.2).
- The diagnostic answered it: every construct ran, but a `.swb` runs only
  through a Sub named `main` (a lone `Sub Add_3_holes` failed; the generated
  macro ran once its Sub was renamed `main`). The macro now opens with
  `Sub main()` calling the named Sub, so `execute_macro` runs it with no
  `proc_name`.
- Demo 10 rerun passed: the macro ran on the part and on the drawing,
  which it left unchanged. `generate_vba_code` is stable.
