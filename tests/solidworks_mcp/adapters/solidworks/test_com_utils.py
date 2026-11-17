"""Tests for the small COM helpers shared by the selection and rebuild code."""

from __future__ import annotations

import builtins
import sys
from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters.solidworks.com_utils import (
    as_list,
    dispatch_array,
    double_array,
    string_array,
    strip_op_prefix,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, []), ((1, 2), [1, 2]), ([3], [3]), ("scalar", ["scalar"])],
)
def test_as_list_normalises_com_returns(value: object, expected: list) -> None:
    assert as_list(value) == expected


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, None),
        ("", ""),
        ("Error in select_feature: Feature not found", "Feature not found"),
        ("Feature not found", "Feature not found"),
    ],
)
def test_strip_op_prefix(error: str | None, expected: str | None) -> None:
    assert strip_op_prefix(error, "select_feature") == expected


class TestStringArray:
    def test_variant_on_windows(self, monkeypatch) -> None:
        fake_w32 = SimpleNamespace(VARIANT=lambda vt, values: ("VARIANT", vt, values))
        monkeypatch.setitem(
            sys.modules, "pythoncom", SimpleNamespace(VT_ARRAY=0x2000, VT_BSTR=8)
        )
        monkeypatch.setitem(sys.modules, "win32com", SimpleNamespace(client=fake_w32))
        monkeypatch.setitem(sys.modules, "win32com.client", fake_w32)
        assert string_array(["Default", 2]) == ("VARIANT", 0x2008, ["Default", "2"])

    def test_plain_tuple_without_pywin32(self, monkeypatch) -> None:
        real_import = builtins.__import__

        def no_pythoncom(name, *args, **kwargs):
            if name == "pythoncom":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_pythoncom)
        assert string_array(["Long"]) == ("Long",)


class TestDoubleArray:
    def test_variant_on_windows(self, monkeypatch) -> None:
        fake_w32 = SimpleNamespace(VARIANT=lambda vt, values: ("VARIANT", vt, values))
        monkeypatch.setitem(
            sys.modules,
            "pythoncom",
            SimpleNamespace(VT_ARRAY=0x2000, VT_R8=5),
        )
        monkeypatch.setitem(sys.modules, "win32com", SimpleNamespace(client=fake_w32))
        monkeypatch.setitem(sys.modules, "win32com.client", fake_w32)
        assert double_array([1, 2]) == ("VARIANT", 0x2005, [1.0, 2.0])

    def test_plain_tuple_without_pywin32(self, monkeypatch) -> None:
        real_import = builtins.__import__

        def no_pythoncom(name, *args, **kwargs):
            if name == "pythoncom":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_pythoncom)
        assert double_array([1.0, 2.0]) == (1.0, 2.0)


class TestDispatchArray:
    def test_variant_on_windows(self, monkeypatch) -> None:
        fake_w32 = SimpleNamespace(VARIANT=lambda vt, values: ("VARIANT", vt, values))
        monkeypatch.setitem(
            sys.modules, "pythoncom", SimpleNamespace(VT_ARRAY=0x2000, VT_DISPATCH=9)
        )
        monkeypatch.setitem(sys.modules, "win32com", SimpleNamespace(client=fake_w32))
        monkeypatch.setitem(sys.modules, "win32com.client", fake_w32)
        edge = object()
        assert dispatch_array([edge]) == ("VARIANT", 0x2009, [edge])

    def test_plain_tuple_without_pywin32(self, monkeypatch) -> None:
        real_import = builtins.__import__

        def no_pythoncom(name, *args, **kwargs):
            if name == "pythoncom":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_pythoncom)
        assert dispatch_array(["edge"]) == ("edge",)
