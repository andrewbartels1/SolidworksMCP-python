## 1. Section and detail views

- [x] 1.1 New inputs for `create_section_view` (`view`, `line_start`, `line_end`, `position`, `label`) and `create_detail_view` (`view`, `center`, `radius`, `position`, `scale`, `label`); the off-sheet and missed-view checks; tests
- [x] 1.2 Adapter interface for both through `base.py`, `circuit_breaker.py`, `connection_pool.py`; tests
- [x] 1.3 Real adapter: activate the view, sketch the line or circle in view space, `CreateSectionViewAt5` / `CreateDetailViewAt4`, delete the sketch entity on failure; tests
- [x] 1.4 Mock adapter: a new view appended to its view list with a label and outline; tests

## 2. Title block and sheet format

- [x] 2.1 One title-block helper shared by `generate_drawing_package` and `update_title_block` (mapping, merge over current values, fit); tests
- [x] 2.2 `update_title_block` input (at least one field) and tool; tests
- [x] 2.3 `update_sheet_format` input and tool; `find_sheet_format` errors name the folders searched; tests
- [x] 2.4 Adapter interface for the sheet format through every layer; tests
- [x] 2.5 Real adapter: `SetTemplateName`, `ReloadTemplate(True)`, `SetProperties2`; tests
- [x] 2.6 Mock adapter: the sheet's format and size change, views kept; tests

## 3. Drawing dimensions (#102)

- [x] 3.1 `add_dimension` input (type, points, position) and the two-entity rule; tests
- [x] 3.2 `auto_dimension_view` input (`view`, `scheme`); tests
- [x] 3.3 Adapter interface for both through every layer; tests
- [x] 3.4 Real adapter: point picks with the null callout, `AddDimension` with the direction, value read back; `ActivateView`, `AutoDimension`, the count before and after; tests
- [x] 3.5 Mock adapter: a dimension's value from its mock geometry; auto-dimension adds two per view; tests

## 4. Drawing check

- [x] 4.1 Adapter method returning views (name, type, outline, dimension count), sheet size, title-block properties, BOM present, dangling count; through every layer; tests
- [x] 4.2 Real adapter: `GetOutline`, `GetDimensionCount4`, `IsDangling`, BOM table lookup; tests
- [x] 4.3 Mock adapter: the same report from its drawing state; tests
- [x] 4.4 The five rules as plain functions; `check_drawing` replaces `check_drawing_standards`; tests for each rule and for a part being active

## 5. Levels and descriptions

- [x] 5.1 The seven tools' descriptions rewritten to the standard (no "Not available yet"); `auto_dimension_view` vs `insert_model_dimensions` stated; levels `beta` until the bundle passes
- [x] 5.2 The support-level test: no tool `planned`

## 6. Live bundle (one set, run together, then fixes one by one)

- [x] 6.1 (`tests/live/test_live_sw_drawing_pack.py`, passed on SolidWorks 2026 on 2026-11-16 after the fixes in design decision 7; the detail magnifies the bore in the section, not a plain corner; the off-sheet and no-BOM checks are unit-tested; the BOM-on-A3 check for #158 is left out, as no assembly is drawn) Live tests: a section through a plate's hole and one off the view; a 3:1 corner detail; revision B on a package drawing; A3 to A2 keeping views and title values; width 60 and Ø6 dimensions; auto-dimension on the front view; `check_drawing` on a finished package, a view off the sheet and an assembly with no BOM; `insert_bom_table` on the A3 ISO format, checked on the sheet (#158)
- [x] 6.2 Hand the user the bundle; fix each failure afterwards, one at a time; move each tool to stable when its tests pass

## 7. Docs and finish

- [x] 7.1 Drawing catalog pages, the drawing tutorial's "What is and isn't live today" table, the agent skill's drawing workflow (views, then dimensions, then `check_drawing`, then export)
- [x] 7.2 CHANGELOG (Added; Changed: `check_drawing_standards` is now `check_drawing`), progress bars regenerated
- [x] 7.3 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`
- [x] 7.4 Sign-off, PR (no attribution) closing #102, a comment on #158 for the BOM check, archive, the queue updated
