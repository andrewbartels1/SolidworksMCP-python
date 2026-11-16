## Purpose

`create_hole` makes a standard Hole Wizard hole at a point on a flat face,
so the hole matches its fastener and a drawing can call it out.

## ADDED Requirements

### Requirement: A standard hole at a point on a face
`create_hole` SHALL take `hole_type` (`simple`, `counterbore`,
`countersink` or `tapped`), `standard` (`iso` or `ansi_inch`), `size` (for
example `M6`, `#10`), `end_condition` (`blind` or `through_all`), `depth`
in millimetres for `blind`, and `position`, `[x, y, z]` in millimetres on a
flat face of the active part. It SHALL make one Hole Wizard feature at that
point, normal to the face, and reply with the feature's name and
`measured_change`.

#### Scenario: A through M6 counterbore
- **WHEN** a 10 mm plate is active and `create_hole` is called with
  `counterbore`, `iso`, `M6`, `through_all` and a point on the top face
- **THEN** one Hole Wizard feature appears in the tree, the volume falls,
  and the reply names the feature

#### Scenario: A blind tapped hole
- **WHEN** `create_hole` is called with `tapped`, `iso`, `M5`, `blind` and
  `depth` 8
- **THEN** the hole is 8 mm deep (measured from the volume change within
  1 %), and its feature carries the M5 thread data

### Requirement: Bad hole inputs fail before SolidWorks
`create_hole` SHALL fail with `invalid_input` when `size` is not a size of
the given `standard` and `hole_type`, when `blind` has no `depth`, or when
`position` is not three numbers; nothing SHALL be added.

#### Scenario: A size from the wrong standard
- **WHEN** `standard` is `iso` and `size` is `#10`
- **THEN** the call fails with `invalid_input` listing the ISO sizes

### Requirement: The point must be on a flat face
When `position` is not on a flat face of the active part, `create_hole`
SHALL fail with `invalid_input`, name the point, and add nothing.

#### Scenario: A point in the air
- **WHEN** `position` is 50 mm above the plate
- **THEN** the call fails with `invalid_input` and the feature tree is
  unchanged

### Requirement: Several holes in one feature
`create_hole` SHALL take an optional `positions`, a list of further
`[x, y, z]` points in millimetres on the same face. The holes at
`face_point` and at every point of `positions` SHALL be one Hole Wizard
feature, each point a point of the hole's position sketch, as when holes are
placed on sketch points in SolidWorks' Hole Wizard. The reply SHALL give
`hole_count`.

#### Scenario: Three holes in one call
- **WHEN** `create_hole` is called with a `face_point` and two `positions`
  on the same face
- **THEN** one hole feature is added, its position sketch has three points,
  `hole_count` is 3, and the volume falls by three holes' worth

#### Scenario: A position off the face
- **WHEN** a point of `positions` is not on the face
- **THEN** the call fails naming the point, and the hole feature is removed

### Requirement: A simple hole through all
SolidWorks refuses `through_all` for a simple Hole Wizard hole (seen live on
SolidWorks 2026, every argument variant). `create_hole` SHALL then make the
simple hole blind, as deep as the part's bounding-box diagonal so it passes
through, and reply with `end_condition_used: "blind"`, the depth used, and a
warning that a part made thicker later needs the depth changed.

#### Scenario: A simple M6 hole through all
- **WHEN** `create_hole` is called with `simple`, `iso`, `Ø6.0` and
  `through_all` on a 20 mm block
- **THEN** the hole goes through the block, `end_condition_used` is `blind`,
  and the reply carries the warning
