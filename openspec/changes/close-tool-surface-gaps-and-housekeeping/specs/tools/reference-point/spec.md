## Purpose

Lets a caller create a reference point — the one reference-geometry
primitive left after plane/axis shipped in PR #69.

## ADDED Requirements

### Requirement: Reference point can be created at a vertex, along a curve, or at a sketch point
The adapter SHALL expose `create_reference_point`, supporting three
placement modes: at an existing vertex, along an existing curve/edge (by
percent-of-length or fixed distance from an endpoint), or at an existing
sketch point. Each SHALL add a reference point feature and return its
name.

#### Scenario: Point at a vertex
- **WHEN** `create_reference_point` is called with a reference to an
  existing vertex
- **THEN** a reference point is added at that vertex and its name is
  returned

#### Scenario: Point along an edge
- **WHEN** `create_reference_point` is called with a reference to an
  existing edge and either a percentage or a fixed distance from an
  endpoint
- **THEN** a reference point is added at the corresponding location and
  its name is returned

#### Scenario: Point at a sketch point
- **WHEN** `create_reference_point` is called with a reference to an
  existing sketch point
- **THEN** a reference point is added at that location and its name is
  returned

### Requirement: Reference point creation fails clearly on an unresolvable reference
`create_reference_point` SHALL return a failed `AdapterResult` — not raise
an unhandled exception — when the given vertex, edge, or sketch point
can't be resolved.

#### Scenario: Reference cannot be resolved
- **WHEN** `create_reference_point` is called with a reference that
  doesn't resolve to an existing vertex, edge, or sketch point
- **THEN** the response status indicates failure and nothing is created
