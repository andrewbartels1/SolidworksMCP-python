## Why

Sheet metal is a common SolidWorks workflow (a base flange, flanges off its
edges, bends, then the flat pattern for the laser) that the server can't
start: `export_flat_pattern` writes the DXF of a sheet-metal part, but no
tool makes one. Issue #57, queue item 15.

## What Changes

Four tools, following the verb list:

- **`create_base_flange`**: a sheet-metal part's first feature, from the
  last closed sketch. A closed profile makes a flat plate; an open profile
  (a line or an L) makes a bent profile extruded by `depth`. Takes
  `thickness`, `bend_radius` and `k_factor` (default 0.5), and reports them
  back from the feature.
- **`add_edge_flange`**: a flange off one edge of the sheet, picked by a
  point on it in mm, with `length`, `angle` (default 90°) and the bend
  radius (the sheet's by default). The reply gives the volume added.
- **`create_sketched_bend`**: a bend along the line of the last closed
  sketch, drawn on a face of the sheet: `angle`, the direction and the
  bend radius. SolidWorks chooses the side that stays put (design, "What
  the live probes settled").
- **`set_flat_pattern`**: flatten (`flat: true`) or fold the part, and
  report the flat part's size, the blank to cut.

Each refuses a part that isn't sheet metal (except `create_base_flange`,
which makes it so) with `wrong_document_type` or `invalid_input`, before
SolidWorks is asked where it can.

## Capabilities

### New Capabilities
- `tools/sheet-metal`: making and flattening sheet-metal parts.

### Modified Capabilities
None.

## Impact

- COM, in a new adapter mixin `adapters/solidworks/sheet_metal.py`:
  `IFeatureManager.InsertSheetMetalBaseFlange2`, `CreateCustomBendAllowance`,
  `InsertSheetMetalEdgeFlange2`, `CreateDefinition(swFmSketchBend)` with
  `ISketchedBendFeatureData` and `CreateFeature`, and
  `IModelDoc2.SetBendState`. All run in `_handle_com_operation` on the
  connect thread.
- The base adapter, circuit breaker, connection pool and the mock adapter
  (its own mixin).
- `tools/modeling.py`: the four tools, beta until the live check; hints,
  catalog, the skill's workflows, CHANGELOG. Four more tools (139).
- Closes #57.
