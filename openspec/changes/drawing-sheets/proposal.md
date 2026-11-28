## Why

A drawing can hold several sheets, but an agent can't see them, add one or
choose which one views go on: every view, dimension and note lands on the
sheet that happens to be active. A general arrangement on one sheet and
enlarged details on another is the usual layout of a drawing of any size.
Queue item 37 (drawing sheets and callouts), first part: the sheets.

## What Changes

- **`list_sheets`**: the active drawing's sheets with each one's paper size,
  scale and projection, and which is active.
- **`add_sheet`**: a new sheet with a format (e.g. `a3 - iso`), paper size,
  scale and projection (the active sheet's by default), made active.
- **`activate_sheet`**: choose the active sheet by name.
- Three tools, beta until the live demo. Callouts, auxiliary and break
  views, the revision table and ordinate dimensions stay in item 37.

## Capabilities

### New Capabilities

- `tools/drawing-sheets`: `list_sheets`, `add_sheet`, `activate_sheet`.

### Modified Capabilities

None.

## Impact

- `adapters/sheet_rules.py` (pure), `adapters/solidworks/drawing_sheets.py`
  (COM, on the drawing pack's helpers), `adapters/mock_drawing_sheets.py`;
  base, circuit breaker and connection pool wrappers.
- `tools/drawing_sheets.py`, in the `drawing` toolset; support levels,
  hints, classifier rules.
- Docs: a catalog page and counts. Tests mirroring src; a live test.
