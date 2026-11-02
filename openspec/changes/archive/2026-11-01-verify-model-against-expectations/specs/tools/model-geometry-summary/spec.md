## Purpose

Gives tools one side-effect-free read of the active document's overall size
and makeup (bounding box, solid bodies, volume, components, mates). Both
model verification and per-feature measured change are built on it.

## ADDED Requirements

### Requirement: Adapter exposes a geometry summary of the active document
The adapter interface SHALL expose `get_model_geometry_summary`. For a part
or an assembly, it returns:
- `document_type`;
- `volume_mm3`;
- `bounding_box_mm`, with `min`, `max` and `size` as `[x, y, z]` in mm;
- `bounding_box_method`;
- `solid_body_count`.

For an assembly it also returns `component_count` (top-level components) and
`mate_count`. Any value the adapter cannot determine is `null`, never a
guessed number.

#### Scenario: Summary of a single-body part
- **WHEN** the active document is a part with one solid block of
  100 × 50 × 10 mm
- **THEN** the summary reports `solid_body_count: 1`, a bounding-box size of
  about `[100, 50, 10]`, and a volume of about 50000 mm³

#### Scenario: Summary of an assembly
- **WHEN** the active document is an assembly with three top-level components
  and two mates
- **THEN** the summary reports `component_count: 3` and `mate_count: 2`

#### Scenario: Mock adapter has no geometry
- **WHEN** the mock adapter is active
- **THEN** `bounding_box_mm`, `volume_mm3` and `solid_body_count` are `null`.
  For an assembly, `component_count` and `mate_count` reflect the components
  inserted and mates added during the session.

### Requirement: The summary does not change the model or the selection
`get_model_geometry_summary` SHALL NOT force a rebuild, modify the document,
mark it dirty, or clear the user's current selection.

#### Scenario: Selection survives a summary read
- **WHEN** entities are selected and `get_model_geometry_summary` is called
- **THEN** the same entities are still selected afterwards

### Requirement: Unsupported documents fail clearly
The adapter SHALL return a failed result when there is no active document or
the active document is a drawing. Adapters that do not implement the read
SHALL return a failed result saying so.

#### Scenario: Drawing is active
- **WHEN** the active document is a drawing
- **THEN** the result is an error stating that a part or assembly is required
