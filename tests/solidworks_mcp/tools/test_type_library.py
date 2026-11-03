"""Reading the SolidWorks type library into the docs index.

The library is faked with the handful of ``ITypeLib`` / ``ITypeInfo`` methods
the reader uses, so these run anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.tools.tool_boundary import ToolOperationError
from solidworks_mcp.tools.type_library import (
    SOLIDWORKS_TYPELIB_GUID,
    ApiInterface,
    TypeLibraryUnavailable,
    choose_version,
    index_type_library,
    load_type_library,
    registered_versions,
    target_version,
    year_of,
)

FUNC, GET, PUT = 1, 2, 4
IN, OUT, IN_OUT = 1, 2, 3
LONG, STRING, BOOL, VOID, HRESULT, PTR, USERDEFINED = 3, 8, 11, 24, 25, 26, 29


class FakeTypeInfo:
    """An ITypeInfo holding a list of functions.

    Each function is ``(names, invkind, args, return typedesc, description)``;
    ``args`` is a list of ``(typedesc, paramflags)``.
    """

    def __init__(
        self,
        name: str,
        functions: Sequence[tuple[Any, ...]] = (),
        refs: dict[int, str] | None = None,
    ) -> None:
        self.name = name
        self.functions = list(functions)
        self.refs = refs or {}

    def GetTypeAttr(self) -> SimpleNamespace:
        return SimpleNamespace(cFuncs=len(self.functions))

    def GetFuncDesc(self, position: int) -> SimpleNamespace:
        _names, invkind, args, rettype, _doc = self.functions[position]
        return SimpleNamespace(
            memid=position,
            invkind=invkind,
            args=tuple((typedesc, flags, None) for typedesc, flags in args),
            rettype=(rettype, 0, None),
        )

    def GetNames(self, memid: int) -> tuple[str, ...]:
        return self.functions[memid][0]

    def GetDocumentation(self, memid: int) -> tuple[Any, ...]:
        if memid == -1:
            return (self.name, None, 0, None)
        return (self.functions[memid][0][0], self.functions[memid][4], 0, None)

    def GetRefTypeInfo(self, href: int) -> FakeTypeInfo:
        return FakeTypeInfo(self.refs[href])


class FakeTypeLib:
    """An ITypeLib over ``(name, typekind, typeinfo)`` entries."""

    def __init__(self, entries: list[tuple[str, int, FakeTypeInfo]]) -> None:
        self.entries = entries

    def GetTypeInfoCount(self) -> int:
        return len(self.entries)

    def GetTypeInfoType(self, position: int) -> int:
        return self.entries[position][1]

    def GetDocumentation(self, position: int) -> tuple[Any, ...]:
        return (self.entries[position][0], None, 0, None)

    def GetTypeInfo(self, position: int) -> FakeTypeInfo:
        return self.entries[position][2]


def _index(*functions: tuple[Any, ...], refs: dict[int, str] | None = None) -> dict:
    """Index one fake dispatch interface ``IThing``; return its record as saved."""
    info = FakeTypeInfo("IThing", functions, refs)
    record = index_type_library(FakeTypeLib([("IThing", 4, info)]))["IThing"]
    assert isinstance(record, ApiInterface)
    return record.model_dump()


def test_a_method_records_parameters_directions_and_return_type() -> None:
    record = _index(
        (
            ("OpenDoc6", "FileName", "Errors", "Warnings", "Flag"),
            FUNC,
            [(STRING, IN), ((PTR, LONG), IN_OUT), ((PTR, LONG), OUT), (BOOL, 0)],
            (PTR, (USERDEFINED, 7)),
            "Opens an existing document",
        ),
        refs={7: "IModelDoc2"},
    )

    assert record["methods"] == ["OpenDoc6"]
    assert record["method_count"] == 1
    assert record["members"]["OpenDoc6"] == {
        "kind": "method",
        "description": "Opens an existing document",
        "parameters": [
            {"name": "FileName", "type": "String", "direction": "in"},
            {"name": "Errors", "type": "Long", "direction": "in_out"},
            {"name": "Warnings", "type": "Long", "direction": "out"},
            # No PARAMFLAG bits at all reads as an input.
            {"name": "Flag", "type": "Boolean", "direction": "in"},
        ],
        "return_type": "IModelDoc2",
    }


@pytest.mark.parametrize(
    ("rettype", "expected"),
    [
        (VOID, None),
        (HRESULT, None),
        (999, "Variant"),
        ((PTR, (PTR, LONG)), "Long"),
        # A SAFEARRAY of Long: SolidWorks passes arrays as Variant.
        ((27, LONG), "Variant"),
    ],
)
def test_return_types(rettype: Any, expected: str | None) -> None:
    record = _index((("Run",), FUNC, [], rettype, None))

    assert record["members"]["Run"]["return_type"] == expected
    # A member with no help string gets an empty description.
    assert record["members"]["Run"]["description"] == ""


def test_a_get_and_put_pair_is_one_read_write_property() -> None:
    record = _index(
        (("Visible",), PUT, [(BOOL, IN)], VOID, "Visibility"),
        (("Visible",), GET, [], BOOL, None),
    )

    assert record["properties"] == ["Visible"]
    assert record["property_count"] == 1
    assert record["members"]["Visible"] == {
        "kind": "property",
        "description": "Visibility",
        "type": "Boolean",
        "access": "read_write",
    }


def test_a_getter_keeps_an_existing_description_and_sets_the_type() -> None:
    record = _index(
        (("Name",), GET, [], STRING, "The name"),
        (("Name",), PUT, [(LONG, IN)], VOID, "ignored"),
    )

    assert record["members"]["Name"] == {
        "kind": "property",
        "description": "The name",
        "type": "String",
        "access": "read_write",
    }


def test_read_only_and_write_only_properties() -> None:
    record = _index(
        (("Extension",), GET, [], (PTR, (USERDEFINED, 1)), "Extension"),
        (("Password",), PUT, [(STRING, IN)], VOID, ""),
        refs={1: "IModelDocExtension"},
    )

    assert record["members"]["Extension"]["type"] == "IModelDocExtension"
    assert record["members"]["Extension"]["access"] == "read"
    assert record["members"]["Password"]["type"] == "String"
    assert record["members"]["Password"]["access"] == "write"


def test_a_name_that_is_both_a_method_and_a_property_is_a_method() -> None:
    record = _index(
        (("Material",), GET, [], STRING, ""),
        (("Material",), FUNC, [], STRING, ""),
        (("Rebuild",), FUNC, [], BOOL, ""),
        (("Rebuild",), GET, [], BOOL, ""),
    )

    assert record["methods"] == ["Material", "Rebuild"]
    assert record["properties"] == []


def test_a_setters_unnamed_value_argument_is_called_value() -> None:
    record = _index((("Size",), FUNC, [(LONG, IN)], VOID, ""))

    assert record["members"]["Size"]["parameters"][0]["name"] == "Value"


def test_com_plumbing_and_hidden_names_are_skipped() -> None:
    plumbing = [
        ((name,), FUNC, [], VOID, "")
        for name in ("QueryInterface", "AddRef", "Release", "Invoke", "_Hidden")
    ]
    record = _index(*plumbing, (("GetTitle",), FUNC, [], STRING, ""))

    assert record["methods"] == ["GetTitle"]


def test_only_dispatch_interfaces_are_indexed() -> None:
    lib = FakeTypeLib(
        [
            ("ISldWorks", 4, FakeTypeInfo("ISldWorks")),
            ("SldWorks", 5, FakeTypeInfo("SldWorks")),
            ("IVtable", 3, FakeTypeInfo("IVtable")),
        ]
    )

    assert list(index_type_library(lib)) == ["ISldWorks"]


class FakeKey:
    """A registry key handle, usable as a context manager."""

    def __init__(self, subkeys: list[str]) -> None:
        self.subkeys = subkeys

    def __enter__(self) -> FakeKey:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class FakeRegistry:
    """``winreg`` with one TypeLib key holding the given version subkeys."""

    HKEY_CLASSES_ROOT = "HKCR"

    def __init__(self, subkeys: list[str] | None) -> None:
        self.subkeys = subkeys
        self.opened: list[tuple[str, str]] = []

    def OpenKey(self, root: str, path: str) -> FakeKey:
        self.opened.append((root, path))
        if self.subkeys is None:
            raise FileNotFoundError(path)
        return FakeKey(self.subkeys)

    def QueryInfoKey(self, key: FakeKey) -> tuple[int, int, int]:
        return (len(key.subkeys), 0, 0)

    def EnumKey(self, key: FakeKey, position: int) -> str:
        return key.subkeys[position]


def test_registered_versions_parses_hex_keys() -> None:
    # "1.0" would read as SolidWorks 1993, before its first release (1995).
    registry = FakeRegistry(["22.0", "1.0", "21", "bad.x", "3.0"])

    assert registered_versions(registry) == [(34, 0), (33, 0), (3, 0)]
    assert registry.opened == [("HKCR", rf"TypeLib\{SOLIDWORKS_TYPELIB_GUID}")]


def test_registered_versions_is_empty_without_the_key() -> None:
    assert registered_versions(FakeRegistry(None)) == []


def test_choose_version_by_year_or_newest() -> None:
    registered = [(33, 0), (34, 0), (34, 1)]

    assert choose_version(registered, 2025, strict=True) == (33, 0)
    assert choose_version(registered, 2026, strict=False) == (34, 1)
    assert choose_version(registered, None, strict=False) == (34, 1)
    # A configured or detected year that isn't registered falls back.
    assert choose_version(registered, 2030, strict=False) == (34, 1)


def test_choose_version_names_the_installed_years_for_a_missing_year() -> None:
    with pytest.raises(TypeLibraryUnavailable) as raised:
        choose_version([(34, 0), (33, 0), (34, 1)], 2024, strict=True)

    assert str(raised.value) == (
        "SolidWorks 2024 isn't installed here; installed: 2025, 2026, 2026."
    )


def test_choose_version_without_solidworks_installed() -> None:
    with pytest.raises(TypeLibraryUnavailable, match="needs SolidWorks installed"):
        choose_version([], None, strict=False)


class FakeCom:
    """``pythoncom``'s two type library loaders and its error type."""

    com_error = OSError

    def __init__(self, missing_file: bool = False) -> None:
        self.loaded: list[tuple[str, int, int]] = []
        self.missing_file = missing_file

    def LoadRegTypeLib(self, guid: str, major: int, minor: int) -> str:
        self.loaded.append((guid, major, minor))
        if self.missing_file:
            raise self.com_error("Error loading type library/DLL.")
        return "the library"

    def QueryPathOfRegTypeLib(self, guid: str, major: int, minor: int) -> str:
        return r"C:\SOLIDWORKS\sldworks.tlb"


