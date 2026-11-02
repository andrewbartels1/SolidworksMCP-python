## Purpose

Lets an agent confirm in one call that the active part or assembly matches
what it meant to build: measured values compared against expectations, with a
pass/fail result per check and an overall verdict.

## ADDED Requirements

### Requirement: verify_model reads the active document back against optional expectations
The server SHALL expose a `verify_model` tool. Every expectation is optional:
- `mass_kg` and `volume_mm3`, compared within `relative_tolerance`, a fraction
  that defaults to 0.01;
- `bounding_box_mm` as `[x, y, z]` extents, compared per axis within
  `length_tolerance_mm`, which defaults to 0.1;
- `feature_count` and `solid_body_count`, compared exactly;
- for assemblies, `component_count` and `mate_count` (exact) and
  `no_interference` (boolean).

Each check runs only when its expectation is given.

#### Scenario: Part matches every expectation
- **WHEN** `verify_model` is called on a part whose measured volume, bounding
  box, feature count and solid-body count all fall within tolerance of the
  given expectations
- **THEN** the response has `status: "success"`, `verdict: "pass"`, and one
  check entry per given expectation, each with `passed: true`

#### Scenario: One expectation is out of tolerance
- **WHEN** the measured volume differs from `volume_mm3` by more than
  `relative_tolerance`
- **THEN** that check has `passed: false`, the verdict is `"fail"`, the
  message names the failing check, and `status` is still `"success"` (the
  tool worked; the model did not match)

#### Scenario: No expectations given
- **WHEN** `verify_model` is called with no expectations
- **THEN** the response has `verdict: "report_only"`, an empty `checks`
  list, and the full `measured` block

### Requirement: Every check reports expected, actual, tolerance and outcome
Each entry in `checks` SHALL carry `name`, `expected`, `actual`,
`tolerance` (null for exact checks), `unit`, and `passed`. `passed` is
`true`, `false`, or `null`; `null` means the value could not be measured, and
`note` then says why.

#### Scenario: Bounding box check reports per-axis values
- **WHEN** a `bounding_box_mm` expectation is given
- **THEN** its check entry reports the expected and measured `[x, y, z]`
  extents, and `passed` is `true` only if every axis is within
  `length_tolerance_mm`

### Requirement: Unmeasurable values never count as a pass
A check whose actual value cannot be determined SHALL report
`passed: null`, never `true`. The overall verdict SHALL be:
- `"fail"` if any check failed;
- otherwise `"inconclusive"` if any check is `null`;
- otherwise `"pass"`.

#### Scenario: Interference cannot be determined
- **WHEN** `no_interference: true` is expected and the adapter reports the
  interference result as not determinable (as the mock adapter does)
- **THEN** that check has `passed: null` with a note, and, with no other
  failures, the verdict is `"inconclusive"`

### Requirement: The response includes everything measured
The response SHALL include a `measured` block:
- document type;
- mass and volume;
- the bounding box and how it was measured;
- solid-body count;
- the names of the modelling features counted;
- for assemblies, component and mate counts.

Agents can then correct a failure without a second call.

#### Scenario: Counted features are listed
- **WHEN** a `feature_count` check runs
- **THEN** `measured.features` lists the names that were counted

### Requirement: Feature count counts modelling features only
`feature_count` SHALL count the document's own unsuppressed features, and
excludes:
- sketches;
- the origin;
- folder entries;
- the three default reference planes;
- the mate group.

The agent can then predict the number from the features it created.

#### Scenario: Part with two extrudes and a fillet
- **WHEN** a part's tree holds the default entries, two sketches, two
  extrudes and one fillet
- **THEN** the measured feature count is 3

### Requirement: Invalid requests fail clearly
The tool SHALL return the standard error payload (`status: "error"`,
`error_type`, `hint`):
- when there is no active document;
- when an assembly-only expectation (`component_count`, `mate_count`,
  `no_interference`) is given for a part;
- when a tolerance is negative;
- when the active document is a drawing.

#### Scenario: Mate count requested on a part
- **WHEN** `mate_count` is given and the active document is a part
- **THEN** the response has `status: "error"` and the message says the
  expectation applies only to assemblies
