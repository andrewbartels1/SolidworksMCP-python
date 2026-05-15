"""
SolidWorks type-library introspection for robust COM method resolution.

Background: pywin32's late-binding (``CDispatch``) sometimes resolves SW
zero-argument methods (``GetType``, ``GetTitle``, ``GetPathName``,
``RevisionNumber`` …) as *properties* instead of methods. Calling them raises
``TypeError: 'int'/'str' object is not callable`` because the property getter
returns the value, and Python tries to call the value.

Fix: call ``CDispatch._FlagAsMethod(name)`` for each method name **that actually
belongs to the object's COM interface**. The calls tell pywin32 to resolve
``name`` via method invocation (IDispatch ``Invoke``), not property access.

This module:

1. Loads the makepy-generated wrapper for ``sldworks.tlb`` (``gen_py``).
2. Builds per-interface sets of method names (``ISldWorks``, ``IModelDoc2``,
   ``IAssemblyDoc``, ``IPartDoc``, ``IDrawingDoc`` …).
3. Exposes ``flag_methods(obj, *interfaces)`` to flag a dispatch in one shot.

Why per-interface rather than flagging everything: flagging an unknown name
triggers a COM ``GetIDsOfNames`` round-trip that fails with ``Unknown name.``.
Those round-trips are ~5 ms each; the full SW TLB has ~6 000 method names
across 482 interfaces, so a naive flag-everything approach costs ~30 s per
object. Per-interface flagging is ~1-3 s.

Fallback: if the gen_py wrapper is missing (e.g. fresh install on a new box),
we attempt lazy generation via ``gencache.EnsureModule``. If that also fails,
``flag_methods`` silently becomes a no-op; callers will fall back to the
original ``TypeError`` symptom on affected methods, but everything else still
works.
"""

from __future__ import annotations

import inspect
from typing import Any

from loguru import logger

try:
    import win32com.client  # noqa: F401 — optional Windows dep
    from win32com.client import DispatchBaseClass, gencache

    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False


# SolidWorks type library IID (stable across SW versions).
SW_TLB_IID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"

# Module state: populated by _load_wrapper() the first time it's needed.
_wrapper_module: Any | None = None
_interface_methods: dict[str, frozenset[str]] = {}
# Per-object record of which interfaces have already been flagged. Keyed by
# id(obj) so ``flag_methods(doc, 'IModelDoc2')`` followed by
# ``flag_methods(doc, 'IAssemblyDoc')`` does incremental work, not a no-op.
_flag_cache: dict[int, set[str]] = {}


def _load_wrapper() -> None:
    """Load the gen_py wrapper and extract per-interface method names.

    Tries ``GetModuleForTypelib`` first (fast path, no COM work), falls back
    to ``EnsureModule`` (may trigger makepy generation), then gives up and
    logs a warning. Probes common SW major versions (33..30) because the
    minor/major numbers change per SW year.
    """
    global _wrapper_module, _interface_methods

    if not PYWIN32_AVAILABLE:
        return

    # Try version numbers from newest to oldest. SW 3DEXPERIENCE R2026x = 34,
    # SW 2025 = 33, SW 2024 = 32, SW 2023 = 31, SW 2022 = 30.
    for major in (35, 34, 33, 32, 31, 30):
        try:
            mod = gencache.GetModuleForTypelib(SW_TLB_IID, 0, major, 0)
        except Exception:
            mod = None
        if mod is not None:
            _wrapper_module = mod
            break

    if _wrapper_module is None:
        # Gen_py wrapper not generated yet — try to generate now.
        for major in (35, 34, 33, 32, 31, 30):
            try:
                gencache.EnsureModule(SW_TLB_IID, 0, major, 0)
                _wrapper_module = gencache.GetModuleForTypelib(SW_TLB_IID, 0, major, 0)
                if _wrapper_module is not None:
                    break
            except Exception:
                continue

    if _wrapper_module is None:
        logger.warning(
            "SolidWorks gen_py wrapper not available; method flagging "
            "disabled. Zero-arg SW methods may raise TypeError. To fix, "
            "run: python -m win32com.client.makepy "
            '"C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\sldworks.tlb"'
        )
        return

    # Build per-interface method sets by inspecting each DispatchBaseClass
    # subclass in the wrapper module.
    for name in dir(_wrapper_module):
        cls = getattr(_wrapper_module, name, None)
        if not (inspect.isclass(cls) and issubclass(cls, DispatchBaseClass)):
            continue
        method_names: set[str] = set()
        for attr_name, attr in vars(cls).items():
            if attr_name.startswith("_"):
                continue
            if callable(attr):
                method_names.add(attr_name)
        if method_names:
            _interface_methods[name] = frozenset(method_names)

    logger.info(
        f"SolidWorks type info loaded: {len(_interface_methods)} interfaces, "
        f"wrapper={_wrapper_module.__name__}"
    )


