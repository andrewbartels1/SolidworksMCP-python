## Context

Gaps from #209, checked against the code and the two U-joint transcripts on
2026-11-06:

- `add_mate` selects each entity with `IComponent2::FeatureByName` +
  `IFeature::Select2`, so only named tree features (planes, axes) can be
  mated.
- Nothing calls `IAssemblyDoc::FixComponent` / `UnfixComponent` or sets a
  component's solving (rigid / flexible).
- `create_reference_plane` refuses `angle`: measured on SW 2025, an angle
  constraint with one reference adds nothing. A face can only be named, and
  faces have no names.
- `add_chamfer` calls `InsertFeatureChamfer(1, 1, width, pi/4, ...)`. In
  `swChamferType_e` 1 is **angle-distance**, not equal distance (16): it has
  always made an angle-distance chamfer at a fixed 45°. Options = 1 is
  `swFeatureChamferFlipDirection`.
- `create_extrusion` already maps `both_directions` to `swEndCondMidPlane`
  (#191) and builds thin walls with `FeatureExtrusionThin2`. In the
  transcripts the bodies came out mid-plane (symmetric bounding boxes), but
  the reply echoed the input `direction: "blind"`, so the agent believed the
  flag was ignored. The thin call's `RevThinDir` is fixed at 0 (one side).
- Over MCP, arguments arrive validated as the tool's model; a script calling
  the function with a dict hits `'dict' object has no attribute ...` on most
  tools. The export tools fixed this one by one (6ae900f).

COM members, checked with the project's API lookup (type library 34.0) and
`swconst.tlb`:

| Member | Signature / values |
| --- | --- |
| `IAssemblyDoc::AddMate5` | (type, align, flip, distance, upper, lower, gear num, gear den, angle, upper, lower, positioning only, lock rotation, width option, out error) |
| `IAssemblyDoc::FixComponent`, `UnfixComponent` | act on the selected component |
| `IAssemblyDoc::CompConfigProperties6` | (suppression, solving, visibility, use named config, config name, exclude from BOM, is envelope, save-as-part option): sets all of them for the selected component |
| `IComponent2` | `IsFixed()`, `Solving` (read), `GetSuppression2`, `Visible`, `ReferencedConfiguration`, `ExcludeFromBOM`, `IsEnvelope`, `GetBodies2(type)`, `Transform2`, `Select4(append, data, popup)` |
| `IFeatureManager::InsertRefPlane` | (first constraint, value, second, value, third, value) |
| `IFeatureManager::InsertFeatureChamfer` | (options, type, width, angle, other distance, vertex 1, 2, 3) |
| `IFeatureManager::FeatureExtrusionThin2` | ... `Thk1, Thk2, EndThk, RevThinDir, CapEnds` ... |
| `swRefPlaneReferenceConstraints_e` | Parallel 1, Coincident 4, Distance 8, Angle 16, OptionFlip 256 |
| `swChamferType_e` | AngleDistance 1, DistanceDistance 2, EqualDistance 16 |
| `swComponentSolvingOption_e` | Rigid 0, Flexible 1 |
| `swThinWallType_e` | OneDirection 0, OppDirection 1, MidPlane 2, TwoDirection 3 |
| `swMateType_e` / `swMateAlign_e` | as in `_MATE_TYPES` / `_MATE_ALIGNMENTS` |

## Goals / Non-Goals

**Goals:** every gap in #209 closed and checked live on SolidWorks 2026; the
U-joint's pin-in-hole and spinning knob possible with the tools; replies that
say what SolidWorks built.

**Non-Goals:** the queue's other `create_extrusion` faults (`sketch_name`,
`direction`), gear/cam/limit mates, rebuilding the U-joint demo, edge mates.

## Decisions

### A face is a point on it, in the part's own coordinates

`face_a` / `face_b` are `[x, y, z]` mm in the component's part coordinates,
which is what an agent knows from building the part. The adapter maps the
point into the assembly with the component's `Transform2` (an `IMathPoint`
from `IMathUtility::CreatePoint`, `MultiplyTransform`). It searches only that
component's faces (`GetBodies2`, the face closest to the point within
0.01 mm, as `select_face_edges` does) and selects the face with
`IEntity::Select4`, the first under mark 1 and the second appended. Whether
component faces report assembly or part coordinates is measured live first
(a read-only probe); the transform step is kept only if needed.

Alternative, `SelectByID2("", "FACE", x, y, z)` at an assembly point:
rejected. A pin's surface and its hole's surface are at the same points, so
the pick could land on the wrong component.

Each side takes exactly one of `entity_*` or `face_*`. The default stays
`"Front Plane"` only when neither is given, so existing calls are unchanged.

### `set_component_state` is its own tool

Input: `component`, and any of `fixed` (true fixes, false floats) and
`flexible` (true flexible, false rigid). Fix and float select the component
and call `FixComponent` / `UnfixComponent`. Solving goes through
`CompConfigProperties6`, which also sets suppression, visibility,
configuration, BOM and envelope: the adapter reads each one from the
component first and passes it back, so only solving changes. The reply is
the state read back (`fixed`, `flexible`). Alternative, more fields on
`add_mate`: rejected, a component's state isn't a mate.

### Reference planes: angle about an axis; a face by a point

- `angle` needs `axis`: a named axis (`"Axis1"`) or a temporary axis name,
  selected under mark 1, with constraints `Angle | flip` on the plane (mark 0)
  and `Coincident` on the axis. This is what the SW 2025 measurement said was
  missing.
- `face_point` (`[x, y, z]` mm) replaces `reference` with the planar face at
  that point, found as `select_face_edges` finds it, and selected under
  mark 0. With `offset` it makes a parallel plane; with `offset` 0 a plane on
  the face.

### Chamfer: angle and flip on the call it already makes

`angle` (degrees, 0 < angle < 90, default 45) and `flip` (measure the
distance on the other face). The call stays `InsertFeatureChamfer`, type 1
(angle-distance), `Options = 1 if flip else 0`. The comment that called
type 1 "equal distance" is corrected. Equal-distance (16) is not used: at 45°
angle-distance gives the same chamfer and has been verified live.

### Extrusion reply

`extrusion` reports `end_condition` (as SolidWorks applied it), `both_directions`,
and, for thin walls, `thin_thickness` and `thin_side`; `direction` is no longer
echoed. `thin_side` (`one_side`, `other_side`, `mid_plane`) maps to
`RevThinDir` 0, 1, 2.

### Plain dicts at the boundary

At registration, `tool_boundary` finds the parameters annotated with a
pydantic model (alone or `| None`). At call time a dict in one of them is
validated with `normalize_input`, so a bad dict is an `invalid_input` error
like any other. The export tools' `_file_input` keeps its default
`format_type` and stays.

## Risks / Trade-offs

- [Component face coordinates differ by build] → measured live before the
  code depends on it; the live test mates a pin in a hole away from the
  origin, so a wrong space fails.
- [CompConfigProperties6 resets something we didn't read] → the live test
  reads suppression, visibility and configuration before and after.
- [Boundary conversion changes a tool that took a raw dict on purpose] → only
  parameters annotated with a model are converted; the full suite runs.

## Migration Plan

Additive: new optional fields and one new tool. `add_chamfer` without
`angle` behaves as before.
