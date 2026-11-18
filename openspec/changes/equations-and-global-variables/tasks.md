## 1. Adapter

- [x] 1.1 Adapter interface `list_equations`, `set_equation`, `delete_equation` through `base.py`, `circuit_breaker.py`, `connection_pool.py`; tests
- [x] 1.2 Real adapter mixin `adapters/solidworks/equations.py`: walk, name parse, dimension check, `Add3` / `SetEquationAndConfigurationOption` with read-back and restore, `Delete`, `EvaluateAll` + rebuild; tests with fake COM objects
- [x] 1.3 Mock adapter: equation list, simple values, refusal of an unknown global variable; tests

## 2. Tools

- [x] 2.1 `tools/equations.py`: inputs (name and expression checks, `configurations`), the three tools, registration; tests
- [x] 2.2 `equation_refused` classifier rule; hints, support levels, toolsets; tool count 143; the `delete_` meaning in the description standard

## 3. Docs

- [x] 3.1 Catalog page; the agent skill's note on making a part parametric; CHANGELOG; queue row 29; progress bars regenerated
- [x] 3.2 Full mock suite at 100% coverage, ruff, mypy, `mkdocs build --strict`

## 4. Live

- [ ] 4.1 Live test `tests/live/test_live_sw_equations.py` (written, run by the user): `Width` = 60mm drives `D1@Sketch1` = `"Width" / 2` (30 mm, then 40 mm after `Width` = 80mm); a refused expression leaves the list unchanged; a value in one configuration only; delete keeps the last value; confirm the units of `Value`
- [ ] 4.2 Fix any failure; archive after the user's pass
