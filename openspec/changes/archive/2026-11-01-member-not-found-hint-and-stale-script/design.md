## Context

The classifier's rule table in `tools/error_classifier.py` maps an error to an
`error_type` and a fixed hint. Agents act on that hint as written, so a wrong
first suggestion costs them a restart and a cache rebuild that changes nothing.

## Goals / Non-Goals

**Goals:** the hint points at the likely cause first, and the dead script is gone.

**Non-Goals:** telling the two causes apart at runtime. The error text is the
same either way, and a guess would be worse than naming both. Deciding on
mypy (#157 part 2).

## Decisions

- **Hint wording.** "SolidWorks could not resolve this API member. Usually a
  server bug: a method called without being flagged (report the tool name).
  After a SolidWorks upgrade it can be a stale type cache: delete
  %TEMP%\gen_py and restart the MCP server." The rule's patterns and HRESULT
  stay the same, so classification does not change.
- **Delete, don't rewrite, `validate_coverage.py`.** Everything it tried to do
  is already covered by pytest-cov's `fail_under` and `test_test_layout.py`.

## Risks / Trade-offs

- [A caller matching on the old hint text breaks] → Hints are free text for
  people and agents. Callers branch on `error_type`, which is unchanged.
