## ADDED Requirements

### Requirement: Trim the piece nearest a point
`sketch_trim` SHALL take `point`, `[x, y]` in sketch mm on the piece of an
entity to remove. With a sketch open, it SHALL remove that piece back to the
nearest places it meets other entities (the whole entity when it meets
none), and reply with the sketch's segment count before and after.

#### Scenario: A keyhole's inner arc trimmed
- **WHEN** a circle of radius 8 at `[0, 10]` meets two vertical lines at
  x = -3 and x = 3, and `sketch_trim` is called at `[0, 2]`
- **THEN** the circle's arc between the two lines is removed, and the
  sketch closes into one keyhole profile

### Requirement: Extend an entity to the next one
`sketch_extend` SHALL take `point`, `[x, y]` in sketch mm near the end of an
entity to lengthen. It SHALL extend that entity from its end nearest the
point until it meets the next entity, and reply with the segment counts.

#### Scenario: Lines extended up to a circle
- **WHEN** a vertical line from `[-3, -15]` to `[-3, 0]` stops below a
  circle of radius 8 at `[0, 10]`, and `sketch_extend` is called at
  `[-3, -0.5]`
- **THEN** the line ends on the circle, at y = 10 - sqrt(55)

### Requirement: Nothing under the point changes nothing
Both tools SHALL fail with `invalid_input` when no sketch is open or no
entity is at the point, or when SolidWorks refuses the trim or extension,
naming the point; the sketch SHALL be unchanged.

#### Scenario: Empty space
- **WHEN** `sketch_trim` is called at a point no entity passes through
- **THEN** it fails with `invalid_input` naming the point
