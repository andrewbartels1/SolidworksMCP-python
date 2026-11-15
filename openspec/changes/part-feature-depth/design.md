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
- Several holes in one call: one hole per call, then `pattern_linear` or
  `pattern_circular`. Editing a Hole Wizard position sketch is a second
  feature's worth of work.
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
