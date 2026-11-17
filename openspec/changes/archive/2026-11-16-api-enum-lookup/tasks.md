## 1. Index

- [x] 1.1 `type_library.py`: `ApiEnum`, `index_enums(lib)`, `load_constants_library(major, minor)`
- [x] 1.2 `docs_discovery.py`: the index reads the enums (format 2.1); a failure leaves them empty with a note

## 2. Tool

- [x] 2.1 `get_api_enum` with `GetApiEnumInput` and `EnumLookup`; hints, level, `needs:installed`
- [x] 2.2 Unit tests: an enum, a member, case, unknown, no constants library, the index format
- [x] 2.3 Live: `swUnitSystem_e` read from this machine's library (in `test_live_sw_api_lookup.py`)

## 3. Docs

- [x] 3.1 Catalog entry, overview list, counts (140), CHANGELOG
- [x] 3.2 Full suite at 100%, ruff, mypy, docs strict
