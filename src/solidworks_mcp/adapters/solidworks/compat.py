"""COM calls whose shape differs between SolidWorks releases.

The adapter is written and checked live against SolidWorks 2026. Reports
from SolidWorks 2024 (#255, #264-#276) show two kinds of difference, and
this module handles the first one in one place:

1. **The same member, another dispatch kind.** A member SolidWorks 2026
   answers as a method may only answer as a property on another release, or
   the reverse; pywin32 then gets ``DISP_E_MEMBERNOTFOUND`` ("Member not
   found", #265: every equation tool on 2024). :func:`invoke` and
   :func:`read` make the call exactly as before, so 2026 is unchanged, and
   only on "Member not found" retry it through ``IDispatch.Invoke`` with
   both dispatch kinds allowed.
2. **The same member, another argument list** (#255: ``FeatureFillet3``
   took 15 arguments on one interface and 14 on another). These are fixed
   where they occur, by calling the one form every release has; they are
   listed in ``docs/agents/com-api-pitfalls.md``.

Every member that needed the retry is recorded in :data:`fallbacks`, which
``selftest`` reports, so a report from a release we don't have names the
members that differ there.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

#: ``DISP_E_MEMBERNOTFOUND``: the member exists but not as invoked.
DISP_E_MEMBERNOTFOUND = -2147352573
#: ``DISPATCH_METHOD | DISPATCH_PROPERTYGET``: either kind will do.
_METHOD_OR_GET = 1 | 2

#: Members that answered only through the retry this session, as
#: ``"Interface.Member"`` (or the bare member name).
fallbacks: set[str] = set()


def member_not_found(exc: BaseException) -> bool:
    """Whether ``exc`` is SolidWorks' "Member not found"."""
    code = exc.args[0] if exc.args else None
    if code == DISP_E_MEMBERNOTFOUND:
        return True
    return "member not found" in str(exc).lower()


def _either_kind(obj: Any, name: str, args: tuple[Any, ...], label: str) -> Any:
    """Call ``name`` through ``IDispatch.Invoke``, method or property get."""
    dispatch = obj._oleobj_
    dispid = dispatch.GetIDsOfNames(name)
    result = dispatch.Invoke(dispid, 0, _METHOD_OR_GET, True, *args)
    if label not in fallbacks:
        fallbacks.add(label)
        logger.info("[compat] {} answered only as the other dispatch kind", label)
    return result


def invoke(obj: Any, name: str, *args: Any, interface: str = "") -> Any:
    """Call method ``name`` with ``args`` on any SolidWorks release.

    Made exactly as ``obj.name(*args)`` first; on "Member not found" only,
    retried with either dispatch kind (an indexed property such as
    ``IEquationMgr.Equation(i)`` may be property-only there).

    Raises:
        Exception: Whatever the call raised, when it isn't "Member not
            found", or when the retry fails too.
    """
    try:
        return getattr(obj, name)(*args)
    except Exception as exc:  # noqa: BLE001 - re-raised unless it's the one we handle
        if not member_not_found(exc):
            raise
    return _either_kind(obj, name, args, f"{interface}.{name}" if interface else name)


def read(obj: Any, name: str, *, interface: str = "") -> Any:
    """Read property ``name`` on any SolidWorks release.

    Read exactly as ``obj.name`` first; on "Member not found" only, read
    with either dispatch kind (it may be a method there).

    Raises:
        Exception: Whatever the read raised, when it isn't "Member not
            found", or when the retry fails too.
    """
    try:
        return getattr(obj, name)
    except Exception as exc:  # noqa: BLE001 - re-raised unless it's the one we handle
        if not member_not_found(exc):
            raise
    return _either_kind(obj, name, (), f"{interface}.{name}" if interface else name)


def release_year(revision: str | None) -> int | None:
    """The SolidWorks year from ``ISldWorks.RevisionNumber`` (``"32.5.0"``).

    Major 32 is 2024, 33 is 2025, 34 is 2026: year = major + 1992.
    """
    major = str(revision or "").split(".", 1)[0]
    return int(major) + 1992 if major.isdigit() and int(major) >= 20 else None
