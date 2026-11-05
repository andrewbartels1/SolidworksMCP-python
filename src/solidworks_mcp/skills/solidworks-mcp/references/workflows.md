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
    then `save_part` with a `file_path` ending in `.sldprt`.

## Sketching somewhere other than the three planes

`create_reference_plane` with `reference: "Top Plane"` and `offset: 10` makes
a plane 10 mm up; its name (e.g. "Plane1") goes into `create_sketch`. Angled
planes aren't supported yet.

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

Don't use `pattern_circular` on a cut: it reports an error unless the
volume grows.

## Changing an existing model

1. `open_model`, then `list_features` and `list_model_dimensions`.
2. `set_dimension` with the full name (e.g. "D1@Boss-Extrude1") and the new
   value in mm.
3. `rebuild_model`: an error names each failing feature and how to fix it.
4. `verify_model` with the new expected size.

To turn a feature off without deleting it, `suppress_feature`. After
`delete_feature`, call `list_features`: dependents may have gone too.

## An assembly

1. Save each part first (`save_part`): `insert_component` takes a file path.
2. `create_assembly`, then `insert_component` for each part, with a
   position in mm.
3. `list_components` for the instance names (e.g. "plate-1").
4. `add_mate` between components, by reference plane or axis name
   ("Front Plane", "Axis1"). Faces and edges can't be mated by these tools.
5. `check_interference`, then `verify_model` with `component_count`,
   `mate_count` and `no_interference: true`.
6. `save_assembly`, or `pack_and_go_assembly` for a self-contained folder.

## A drawing

The whole drawing in one call: `generate_drawing_package` with the saved
model's `model_path`. It makes an A3 drawing with views, dimensions, title
block and notes, checks nothing overlaps, and saves it with a PDF.

Step by step instead:

1. `create_drawing`, then `create_drawing_view` for each view.
2. `insert_model_dimensions`, then `arrange_dimensions` (it reports any
   overlap it couldn't clear; `set_sheet_scale` gives more room).
3. `auto_center_marks`, `add_note`, and for an assembly `insert_bom_table`.
4. `save_file` with a `.slddrw` path, and `export_pdf`.

## Exporting

`export_step`, `export_stl` and the other `export_*` tools write the active
document; the file extension decides the format, so name it to match.
`export_image` saves a picture in a chosen view: useful to show the user the
result.
