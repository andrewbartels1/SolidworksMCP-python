## 1. Table and tag

- [x] 1.1 `tools/requirements.py`: `Requirement` enum, `REQUIREMENTS` table (the 20 exceptions), `requirement_of(name)`
- [x] 1.2 `ToolRegistrar` adds `needs:<requirement>`
- [x] 1.3 Tests: the enum and lookup; every table name registered; one `needs:` tag per tool; `installed` descriptions say SolidWorks need not run

## 2. Docs

- [x] 2.1 Tools overview: "What each tool needs from SolidWorks", the licence sentence and the 20 tools by requirement
- [x] 2.2 Check: the overview's list equals the table
- [x] 2.3 README "Supported Today": one line pointing there; CHANGELOG
- [x] 2.4 Full suite at 100%, ruff, `mkdocs build --strict`
