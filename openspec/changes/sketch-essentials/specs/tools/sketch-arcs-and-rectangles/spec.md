## ADDED Requirements

### Requirement: Three ways to draw an arc
`add_arc` SHALL take `kind`: `center` (the default: `center`, `start` and
`end`, as today), `three_point` (`start`, `end`, and `through_x`/`through_y`,
a point the arc passes through) or `tangent` (`start`, the end of an
existing entity, and `end`; the arc leaves tangent to that entity). It
SHALL reply with the arc's id and points.

#### Scenario: A stadium window from lines and arcs
- **WHEN** a line runs from `[-20, 25]` to `[10, 25]`, a tangent arc from
  `[10, 25]` to `[10, 35]`, a line back to `[-20, 35]`, and a three-point
  arc from `[-20, 35]` to `[-20, 25]` through `[-25, 30]`
- **THEN** the profile is closed, and cutting it through an 8 mm plate
  removes `8 * (30 * 10 + pi * 25)` mm³

#### Scenario: A missing field
- **WHEN** `kind` is `three_point` and `through_x` is missing
- **THEN** it fails with `invalid_input` naming `through_x`

### Requirement: A rectangle from its centre
`add_rectangle` with `from_center` on SHALL take `x1`, `y1` as the centre
and `x2`, `y2` as a corner, and draw the rectangle centred there. The reply's
`corner1` and `corner2` SHALL be its real opposite corners and `width` and
`height` its full size.

#### Scenario: A plate centred on the origin
- **WHEN** `add_rectangle` is called with `from_center`, `x1` 0, `y1` 0,
  `x2` 60, `y2` 40
- **THEN** the rectangle runs from `[-60, -40]` to `[60, 40]`, and the reply
  gives width 120 and height 80
