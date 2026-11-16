## 0. Before starting

- [x] 0.1 Confirm the honest-tool-list change is merged; read its design-table finding (its design decision 8). If `manage_design_table` was kept, add its tasks here (insert, read, update rows) before section 1 (Known 2026-11-14: design tables don't work through COM here, so `manage_design_table` was removed; build configurations without Excel.)

## 1. Create, activate, delete

- [x] 1.1 Inputs and tools `create_configuration`, `activate_configuration`, `delete_configuration`, with the name checks (existing, unknown, active, only); tests
- [x] 1.2 Adapter interface for the three through `base.py`, `circuit_breaker.py`, `connection_pool.py`; tests
- [x] 1.3 Real adapter: `AddConfiguration2` (restore the previous configuration unless `activate`), `ShowConfiguration2`, `DeleteConfiguration2`; tests
- [x] 1.4 Mock adapter: a configuration list with an active one; tests

## 2. The active configuration

- [x] 2.1 `list_configurations` reports `active` (real: `ActiveConfiguration.Name`); tests
- [x] 2.2 Mock adapter: `active` from its state; tests

## 3. Scoped changes

Not started (2026-11-15): sections 1, 2 and 5 shipped first so the three
configuration tools reach the morning live run.


- [ ] 3.1 `configurations` input on `set_dimension` and `suppress_feature`; a list checked against the model's configurations; replies name the configurations; tests
- [ ] 3.2 Adapter interface: `configurations` on `set_dimension` and `suppress_feature` through every layer; tests
- [ ] 3.3 Real adapter: `SetSystemValue3` with 1, 2 or 3 and the names array; `SetSuppression2` for `all` or a list, `EditSuppress2` kept for `this`; tests
- [ ] 3.4 Mock adapter: per-configuration dimension values and suppression; tests
- [ ] 3.5 Descriptions of `set_dimension`, `suppress_feature` and `get_dimension` say which configuration they act on

## 4. Live bundle (one set, run together, then fixes one by one)

- [ ] 4.1 (create/activate/delete written in tests/live/test_live_sw_configurations.py, not yet run; the scoped-change scenarios wait on section 3) Live tests: create `Long`, activate it and back; delete refused while active; a length in `Long` only, read in both; `Fillet1` suppressed in `all`; an unknown name refused
- [ ] 4.2 Hand the user the bundle; fix each failure afterwards, one at a time

## 5. Docs and finish

- [x] 5.1 Catalog pages; the agent skill's note on configurations (scope defaults to the active one)
- [x] 5.2 CHANGELOG (Added; Changed: `list_configurations` reports `active`), progress bars regenerated
- [x] 5.3 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`
- [ ] 5.4 Sign-off, PR (no attribution), archive, the queue updated
