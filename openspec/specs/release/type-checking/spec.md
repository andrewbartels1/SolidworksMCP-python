# release/type-checking Specification

## Purpose
TBD - created by archiving change mypy-gates-ci. Update Purpose after archive.
## Requirements
### Requirement: mypy gates CI

CI SHALL run mypy over `src/solidworks_mcp` with the project's
configuration and fail on any error. mypy SHALL check as if on Windows, so
the result doesn't depend on the machine running it.

#### Scenario: A type error is pushed
- **WHEN** a commit adds code mypy reports an error in
- **THEN** the CI job fails at the type-check step, before the tests

#### Scenario: The code base is clean
- **WHEN** `make typecheck` runs on `main` after this change
- **THEN** mypy reports no errors

### Requirement: Suppressions are explained

A `# type: ignore` SHALL name its error code. A new one SHALL also say
why, on its line or the one above.

#### Scenario: A bare ignore
- **WHEN** the source contains `# type: ignore` without an error code
- **THEN** the check fails and names the line

