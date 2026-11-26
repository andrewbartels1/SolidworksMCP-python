## MODIFIED Requirements

### Requirement: The revolve axis can be a reference axis

`create_revolve` with `axis_entity` naming a reference axis SHALL revolve about
that axis. With `axis_entity` set to the id `add_centerline` or `add_line`
returned for a line of the revolved sketch, it SHALL revolve about that line.
Without `axis_entity`, it SHALL revolve about the centreline drawn in the
sketch. Any other `axis_entity` SHALL fail before anything is built.

#### Scenario: Revolving about Axis1
- **WHEN** a sketch holds a 10 × 20 mm rectangle 5 mm from `Axis1`, with no centreline, and an agent revolves it 360° about `axis_entity: "Axis1"`
- **THEN** the body is a tube with volume π·(15² − 5²)·20 = 12,566.4 mm³ within 0.1 %

#### Scenario: Revolving about the sketch's centreline by its id
- **WHEN** a Front sketch holds a centreline from (0, -5) to (0, 45), whose id is `Centerline_1`, and a 10 × 40 mm rectangle from the origin, and an agent revolves it 360° about `axis_entity: "Centerline_1"`
- **THEN** the volume rises by π·10²·40 = 12,566.4 mm³ within 0.01 % and the bounding box is 20 × 40 × 20 mm

#### Scenario: A word is not an axis
- **WHEN** an agent revolves about `axis_entity: "centerline"`
- **THEN** the call fails before anything is built, saying `axis_entity` takes a sketch line's id or a reference axis
