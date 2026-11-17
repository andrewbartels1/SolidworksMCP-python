## 1. Adapter

- [x] 1.1 `adapters/solidworks/sheet_metal.py`: the mixin, the sheet-metal check, the base flange with its K-factor and read-back; tests on fake COM
- [x] 1.2 The edge flange by a point on the edge; tests
- [x] 1.3 The sketched bend through `CreateDefinition`; tests
- [x] 1.4 `set_flat_pattern` with the bounding box after; tests
- [x] 1.5 The four methods on the base adapter interface, circuit breaker and connection pool; tests
- [x] 1.6 The mock adapter's sheet metal (its own mixin): volumes and a flat size from the K-factor; tests

## 2. Tools

- [x] 2.1 The four tools in `tools/modeling.py`: inputs, descriptions, support level beta, hints; tests (including the refusals)

## 3. Docs

- [x] 3.1 Modeling catalog entries, counts, the skill's workflow (base flange, edge flange, flatten, export the DXF), CHANGELOG

## 4. Live check

- [x] 4.1 (passed 2026-11-16 after the probes in the design; the part is saved before the DXF, which `export_flat_pattern` now asks for) `tests/live/test_live_sw_sheet_metal.py`: a 100 x 60 x 2 mm plate; a 20 mm flange on a long edge; the flat blank's width against the K-factor's; a sketched bend on a second plate; a block refused; the DXF exported
- [x] 4.2 Fixes one at a time, the decisions recorded in the design; the tools stable when they pass; archive; queue updated; PR closing #57
