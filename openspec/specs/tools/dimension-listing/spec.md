# tools/dimension-listing Specification

## Purpose
`list_model_dimensions` lists every dimension in the active part or assembly
once, under the feature that owns it, so an agent can find a dimension by
name before reading or changing it.
## Requirements
### Requirement: Every dimension is listed with no feature name
`list_model_dimensions` with no `feature_name` SHALL return every dimension
of every feature in the active part or assembly: sketch dimensions, feature
dimensions such as an extrude's depth, and reference-plane offsets. It SHALL
return the same dimensions the per-feature calls return, together.

#### Scenario: The monitor stand
- **WHEN** a part holds an extrude, two cuts, a fillet, `Plane1` and a cut
  sketched on `Plane1`, and `list_model_dimensions` is called with no
  `feature_name`
- **THEN** the result holds each dimension that a call naming each feature
  in turn returns, and no fewer

### Requirement: Each dimension is listed once, under its own feature
Each dimension SHALL appear once in the result, and its `feature` SHALL be
the feature its `full_name` names after the `@`.

#### Scenario: A plane's offset seen from the cut on it
- **WHEN** a cut is sketched on `Plane1`, and SolidWorks also reports
  `D1@Plane1` among the cut's dimensions
- **THEN** `D1@Plane1` appears once, with `feature` `Plane1`

#### Scenario: Asking for one feature
- **WHEN** `list_model_dimensions` is called with `feature_name` `Cut-Extrude3`
- **THEN** only dimensions whose `full_name` ends in `@Cut-Extrude3` (or its
  sketch's own name, for a sketch) are returned, not `D1@Plane1`

