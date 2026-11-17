## 1. Adapter

- [x] 1.1 `save_as_template(file_path)` and `get_template_folders()` on the base adapter interface, circuit breaker and connection pool, with tests
- [x] 1.2 The real adapter (`adapters/solidworks/templates.py`): `IModelDocExtension.SaveAs`, the file and the open document's path and title checked after (design decision 1); the template folders from the preference; tests
- [x] 1.3 The mock adapter: a template folder, the copy recorded, `create_part` from it carries the settings; tests

## 2. Tool

- [x] 2.1 `save_as_template` in `tools/file_management.py`: `file_path` or `name`, `overwrite`; the checks in design decision 2 before the adapter; support level beta, hints; tests

## 3. Docs

- [x] 3.1 The file-management catalog entry, the skill's workflows (set up a part once, save it as a template), CHANGELOG

## 4. Live check

- [x] 4.1 (passed 2026-11-16 on the third run, after design decision 1) `tests/live/test_live_sw_templates.py`: a part set to IPS, 6061-T6 and a `Company` property, saved as a template by path; a new part from it carries all three; a saved part's template opens in its place and its file stays on disk; a wrong extension refused
- [x] 4.2 Sign-off: the tool stable, archive, the queue updated
