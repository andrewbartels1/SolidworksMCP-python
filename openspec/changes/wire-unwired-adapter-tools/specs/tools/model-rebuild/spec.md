## Purpose

Lets an MCP caller force a rebuild of the active model after programmatic
edits (dimension changes, feature edits). It reports exactly which features
fail and why, with a concrete fix hint for each, so an LLM can repair the
model instead of getting a bare "didn't work".

## ADDED Requirements

### Requirement: rebuild_model is exposed as an MCP tool
The server SHALL register a `rebuild_model` tool with an optional boolean
`top_level_only` input. The default `false` rebuilds the whole model,
including sub-assemblies. Every response SHALL carry `status`, `message`,
`execution_time` and a `data` payload with:
- `rebuilt` (bool)
- `top_level_only` (bool)
- `errors` (list)
- `error_count` (int)
- `warning_count` (int)

#### Scenario: Clean rebuild
- **WHEN** `rebuild_model` is called on a part whose features are all valid
- **THEN** the response has `status: "success"`, `data.rebuilt` is true,
  `data.errors` is empty, and both counts are 0

### Requirement: Rebuild diagnostics identify each failing feature
For every feature that SolidWorks flags after the rebuild, `data.errors`
SHALL contain one entry with:
- `feature`: the feature name
- `type`: the SolidWorks feature type name
- `code`: the integer feature-error code
- `code_name`: the symbolic name of that code, resolved from SolidWorks'
  feature-error enumeration
- `severity`: `"error"` or `"warning"`
- `description`: plain-language text
- `parents`: names of the features or sketches it references
- `hint`: a concrete next action. Codes without a specific hint get a
  generic one.

Suppressed features SHALL NOT be reported.

#### Scenario: Fillet loses its edge
- **WHEN** a dimension edit removes the edge a fillet was built on and
  `rebuild_model` is called
- **THEN** `data.errors` contains an entry whose `feature` is the fillet's
  name, `severity` is `"error"`, `code_name` is a non-empty SolidWorks enum
  member name, and `hint` tells the caller how to re-target or recreate the
  fillet

#### Scenario: Unknown error code
- **WHEN** a feature reports an error code with no curated hint
- **THEN** its entry still carries `code`, `code_name` (or the raw code
  when no name resolves), and a generic `hint`

### Requirement: Rebuild status reflects remaining errors
`rebuild_model` SHALL return `status: "error"` whenever at least one entry has
`severity: "error"`. The full `data` payload SHALL still be included, and the
`message` SHALL name the failing features. When the only entries are
warnings, it SHALL return `status: "success"` and the `message` SHALL mention
the warnings.

#### Scenario: Errors remain after rebuild
- **WHEN** the rebuild completes but one feature is in error
- **THEN** the response has `status: "error"`, `data.error_count` is 1, and
  the message names that feature

#### Scenario: Warnings only
- **WHEN** the rebuild completes with only warning-severity entries
- **THEN** the response has `status: "success"` and `data.warning_count`
  is greater than 0

### Requirement: rebuild_model fails clearly
`rebuild_model` SHALL return `status: "error"` and SHALL NOT raise in either
of these cases:
- no document is active
- SolidWorks reports that the rebuild call itself failed

#### Scenario: No active document
- **WHEN** `rebuild_model` is called with no document open
- **THEN** the response has `status: "error"` and the message says there is
  no active model

#### Scenario: Rebuild reports failure without naming a feature
- **WHEN** SolidWorks reports the rebuild failed but lists no failing feature
- **THEN** the response has `status: "error"` and the message says the
  rebuild failed without a named cause. (When features are listed, the
  per-feature diagnostics above are returned instead - SolidWorks reports
  the rebuild as failed whenever any feature fails.)

### Requirement: Adapter interface declares rebuild_model
Every adapter layer (base interface, circuit breaker, connection pool, mock,
real) SHALL expose `rebuild_model(top_level_only: bool = False)` returning an
`AdapterResult` whose data is the payload above. The base interface default
SHALL be an ERROR result stating that the adapter does not implement it.

#### Scenario: Wrapped adapter
- **WHEN** a tool calls `rebuild_model` on the adapter as wired by the server
  (circuit breaker / connection pool around the real or mock adapter)
- **THEN** the call reaches the underlying implementation instead of raising
  `AttributeError`
