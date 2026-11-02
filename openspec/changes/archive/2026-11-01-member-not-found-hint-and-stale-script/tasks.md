## 1. Hint (#155)

- [x] 1.1 Reword the `com_member_not_found` hint in `src/solidworks_mcp/tools/error_classifier.py`: unflagged method first, stale `gen_py` after an upgrade second.
- [x] 1.2 Add a test in `tests/solidworks_mcp/tools/test_error_classifier.py` that the hint names both causes, flagging first.
- [x] 1.3 Correct the `com_member_not_found` row in `docs/user-guide/tool-catalog/index.md`.

## 2. Stale script (#157, part 1)

- [x] 2.1 Delete `src/utils/validate_coverage.py`, after confirming nothing references it.
- [x] 2.2 Update the #157 row in `docs/planning/roadmap.md`.

## 3. Check

- [x] 3.1 Run `ruff check` and `pytest tests -m "not solidworks_only"`, with coverage at 100%.
- [x] 3.2 Run `openspec validate member-not-found-hint-and-stale-script --strict`.
