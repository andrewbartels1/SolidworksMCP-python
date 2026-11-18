## ADDED Requirements

### Requirement: Save Bodies leaves no document behind

After `save_body_as_part`, no document SHALL be open that wasn't open
before the call, except the part itself. A new, unsaved assembly that
SolidWorks opened alongside SHALL be closed, the part made active again,
and the reply's `closed_documents` SHALL name it.

#### Scenario: SolidWorks opens an assembly
- **WHEN** the Save Bodies call leaves a new, unsaved assembly open
- **THEN** it is closed, the part is active, and `closed_documents` names it

#### Scenario: The user's own assembly
- **WHEN** an assembly was open before the call, or has a file
- **THEN** it is left open
