## Context

The drawing tools are in `tools/drawing.py` and `tools/drawing_automation.py`;
the real adapter's drawing work is in `adapters/solidworks/documentation.py`
and `drawing_standard.py`. Already there and reusable:

- `_sheet_bounds(drawing)`: the sheet's size, used to keep views on it;
- `title_block_properties(...)` and the DWG NO./TITLE fit in
  `generate_drawing_package`;
- `find_sheet_format(adapter, name)`: finds a `.slddrt` by name;
- `list_drawing_views`, `insert_model_dimensions`, `insert_bom_table`.

The seven tools are registered as `planned`; each raises
`UnsupportedOperationError` or fails `require_capability`. Their current
inputs were never used, so they can change.

COM members, from the type library index:

| Need | Member |
| --- | --- |
| Section view | `IDrawingDoc.CreateSectionViewAt5(X, Y, Z, SectionLabel, Options, ExcludedComponents, SectionDepth)` |
| Detail view | `IDrawingDoc.CreateDetailViewAt4(X, Y, Z, Style, Scale1, Scale2, LabelIn, Showtype, FullOutline, JaggedOutline, NoOutline, ShapeIntensity)` |
| Pick a view | `IDrawingDoc.ActivateView(ViewName)` |
| One dimension | `IModelDocExtension.AddDimension(X, Y, Z, Direction)` |
| Auto dimension | `IDrawingDoc.AutoDimension(EntitiesToDimension, HorizontalScheme, HorizontalPlacement, VerticalScheme, VerticalPlacement)` |
| Sheet format | `ISheet.SetTemplateName(NameIn)`, `ISheet.ReloadTemplate(KeepNoteChanges)`, `ISheet.SetProperties2(...)` |
| Checks | `IView.GetOutline()`, `IView.GetDimensionCount4()`, `IAnnotation.IsDangling()` |

## Goals / Non-Goals

**Goals:**
- The seven planned drawing tools work on SolidWorks, and no tool is left
  `planned`.
- Every position is in sheet millimetres, the unit the other drawing tools
  use.

