## ADDED Requirements

### Requirement: Make entities construction geometry, or normal again
`set_construction_geometry` SHALL take `entities` (sketch entity ids) and
`construction` (default on). It SHALL set every segment of every entity to
construction geometry, or back to normal, read each back, and reply with the
ids and their state. Setting an entity to the state it is already in SHALL
succeed and change nothing.

#### Scenario: A reference line left out of a cut
- **WHEN** a line across the plate is made construction geometry and the
  sketch is cut through the plate
- **THEN** the cut uses only the closed profiles, and the plate loses only
  their area times its thickness

#### Scenario: Unknown id
- **WHEN** an id was never returned by a sketch tool
- **THEN** it fails with `invalid_input` naming the id, and no entity
  changes

### Requirement: `construction` is honoured when drawing
`add_line`, `add_circle` and `add_rectangle` with `construction` on SHALL
draw construction geometry on SolidWorks, as their replies say.

#### Scenario: A construction line from add_line
- **WHEN** `add_line` is called with `construction` on and the sketch is
  cut
- **THEN** the line is construction geometry and doesn't change the cut
