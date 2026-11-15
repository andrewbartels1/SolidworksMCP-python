## Purpose

`create_sketch` opens a sketch on a flat face of the body, given a point on
that face, so a feature can follow the face when the model's dimensions
change.

## ADDED Requirements

### Requirement: A sketch opens on the flat face at a point
`create_sketch` SHALL accept `face_point`, `[x, y, z]` in millimetres in
model coordinates, in place of `plane`. It SHALL open the sketch on the flat
face of the active part at that point, and reply with the sketch's name
as it does for a plane.

#### Scenario: Sketching on the top face
- **WHEN** a part has a 20 mm tall block whose top face is at y = 20 mm, and
  `create_sketch` is called with `face_point` `[0, 20, 0]`
- **THEN** a sketch opens on that face, and a cut drawn there and extruded
  3 mm leaves the block 3 mm lower at the cut

#### Scenario: The sketch follows the face
- **WHEN** the block's height is changed afterwards and the model rebuilt
- **THEN** the sketch, and the cut made from it, move with the top face

### Requirement: Exactly one of plane and face_point
`create_sketch` SHALL fail with `invalid_input` when both `plane` and
`face_point` are given, or neither, or `face_point` does not have three
numbers.

#### Scenario: Both given
- **WHEN** `create_sketch` is called with `plane` `Top` and a `face_point`
- **THEN** the call fails with `invalid_input`, and nothing is opened

### Requirement: A point that is not on a flat face fails
When `face_point` is not on a face of the active part, or is on a curved
face, `create_sketch` SHALL fail with `invalid_input`, name the point, and
open no sketch.

#### Scenario: A point in the air
- **WHEN** `face_point` is 50 mm above the part
- **THEN** the call fails with `invalid_input` naming the point, and no
  sketch is open afterwards

#### Scenario: A point on a fillet
- **WHEN** `face_point` lies on a filleted (curved) face
- **THEN** the call fails with `invalid_input` saying the face is not flat