**Non-Goals:**
- Aligned, half or offset sections; section depth; excluding components.
- Ordinate dimensions, chamfer dimensions, tolerances on `add_dimension`.
- The title-block fit for fields other than DWG NO. and TITLE (#158).
- A drafting-standard score (ASME/ISO rule sets). `check_drawing` checks
  completeness, not a standard.

## Decisions

### 1. Section line and detail circle are sketched in the parent view

`CreateSectionViewAt5` and `CreateDetailViewAt4` use the selected sketch
line or circle. The adapter activates the parent view, sketches the line
(or circle) with the sketch manager in sheet coordinates converted to the
view's sketch space, selects it, and calls the creator at `position`. If
the call returns nothing, the sketch entity is deleted so no stray line is
left. The section line is checked against `IView.GetOutline()` first, and
`position` plus the parent view's size against `_sheet_bounds`, so the
common failures are `invalid_input` before any COM change.

### 2. Picks for `add_dimension` are sheet points

`SelectByID2("", "EDGE" | "VERTEX", x, y, 0, append, 0, null_callout, 0)`
in sheet metres selects view entities on a drawing. The adapter selects
entity 1, then entity 2 with `append`, then calls
`IModelDocExtension.AddDimension(x, y, 0, direction)` with the
direction from `dimension_type` (`swSmartDimensionDirection_e`: horizontal,
vertical, aligned; radial, diameter and angular use the smart direction).
The reply reads the new display dimension's `GetDimension2(0).Value`.

*Alternative:* entity names from a view registry, as sketches have. Rejected
for now: drawing entities have no stable names, and agents can compute
sheet points from `list_drawing_views`' outlines.

### 3. `auto_dimension_view` counts before and after

The adapter activates and selects the view, calls `AutoDimension` with all
edges, the scheme for both directions, and placement above/right, then
reports `GetDimensionCount4()` after minus before. Zero added is a failure,
so a call that silently does nothing is visible.

### 4. `update_title_block` reuses the package's mapping

It calls `title_block_properties` with the given fields merged over the
current property values (read first), writes model and drawing properties
through the adapter's custom-property methods, then reruns the fit for
DWG NO. and TITLE and rebuilds. It is the same code path
`generate_drawing_package` uses, moved into one helper both call.

### 5. `update_sheet_format` changes the template in place

`find_sheet_format` resolves the name; the adapter calls
`SetTemplateName` then `ReloadTemplate(True)`, and `SetProperties2` for a
new paper size, then checks the views are still listed and on the sheet.
The live bundle confirms the title block's linked fields survive the
reload.

### 6. `check_drawing` is read-only and composed from reads

A new adapter method returns, per view: name, type, outline, dimension
count; plus the sheet size, the title-block properties, whether a BOM
table exists, and the dangling annotation count. The rules run in the tool
module as plain functions on that data (unit-tested without COM). The tool
is the renamed `check_drawing_standards`; the old name was planned and
never worked, so no deprecation is needed.

### 7. What changed while building it (2026-11-16)

- **Sheet to view space** uses the view's sketch:
  `IView.GetSketch().ModelToSketchTransform` maps the drawing's document
  space (the sheet) into the view's sketch, scale and offset included, the
  mapping the hole positions use. The first live run (2026-11-16) used
  `IView.GetXform` (elements 9-10 and 12) and put the detail circle in empty
  space and the section line off the hole.
- **Auto-dimension** selects the view (`SelectByID2` as `DRAWINGVIEW`)
  after activating it, as `insert_model_dimensions`' fallback does; the
  first live run only activated it, and `AutoDimension` returned success
  with nothing added.
- **Dimensions** use `AddHorizontalDimension2`, `AddVerticalDimension2`,
  `AddRadialDimension2`, `AddDiameterDimension2` and `AddDimension2`
  (aligned and angular) after the picks, rather than
  `IModelDocExtension.AddDimension` with a direction: each places a typed
  dimension directly. The value is the dimension's `SystemValue`.
- **The sheet format** is applied with `IDrawingDoc.SetupSheet5`, the call
  `generate_drawing_package` already makes live, keeping the sheet's scale
  and projection, instead of `SetTemplateName` and `ReloadTemplate`.
- **The title block** writes each field to its property directly (the title
  to the model's `Description` through the first view's referenced
  document, the rest to the drawing), rather than re-running the package's
  mapping and fit; `drawing_number` goes to the drawing's `DrawingNo`. The
  ISO format's DWG NO. box shows the file name, not that property.
- **Errors** follow the other drawing tools: an unknown view is `not_found`,
  a part instead of a drawing `wrong_document_type`; geometry refusals
  (off the sheet, a line missing the view, nothing at a pick point, an
  unknown format) are `invalid_input`.
- **The rules** are in `tools/drawing_check.py`; the mock adapter's drawing
  pack is its own mixin (`adapters/mock_drawing_pack.py`).
- **Enum values** (`swAutodimScheme_e` chain is 3, `swDetViewStyle_e`,
  `swDetCircleShowType_e`, `swDrawingViewTypes_e`, `swTableAnnotationType_e`,
  `swDwgPaperSizes_e`) were read from the installed `swconst.tlb`.

## Risks / Trade-offs

- [Sheet-to-view coordinate conversion for the section line] → the
  conversion uses the view's position and scale (`IView.Position`,
  `ScaleDecimal`); the live bundle checks a section through a hole's centre.
- [`AutoDimension` places dimensions over each other] → `arrange_dimensions`
  already exists; the description points to it.
- [`ReloadTemplate` drops edited notes] → `KeepNoteChanges` is true; the
  live test checks the title-block values after the reload.
- [`SelectByID2` on a drawing picks the wrong view's edge where views
  overlap] → views are checked to be on the sheet; overlapping views are
  rare in generated drawings; the error says which entity was picked.
