## ADDED Requirements

### Requirement: A fillet works on every supported SolidWorks version
`add_fillet` SHALL build the fillet with the same COM call on every
SolidWorks version the server supports, so no version takes a branch that
has never run.

#### Scenario: SolidWorks 2024
- **WHEN** `add_fillet` runs against SolidWorks 2024 (major version 32)
- **THEN** it calls `IModelDoc2.FeatureFillet3` with its 9 arguments, as on
  2025 and 2026, and adds the fillet
