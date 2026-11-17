## Why

Issue #157: mypy is configured in `pyproject.toml` but nothing runs it, and
`main` has 139 errors in 22 files. New code adds more and nobody notices,
while the project's rule is that every function is typed. The issue's other
half, the stale `src/utils/validate_coverage.py`, was already deleted by an
earlier change.

## What Changes

- Fix the 139 errors without changing behaviour: annotations, narrowing and
  `cast` where COM returns `Any`. A `# type: ignore` names its error code
  (the code base already has 30 that do).
- mypy checks as if on Windows (`platform = "win32"`), so CI on Linux and a
  developer on Windows see the same result.
- `make typecheck` runs it, and CI runs `make typecheck` before the tests.

## Capabilities

### New Capabilities
- `release/type-checking`: mypy gates CI with zero errors.

### Modified Capabilities
None.

## Impact

`pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, the 22 files with
errors. No tool's behaviour changes; the unit suite at 100% coverage is the
check.
