# Workflows

Tool sequences for the common jobs, with the check to make after each
step. Values are examples; sizes are millimetres.

## A plate with a hole and rounded top edges

1. `create_part` with `name: "plate"`.
2. `create_sketch` with `plane: "Top"`.
3. `add_rectangle` from (-50, -30) to (50, 30).
4. `exit_sketch`.
5. `create_extrusion` with `depth: 10`. Check `measured_change`: the box
   should grow to 100 x 10 x 60 (a Top-plane sketch extrudes along y).
6. `create_sketch` with `plane: "Top"`, then `add_circle` at (0, 0) with
   `radius: 5`, then `exit_sketch`. The reply names the sketch, e.g.
   "Sketch2".
7. `create_cut_extrude` with `sketch_name: "Sketch2"`,
   `end_condition: "ThroughAll"`, `depth: 10`. A sketch under the body is
   cut the other way automatically (`direction_flipped: true`). Check that
   the volume dropped by about π·5²·10 ≈ 785 mm³.
8. `select_face_edges` with `side: "top"` and `edge_type: "linear"`, then
   `add_fillet` with `radius: 2` and `edge_names: []`.
9. `verify_model` with `bounding_box_mm: [100, 10, 60]`,
   `solid_body_count: 1`, `feature_count: 3`, and a `volume_mm3` with a
   `relative_tolerance` wide enough for the fillets.
10. `set_material` (find the exact name with `list_available_materials`),
    then `save_file` with a `file_path` ending in `.sldprt`. To choose the
    material by strength or stiffness, compare candidates first with
    `get_material` and `material`: it reads the yield strength and the
    elastic modulus, in Pa, without assigning anything.

## Sketching somewhere other than the three planes

On a flat face of the body: `create_sketch` with `face_point`, a point on the
face in mm (e.g. `[0, 20, 0]` on the top of a 20 mm tall block). The sketch
sits on the face, so a cut made from it follows the face when a dimension
changes later. Prefer this to a plane at the same height.

Away from the body: `create_reference_plane` with `reference: "Top Plane"`
and `offset: 10` makes a plane 10 mm up; its name (e.g. "Plane1") goes into
`create_sketch`.

- At an angle: `create_axis` first (its reply names the axis, e.g. "Axis1"),
  then `reference`, `angle` (degrees) and `axis`.
- On or off a face, sloped or not: `face_point`, a point on the face in mm,
  with `offset` (0 puts the plane on the face).

## A bent plate or other wall from an open outline

Draw the outline as an open chain of `add_line` (the plate's centreline or
one edge), `exit_sketch`, then `create_extrusion` with `thin_feature: true`,
`thin_thickness` and `thin_side` (`"one_side"`, `"other_side"` or `"mid_plane"`).
`both_directions: true` extrudes half the depth each side of the sketch
plane; the reply's `end_condition` says `MidPlane`.

## A revolved part (a knob or a shaft)

1. `create_sketch` on "Front".
2. Draw half the profile with `add_line` (closed), and the axis with
   `add_centerline` along it.
3. `exit_sketch`, then `create_revolve` with `angle: 360`. It uses the sketch
   you just closed and the centreline in it.

## A ring of holes

1. One sketch on the face's plane: `add_circle` for the first hole at its
   radius from the origin.
2. `sketch_circular_pattern` with that circle's `id` and `count: 6`. The
   centre is always the sketch origin.
3. `exit_sketch`, then one `create_cut_extrude`.

A cut or a `create_hole` hole that already exists can be repeated instead:
`create_axis` with `reference: "y"` (an axis through the origin), then
`pattern_circular` with the feature's name, the axis and `count`.

## Standard holes, threads, shells and ribs

- **A hole for a screw:** `create_hole` with a point on the face where the
  hole's centre goes, the `hole_type` and a size from `list_hole_sizes`
  (`M6`, `#10`; on a simple hole `M6` is a clearance hole, `6` a drilled
  one). An unknown size is refused with the nearest ones. More holes on the same face go in
  `positions` (points in mm): one feature, a hole at each point. A
  regular row or grid can also use `pattern_linear`. A simple hole can't
  be through all in SolidWorks: it is made blind through the part, and the
  reply says so.
- **A thread on a shaft or a plain hole:** make the round feature first,
  then `add_cosmetic_thread` with a point on its circular edge. Tapped
  holes already carry their thread.
- **A box or a housing:** model the solid, then `create_shell` with a
  point on the face to open. Add stiffeners with `create_rib`: sketch an
  open line where the rib goes, close the sketch, pass its name.