def _ensure_loaded() -> None:
    """Lazy-load the wrapper on first use."""
    if _wrapper_module is None and PYWIN32_AVAILABLE:
        _load_wrapper()


def interface_method_names(interface: str) -> frozenset[str]:
    """Return the set of method names declared by the given SW interface.

    Args:
        interface: Interface name as it appears in the type library
            (e.g. ``"ISldWorks"``, ``"IModelDoc2"``).

    Returns:
        Immutable set of method names, or an empty set if the interface is
        unknown or the wrapper isn't loaded.
    """
    _ensure_loaded()
    return _interface_methods.get(interface, frozenset())


# Interface sets most tool operations need to flag. When acquiring a doc
# dispatch, always flag IModelDoc2 (base) plus the subclass that matches the
# doc type. For the app root, flag ISldWorks.
DOC_TYPE_TO_INTERFACES: dict[int, tuple[str, ...]] = {
    # Values match swDocumentTypes_e: 1=Part, 2=Assembly, 3=Drawing
    1: ("IModelDoc2", "IPartDoc"),
    2: ("IModelDoc2", "IAssemblyDoc"),
    3: ("IModelDoc2", "IDrawingDoc"),
}


def flag_methods(obj: Any, *interfaces: str) -> int:
    """Flag SW methods on ``obj`` so pywin32 dispatches them as methods,
    not properties.

    Safe to call repeatedly on the same object — results are cached by
    ``id(obj)``. Unknown method names are silently skipped (those are
    the ones that don't belong to the object's real interface).

    Args:
        obj: A pywin32 ``CDispatch`` wrapping a SolidWorks COM object.
        *interfaces: One or more interface names whose methods to flag.
            Common values: ``"ISldWorks"``, ``"IModelDoc2"``,
            ``"IAssemblyDoc"``, ``"IPartDoc"``, ``"IDrawingDoc"``.

    Returns:
        Number of methods successfully flagged.
    """
    _ensure_loaded()

    if not _interface_methods or obj is None:
        return 0

    obj_id = id(obj)
    already = _flag_cache.setdefault(obj_id, set())

    # Only flag methods from interfaces we haven't already processed for
    # this object. Repeats are a no-op; novel interfaces add incrementally.
    new_interfaces = [i for i in interfaces if i not in already]
    if not new_interfaces:
        return 0

    names: set[str] = set()
    for iface in new_interfaces:
        names.update(_interface_methods.get(iface, ()))

    flagged = 0
    for name in names:
        try:
            obj._FlagAsMethod(name)
            flagged += 1
        except Exception:
            # Name not on this dispatch's real interface — skip silently.
            pass

    already.update(new_interfaces)
    return flagged


def flagged(obj: Any, *interfaces: str) -> Any:
    """Flag ``obj``'s methods then return ``obj`` — call-chain friendly.

    Useful for inline flagging of short-lived dispatches::

        config = sw_type_info.flagged(
            model.GetActiveConfiguration(), "IConfiguration"
        )
        name = config.GetName()

    If ``obj`` is ``None`` (e.g. SW returned Nothing), passes through
    unchanged.
    """
    if obj is not None:
        flag_methods(obj, *interfaces)
    return obj


def flag_doc(obj: Any, doc_type: int) -> int:
    """Flag methods for a SolidWorks document dispatch given its type.

    Convenience wrapper around ``flag_methods`` that looks up the correct
    interface list for the document type.

    Args:
        obj: ``CDispatch`` wrapping the document.
        doc_type: Value returned by ``swDoc.GetType()`` — 1=Part, 2=Assembly,
            3=Drawing.

    Returns:
        Number of methods flagged.
    """
    interfaces = DOC_TYPE_TO_INTERFACES.get(doc_type, ("IModelDoc2",))
    return flag_methods(obj, *interfaces)


def invalidate_flag_cache(obj: Any | None = None) -> None:
    """Forget that ``obj`` has been flagged, or clear the cache entirely.

    Needed when a dispatch is closed / re-acquired; the new object at the
    same address would otherwise be treated as already-flagged.
    """
    if obj is None:
        _flag_cache.clear()
    else:
        _flag_cache.pop(id(obj), None)
