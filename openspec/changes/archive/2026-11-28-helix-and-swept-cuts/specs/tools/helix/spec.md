## ADDED Requirements

### Requirement: A helix from a base circle
`create_helix` SHALL make a helix (or a flat spiral) from a named sketch
that holds exactly one circle. The circle's diameter is the helix's
diameter and its centre is on the helix's axis, which is normal to the
sketch. The helix is defined by two of height, pitch and revolutions,
chosen by `defined_by`: `height_and_pitch` (the default),
`height_and_revolutions` or `pitch_and_revolutions`; `spiral` takes pitch
and revolutions and stays in the sketch's plane. Lengths are in mm and
angles in degrees. Options: `clockwise`, `reverse` (the other side of the
sketch), `start_angle`, and `taper_angle` with `taper_outward`.

The reply SHALL give the helix's name, its height, pitch and revolutions
(the two given and the one worked out from them), its diameter, its length,
and the point where it starts in model mm, so a profile can be drawn there.

#### Scenario: A helix by height and pitch
- **WHEN** a sketch holds a 20 mm circle and `create_helix` is called with
  `height` 48 and `pitch` 6
- **THEN** a helix is made, and the reply gives 8 revolutions, a 20 mm
  diameter, its length and its start point

#### Scenario: The values that define it are checked first
- **WHEN** `defined_by` is `height_and_revolutions` and `revolutions` is
  missing, or any of height, pitch or revolutions is zero or negative
- **THEN** the call fails as `invalid_input` naming the field, and nothing
  is made

#### Scenario: The base sketch must be one circle
- **WHEN** the named sketch doesn't exist, or holds anything other than
  exactly one circle
- **THEN** the call fails, saying what the sketch holds, and nothing is made

#### Scenario: A flat spiral
- **WHEN** `defined_by` is `spiral` with `pitch` 5 and `revolutions` 3
- **THEN** a spiral is made in the sketch's plane and the reply's height is 0
