# tools/dimension-reading Specification

## Purpose
`get_dimension` reads a dimension's value in the unit its type gives it: millimetres for a length, degrees for an angle, and no unit for a count.

## Requirements
### Requirement: A dimension is read in the unit its type gives it

`get_dimension` SHALL report a length dimension in millimetres with
`units: "mm"`, an angle dimension in degrees with `units: "deg"`, and a
count (such as a pattern's instance count) as a plain number with
`units: null`. The unit SHALL come from the dimension's own type, never be
assumed. A dimension whose value can't be read SHALL fail rather than return
a guessed number.

#### Scenario: A length
- **WHEN** a part has a 10 mm extrusion and an agent reads `D1@Boss-Extrude1`
- **THEN** the reply's `dimension` is `value: 10.0`, `units: "mm"`

#### Scenario: An angle
- **WHEN** a part has a revolve of 270° and an agent reads its angle dimension
- **THEN** the reply's `dimension` is `value: 270.0`, `units: "deg"`

#### Scenario: A name that doesn't exist
- **WHEN** an agent reads `D9@Sketch1` on a part that has no such dimension
- **THEN** the call fails with `not_found`, and the message points to `list_model_dimensions`

