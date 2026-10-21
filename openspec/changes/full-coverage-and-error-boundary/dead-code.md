# Dead-code ledger

Code that no real input, fixture or fake can reach. **Nothing here is deleted
until the user reviews this list** (task 3.5).

| # | Location | Guard | Why it cannot be reached | Evidence | Proposed action |
|---|---|---|---|---|---|
| 1 | `tools/modeling.py` `get_dimension` and `set_dimension`: `if not input_data.name: raise InvalidInputError(...)` | empty dimension name | `GetDimensionInput` / `SetDimensionInput.model_post_init` already reject an empty name during `normalize_input`, so the tool body never sees one | `test_modeling.py::test_dimension_empty_name_validation` reaches it only by patching the normaliser to return a fake | Delete both guards; replace the patched test with a real-input test asserting `invalid_input` |
