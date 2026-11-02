## MODIFIED Requirements

### Requirement: Known SolidWorks failures are named
Failures with a recognisable cause SHALL be reported with a specific
`error_type` and a matching hint:

- **`solidworks_unavailable`:** the SolidWorks process disconnected or crashed
  (RPC disconnected / RPC server unavailable). Hint: restart SolidWorks, then retry.
- **`circuit_open`:** the operation is temporarily blocked after repeated
  failures. Hint: wait for the breaker timeout, or fix the cause, then retry.
- **`com_member_not_found`:** the SolidWorks API member could not be resolved.
  Hint: name the common cause first, a method the server called without
  flagging it (a server bug to report with the tool name); then the
  fallback, a stale type cache after a SolidWorks upgrade (delete
  `%TEMP%\gen_py` and restart the MCP server).
- **`com_type_mismatch`:** an argument had the wrong COM type. Hint: report as a bug.
- **`not_found`:** a named document, feature, sketch, view or entity does not exist.
- **`not_supported`:** the active adapter has no capability for the operation
  (for example, the mock adapter or a non-Windows host). Hint: use the real
  SolidWorks adapter, another tool, or do the step in SolidWorks directly.
- **`no_active_document`:** the operation needs an open or active document and
  there is none.
- **`no_active_sketch`:** the operation needs an open sketch and none is in edit
  mode. Hint: create or open a sketch first.

#### Scenario: SolidWorks crashed mid-call
- **WHEN** the adapter call fails because the SolidWorks RPC server is unavailable
- **THEN** the payload has `error_type: "solidworks_unavailable"` and a hint telling the user to restart SolidWorks

#### Scenario: Circuit breaker is open
- **WHEN** the adapter rejects the call because its circuit breaker is open
- **THEN** the payload has `error_type: "circuit_open"` and a hint explaining that calls resume after the timeout

#### Scenario: API member not found
- **WHEN** an adapter error reads "Member not found" or carries `DISP_E_MEMBERNOTFOUND`
- **THEN** the payload has `error_type: "com_member_not_found"`, and its hint names an unflagged method as the first cause and a stale `gen_py` cache after an upgrade as the second

#### Scenario: Operation not supported by the adapter
- **WHEN** a tool needs an adapter capability the active adapter does not have
- **THEN** the payload has `error_type: "not_supported"`, a message saying what was not done, and no adapter call is attempted

#### Scenario: No active document
- **WHEN** a tool that needs a document runs with no active model
- **THEN** the payload has `error_type: "no_active_document"` and a hint to open or create a document first

#### Scenario: Unrecognised adapter error
- **WHEN** an adapter error matches no known category
- **THEN** the payload has `error_type: "operation_failed"`, carries the adapter's message unchanged, and gives a generic hint
