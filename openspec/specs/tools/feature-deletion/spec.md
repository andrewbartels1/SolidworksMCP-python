# tools/feature-deletion Specification

## Purpose
What `delete_feature` reports, so an agent knows every feature that went,
including the dependent features SolidWorks removed along with the named one.
## Requirements
### Requirement: The reply names every feature removed

`delete_feature` SHALL return `removed_features`, the names of every feature
that was in the tree before the call and isn't after it. Its message SHALL
name the dependent features too.

#### Scenario: Deleting a sketch that a feature uses
- **WHEN** an agent deletes `Sketch2`, which `Cut-Extrude1` was built from
- **THEN** `removed_features` lists both `Sketch2` and `Cut-Extrude1`, and the message says the cut went with it

