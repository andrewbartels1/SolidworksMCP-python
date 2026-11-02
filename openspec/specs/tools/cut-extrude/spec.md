# tools/cut-extrude Specification

## Purpose
Lets an MCP caller cut material away with an extruded sketch profile. It
states which way each end condition cuts, how a one-way cut whose direction
finds no material recovers, and what the caller is told when nothing can be
cut.
## Requirements
### Requirement: A one-way cut removes material in one direction only
When `create_cut_extrude` is called with end condition `Blind` (the default)
or `ThroughAll`, and `both_directions` is not set, the adapter SHALL cut from
the sketch plane in one direction only. A Blind cut SHALL go `depth` mm; a
Through All cut SHALL go through the body. No material SHALL be removed on the
other side of the sketch plane. This SHALL hold on every supported SolidWorks
version.

#### Scenario: Blind cut from a sketch through the middle of the body
- **WHEN** a 20 x 20 x 10 mm block is centred on the Front Plane, a Ø4 mm
  circle is sketched on the Front Plane, and `create_cut_extrude` is called
  with `depth: 3.0`
- **THEN** the response has `status: "success"`, and the part volume drops by
  π × 2² × 3 ≈ 37.70 mm³ (to within 1e-6 relative)

#### Scenario: Through All one way from the middle of the body
- **WHEN** the same setup is cut with `end_condition: "ThroughAll"` and no
  `both_directions`
- **THEN** the volume drops by π × 2² × 5 ≈ 62.83 mm³ (half the block)

### Requirement: A one-way cut that finds no material tries the other direction
The cut SHALL first go in the requested direction: along the sketch plane's
normal, or against it when `reverse_direction` is true. If that builds no
feature, the adapter SHALL reselect the same sketch and cut once in the
opposite direction. When the opposite direction built the feature, the
adapter result's `parameters.direction_flipped` SHALL be true. The tool reply
SHALL then carry `cut_extrude.direction_flipped: true` and say so in
`message`. Otherwise `direction_flipped` SHALL be false.

#### Scenario: Hole from a plane at the edge of the body
- **WHEN** a 30 x 30 x 15 mm block is extruded up from the Top Plane, a
  Ø5.5 mm circle is sketched on the Top Plane, and `create_cut_extrude` is
  called with `depth: 6.0`
- **THEN** the response has `status: "success"`, the volume drops by
  ≈ 142.5 mm³, and `cut_extrude.direction_flipped` is true

#### Scenario: The requested direction works
- **WHEN** the blind cut from the middle of the body above succeeds in the
  requested direction
- **THEN** `cut_extrude.direction_flipped` is false

### Requirement: Through All both ways cuts both sides
`create_cut_extrude` with `ThroughAllBoth`, or with `ThroughAll` plus
`both_directions: true`, SHALL cut through the whole body on both sides of
the sketch plane.

#### Scenario: Through All both ways from the mid plane
- **WHEN** the mid-plane block and Ø4 mm circle are cut with
  `end_condition: "ThroughAllBoth"`, or with `"ThroughAll"` and
  `both_directions: true`
- **THEN** the volume drops by π × 2² × 10 ≈ 125.66 mm³, and the centre of
  mass stays on the sketch plane

### Requirement: A cut that builds nothing explains what was tried
When no attempted form builds a feature, the tool SHALL fail with
`error_type: "feature_not_built"`. The message SHALL name the sketch, the
forms tried (for a one-way cut, both directions) and the depth. It SHALL say
to check that the profile is closed and overlaps the body, or to use Through
All. The hint SHALL tell the caller to change the inputs rather than retry
the same call.

#### Scenario: Profile misses the body
- **WHEN** a one-way cut's profile removes no material in either direction
- **THEN** the payload has `status: "error"`,
  `error_type: "feature_not_built"`, and a message containing "tried: the
  requested direction; direction flipped"

