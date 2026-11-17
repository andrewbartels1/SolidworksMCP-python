## 1. Errors

- [x] 1.1 `platform = "win32"` in `[tool.mypy]`; re-count
- [x] 1.2 Fix every error, file by file, with no behaviour change
- [x] 1.3 Test: no bare `# type: ignore` in `src/`

## 2. Gate

- [x] 2.1 `make typecheck`; CI runs it before the tests
- [x] 2.2 CONTRIBUTING or CLAUDE.md: mypy is part of the checks
- [x] 2.3 Full suite at 100%, ruff, mypy clean, docs strict
