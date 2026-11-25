## ADDED Requirements

### Requirement: The hole is exactly at its point
The first hole of `create_hole` SHALL have its axis through `face_point`
within 0.001 mm, whatever point the face's pick landed on. When the hole
can't be moved there, it SHALL be removed and the call SHALL fail, naming how
far off it is.

#### Scenario: A hole the pick put 0.04 mm off
- **WHEN** a Ø6 simple hole is made at (-20, 20, -12) mm on the top face of a
  60 x 40 x 20 mm block, and SolidWorks puts it where the pick landed
- **THEN** the hole's axis is at x = -20 mm, z = -12 mm within 0.001 mm and
  its radius is 3 mm
