# tools/multibody-part-export Specification

## Purpose
Lets a caller extract one solid body from a multibody part into its own
standalone part file, for design-then-split machining/assembly workflows.
## Requirements
### Requirement: A named body can be saved as a standalone part file
The adapter SHALL expose `save_body_as_part`, which writes a named body
from the active multibody part to a new part file at a target path and
returns that path. It SHALL NOT alter the source document's bodies.

#### Scenario: Extracting one body from a multibody part
- **WHEN** `save_body_as_part` is called with an existing body name and a
  target path
- **THEN** a new part file containing only that body is written, the
  response reports the path, and the source part's bodies are unchanged

### Requirement: save_body_as_part fails clearly for an unresolvable body
`save_body_as_part` SHALL return a failed `AdapterResult` — not raise, not
write a file — when the named body doesn't exist on the active document.

#### Scenario: Body name does not exist
- **WHEN** `save_body_as_part` is called with a body name matching no
  body on the active part
- **THEN** the response status indicates failure and no file is written

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

