## Context

`mypy src/solidworks_mcp` on 2026-11-16: 139 errors in 22 files. The large
groups: `hole_library.py` (50; dict literals typed too narrowly and a
SQLAlchemy `select` on a reflected `Table`), `documentation.py` (37; mostly
lambdas passed to `_attempt`, "Cannot infer type of lambda"),
`drawing_standard.py` (18), `features.py` (14), the adapters (21).

## Decisions

- **Gate, not remove.** The repo's rule is typed code with docstrings; a
  gate keeps that true. The count is small enough to clear in one change.
- **Generic `_attempt`.** `def _attempt[T](self, op: Callable[[], T],
  default: T) -> T` clears most of `documentation.py`.
- **`platform = "win32"`** in `[tool.mypy]`, so `sys.platform` branches
  are checked the same everywhere.
- **No behaviour change.** Fixes are annotations, `cast`, and narrowing
  that the code already implies. Where narrowing would need a new runtime
  check, the check must be one a test already reaches; otherwise use a cast.
- **Bare-ignore check** as a unit test that scans `src/` for
  `# type: ignore` without `[code]`.

## What the fix found

- 47 errors were lambdas binding loop values as defaults (`lambda i=i:`),
  which mypy can't match to `Callable[[], T]`; the `_attempt` helpers now
  take `Callable[..., T]`.
- One real fault: `plan_layout` with `inside_first` raised `TypeError` for
  a leader dimension with no lines (`leader_anchor` returns `None`). It now
  places that dimension outside, with a test.
- The stub packages `types-PyYAML` and `types-defusedxml` join the dev
  extra.
- **CI step** `make typecheck` before `make test`, in the same job.
