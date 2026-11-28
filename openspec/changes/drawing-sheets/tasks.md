## 1. Probe

- [x] 1.1 Probe GetSheetNames, GetProperties2, NewSheet4 and ActivateSheet
      on SolidWorks 2026 (answers in design.md)

## 2. Build

- [x] 2.1 `adapters/sheet_rules.py`; base, circuit breaker and pool wrappers
- [x] 2.2 `adapters/solidworks/drawing_sheets.py` and the mock
- [x] 2.3 `tools/drawing_sheets.py`; registration, drawing toolset, support
      levels (beta), hints, classifier rules

## 3. Tests

- [x] 3.1 Unit tests mirroring src, 100% coverage
- [x] 3.2 Live test `tests/live/test_live_sw_drawing_sheets.py` (passed
      2026-11-28: Sheet1 with a front view; "sheet1" refused; Details A2
      at 1:2 active with an isometric view; back to Sheet1)

## 4. Docs

- [x] 4.1 Catalog page, counts, CHANGELOG, queue
- [ ] 4.2 A demo and GIF once the user has seen it
