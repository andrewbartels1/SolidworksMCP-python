---
name: solidworks-mcp
description: How to build and check SolidWorks parts, assemblies and drawings with the SolidWorks MCP server's tools. Use whenever you call its tools (create_part, create_sketch, create_extrusion, verify_model, generate_drawing_package and the rest), plan a CAD model, or recover from one of its errors.
---

# Using the SolidWorks MCP server

These tools drive a real SolidWorks session through its API. Each tool's own
description says what it does and what it needs; this skill covers what
spans tools: the order to call them in, units, choosing faces and edges,
checking the result, and what doesn't work yet.

## Before anything

- Call `get_model_info` first. It says which document is active (it follows
  a switch the user made in the SolidWorks window). `list_open_documents`
  lists every open document; `activate_document` switches.
- Call tools one at a time and wait for each result. The server pauses
  after every SolidWorks call on purpose: driving SolidWorks back-to-back
  crashes it.

## The build order

A solid feature always comes from a closed sketch:

1. `create_part` (or `open_model` for an existing file).
2. `create_sketch` on a plane: "Front", "Top", "Right", or a plane from
   `create_reference_plane`. Pass `sketch_name` to name it; the name is
   given when `exit_sketch` closes it, and that reply has the final name.
3. Draw: `add_rectangle`, `add_circle`, `add_line`, `add_arc`, `add_polygon`,
   and so on. For a revolve, add the axis with `add_centerline` in this
   sketch, or make a reference axis with `create_axis`.
4. `exit_sketch`.
5. The feature: `create_extrusion` (add material), `create_cut_extrude`
   (remove it), `create_revolve`, `create_sweep`, `create_loft`.
   Each takes `sketch_name`; without it, the sketch you closed last is
   used. `create_revolve` turns about the sketch's centreline, or about
   the reference axis `axis_entity` names.
6. Then edge treatments: `select_face_edges`, then `add_fillet` or
   `add_chamfer` with empty `edge_names`.
7. Finish with `verify_model` (see "Check the result").
8. `set_material`, then `save_part` with a `file_path`.

Repeat 2-5 for each feature. For holes in a ring or a row, draw every
circle in one sketch (`sketch_circular_pattern`, `sketch_linear_pattern`)
and cut once: `pattern_circular` and `mirror_feature` can't repeat a cut yet.

Worked sequences for parts, assemblies and drawings:
[references/workflows.md](references/workflows.md).

## Units

Inputs are millimetres and degrees, with two exceptions that take metres:
the `"x,y,z"` and `"face:x,y,z"` point specs in `add_fillet` and
`add_chamfer` `edge_names`, and every coordinate and result of
`measure_entities`. When a field's description says metres, believe it.
Details and the model axes: [references/selection-and-units.md](references/selection-and-units.md).

## Choosing faces and edges

- To treat the edges of one face, use `select_face_edges` (by `side`, a
  `point` in mm, or a `plane`), then `add_fillet` or `add_chamfer` with empty
  `edge_names`. Do it right before the fillet: anything that rebuilds or
  selects in between (including `calculate_mass_properties`) clears the
  selection.
- If the user says "this face" or "these edges", call
  `get_selected_entities` to read what they clicked rather than guessing.
- A point on an edge where two faces meet can pick the wrong edge; give a
  point inside a face (`"face:x,y,z"`) instead.

## Check the result

A tool returning `status: success` means SolidWorks accepted the call, not
that the geometry is what you meant. After a feature:

- `create_extrusion`, `create_revolve` and `create_cut_extrude` return
  `measured_change` (volume and bounding box before and after). A cut whose
  volume didn't drop, or an extrusion whose box didn't grow as planned, is
  wrong even though it succeeded.
- At the end, call `verify_model` with what you expect: `bounding_box_mm`,
  `volume_mm3`, `mass_kg`, `feature_count`, `solid_body_count`, and for an
  assembly `component_count`, `mate_count`, `no_interference`. Work out the
  expected values before building. A `fail` verdict still has
  `status: success`; read `verdict`.
- For one size, `measure_entities` or `get_dimension`.

## When something fails

Every error carries `error_type` and a `hint`; follow the hint. The common
ones, and `rebuild_model`, `undo` and what to tell the user:
[references/errors-and-limits.md](references/errors-and-limits.md).

## What doesn't work yet

- Every tool has a support level, in its tags (`level:stable`, `level:beta`,
  `level:experimental`, `level:planned`). A beta tool works but has a known
  gap, and an experimental one hasn't been checked on real SolidWorks: their
  description opens with "Beta: ..." or "Experimental: ...", and a successful
  result carries the same sentence as `warning`. Read it, and check the
  result (`verify_model`, `list_features`) before building on it.
- 40 tools are planned: registered, but nothing implements them. Their
  description says "Not available yet" and every call returns
  `not_supported`. Use the tool their description names instead.
- Some tools ignore some of their inputs, and a few behave in ways you must
  work around. The list, with the workaround for each:
  [references/errors-and-limits.md](references/errors-and-limits.md).

## When to write VBA instead

Only when no tool does the job (a shell, an option a tool doesn't expose):
[references/vba-fallback.md](references/vba-fallback.md). The `generate_vba_*`
tools return macro text for the user to run; they don't change the model.
