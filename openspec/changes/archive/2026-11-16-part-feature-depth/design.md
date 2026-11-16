## Context

The feature tools live in `tools/modeling.py` and call adapter methods
implemented in `adapters/solidworks/features.py` (real) and
`mock_adapter.py`. Faces and edges are already picked by points:
`create_reference_plane`'s `face_point`, `select_face_edges`, and
`face_selection.py`'s helpers, which rebuild first and pass a `VT_DISPATCH`
null callout (runbook #11, #13). `pattern_circular` and `mirror_feature`
already check the volume change, and the extrude tools report
`measured_change`.

The COM calls, from the type library index (`lookup_api_method`):

| Tool | COM call |
| --- | --- |
| `create_hole` | `IFeatureManager.HoleWizard5` (27 arguments) |
| `add_cosmetic_thread` | `IFeatureManager.InsertCosmeticThread3(Standard, StandardType, Size, Diameter, EndType, Depth, Note)` |
| `pattern_linear` | `IFeatureManager.FeatureLinearPattern5` (22 arguments) |
| `create_shell` | `IModelDoc2.InsertFeatureShell(Thickness, Outward)` |
| `add_draft` | `IFeatureManager.InsertMultiFaceDraft(Angle, FlipDir, EdgeDraft, PropType, IsStepDraft, IsBodyDraft)` |
| `create_rib` | `IFeatureManager.InsertRib(Is2Sided, ReverseThicknessDir, Thickness, ReferenceEdgeIndex, ReverseMaterialDir, IsDrafted, DraftOutward, DraftAngle, IsNormToSketch, IsDraftedFromWall)` |
| `sketch_convert_entities` | `ISketchManager.SketchUseEdge3(Chain, InnerLoops)` |

## Goals / Non-Goals

**Goals:**
- The six features and convert-entities, each in one call, with points
  for every pick.
- Each solid tool proves itself by the volume change, as the existing ones
  do.

**Non-Goals:**
- Several holes in one call was out of scope at first; added after the
  live demos (2026-11-15) at the user's request: see decision 7.
- Every Hole Wizard standard and fastener type: ISO and ANSI inch, four
  hole types, a fixed size list each.
- Variable-pitch patterns, step draft, drafted ribs, multi-thickness
  shells.
- Sheet metal (queue item 15).

## Decisions

### 1. Points for every pick, through `face_selection.py`

Every face or edge input is a point in millimetres, as the existing tools
take, resolved by the shared helpers (rebuild once, `SelectByID2` with
`FACE` or `EDGE` and the null callout, read the selected object's type).
Marks: the shell's faces to remove and the draft's faces are mark 1 (the
draft's neutral face is mark 2), set through the helpers' `append`/`mark`
arguments. No tool takes face or edge names; agents don't know them.

### 2. `HoleWizard5` is mapped by a live diagnostic first

`HoleWizard5` takes integer standard, fastener-type and end-condition
codes, a size string, and twelve type-dependent values. The first task is
a live diagnostic (run in the bundle, not before) that makes one hole of
each of the four types for ISO and ANSI at one size, with the codes from
the `swWzdHoleStandards_e` and `swWzdHoleStandardFastenerTypes_e` enums,
and records which arguments SolidWorks honours. The tool's table of
`(hole_type, standard) → (StandardIndex, FastenerTypeIndex)` and its size
lists come from that run. Until it passes, `create_hole` is `beta`.

The hole sits where the face was picked: `HoleWizard5` places the hole at
the selection point of the selected face.

### 3. `pattern_linear` mirrors `pattern_circular`

Same input style (`features`, plus per-direction direction, count and
spacing), same adapter flow: select the features (mark 4), the direction
edge or axis (mark 1, and mark 2 for direction 2), call
`FeatureLinearPattern5` with `GeometryPattern` off and the
`CtrlByNum`/offset arguments at their defaults, then check the volume.

### 4. One success rule

A solid tool succeeds when its feature exists and the volume moved. When
SolidWorks returns a feature but the volume didn't change, the tool deletes
the feature it made (the same path `delete_feature` uses) and fails, so a
failure never leaves a no-op feature in the tree. `add_cosmetic_thread` is
the exception: its check is the thread feature in the tree and an
unchanged volume.

### 5. `sketch_convert_entities` returns registry ids

The sketch adapter keeps a registry of entities it created so other tools
can name them. `SketchUseEdge3` returns only a Boolean, so the adapter
reads the sketch's segments before and after, registers the new ones, and
sets them to construction when asked (`ISketchSegment.ConstructionGeometry`).

### 6. Names follow the verb list

`create_` for features built from a sketch or acting on the body (hole,
shell, rib), `add_` for treating existing faces and edges (draft, thread),
`pattern_` and `sketch_` as listed in the honest-tool-list change's verb
table. This change depends on that change being merged first.

## Risks / Trade-offs

- [`HoleWizard5`'s codes differ by SolidWorks version] → the diagnostic
  runs on the user's SolidWorks 2026; the tool stays `beta` with that as
  its reason until checked on another version.
- [A point on an edge also lies on two faces] → face picks use `FACE`, edge
  picks `EDGE`; the helpers already handle this for chamfers.
- [Seven new tools grow the tool list] → item 10 removes 33 first, and
  item 14's toolsets can turn families off.
- [Shell or draft fails on a body with fillets] → SolidWorks' own error is
  passed on through the error classifier; no retry.

## Implementation notes (2026-11-15)

- **Codes from the type libraries, not memory.** Argument lists come from
  the gen_py wrapper of `sldworks.tlb`; enum values from `swconst.tlb`
  (read directly with `pythoncom.LoadTypeLib`): hole types
  (`swWzdGeneralHoleTypes_e`: counterbore 0, countersink 1, simple 2,
  tapped 4), standards (`swWzdHoleStandards_e`: ANSI inch 0, ISO 8), the
  fastener lists (`swWzdHoleStandardFastenerTypes_e`: ISO drill sizes 143,
  socket head cap 139, CTSK flat head 141, tapped hole 147; ANSI inch all
  drill sizes 18, socket cap screw 9, flat head 82 15, tapped hole 27),
  end conditions and `swCosmeticThreadType_e`.
- **`HoleWizard5` sizes from the table.** Diameter, length and Value1-12
  are passed as -1 so the standard's table for the size fills them; only a
  blind depth is given. The live diagnostic confirms which sizes each
  standard accepts (e.g. whether ISO drill sizes read `Ø6.0`).
- **One adapter module.** The six solid features and convert entities live
  in `adapters/solidworks/part_features.py` (`SolidWorksPartFeaturesMixin`),
  sharing `_measured`, the volume rule with the delete-on-no-change step.
- **Selection marks to confirm live.** The shell's faces are picked with
  mark 0; the draft's neutral face with mark 1 and its faces with mark 2.
  The SolidWorks help for these calls couldn't be read here; the live
  bundle settles them.
- **Calls that return nothing.** `InsertRib` and `InsertFeatureShell`
  return no feature, so the new feature's name is read from the end of the
  tree, and the volume decides success.
- **Linear pattern directions** are a point on a straight edge or a name
  (axis or edge); marks 1 and 2, features mark 4, as the circular pattern.
- All seven are `beta` with the reason "not yet checked on SolidWorks
  (queue item 11's live bundle)"; each moves to `stable` when its live test
  passes.

## Added after the live demos (2026-11-15)

### 7. Several holes: points in the hole's position sketch

The user places holes by clicking sketch points in the Hole Wizard's
Positions tab: every point of the hole's position sketch is a hole. The API
does the same: after `HoleWizard5` makes the first hole, the position sketch
(the hole's sub-feature sketch holding a point at `face_point`) is opened
with `EditSketch`, a point is added for each of `positions` with
`ISketchManager.CreatePoint` (model millimetres turned into sketch
coordinates through `ISketch.ModelToSketchTransform`, `AddToDB` on so no
point snaps to the first hole), and the sketch is closed with
`InsertSketch(True)`, which rebuilds the hole at every point. A point the
sketch can't take, or a hole count short of the points after the rebuild,
deletes the feature and fails. Alternative: a hole per call and a pattern;
kept for regular grids, but scattered holes need points.

### 8. Simple holes through all fall back to blind

The diagnostic `test_simple_hole_through_all_diagnostic` showed `HoleWizard5`
returns nothing for a simple hole with `through_all` whatever the diameter,
depth or table, while blind simple holes and through-all tapped holes build.
So a simple hole that comes back empty is retried blind, the depth being the
part box's diagonal (`IPartDoc.GetPartBox`) plus 1 mm, and the reply says so.
