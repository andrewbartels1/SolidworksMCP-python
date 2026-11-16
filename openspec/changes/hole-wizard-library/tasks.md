## 1. Reading the library

- [ ] 1.1 `adapters/solidworks/hole_library.py`: find the file (setting, registry, install template), open it read-only and immutable, read a standard's hole types by kind (the `ValidHoleTypes` bits) and their enabled sizes, and one size's dimensions; cache per path and modification time
- [ ] 1.2 Nearest sizes for a size that doesn't exist
- [ ] 1.3 Tests in `tests/solidworks_mcp/adapters/solidworks/test_hole_library.py` against a small SQLite fixture built in the test (both table kinds, disabled rows, repeated names, a missing column, no file)

## 2. Adapter method

- [ ] 2.1 `list_hole_sizes` on the base adapter interface, the circuit breaker and the connection pool, with tests
- [ ] 2.2 The real adapter's `list_hole_sizes` (calls 1.1, no COM), with tests
- [ ] 2.3 The mock adapter's `list_hole_sizes`: a built-in ISO and ANSI inch library (a few drill, clearance, cap-screw and tapped sizes), with tests

## 3. Tools

- [ ] 3.1 `list_hole_sizes` tool in `tools/modeling.py` (inputs, read-only hints, support level beta, tool hints), with tests
- [ ] 3.2 `create_hole`: optional `fastener`, the standards ansi_metric, din and jis, the simple-hole choice of table (design decision 5), the size check before the COM call, the warning when the library can't be read; remove `simple_iso_size`; the mock and tool tests
- [ ] 3.3 The reply names the hole type used (`fastener`)

## 4. Docs

- [ ] 4.1 Modeling catalog page, overview counts, the skill's workflows ("find the size with `list_hole_sizes`"), api-coverage, CHANGELOG

## 5. Live checks

- [ ] 5.1 `tests/live/test_live_sw_hole_library.py`: list ISO simple and counterbore sizes from the installed library; `create_hole` with `M6` (clearance), `6` (drill) and an unknown size refused with no feature made
- [ ] 5.2 Rerun the pattern demo (`test_pattern_a_row_and_a_grid`) with the clearance hole
