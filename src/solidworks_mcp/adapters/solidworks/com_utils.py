"""Small COM helpers shared by the selection / face / rebuild modules.

One copy of each, so error-handling and flagging behaviour cannot drift
between modules.
"""

from __future__ import annotations

from typing import Any

from .. import sw_type_info as _sw_type_info


def attempt(adapter: Any, fn: Any, default: Any = None) -> Any:
    """Run ``fn`` through the adapter's ``_attempt`` (exceptions -> default)."""
    return adapter._attempt(fn, default=default)


def flag(adapter: Any, obj: Any, *names: str) -> None:
    """Flag just ``names`` as methods on ``obj`` (no-op for ``None``/fakes).

    Flagging a whole interface costs ~27 ms per fresh dispatch (see
    ``WALK_MEMBERS`` in feature_walk); SolidWorks hands back a fresh
    dispatch on most calls, so flag only what is about to be read.
    """
    attempt(adapter, lambda: _sw_type_info.flag_members(obj, *names), 0)


def as_list(value: Any) -> list[Any]:
    """Normalise a COM array/scalar/None return into a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def selection_count(adapter: Any, model: Any) -> int | None:
    """Number of entities currently selected in ``model``, or None."""
    sel_mgr = attempt(adapter, lambda: model.SelectionManager)
    if sel_mgr is None:
        return None
    flag(adapter, sel_mgr, "GetSelectedObjectCount2")
    count = attempt(adapter, lambda: sel_mgr.GetSelectedObjectCount2(-1))
    return int(count) if isinstance(count, (int, float)) else None


def strip_op_prefix(error: str | None, operation_name: str) -> str | None:
    """Drop ``_handle_com_operation``'s generic ``"Error in <op>: "`` prefix.

    Expected failures (not found, nothing to select, rebuild errors) then read
    as plain sentences for the LLM caller.
    """
    if not error:
        return error
    return error.removeprefix(f"Error in {operation_name}: ")


def string_array(values: list[str]) -> Any:
    """``VARIANT(VT_ARRAY | VT_BSTR)``, e.g. configuration names (tuple when pywin32 is absent)."""
    try:
        import pythoncom
        import win32com.client as w32

        return w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_BSTR, [str(v) for v in values]
        )
    except ImportError:  # non-Windows
        return tuple(values)


def double_array(values: list[float]) -> Any:
    """``VARIANT(VT_ARRAY | VT_R8)`` for array-valued COM properties (tuple when pywin32 is absent)."""
    try:
        import pythoncom
        import win32com.client as w32

        return w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values]
        )
    except ImportError:  # non-Windows
        return tuple(values)


def dispatch_array(values: list[Any]) -> Any:
    """``VARIANT(VT_ARRAY | VT_DISPATCH)``, e.g. edges for a flange (tuple when pywin32 is absent)."""
    try:
        import pythoncom
        import win32com.client as w32

        return w32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(values))
    except ImportError:  # non-Windows
        return tuple(values)
