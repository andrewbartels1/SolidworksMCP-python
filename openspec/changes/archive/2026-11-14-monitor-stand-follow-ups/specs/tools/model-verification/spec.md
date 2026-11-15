## MODIFIED Requirements

### Requirement: Feature count counts modelling features only
`feature_count` SHALL count the document's own unsuppressed features, and
excludes:
- sketches;
- the origin;
- folder entries;
- the three default reference planes, which are the first three reference
  planes in tree order, whatever their names;
- the mate group.

A reference plane the agent made SHALL be counted. The agent can then
predict the number from the features it created.

#### Scenario: Part with two extrudes and a fillet
- **WHEN** a part's tree holds the default entries, two sketches, two
  extrudes and one fillet
- **THEN** the measured feature count is 3

#### Scenario: A part with a plane the agent made
- **WHEN** a part holds an extrude, `Plane1` offset from Top Plane, and a
  cut sketched on `Plane1`
- **THEN** the measured feature count is 3, and the counted features are
  the extrude, `Plane1` and the cut, never `Front Plane`
