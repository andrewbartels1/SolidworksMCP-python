# tools/reference-plane Specification

## Purpose
TBD - created by archiving change ujoint-tool-gaps. Update Purpose after archive.
## Requirements
### Requirement: A plane at an angle about an axis

`create_reference_plane` SHALL make a plane at `angle` degrees to a reference plane or face, rotated about a named `axis`.

#### Scenario: 40 degrees about an axis
- **WHEN** an agent asks for a plane at 40° to the Top Plane about an axis lying in it
- **THEN** a new plane is added at 40° to the Top Plane, and its name comes back

#### Scenario: An angle with no axis
- **WHEN** `angle` is given without `axis`
- **THEN** the call fails with `invalid_input` and says an axis is needed

### Requirement: A plane from a face

`create_reference_plane` SHALL accept `face_point`, a point on a planar face in mm, as the reference in place of a named plane.

#### Scenario: Parallel to a sloped face
- **WHEN** an agent gives a point on a sloped face and an offset
- **THEN** a plane parallel to that face, offset by that distance, is added