- **Moulded walls:** `add_draft` with a point on each wall and on the face
  the draft pivots on.
- **Following an existing edge:** in an open sketch, `sketch_convert_entities`
  copies edges (or a face's outline) exactly; cut or extrude from that
  sketch instead of re-drawing the edge at guessed coordinates.

## Sheet metal (a bracket, a cover)

1. `create_part`, `create_sketch` on a plane, `add_rectangle` (or an open
   line or L for a bent profile), `exit_sketch`.
2. `create_base_flange` with `thickness`, `bend_radius` and `k_factor`
   (`depth` for an open profile).
3. `add_edge_flange` with a point on the edge and a `length` measured from
   that edge.
4. For a bend across a face: `create_sketch` with `face_point`, `add_line`,
   `exit_sketch`, then `create_sketched_bend`. SolidWorks keeps one side
   fixed; read the reply's box to see which.
5. `set_flat_pattern` with `flat: true` gives the blank's size; check it,
   `export_flat_pattern` for the DXF, then `flat: false` to fold it back.

## Changing an existing model

1. `open_model`, then `list_features` and `list_model_dimensions`.
2. `set_dimension` with the full name (e.g. "D1@Boss-Extrude1") and the new
   value in mm.
3. `rebuild_model`: an error names each failing feature and how to fix it.
4. `verify_model` with the new expected size.

To turn a feature off without deleting it, `suppress_feature`. After
`delete_feature`, call `list_features`: dependents may have gone too.

## Variants of one part (configurations)

1. `create_configuration` with a name (`Long`); the active one doesn't change.
2. `set_dimension` or `suppress_feature` with `configurations: ["Long"]`
   changes only `Long`; `"all"` changes every one. Without it, only the
   active configuration changes.
3. `activate_configuration` to look at a variant; `get_dimension` reads the
   active one.

## Starting every part the same way (a template)

1. `create_part`, then set it up: `set_units`, `set_material`,
   `set_custom_property` (company, drawn by). Add no features if only the
   settings should carry over.
2. `save_as_template` with a `name` (it goes in SolidWorks' template folder
   and shows in File > New) or a `file_path` ending in `.prtdot`.
3. `create_part` with `template` set to the reply's `file_path`: the new part
   starts with those units, material and properties.

## An assembly

1. Save each part first (`save_file`): `insert_component` takes a file path.
2. `create_assembly`, then `insert_component` for each part, with a
   position in mm.
3. `list_components` for the instance names (e.g. "plate-1").
4. `add_mate` between components. Each side is a reference plane or axis
   name (`entity_a`: "Front Plane", "Axis1") or a face (`face_a`: a point on
   it, in mm, in that part's own coordinates, as you modelled it). A pin in a
   hole: `concentric`, a point on the pin's round face and one on the hole's
   wall.
   The first part inserted is fixed. To let mates move it, or to hold a part
   still, use `set_component_state` (`fixed`); to let a sub-assembly's own
   mates move in the main assembly (a crank that turns), `flexible: true`.
5. `check_interference`, then `verify_model` with `component_count`,
   `mate_count` and `no_interference: true`.
6. `save_file`, or `pack_and_go_assembly` for a self-contained folder.

## A drawing

The whole drawing in one call: `generate_drawing_package` with the saved
model's `model_path`. It makes an A3 drawing with views, dimensions, title
block and notes, checks nothing overlaps, and saves it with a PDF.

Step by step instead:

1. `create_drawing`, then `create_drawing_view` for each view.
2. `insert_model_dimensions`, then `arrange_dimensions` (it reports any
   overlap it couldn't clear; `set_sheet_scale` gives more room).
3. `auto_center_marks`, `add_note`, and for an assembly `insert_bom_table`.
4. `check_drawing`, then fix what it finds.
5. `save_file` with a `.slddrw` path, and `export_pdf`.

Finishing a drawing: `create_section_view` (a line across a view, in sheet
mm) and `create_detail_view` (a circle in a view, at a scale) add views;
`add_dimension` picks edges by sheet points and replies with the value;
`update_title_block` changes the revision and other fields;
`update_sheet_format` moves to a bigger sheet, keeping the views. Read the
views' outlines from `check_drawing` to work out the points.

## Exporting

`export_step`, `export_stl` and the other `export_*` tools write the active
document; the file extension decides the format, so name it to match.
`export_image` saves a picture in a chosen view: useful to show the user the
result.
