---
name: extract-and-test
description: "Use when refactoring a method in pywin32_adapter.py that contains untestable closures, nested try/except blocks, or COM logic that can't be unit-tested in isolation. Apply SOLID principles: extract helpers, refactor to thin orchestrator, add full branch-coverage tests. Trigger phrases: extract helper, SOLID refactor, untestable closure, nested try/except, branch coverage, TestPyWin32AdapterBranches, pywin32_adapter method, select_feature, execute_macro, export_image, adapter refactor."
---

# Extract & Test — pywin32_adapter.py

Apply this skill whenever a method in `src/solidworks_mcp/adapters/pywin32_adapter.py` contains:
- Deeply nested `try/except` blocks or inner closures that can't be tested in isolation
- Mixed concerns (COM selection strategy + fallback + error handling all in one body)
- A closure that calls `self._attempt(...)` with an inner `_run`/`_operation` lambda

---

## Step 1 — Read and Analyse

Read the target line range. For each logical block, fill in this table:

| Concern | COM calls involved | Failure mode | Return contract |
|---|---|---|---|
| (fill in) | (fill in) | (fill in) | (fill in) |

Apply these heuristics to determine the right helper shape:

| Shape | When to use |
|---|---|
| `-> None` (log, never raise) | Setup/orientation side-effects — failure is acceptable |
| `-> bool` | COM operation that writes a file; True = file exists |
| `-> dict \| None` | COM selection/query strategy; None = this strategy failed, try next |
| `-> dict` (raises on failure) | Last-chance fallback or invoker — surface error to caller |
| `@staticmethod` | Pure string/data transformation with no `self` state |

---

## Step 2 — Extract Helpers

Write one helper per concern. Insert helpers **immediately before** the `async def` they support.

```python
def _<verb>_<noun>(self, <args>) -> <return type>:
    """<One-line description>.

    Args:
        <arg>: <description>

    Returns:
        <type>: <description>

    Raises:
        <ExceptionType>: <when>
    """
    ...
```

**Examples by return contract:**

```python
# Graceful-failure helper — log, never raise
def _set_view_orientation(self, target_doc, orientation, view_const) -> None:
    try:
        target_doc.ShowNamedView2("", view_const)
    except Exception:
        logger.warning("Could not set view orientation to %s", orientation)

# Boolean helper — True = file written
def _save_screenshot_with_modelview(self, model_view, path, width, height) -> bool:
    try:
        model_view.SaveBitmapWithVariableSize(path, width, height)
        return os.path.exists(path)
    except Exception:
        return False

# Optional-dict helper — None = strategy failed, try next
def _try_select_by_extension(self, target_doc, candidates, feature_name) -> dict | None:
    for candidate in candidates:
        for entity_type in ENTITY_TYPES:
            try:
                if target_doc.Extension.SelectByID2(candidate, entity_type, 0, 0, 0, False, 0, None, 0):
                    return {"selected": True, "feature_name": feature_name, ...}
            except Exception:
                continue
    return None

# Raising helper — last-chance invoker
def _invoke_run_macro2(self, macro_path, module_name, proc_name) -> dict:
    result = self.swApp.RunMacro2(macro_path, module_name, proc_name, 0, 0)
    success = result[0] if isinstance(result, (list, tuple)) else bool(result)
    if not success:
        raise SolidWorksMCPError(f"RunMacro2 failed for {macro_path}")
    return {"macro_path": macro_path, "module_name": module_name}
```

---

## Step 3 — Refactor the Orchestrator

Replace the closure body with a sequential `if result: return result` chain:

```python
def _operation() -> dict:
    target_doc = self.currentModel
    candidates = self._build_feature_candidate_names(feature_name, target_doc)
    result = self._try_select_by_extension(target_doc, candidates, feature_name)
    if result:
        return result
    result = self._try_select_by_component(target_doc, candidates, feature_name)
    if result:
        return result
    result = self._try_select_by_feature_tree(target_doc, feature_name, candidates)
    if result:
        return result
    return {"selected": False, "feature_name": feature_name}
```

---

## Step 4 — Write Tests

Add tests to `TestPyWin32AdapterBranches` in `tests/test_adapters.py`.

**Critical rules:**
- Use `self._build_adapter(monkeypatch)` — never construct `PyWin32Adapter` directly.
- Mock COM objects with `SimpleNamespace` + `unittest.mock.Mock`.
- Never import `win32com`, `pywintypes`, or `pythoncom` — use monkeypatch.
- Use `tmp_path` fixture for file-existence checks.
- Tests must be **class-level methods** at 4-space indentation under the class — never nested inside another test function.
- Use the top-level `SolidWorksMCPError` import (already present at module top); do NOT add a local `from solidworks_mcp.exceptions import SolidWorksMCPError` inline — it creates a different class object that won't match `pytest.raises`.

**Coverage requirement per helper:**

| Scenario | Must cover |
|---|---|
| Happy path | Returns expected value when COM calls succeed |
| Failure path | Returns None / False / raises when COM call fails or returns False |
| Edge cases | None input, empty list, fallback chain exhausted |

```python
def test_<helper_name>_<scenario>(self, monkeypatch) -> None:
    """<helper_name> should <expected behaviour> when <condition>."""
    adapter = self._build_adapter(monkeypatch)
    # arrange
    target_doc = SimpleNamespace(Method=Mock(return_value=<value>))
    # act
    result = adapter.<helper_name>(target_doc, ...)
    # assert
    assert result == <expected>
```

---

## Step 5 — Validate

Run only the new tests first (no coverage threshold):

```powershell
.\.venv\Scripts\python.exe -m pytest -o addopts="" tests/test_adapters.py::TestPyWin32AdapterBranches -k "<new_test_fragment>" -q
```

Run the full class to catch regressions:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_adapters.py::TestPyWin32AdapterBranches -q --no-cov
```

All tests must pass before the task is complete.

---

## Known Pitfall — SolidWorksMCPError identity

The project uses `src.solidworks_mcp.exceptions` as the import path in the adapter module. If a test imports `from solidworks_mcp.exceptions import SolidWorksMCPError` inline, Python loads a separate module object and `pytest.raises` won't catch the exception even though the message is identical. Always use the module-level import:

```python
# at the top of test_adapters.py — already present:
from src.solidworks_mcp.exceptions import SolidWorksMCPError
```
