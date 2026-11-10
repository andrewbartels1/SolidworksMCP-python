# tools/macro-execution Specification

## Purpose
How many times `execute_macro` runs a macro, and what its reply says about the
runs.
## Requirements
### Requirement: A macro runs repeat_count times

`execute_macro` SHALL run the macro `repeat_count` times, waiting
`pause_between_runs` seconds between runs. It SHALL stop at the first run that
fails. The reply SHALL give the number of runs that completed, and the message
SHALL state that number, not the number asked for.

#### Scenario: Three runs
- **WHEN** an agent runs a macro that adds one feature with `repeat_count: 3`
- **THEN** three features are added and the reply says 3 runs completed

#### Scenario: A run fails part way
- **WHEN** the second of three runs fails
- **THEN** the reply is an error saying 1 run completed and the second failed, and no third run is attempted

