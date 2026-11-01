## Purpose

Lets an MCP caller cut material away with an extruded sketch profile. It
states which way each end condition cuts, and that a cut works wherever its
sketch sits: on a face or inside the body.

## ADDED Requirements

### Requirement: A blind cut removes material in one direction only
When `create_cut_extrude` is called with end condition `Blind` (the default)
and a `depth`, the adapter SHALL cut from the sketch plane by `depth` in
one direction only. `reverse_direction` SHALL choose which side. No material
SHALL be removed on the other side of the sketch plane. This SHALL hold on
every supported SolidWorks version.

#### Scenario: Blind cut from a sketch inside the body
- **WHEN** a 20 x 20 x 10 mm block is centred on the Front Plane, a Ø4 mm
  circle is sketched on the Front Plane, and `create_cut_extrude` is called
  with `depth: 3.0`
- **THEN** the response has `status: "success"`, and the part volume drops
  by π × 2² × 3 ≈ 37.70 mm³ (to within 1e-6 relative)

#### Scenario: Blind cut from a sketch on a face
- **WHEN** a Ø5.5 mm circle is sketched on the top face of a
  30 x 30 x 15 mm block, and `create_cut_extrude` is called with
  `depth: 6.0`
- **THEN** the response has `status: "success"`, and the part volume drops
  by ≈ 142.5 mm³

### Requirement: Through All cuts one way unless asked for both
`create_cut_extrude` with end condition `ThroughAll` SHALL cut through the
whole body in one direction. With `ThroughAllBoth`, or with `ThroughAll`
plus `both_directions: true`, it SHALL cut through the whole body in both
directions.

#### Scenario: Through All both ways from the mid plane
- **WHEN** the same mid-plane block and Ø4 mm circle are cut with
  `end_condition: "ThroughAllBoth"`
- **THEN** the volume drops by π × 2² × 10 ≈ 125.66 mm³, and the centre of
  mass stays on the sketch plane

#### Scenario: Through All one way from the mid plane
- **WHEN** the same setup is cut with `end_condition: "ThroughAll"` and no
  `both_directions`
- **THEN** the volume drops by π × 2² × 5 ≈ 62.83 mm³ (half the block's
  thickness)
