## Context

No sheet-metal feature tool exists. `export_flat_pattern`
(`adapters/solidworks/documentation.py`) already tells a sheet-metal body
apart with `IBody2.IsSheetMetal`. Feature tools follow one pattern: a
mixin per area under `adapters/solidworks/`, the work inside
`_handle_com_operation`, a feature count or volume checked after the call
because SolidWorks often reports success and builds nothing.

COM members, from the SolidWorks 2026 type library:

| Need | Member |
| --- | --- |
| Base flange | `IFeatureManager.InsertSheetMetalBaseFlange2(Thickness, ThickenDir, Radius, ExtrudeDist1, ExtrudeDist2, FlipExtruDir, EndCondition1, EndCondition2, DirToUse, PCBA, UseDefaultRelief, ReliefType, ReliefWidth, ReliefDepth, ReliefRatio, UseReliefRatio, Merge, UseFeatScope, UseAutoSelect)` |
| K-factor | `IFeatureManager.CreateCustomBendAllowance()` → `ICustomBendAllowance` (`Type` = `swBendAllowanceKFactor` 2, `KFactor`) |
| Edge flange | `IFeatureManager.InsertSheetMetalEdgeFlange2(FlangeEdges, SketchFeats, BooleanOptions, FlangeAngle, FlangeRadius, BendPosition, FlangeOffsetDist, ReliefType, ReliefRatio, ReliefWidth, ReliefDepth, FlangeSharpType, CustomBendAllowance)` |
| Sketched bend | `IFeatureManager.CreateDefinition(swFmSketchBend = 35)` → `ISketchedBendFeatureData` (`BendAngle`, `BendRadius`, `PositionType`, `SetFixedFace`), then `CreateFeature` |
| Flat pattern | `IModelDoc2.SetBendState(swSMBendStateFlattened = 2 / swSMBendStateFolded = 3)`, `GetBendState` |
| Read back | `IBaseFlangeFeatureData` (`Thickness`, `BendRadius`, `KFactor`) |

Enums read from `swconst.tlb`: `swSheetMetalReliefTypes_e`
(rectangular 1 … none 4), `swFlangePositionTypes_e` (material inside 1,
outside 2, bend outside 3), `swEndConditions_e` (blind 0).

## Goals / Non-Goals

**Goals:** the four steps of the common workflow, each checked by the
geometry it makes; the flat blank's size, so an agent can check it.

**Non-Goals:** hems, miter flanges, jogs, lofted bends, corner treatments,
gauge and bend tables (K-factor only), converting a solid to sheet metal,
flat-pattern drawing views (the drawing tools could add one later).

## Decisions

### 1. A mixin, and positions in millimetres

`SolidWorksSheetMetalMixin` in `adapters/solidworks/sheet_metal.py`, like
the part-features mixin. Points are mm in model space, as `create_hole`
takes them, converted to metres for COM.

### 2. Base flange from the last closed sketch

The sketch is selected by name (the adapter's last closed sketch, as
`create_extrusion` uses), then `InsertSheetMetalBaseFlange2` with blind
end conditions. An open profile without `depth` is refused before the
call (the sketch's segments are read to tell open from closed). The
K-factor goes in through `CreateCustomBendAllowance`. Success is the
feature count rising and the body being sheet metal; the reply reads the
values back from `IBaseFlangeFeatureData`.

### 3. Edge flange by a point on the edge

The edge nearest `edge_point` is selected with the existing edge picker
(`_select_edge_by_coord`), and passed as the one-element `FlangeEdges`
array. `SketchFeats` is null so SolidWorks makes the default rectangular
profile; the length is set through `IEdgeFlangeFeatureData` if the insert
call doesn't take it. This is the riskiest call; the live check decides
between the insert call and `CreateDefinition(swFmEdgeFlange)`, and the
decision is recorded here.

### 4. Sketched bend through a feature definition

`IFeatureManager` has no insert call for a sketched bend in 2026, so the
bend is built from `CreateDefinition(swFmSketchBend)`: angle, radius and
position on `ISketchedBendFeatureData`, the fixed face from the face at
`fixed_point`, the sketch selected, then `CreateFeature`.

### 5. Flat pattern is a state, and the reply measures it

`SetBendState` flattens or folds; the reply gives the bounding box after
the rebuild (`get_model_info`'s box reader), so the blank's size is
measured, not computed.

### 6. Sheet metal is checked first

A part with no sheet-metal body (`IsSheetMetal` on its bodies, as
`export_flat_pattern` reads it) is refused by the three later tools before
any COM change, naming `create_base_flange`.

## Risks / Trade-offs

- [Edge flange length isn't an argument of the insert call] → decision 3's
  fallback; the live check settles it.
- [The edge picker picks the wrong edge of a thin sheet: two edges 2 mm
  apart] → the point should sit on the outer edge; the reply names the
  edge's length so a wrong pick is visible.
- [A sketched bend's fixed face] → `fixed_point` names it; the reply says
  which side moved through the bounding box.

## What the live probes settled (2026-11-16)

- **Base flange:** `DirToUse` must be 1; 0 builds nothing. The arguments
  that build: `UseDefaultRelief` false, `ReliefType` 0, `Merge` false,
  `UseFeatScope` and `UseAutoSelect` true, the K-factor through
  `CreateCustomBendAllowance`. The 2 mm plate was exactly 12,000 mm³ and the
  thickness, radius and K-factor read back from the feature (flagged as
  `IFeature` first). The part has no body before it, so the volume before
  is read from the geometry summary (0) rather than the mass properties.
- **Edge flange (decision 3):** `InsertSheetMetalEdgeFlange2` needs a
  profile sketch; with none it builds nothing, and calling
  `InsertSketchForEdgeFlange` out of order made SolidWorks throw (it kept
  running). SolidWorks' "Insert Sheet Metal Edge Flange" example gives the
  order used: the edge selected and read from the selection manager,
  `InsertSketchForEdgeFlange`, the sketch edited, `SketchUseEdge`, three
  lines drawn from the converted line's ends out to the length, the sketch
  closed, then the flange with the edge and the sketch. The length is
  measured from the picked edge: on the 2 mm plate a 20 mm flange stands
  22 mm above the bottom face.
- **Flat pattern (decision 5):** `SetBendState` returned success and changed
  nothing. Flattening unsuppresses the Flat-Pattern feature (found through
  `GetFlatPatternFolder`), as SolidWorks' Flatten does; folding suppresses
  it. The flanged plate flattened to 78.7124 mm, the hand value 78.712.
- **Sketched bend (decision 4):** `SetFixedFace` takes a point (x, y, z in
  metres) and an edge array, not a face; it made no difference to which
  side stayed, with or without the face selected under any mark. The tool
  takes no fixed point; the reply's bounding box shows which side moved.
