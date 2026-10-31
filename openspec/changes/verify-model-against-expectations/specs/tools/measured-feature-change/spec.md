## Purpose

Lets an agent check each solid feature against its plan as it builds. The
extrude, revolve and cut tools report the volume and size change they
actually produced, so a feature SolidWorks silently ignored is visible at once.

## ADDED Requirements

### Requirement: Solid feature tools report the measured change
On success, `create_extrusion`, `create_revolve` and `create_cut_extrude`
SHALL include a `measured_change` block. It reports, read before and after
the feature:
- `volume_before_mm3`, `volume_after_mm3` and `volume_delta_mm3`;
- `bounding_box_before_mm` and `bounding_box_after_mm` as size `[x, y, z]`;
- `solid_body_count_before` and `solid_body_count_after`.

#### Scenario: Extrude adds material
- **WHEN** `create_extrusion` extrudes a 20 × 20 mm square 10 mm onto an empty
  part
- **THEN** `measured_change.volume_delta_mm3` is about 4000 and the
  bounding-box size after is about `[20, 20, 10]`

#### Scenario: Cut removes nothing
- **WHEN** `create_cut_extrude` succeeds but removes no material
- **THEN** `measured_change.volume_delta_mm3` is 0 and the reply carries a
  `warning` saying the feature changed no volume

### Requirement: Measurement never fails the feature
The measured change SHALL be best-effort. If either read fails or the
adapter does not support it, the feature tool still returns its normal
success reply, with `measured_change` either absent or holding `null` values
plus a `note`. Existing keys in the reply are unchanged.

#### Scenario: Adapter cannot measure
- **WHEN** the active adapter does not implement the geometry summary
- **THEN** the feature tool's reply is the same as before this change, apart
  from no `measured_change` key

#### Scenario: Mock adapter
- **WHEN** the mock adapter is active
- **THEN** `measured_change` is present with `null` volumes and sizes and a
  note that they are not determinable
