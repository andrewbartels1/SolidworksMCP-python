"""Tests for sw_type_info method flagging helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_import_handles_missing_pywin32(monkeypatch) -> None:
    """Import should handle missing win32com gracefully."""
    # Load the module under an alias while forcing win32com to fail.
    import builtins

    original_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name.startswith("win32com"):
            raise ImportError("blocked")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    module_path = (
        Path(__file__).parents[3]
        / "src"
        / "solidworks_mcp"
        / "adapters"
        / "sw_type_info.py"
    )
    spec = importlib.util.spec_from_file_location(
        "sw_type_info_no_pywin32", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.PYWIN32_AVAILABLE is False


def test_interface_method_names_empty_when_unloaded(monkeypatch) -> None:
    """interface_method_names should return empty set when wrapper missing."""
    # Force the module to behave as if pywin32 is unavailable.
    from solidworks_mcp.adapters import sw_type_info

    monkeypatch.setattr(sw_type_info, "PYWIN32_AVAILABLE", False)
    sw_type_info._wrapper_module = None
    sw_type_info._interface_methods.clear()

    result = sw_type_info.interface_method_names("ISldWorks")
    assert result == frozenset()


def test_flag_methods_returns_zero_when_no_methods(monkeypatch) -> None:
    """flag_methods should no-op when no interface methods are loaded."""
    # Ensure we return zero when nothing is loaded to flag.
    from solidworks_mcp.adapters import sw_type_info

    monkeypatch.setattr(sw_type_info, "_interface_methods", {})
    assert sw_type_info.flag_methods(object(), "ISldWorks") == 0


def test_flagged_passes_through_none() -> None:
    """flagged should return None when obj is None."""
    # Validate the None short-circuit in flagged().
    from solidworks_mcp.adapters import sw_type_info

    assert sw_type_info.flagged(None, "ISldWorks") is None


def test_invalidate_flag_cache_clears_and_pops() -> None:
    """invalidate_flag_cache should clear or remove entries."""
    # Validate both the full clear and per-object pop behavior.
    from solidworks_mcp.adapters import sw_type_info

    obj = object()
    sw_type_info._flag_cache[id(obj)] = {"ISldWorks"}
    sw_type_info.invalidate_flag_cache(obj)
    assert id(obj) not in sw_type_info._flag_cache

    sw_type_info._flag_cache[id(obj)] = {"ISldWorks"}
    sw_type_info.invalidate_flag_cache()
    assert sw_type_info._flag_cache == {}


def test_load_wrapper_warns_when_genpy_missing(monkeypatch) -> None:
    """_load_wrapper should warn when gen_py is unavailable."""
    # Simulate gencache failing to load or generate a wrapper module.
    from solidworks_mcp.adapters import sw_type_info

    warnings: list[str] = []

    class _FakeCache:
        @staticmethod
        def GetModuleForTypelib(*_a, **_kw):
            return None

        @staticmethod
        def EnsureModule(*_a, **_kw):
            raise RuntimeError("no gen_py")

    monkeypatch.setattr(sw_type_info, "PYWIN32_AVAILABLE", True)
    monkeypatch.setattr(sw_type_info, "gencache", _FakeCache, raising=False)
    monkeypatch.setattr(
        sw_type_info,
        "logger",
        SimpleNamespace(warning=lambda msg: warnings.append(msg)),
    )
    sw_type_info._wrapper_module = None
    sw_type_info._interface_methods.clear()

    sw_type_info._load_wrapper()

    assert sw_type_info._wrapper_module is None
    assert any("gen_py wrapper not available" in msg for msg in warnings)
