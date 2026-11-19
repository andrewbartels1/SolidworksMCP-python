# tools/sketch-corners Specification

## Purpose
TBD - created by archiving change sketch-essentials. Update Purpose after archive.
## Requirements
### Requirement: Round or bevel sketch corners picked by point
`add_sketch_fillet` SHALL take `corners` (one or more `[x, y]` in sketch mm)
and `radius` (mm, above 0). `add_sketch_chamfer` SHALL take `corners` and
`distance` (mm, above 0), with either `distance2` (two distances) or `angle`
(degrees, distance and angle), not both; `distance` alone SHALL make equal
distances. With a sketch open, each tool SHALL find the sketch point at
each corner (within 0.01 mm), round or bevel that corner on its own, trim
the entities either side back to it, and reply with one id per corner.

#### Scenario: A rectangle's corners rounded
- **WHEN** a 120 x 80 mm rectangle centred on the origin is drawn and
  `add_sketch_fillet` is called with `corners` `[[-60, -40], [-60, 40]]`
  and `radius` 10
- **THEN** both corners become 10 mm arcs, two ids are returned, and an
  8 mm extrusion of the profile is `8 * (9600 - 2 * 100 * (1 - pi / 4))`
  mm³

#### Scenario: Equal-distance chamfer
- **WHEN** `add_sketch_chamfer` is called on a rectangle corner with
  `distance` 10
- **THEN** the corner is cut by a line 10 mm along each side, removing
  50 mm² from the profile

### Requirement: A corner that isn't there changes nothing
Each tool SHALL fail with `invalid_input` when no sketch is open, when a
corner has no sketch point, when SolidWorks refuses a point that isn't where
two entities meet, or when `distance2` and `angle` are both given, naming the
corner or the fields; the sketch SHALL be unchanged.

#### Scenario: A point off the profile
- **WHEN** `add_sketch_fillet` is called with a corner at `[0, 0]` inside
  the rectangle
- **THEN** it fails with `invalid_input` naming `[0, 0]`, and no corner is
  rounded

#### Scenario: A sketch point that isn't a corner
- **WHEN** the rectangle was drawn from its centre, so `[0, 0]` is its
  centre point, and `add_sketch_fillet` is called there
- **THEN** SolidWorks refuses it, the tool fails with `invalid_input` saying
  the point isn't where two entities meet, and the part is unchanged

