## Context

Assembly code lives in `adapters/solidworks/io.py` (insert, mate, state,
list, interference) and its tools in `tools/modeling.py`. Components are
named by their instance name (`pin-1`), found with `_find_components`.
Drawing views are found by name with `_resolve_drawing_view`
(`drawing_standard.py`), as `insert_bom_table` does. COM signatures and
enum values below were read from this machine's SolidWorks 2026 type
library.

## Goals / Non-Goals

**Goals:** an assembly an agent can repeat, mirror, swap, hide and explode,
and draw as a ballooned exploded view with a BOM, each in one call with
names it already has.

**Non-goals:** radial explode steps and rotation in explode steps; opposite-
hand mirrored part files (mirror makes instances only); smart components,
SpeedPak, lightweight states; balloon text other than the item number.

## Decisions

### 1. New code in its own modules

`adapters/solidworks/assembly.py` (a mixin, as `sketch.py` is) holds the
COM calls; `tools/assembly.py` holds the tools. `add_balloons` is a drawing
tool (`tools/drawing.py`): it acts on a drawing, so it belongs to the drawing
toolset, and a client with only that toolset still has it. They import the existing
helpers from `io.py` and `drawing_standard.py` rather than copying them.
This follows queue item 40's direction (split by topic) without moving
existing code, which item 40 will do.

### 2. Exploded views

- `create_exploded_view` with no `steps` calls `IAssemblyDoc.AutoExplode`.
- With `steps` (each: `components`, `direction` `x`/`y`/`z`, `distance`
  mm, optional `reverse`), it makes sure the active configuration has an
  exploded view (`CreateExplodedView` when `GetExplodedViewNames` is empty),
  then per step selects the components (mark 1) and the default plane
  normal to the direction (Right for x, Top for y, Front for z; mark 2) and
  calls `IConfiguration.AddExplodeStep2(distance, 0, reverse, 0, 0, False,
  False, False)`. A step that returns nothing fails, naming the step.
- Either way the view is shown (`ShowExploded2(True, name)`) and the reply
  gives its name, the step count and the assembly's bounding box before and
  after, so the explode is measured.

The marks and `ExplDirIndex` 0 follow the API help's example; the live demo
checks them by the bounding box growing along the step's direction.

`set_exploded_view(exploded)` calls `ShowExploded2(exploded, name)` for the
active configuration's first exploded view and reads `IsExploded` back.
With no exploded view it fails as `not_found`.

### 3. Component patterns and mirrors

`pattern_components` (`kind` `linear`, the default, or `circular`) builds a
feature from a definition: `IFeatureManager.CreateDefinition`
(`swFmLocalLPattern` 108 or `swFmLocalCirPattern` 109), sets
`SeedComponentArray` to the seed components, the direction axis (`D1Axis`
or `Axis`, an axis by name from `create_axis`), `D1Spacing` /
`D1TotalInstances` or `Spacing` / `TotalInstances` (circular spacing in
degrees, `EqualSpacing` when the angle is 360), then `CreateFeature`. The
reply gives the feature's name and the component count before and after,
which must grow by (count - 1) x seeds.

`mirror_components` calls `IAssemblyDoc.MirrorComponents3` with the plane
(`Front Plane`, `Top Plane`, `Right Plane` or a plane's name), the
components as `ComponentsToInstance` (mirrored instances of the same
parts, no new files) and nothing to mirror into new files. The reply gives
the new instances' names (the components after minus before).

### 4. Replace

`replace_component` selects the component and calls
`IAssemblyDoc.ReplaceComponents2(file, config, all_instances, 0, True)`
(re-attach mates). The file must exist; the reply gives the component
names before and after and each one's file path after, so the swap is
read back rather than trusted.

### 5. Visibility and transparency

`set_component_state` gains `visible` and `transparent`, through a new
adapter method `set_component_appearance`: visibility sets
`IComponent2.Visible` (1 shown, 0 hidden) and reads it back; transparency
selects the component and calls `IAssemblyDoc.SetComponentTransparent`.
(Built this way rather than through `CompConfigProperties5`, which would
have to pass back every other component property to change one.) The tool
calls the existing state method only for `fixed` / `flexible`.

### 6. Balloons and the exploded drawing view

- `create_drawing_view` gains `exploded`: after the view is placed,
  `IView.ShowExploded(True)`; the reply says whether it shows exploded.
- `add_balloons(view_name, layout)` selects the view, builds
  `IDrawingDoc.CreateAutoBalloonOptions` (layout from
  `swBalloonLayoutType_e`: `square` 1, `circle` 2, `top` 3, `bottom` 4,
  `right` 5, `left` 6; `IgnoreMultiple` on, so one balloon per part) and
  calls `AutoBalloon5`. The reply gives the balloon count and their item
  numbers; none is an error naming the view.

### 7. Naming

`replace_` joins the verb list: "swaps one thing for another (a component
for another file)". The standard says not to add exceptions; a new verb is
a spec change, made here.

## Risks / Trade-offs

- [Explode-step marks or `ExplDirIndex` differ on SolidWorks 2026] → the
  demo measures the bounding box per step; fix before sign-off.
- [Component pattern definition properties need a different shape
  (arrays of dispatch)] → `SeedComponentArray` takes the components as a
  dispatch array (`com_utils`); the demo counts components.
- [`AutoBalloon5` needs the view selected a particular way] → it is selected
  by name (`SelectByID2(view, "DRAWINGVIEW")`); the demo counts balloons.
- [Replace with mates that no longer fit leaves mate errors] → the reply
  passes on `rebuild_model`'s errors for the assembly so the agent sees
  them.
