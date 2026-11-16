# tools/sketch-convert-entities Specification

## Purpose
`sketch_convert_entities` copies model edges into the open sketch, so a new
feature can be drawn on the real geometry instead of a guessed copy of it.
## Requirements
### Requirement: Edges or a face outline into the open sketch
`sketch_convert_entities` SHALL take exactly one of `edge_points` (points
on edges of the active part) and `face_point` (a point on a face, whose
outer loop is converted), plus `construction` (default off). With a sketch
open, it SHALL add one sketch entity per converted edge and reply with the
new entities' ids, usable by `add_sketch_constraint` and
`add_sketch_dimension`.

#### Scenario: A face outline
- **WHEN** a sketch is open on a plate's top face and
  `sketch_convert_entities` is called with a point on that face
- **THEN** four lines are added, one per edge of the face, and their ids
  are returned

#### Scenario: Construction geometry
- **WHEN** `construction` is on
- **THEN** the converted entities are construction geometry, and a cut
  from the sketch uses only the other entities

### Requirement: No sketch or no edge fails
`sketch_convert_entities` SHALL fail with `invalid_input` when no sketch is
open, or when a point is not on an edge (or face) of the active part,
naming the point; nothing SHALL be added.

#### Scenario: No sketch open
- **WHEN** no sketch is open
- **THEN** the call fails with `invalid_input` saying to open a sketch with
  `create_sketch` first

