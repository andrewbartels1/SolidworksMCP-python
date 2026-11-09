## ADDED Requirements

### Requirement: The named sketch is the one used

`create_extrusion` and `create_revolve` SHALL use the sketch `sketch_name`
names, found in the feature tree without regard to case. When the name matches
no sketch, the call SHALL fail before anything is built, and the message SHALL
list the sketches that exist. When `sketch_name` is empty, they SHALL use the
sketch the session closed last, as `create_cut_extrude` does.

#### Scenario: Extruding an earlier sketch
- **WHEN** a part has `Sketch1` (a 20 mm square) and `Sketch2` (a Ø10 circle), both closed, and an agent extrudes `sketch_name: "Sketch1"` 5 mm
- **THEN** the new body is 20 × 20 × 5 mm, 2,000 mm³

#### Scenario: A sketch that doesn't exist
- **WHEN** an agent extrudes `sketch_name: "Sketch9"`
- **THEN** the call fails, naming `Sketch1` and `Sketch2`, and the feature tree is unchanged

### Requirement: The revolve axis can be a reference axis

`create_revolve` with `axis_entity` naming a reference axis SHALL revolve about
that axis. Without `axis_entity`, it SHALL revolve about the centreline drawn
in the sketch.

#### Scenario: Revolving about Axis1
- **WHEN** a sketch holds a 10 × 20 mm rectangle 5 mm from `Axis1`, with no centreline, and an agent revolves it 360° about `axis_entity: "Axis1"`
- **THEN** the body is a tube with volume π·(15² − 5²)·20 = 12,566.4 mm³ within 0.1 %
