## ADDED Requirements

### Requirement: A feature SolidWorks accepted but did not build is named
When an adapter reports that SolidWorks accepted a feature call but built no
feature, the tool SHALL return `error_type: "feature_not_built"`. Its hint
SHALL say that the geometry gave SolidWorks nothing to build, and that the
caller should change the sketch, its plane, the depth or the end condition
rather than retry the same call.

#### Scenario: A cut builds nothing
- **WHEN** the adapter error reads "SolidWorks built no feature from sketch 'Sketch2' (tried: the requested direction; direction flipped ...)"
- **THEN** the payload has `error_type: "feature_not_built"` and a hint telling the caller to change the inputs rather than retry
