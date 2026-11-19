# tools/sketch-slots Specification

## Purpose
TBD - created by archiving change sketch-essentials. Update Purpose after archive.
## Requirements
### Requirement: Straight and arc slots
`add_slot` SHALL take `kind` (`straight`, the default, or `arc`) and
`width` (mm, above 0). A straight slot SHALL take `start` and `end`, its two
arc centres as `[x, y]` in sketch mm. An arc slot SHALL take `center`, the
centre of the arc it follows, and `start` and `end` on that arc, going
counter-clockwise. With a sketch open, it SHALL draw the slot as one closed
profile and reply with its id, centres, width and area.

#### Scenario: A straight slot cut through a plate
- **WHEN** a straight slot from `[-40, -15]` to `[-40, 15]`, 10 mm wide,
  is cut through an 8 mm plate
- **THEN** the plate loses `8 * (30 * 10 + pi * 25)` mm³, and the reply's
  area is `30 * 10 + pi * 25`

#### Scenario: An arc slot
- **WHEN** an arc slot about `[25, 0]` from `[39.142, -14.142]` to
  `[39.142, 14.142]`, 8 mm wide, is cut through the plate
- **THEN** the plate loses 8 mm times the slot's area: the centreline's arc
  length (a quarter of a 20 mm radius circle) times 8, plus a 4 mm radius
  circle for the two rounded ends

### Requirement: Missing points fail
`add_slot` SHALL fail with `invalid_input` when no sketch is open, when a
point its `kind` needs is missing, or when `start` and `end` are the same,
and nothing SHALL be drawn.

#### Scenario: An arc slot without its centre
- **WHEN** `add_slot` is called with `kind` `arc` and no `center`
- **THEN** it fails with `invalid_input` naming `center`

