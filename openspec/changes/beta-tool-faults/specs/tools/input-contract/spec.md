## Purpose

A tool's input schema is a promise: every field it advertises changes what the
tool does, and an input the tool no longer takes is refused, not ignored.

## ADDED Requirements

### Requirement: Advertised inputs are honoured

Every field in a stable tool's input schema SHALL change what the tool does or
what it reports. A tool SHALL NOT echo back an input it didn't apply.

#### Scenario: An input the tool applies
- **WHEN** an agent calls `create_part` with `material: "AISI 304"`
- **THEN** the new part's material is AISI 304, and the reply says so

#### Scenario: No echo of an unapplied input
- **WHEN** a tool's reply names a value the agent passed
- **THEN** that value is what SolidWorks now holds, not only what was asked for

### Requirement: Removed inputs are refused with a pointer

When a call sends an input the tool no longer takes, the tool SHALL return
`status: "error"` with `error_type: "invalid_input"` before anything changes in
SolidWorks. The message SHALL name the input and say which tool or input to use
instead. The removed inputs are:

- `create_extrusion.direction` → `end_condition`
- `create_revolve.direction` → `both_directions`
- `create_assembly.components` → `insert_component`
- `create_drawing.model_path` and `create_drawing.sheet_format` →
  `create_drawing_view` or `generate_drawing_package`
- `create_technical_drawing.template`, `.sheet_size`, `.title` and
  `.output_path` → `generate_drawing_package`
- `save_file.force_save` → none: the tool always saves
- `check_interference.tolerance` and `.check_all_components` → none: the
  check has no tolerance and always covers the whole assembly, or the
  `components` given
- `export_step.options`, `export_iges.options`, `export_stl.options`,
  `export_pdf.options` and `export_dwg.options` → the file extension
- `calculate_mass_properties.model_path`, `.units`, `.include_hidden` and
  `.reference_coordinate_system` → open and activate the model first

#### Scenario: A removed input is sent
- **WHEN** an agent calls `create_assembly` with `components: ["a.sldprt"]`
- **THEN** the reply is an `invalid_input` error naming `components` and `insert_component`, and no assembly is created

#### Scenario: An operation the tool doesn't do
- **WHEN** an agent calls `add_drawing_view` with `operation: "remove"`
- **THEN** the reply is an `invalid_input` error saying the tool only adds views, and the drawing is unchanged

### Requirement: Interference checks follow include_hidden

`check_interference` SHALL leave hidden components out of the check unless
`include_hidden` is on.

#### Scenario: A hidden component overlaps
- **WHEN** two components overlap and one is hidden
- **THEN** the check finds no interference by default, and finds one with `include_hidden: true`

### Requirement: get_material reports the density

`get_material` SHALL return the active part's material density in kg/m³ beside
its name and library, or `null` when no material is assigned.

#### Scenario: A steel part
- **WHEN** an agent reads the material of a part assigned AISI 304
- **THEN** the reply gives the name AISI 304 and the density SolidWorks holds for it, 8,000 kg/m³

### Requirement: The hole tutorial teaches the cut tool

`sketch_tutorial_simple_hole` SHALL tell the agent to make the hole with
`create_cut_extrude`, never with a negative-depth extrusion.

#### Scenario: Reading the tutorial
- **WHEN** an agent calls `sketch_tutorial_simple_hole`
- **THEN** its steps call `create_cut_extrude` for the hole and none passes a negative `depth`
