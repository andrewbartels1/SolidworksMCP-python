# tools/error-boundary Specification

## Purpose
Defines how every MCP tool reports failures, so a calling LLM or user always gets a
consistent payload that names what went wrong and what to try next.
## Requirements
### Requirement: Uniform error payload
Every MCP tool SHALL report any failure as a payload with `status: "error"`, a
human-readable `message`, an `error_type` from a fixed set, and a `hint` with the
next corrective step. The tool SHALL never raise an exception to the MCP client.
`execution_time` SHALL always be a number (the adapter's timing, or the tool's
own wall time when the adapter gave none) so the payload shape is stable, and
`data` SHALL be present when the tool has diagnostic data that explains the
failure (for example, the failing features of a rebuild).

#### Scenario: Adapter reports a failure
- **WHEN** a tool's adapter call returns an error result with a message and an execution time
- **THEN** the tool returns `status: "error"`, that message, an `error_type`, a `hint` and the execution time

#### Scenario: Failure with diagnostic data
- **WHEN** a tool's adapter call fails and returns data describing the failure
- **THEN** the error payload carries that data under `data` alongside the classification

#### Scenario: Unexpected exception inside a tool
- **WHEN** a tool's code raises an exception that no specific category covers
- **THEN** the tool returns `status: "error"` with `error_type: "internal"`, a message naming the tool and the exception type and text, and a hint to report the bug

### Requirement: Invalid input is reported as such
When a tool's input fails validation, the tool SHALL return `error_type:
"invalid_input"`. The message SHALL name the offending field(s), and the tool
SHALL NOT call the adapter.

#### Scenario: Missing required field
- **WHEN** a tool is called without a required field
- **THEN** the payload has `error_type: "invalid_input"`, the message names the missing field, and no adapter method was called

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

### Requirement: Success payload shape is unchanged
Successful tool calls SHALL keep their current keys (`status: "success"`,
`message`, tool-specific data and `execution_time`). The error boundary SHALL
NOT alter success payloads.

#### Scenario: Successful call
- **WHEN** a tool's adapter call succeeds
- **THEN** the payload is identical to the one the tool returned before this change

### Requirement: A feature SolidWorks accepted but did not build is named
When an adapter reports that SolidWorks accepted a feature call but built no
feature, the tool SHALL return `error_type: "feature_not_built"`. Its hint
SHALL say that the geometry gave SolidWorks nothing to build, and that the
caller should change the sketch, its plane, the depth or the end condition
rather than retry the same call.

#### Scenario: A cut builds nothing
- **WHEN** the adapter error reads "SolidWorks built no feature from sketch 'Sketch2' (tried: the requested direction; direction flipped ...)"
- **THEN** the payload has `error_type: "feature_not_built"` and a hint telling the caller to change the inputs rather than retry

### Requirement: A plain dict is accepted as a tool's input

The tool boundary SHALL validate a dict passed where a tool expects its input model, so every tool can be called from a script with a dict.

#### Scenario: A script passes a dict
- **WHEN** a script calls `check_interference` with `{"components": ["a-1", "b-1"]}`
- **THEN** the tool runs as it would over MCP

#### Scenario: A bad dict
- **WHEN** the dict fails validation
- **THEN** the tool returns `error_type: invalid_input`, naming the field

