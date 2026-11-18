## 1. Fix

- [x] 1.1 Note the open documents before Save Bodies; close new unsaved assemblies after; reactivate the part; `closed_documents` in the reply
- [x] 1.2 Unit test: the new assembly closed, the user's saved one left
- [x] 1.3 Live: `test_save_body_as_part_writes_the_body_file` checks no unsaved assembly is open afterwards (passed live 2026-11-17)
- [x] 1.4 Tool description, mock adapter, CHANGELOG; full suite, ruff, mypy
