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
    ``_WALK_MEMBERS`` in pywin32_adapter); SolidWorks hands back a fresh
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
