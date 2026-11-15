## Why

Drawings are where this server goes further than the comparable servers
(the closest one declares drawings out of scope). An agent can already make
a drawing with standard views, a BOM, model dimensions, centre marks, GD&T
and a filled title block. Seven drawing tools are still `planned`, and
they are the ones a real drawing package needs next: a section and a detail
view, editing the title block or sheet format after the drawing exists,
adding one dimension by hand (#102), automatic dimensions on a view, and a
check that the drawing is complete. With them, an agent can take a part or
assembly to a finished, checked drawing.

## What Changes

- **`create_section_view`**: cuts a section through a view along a line
  given by two points in sheet millimetres, and places the section view at
  a point on the sheet, with a label (`A`, `B`, ...).
- **`create_detail_view`**: a detail of a circle (centre and radius in
  sheet millimetres) in a view, placed on the sheet at a scale, with a
  label.
- **`update_title_block`**: sets the title block's fields (title, drawing
  number, drawn by, date, revision, company) on an existing drawing, with
  the same field mapping and fit as `generate_drawing_package`.
- **`update_sheet_format`**: changes the active sheet's format (a format
  name such as `a3 - iso`, or a `.slddrt` path) and paper size, keeping the
  views.
- **`add_dimension`** (#102): one dimension in a view: linear (horizontal,
  vertical or aligned), radial, diameter or angular, between entities
  picked by points in sheet millimetres, placed at a point; it replies with
  the measured value.
- **`auto_dimension_view`** (#102): SolidWorks' auto-dimension on one view
  (baseline or chain, horizontal and vertical), replying with how many
  dimensions it added. Its description says how it differs from
  `insert_model_dimensions` (reference dimensions vs the model's own).
- **`check_drawing`** (the planned `check_drawing_standards`, renamed): a
  read-only check of the active drawing: every view on the sheet, every
  view dimensioned, the title block's fields filled, no dangling
  annotations, and a BOM when the model is an assembly. It replies with a
  list of findings and `passed`.
- All seven move from `planned` to `stable` after the live bundle, leaving
  no planned tools.

## Capabilities

### New Capabilities

- `tools/drawing-section-detail`: section and detail views.
- `tools/drawing-title-block`: `update_title_block` and
  `update_sheet_format` on an existing drawing.
- `tools/drawing-dimensions`: `add_dimension` and `auto_dimension_view`.
- `tools/drawing-check`: `check_drawing`.

### Modified Capabilities

- `tools/support-levels`: no tool is `planned` after this change.

## Impact

- **COM and adapter code, all on the connect thread inside
  `_handle_com_operation`:**
  - `adapters/solidworks/documentation.py` gains the view-creation and
    dimension methods:
    - `IDrawingDoc.CreateSectionViewAt5`, `CreateDetailViewAt4`,
      `AutoDimension`, `ActivateView`;
    - `IModelDocExtension.AddDimension`;
    - `ISheet.SetTemplateName` and `ReloadTemplate`;
    - `IView.GetOutline`, `GetDisplayDimensions`;
    - `IAnnotation.IsDangling`.
  - The section line and detail circle are sketched in the view before the
    call; entity picks use `SelectByID2` with the null callout (runbook #11).
  - New adapter methods through `base.py`, `circuit_breaker.py`,
    `connection_pool.py` and `mock_adapter.py`.
- **Tools:** `drawing.py` (the seven tools; `check_drawing_standards`
  renamed), `tool_hints.py`, `support_levels.py`.
- **Reuse:** `drawing_standard.title_block_properties` and its fit code,
  `find_sheet_format`, `_sheet_bounds`.
- **Docs:** drawing catalog pages, the drawing tutorial's "What is and
  isn't live today" table, the agent skill's drawing workflow, CHANGELOG,
  progress bars.
- Closes #102. From #158 it settles the BOM-on-a-formatted-sheet check (in
  the live bundle); the title-block fit improvements stay in #158.
- Depends on the honest-tool-list change (queue item 10), which leaves
  these seven as the only planned tools.