def test_load_type_library_reports_where_it_came_from() -> None:
    com = FakeCom()

    lib, info = load_type_library(
        2026, strict=True, com=com, registry=FakeRegistry(["22.0", "21.0"])
    )

    assert lib == "the library"
    assert com.loaded == [(SOLIDWORKS_TYPELIB_GUID, 34, 0)]
    assert info.model_dump() == {
        "guid": SOLIDWORKS_TYPELIB_GUID,
        "version": "34.0",
        "year": 2026,
        "path": r"C:\SOLIDWORKS\sldworks.tlb",
    }


def test_a_registered_library_whose_file_is_gone_says_so() -> None:
    with pytest.raises(TypeLibraryUnavailable) as raised:
        load_type_library(
            com=FakeCom(missing_file=True), registry=FakeRegistry(["22.0"])
        )

    assert str(raised.value) == (
        "SolidWorks 2026's type library is registered but couldn't be loaded "
        "(Error loading type library/DLL.); repairing that SolidWorks install "
        "restores it."
    )


def test_load_type_library_without_pywin32_or_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import solidworks_mcp.tools.type_library as module

    monkeypatch.setattr(module, "pythoncom", None)
    monkeypatch.setattr(module, "winreg", None)

    with pytest.raises(TypeLibraryUnavailable, match="needs Windows with pywin32"):
        load_type_library(registry=FakeRegistry(["22.0"]))
    with pytest.raises(TypeLibraryUnavailable, match="needs Windows with pywin32"):
        load_type_library(com=FakeCom())


def test_target_version_reads_the_registry_without_loading() -> None:
    registry = FakeRegistry(["22.0", "21.0"])

    assert target_version(2025, strict=True, registry=registry) == (33, 0)
    assert target_version(registry=registry) == (34, 0)
    assert year_of(34) == 2026


def test_an_unavailable_type_library_is_a_tool_error() -> None:
    # The tool boundary turns it into the usual error payload.
    assert issubclass(TypeLibraryUnavailable, ToolOperationError)


def test_imports_without_pywin32_or_winreg(import_without) -> None:
    attrs = import_without(
        "solidworks_mcp.tools.type_library",
        ["pythoncom", "winreg"],
        ["pythoncom", "winreg"],
    )

    assert attrs == {"pythoncom": None, "winreg": None}
