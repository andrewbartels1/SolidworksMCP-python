## Why

Two leftovers make problems harder to track down than they should be.

- **Misleading hint (#155, part 2).** The `com_member_not_found` hint says the
  cause is "usually a stale type cache" and tells the caller to delete
  `%TEMP%\gen_py`. In this repo the usual cause is different: a zero-argument
  method is called through late binding without being flagged, so SolidWorks
  is asked for a property and answers "Member not found". That is what
  happened with `CreateMeasure` in #139. Deleting `gen_py` doesn't fix it, so
  agents and users follow the hint and get nowhere.
- **Stale script (#157, part 1).** `src/utils/validate_coverage.py` expects
  test files that no longer exist, crashes on a Windows console at startup
  (`UnicodeEncodeError`), and nothing uses it. Coverage is already enforced
  by pytest-cov, and the test layout by `tests/integration/test_test_layout.py`.

Part 1 of #155, docs discovery launching a hidden SolidWorks, was already
fixed by #189. Part 2 of #157, whether mypy gates CI, is a separate decision
and is not part of this change.

## What Changes

- The `com_member_not_found` hint names the common cause first: a method the
  server forgot to flag, which is a server bug to report with the tool name.
  It names the stale `gen_py` cache second, as the fix after a SolidWorks
  upgrade.
- `src/utils/validate_coverage.py` is deleted.
- The `docs/planning/roadmap.md` row for #157 is updated to show the script
  part done.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `tools/error-boundary`: the `com_member_not_found` hint changes as
  described above.

## Impact

- `src/solidworks_mcp/tools/error_classifier.py`: one hint string. This is not
  COM or adapter code: the classifier only reads error text.
- `tests/solidworks_mcp/tools/test_error_classifier.py`: a test for the new
  wording.
- `src/utils/validate_coverage.py`: removed. Nothing imports it.
- Closes #155. #157 stays open for the mypy decision.
