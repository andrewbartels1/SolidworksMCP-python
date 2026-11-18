## 1. Check

- [x] 1.1 `tools/vba_check.py`: tokenizer, declared names, file statements, allowlist, blocklist; `check_vba(source, members, enums)` returns the refusals
- [x] 1.2 Unit tests: a SolidWorks-only macro passes; each refused kind is named with its line; strings and comments ignored; `With` members; continuations

## 2. Setting and tool

- [x] 2.1 `allow_vba_source`: `off` / `restricted` / `full`; other values stop the server with the valid ones
- [x] 2.2 `execute_macro`: restricted runs the check against the type-library index; `vba_source_refused` classifier rule; no index means a refusal
- [ ] 2.3 Live test (written, run pending): the sketch macro runs in restricted mode; a `Shell` line is refused

## 3. Docs

- [x] 3.1 Installation guide: the three values, the default, what each allows and refuses, the blocked members, the limits; catalog entry; CHANGELOG
- [x] 3.2 Full suite at 100%, ruff, mypy, docs strict
