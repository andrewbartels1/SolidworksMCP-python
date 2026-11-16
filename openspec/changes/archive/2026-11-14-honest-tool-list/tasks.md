## 1. The deprecated level

- [x] 1.1 `SupportLevel.DEPRECATED` and `Support.since`; `warning()` gives "Deprecated: use `<tool>`." or "Deprecated: no replacement."; tests
- [x] 1.2 `ToolRegistrar`: the description opening and success `warning` for deprecated tools (same path as beta); tests
- [x] 1.3 Support-level test: a deprecated entry names a registered replacement or "no replacement"; fails when the major version is above `since`'s; every planned reason names a queue item; tests for each rule
- [x] 1.4 Progress generator: deprecated tools counted on their own, left out of the coverage bars; tests

## 2. Remove the 33 planned tools

- [x] 2.0 Check `manage_design_table` before removing it: does `IModelDoc2.InsertFamilyTableNew` work on the user's machine (it needs Excel), and is there a read path (`IDesignTable`) without Excel? Record the finding in design.md. If design tables work, keep the tool `planned` for queue item 13 (`configuration-tools`) and add it there; otherwise remove it with the rest. Its live probe joins this change's live bundle (7.1), not a separate run
- [x] 2.1 Analysis, automation, drawing (`add_annotation`) and export: remove the tools, input models, hints, levels and tests
- [x] 2.2 Drawing analysis (six), file management (three), macros (six), sketching (`tutorial_simple_hole`), templates (five): the same
- [x] 2.3 Remove every "use `<removed tool>`" sentence from other descriptions; a test that no description names an unregistered tool
- [x] 2.4 The seven planned drawing tools' reason: "planned in queue item 12 (the drawing pack)."

## 3. Replacements gain what they replace

- [x] 3.1 `save_file`: `overwrite` input, `_prepare_save_target` on a new path with the extension from the active document's type; tests for a missing folder, the wrong extension, an existing file, and in place
- [x] 3.2 `get_model_info`: `size_bytes`, `created`, `modified` from one `os.stat` helper shared with `get_file_properties`; tests for saved and unsaved
- [x] 3.3 Mock adapter: the model info it returns carries a path that the tests can stat, and an unsaved document has none; tests

## 4. Deprecate the eight stable duplicates

- [x] 4.1 Levels: `load_part`, `load_assembly` → `open_model`; `save_part`, `save_assembly` → `save_file`; `calculate_mass_properties` → `get_mass_properties`; `get_file_properties` → `get_model_info`; `add_drawing_view` → `create_drawing_view`; `sketch_tutorial_simple_hole` → no replacement; all `since` 2.1.0
- [x] 4.2 `save_assembly`'s description names `pack_and_go_assembly` for `include_references`
- [x] 4.3 Replacements' descriptions drop "for X, use `<deprecated>`" pointers; tests

## 5. Verb list

- [x] 5.1 The verb table and its exceptions in `docs/agents/tool-description-standard.md`; CONTRIBUTING.md links it
- [x] 5.2 The naming check in the description-standard test; a test that an unlisted verb fails

## 6. Docs

- [x] 6.1 Tool catalog pages: removed rows gone, deprecated rows marked
- [x] 6.2 The agent skill's tool lists and `errors-and-limits.md`
- [x] 6.3 README counts and progress bars regenerated (`python -m solidworks_mcp.progress.generate`)
- [x] 6.4 CHANGELOG (2.1.0): Removed (the 33 names), Deprecated (the eight), Changed (`save_file` refuses an existing file without `overwrite`; `get_model_info` adds file details)

## 7. Live bundle (one set, run together, then fixes one by one)

- [x] 7.1 Live tests: `save_file` to a new path, a missing folder and an existing file; `get_model_info` on a saved and a new part; one deprecated tool's `warning`; the design-table probe (task 2.0): insert one on a scratch part and read it back
- [x] 7.2 Hand the user the bundle; fix each failure afterwards, one at a time

## 8. Finish

- [x] 8.1 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`
- [x] 8.2 Sign-off, PR (no attribution) closing #174, archive, the queue updated
