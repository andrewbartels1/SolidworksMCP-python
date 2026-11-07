# adapters/circuit-breaker Specification

## Purpose
TBD - created by archiving change circuit-breaker-recovery. Update Purpose after archive.
## Requirements
### Requirement: A success never leaves a breaker open

A successful call SHALL close its operation's breaker, and the next call SHALL be allowed.

#### Scenario: Success then a second call
- **WHEN** `create_extrusion` succeeds and is called again at once
- **THEN** the second call reaches the adapter

### Requirement: An open breaker recovers after its timeout

An open breaker SHALL let one trial call through once its timeout has passed since the last failure, and close when that call succeeds.

#### Scenario: Waiting out the timeout
- **WHEN** a breaker opened after repeated failures and the timeout has passed
- **THEN** the next call reaches the adapter, and on success the breaker is closed

### Requirement: Breakers can be reset by a tool

A `reset_circuit_breaker` tool SHALL close all breakers, or the one named, and report which were open.

#### Scenario: Reset one operation
- **WHEN** an agent calls `reset_circuit_breaker` with `operation: create_extrusion` while it is open
- **THEN** the result lists it as reset and the next `create_extrusion` call reaches the adapter

#### Scenario: No breaker in use
- **WHEN** the adapter has no circuit breaker (mock mode)
- **THEN** the tool succeeds and reports that nothing was open

### Requirement: An open breaker explains itself

The error for a refused call SHALL name the operation, and its `hint` SHALL name the reset tool and the timeout setting.

#### Scenario: Refused call
- **WHEN** a call is refused by an open breaker
- **THEN** `error_type` is `circuit_open` and `hint` names `reset_circuit_breaker` and `SOLIDWORKS_MCP_CIRCUIT_BREAKER_TIMEOUT`

