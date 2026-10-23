"""Tests for SolidWorksDocumentationMixin (engineering data) with fake COM objects."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import documentation as doc
from solidworks_mcp.adapters.solidworks.documentation import (
    SolidWorksDocumentationMixin,
    _parse_material_library,
    _parse_measure_spec,
    _unpack_custom_property,
)

_SLDMAT = """<?xml version="1.0" encoding="UTF-8"?>
<mstns:materials xmlns:mstns="http://www.solidworks.com/sldmaterials">
  <classification name="Steel">
    <material name="AISI 1020"/>
    <material name="AISI 304"/>
    <material/>
    <note name="ignored"/>
  </classification>
  <classification name="Aluminium Alloys">
    <material name="6061-T6 (SS)"/>
  </classification>
</mstns:materials>
"""


@pytest.fixture(autouse=True)
def _plain_com(monkeypatch) -> None:
    """Fake objects need no method flagging or dispatch wrapping."""
    monkeypatch.setattr(
        doc, "_sw_type_info", SimpleNamespace(flagged=lambda obj, *_: obj)
    )
    monkeypatch.setattr(doc, "_as_com", lambda _adapter, obj, _iface: obj)
    monkeypatch.setattr(doc, "_null_callout", lambda: None)


class _Harness(SolidWorksDocumentationMixin):
    """The mixin plus the PyWin32Adapter members it relies on."""

    def __init__(self, model: Any = None, app: Any = None) -> None:
        self.currentModel = model
        self.swApp = app

    def _handle_com_operation(self, name, operation, *args):
        try:
            data = operation(*args)
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

    def _attempt(self, operation, default=None):
        try:
            return operation()
        except Exception:
            return default

    def _get_attr_or_call(self, obj, name):
        value = getattr(obj, name)
        return value() if callable(value) else value


def _raise(*_args: Any) -> Any:
    raise RuntimeError("COM call failed")


# ---- module helpers ----------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("edge:0.01,0.02,0.03", ("", 0.01, 0.02, 0.03, "EDGE")),
        ("vertex:Vertex<1>", ("Vertex<1>", 0.0, 0.0, 0.0, "VERTEX")),
        ("edge:a,b,c", ("a,b,c", 0.0, 0.0, 0.0, "EDGE")),
    ],
)
def test_parse_measure_spec_edge_and_vertex_forms(spec, expected) -> None:
    assert doc._parse_measure_spec(spec) == expected


def test_parse_measure_spec_delegates_other_forms_to_the_edge_parser() -> None:
    assert doc._parse_measure_spec("face:0,0.01,0")[4] == "FACE"
    assert doc._parse_measure_spec("0,0,0")[4] == "EDGE"


def test_parse_material_library_reads_names_and_classes(tmp_path) -> None:
    path = tmp_path / "solidworks materials.sldmat"
    path.write_text(_SLDMAT, encoding="utf-8")

    materials = doc._parse_material_library(str(path))

    assert materials == [
        {
            "name": "AISI 1020",
            "classification": "Steel",
            "database": "solidworks materials",
        },
        {
            "name": "AISI 304",
            "classification": "Steel",
            "database": "solidworks materials",
        },
        {
            "name": "6061-T6 (SS)",
            "classification": "Aluminium Alloys",
            "database": "solidworks materials",
        },
    ]


def test_parse_material_library_unreadable_files_are_empty(tmp_path) -> None:
    bad = tmp_path / "bad.sldmat"
    bad.write_text("<not xml", encoding="utf-8")

    assert doc._parse_material_library(str(bad)) == []
    assert doc._parse_material_library(str(tmp_path / "missing.sldmat")) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ("", "")),
        ((0, "$PRP:SW-Mass", "1.2"), ("$PRP:SW-Mass", "1.2")),
        ((True, "x"), ("x", "x")),
        ((0, 1), ("", "")),
        (["only"], ("only", "only")),
    ],
)
def test_unpack_custom_property_shapes(raw, expected) -> None:
    assert doc._unpack_custom_property(raw) == expected


def test_read_custom_property_prefers_get6() -> None:
    manager = SimpleNamespace(Get6=lambda *_: (0, "A", "A1"), Get=_raise)
    assert doc._read_custom_property(_Harness(), manager, "Rev") == ("A", "A1")


def test_read_custom_property_falls_back_to_get() -> None:
    manager = SimpleNamespace(Get6=_raise, Get=lambda _name: "B")
    assert doc._read_custom_property(_Harness(), manager, "Rev") == ("B", "B")


def test_read_custom_property_non_text_reads_as_empty() -> None:
    manager = SimpleNamespace(Get6=_raise, Get=lambda _name: None)
    assert doc._read_custom_property(_Harness(), manager, "Rev") == ("", "")


@pytest.mark.parametrize(
    ("full_name", "expected"),
    [
        (None, None),
        ("D1@Sketch1@Part1.Part", "D1@Sketch1"),
        ("D1@Sketch1", "D1@Sketch1"),
    ],
)
def test_strip_document_suffix(full_name, expected) -> None:
    assert doc._strip_document_suffix(full_name) == expected


def test_sequence_normalises_com_arrays() -> None:
    assert doc._sequence(None) == []
    assert doc._sequence((1, None, 2)) == [1, 2]
    assert doc._sequence("one") == ["one"]


# ---- document-type guard -------------------------------------------------------


@pytest.mark.asyncio
async def test_guard_needs_an_active_model() -> None:
    result = await _Harness().get_material()
    assert result.error == "No active model"


@pytest.mark.asyncio
async def test_guard_names_the_wrong_document_type() -> None:
    result = await _Harness(SimpleNamespace(GetType=lambda: 3)).get_material()
    assert result.error == (
        "get_material needs an active part document (active document is drawing)."
    )


@pytest.mark.asyncio
async def test_guard_reports_an_unreadable_type_as_unknown() -> None:
    result = await _Harness(SimpleNamespace(GetType=_raise)).list_model_dimensions()
    assert "part or assembly" in result.error
    assert "unknown" in result.error


# ---- list_model_dimensions ----------------------------------------------------


class _Feature:
    def __init__(self, name: str, dims: list[Any], nxt: Any = None) -> None:
        self.Name = name
        self._displays = [
            SimpleNamespace(GetDimension2=lambda _i, d=d: d) for d in dims
        ]
        self._next = nxt

    def GetFirstDisplayDimension(self):  # noqa: N802 - COM name
        return self._displays[0] if self._displays else None

    def GetNextDisplayDimension(self, display):  # noqa: N802 - COM name
        index = self._displays.index(display) + 1
        return self._displays[index] if index < len(self._displays) else None

    def GetNextFeature(self):  # noqa: N802 - COM name
        return self._next


def _dim(full_name: str, value: float) -> SimpleNamespace:
    return SimpleNamespace(
        FullName=full_name, Value=value, SystemValue=value / 1000, ReadOnly=False
    )


def _part_with_dims() -> SimpleNamespace:
    boss = _Feature("Boss-Extrude1", [_dim("D1@Boss-Extrude1@Part1.Part", 10.0)])
    sketch = _Feature("Sketch1", [_dim("D1@Sketch1@Part1.Part", 40.0), None], boss)
    return SimpleNamespace(GetType=lambda: 1, FirstFeature=lambda: sketch)


@pytest.mark.asyncio
async def test_list_model_dimensions_walks_every_feature() -> None:
    result = await _Harness(_part_with_dims()).list_model_dimensions()

    assert result.is_success
    assert result.data == [
        {
            "full_name": "D1@Sketch1",
            "feature": "Sketch1",
            "value": 40.0,
            "system_value": 0.04,
            "read_only": False,
        },
        {
            "full_name": "D1@Boss-Extrude1",
            "feature": "Boss-Extrude1",
            "value": 10.0,
            "system_value": 0.01,
            "read_only": False,
        },
    ]


@pytest.mark.asyncio
async def test_list_model_dimensions_filters_by_feature_case_insensitively() -> None:
    result = await _Harness(_part_with_dims()).list_model_dimensions("boss-extrude1")
    assert [d["full_name"] for d in result.data] == ["D1@Boss-Extrude1"]


@pytest.mark.asyncio
async def test_list_model_dimensions_unknown_feature_is_not_found() -> None:
    result = await _Harness(_part_with_dims()).list_model_dimensions("Fillet9")
    assert not result.is_success
    assert "No dimensions found on feature 'Fillet9'" in result.error


# ---- measure_entities ---------------------------------------------------------


class _Measure:
    Distance = 0.025
    Angle = -1
    Area = 0.0012
    Length = "n/a"
    IsParallel = True

    def __init__(self, calculates: bool = True) -> None:
        self._calculates = calculates

    def Calculate(self, _selection):  # noqa: N802 - COM name
        return self._calculates


def _measurable(
    selects: bool = True, measure: Any = None, parallel: Any = True
) -> SimpleNamespace:
    if measure is not None:
        measure.IsParallel = parallel
    extension = SimpleNamespace(
        SelectByID2=lambda *_args: selects, CreateMeasure=lambda: measure
    )
    return SimpleNamespace(
        GetType=lambda: 1, Extension=extension, ClearSelection2=lambda _all: None
    )


@pytest.mark.asyncio
async def test_measure_entities_reports_applicable_values(monkeypatch) -> None:
    picks: list[tuple] = []
    monkeypatch.setattr(
        doc,
        "_select_edge_by_coord",
        lambda _adapter, x, y, z, append, _mark, kind: (
            picks.append((x, y, z, append, kind)) or True
        ),
    )
    harness = _Harness(_measurable(measure=_Measure()))

    result = await harness.measure_entities(["Edge<1>", "face:0,0.01,0"])

    assert result.is_success
    assert result.data == {
        "selected": ["Edge<1>", "face:0,0.01,0"],
        "distance_m": 0.025,
        "area_m2": 0.0012,
        "is_parallel": True,
    }
    assert picks == [(0.0, 0.01, 0.0, True, "FACE")]


@pytest.mark.asyncio
async def test_measure_entities_omits_a_non_boolean_parallel_flag() -> None:
    harness = _Harness(_measurable(measure=_Measure(), parallel=None))
    result = await harness.measure_entities(["Edge<1>"])
    assert "is_parallel" not in result.data


@pytest.mark.asyncio
@pytest.mark.parametrize("entities", [[], ["Edge<1>", "Edge<2>", "Edge<3>"]])
async def test_measure_entities_takes_one_or_two_specs(entities) -> None:
    result = await _Harness(_measurable()).measure_entities(entities)
    assert result.error == "measure_entities takes one or two entity specs"


@pytest.mark.asyncio
async def test_measure_entities_reports_an_unselectable_entity() -> None:
    result = await _Harness(_measurable(selects=False)).measure_entities(["Edge<9>"])
    assert "No entity found for 'Edge<9>'" in result.error


@pytest.mark.asyncio
async def test_measure_entities_without_a_measure_tool() -> None:
    result = await _Harness(_measurable(measure=None)).measure_entities(["Edge<1>"])
    assert "CreateMeasure returned nothing" in result.error


@pytest.mark.asyncio
async def test_measure_entities_failed_calculation() -> None:
    harness = _Harness(_measurable(measure=_Measure(calculates=False)))
    result = await harness.measure_entities(["Edge<1>"])
    assert "IMeasure.Calculate failed" in result.error


@pytest.mark.asyncio
async def test_measure_entities_guard() -> None:
    result = await _Harness().measure_entities(["Edge<1>"])
    assert result.error == "No active model"


# ---- material -----------------------------------------------------------------


def _part(material: Any) -> SimpleNamespace:
    state = {"material": material}

    def set_material(_config, _library, name):
        if name != "Unobtainium":
            state["material"] = (name, "SOLIDWORKS Materials", "byref")

    def get_material(_config, database):
        raw = state["material"]
        if isinstance(raw, tuple) and len(raw) == 3:  # SW 2026: name + byref db
            database.value = raw[1]
            return raw[0]
        return raw

    return SimpleNamespace(
        GetType=lambda: 1,
        GetMaterialPropertyName2=get_material,
        SetMaterialPropertyName2=set_material,
        EditRebuild3=lambda: True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "material", "database"),
    [
        (("AISI 1020", "SOLIDWORKS Materials"), "AISI 1020", "SOLIDWORKS Materials"),
        (
            ("AISI 304", "SOLIDWORKS Materials", "byref"),
            "AISI 304",
            "SOLIDWORKS Materials",
        ),
        ("ABS", "ABS", None),
        (None, None, None),
    ],
)
async def test_get_material_reads_the_assignment(raw, material, database) -> None:
    result = await _Harness(_part(raw)).get_material("Default")
    assert result.data == {
        "material": material,
        "database": database,
        "configuration": "Default",
    }


@pytest.mark.asyncio
async def test_set_material_reads_it_back() -> None:
    result = await _Harness(_part(None)).set_material("AISI 1020")
    assert result.data == {
        "material": "AISI 1020",
        "database": "SOLIDWORKS Materials",
        "configuration": None,
    }


@pytest.mark.asyncio
async def test_set_material_reports_a_name_that_did_not_apply() -> None:
    result = await _Harness(_part(None)).set_material("Unobtainium", "Custom")
    assert "'Unobtainium' from 'Custom' was not applied" in result.error
    assert "no material" in result.error


@pytest.mark.asyncio
async def test_set_material_needs_a_name() -> None:
    result = await _Harness(_part(None)).set_material("  ")
    assert result.error == "material_name is required"


@pytest.mark.asyncio
async def test_set_material_guard() -> None:
    result = await _Harness().set_material("AISI 1020")
    assert result.error == "No active model"


# ---- list_available_materials ----------------------------------------------


def _library_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sldmaterials"
    folder.mkdir()
    (folder / "solidworks materials.sldmat").write_text(_SLDMAT, encoding="utf-8")
    (folder / "readme.txt").write_text("not a library", encoding="utf-8")
    return folder


def _app(pref: Any, exe: str = "", language: Any = "english") -> SimpleNamespace:
    return SimpleNamespace(
        GetUserPreferenceStringValue=lambda _pref: pref,
        GetExecutablePath=lambda: exe,
        GetCurrentLanguage=lambda: language,
    )


@pytest.mark.asyncio
async def test_list_available_materials_reads_configured_folders(tmp_path) -> None:
    folder = _library_folder(tmp_path)
    app = _app(f"{tmp_path / 'missing'};{folder};")

    result = await _Harness(app=app).list_available_materials()

    assert [m["name"] for m in result.data] == ["AISI 1020", "AISI 304", "6061-T6 (SS)"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("search", "count"), [("1020", 1), ("steel", 2)])
async def test_list_available_materials_filters(tmp_path, search, count) -> None:
    app = _app(str(_library_folder(tmp_path)))
    result = await _Harness(app=app).list_available_materials(search)
    assert len(result.data) == count


@pytest.mark.asyncio
@pytest.mark.parametrize("exe_name", ["SLDWORKS.exe", ""])
async def test_list_available_materials_falls_back_to_the_install(
    tmp_path, exe_name
) -> None:
    install = tmp_path / "SOLIDWORKS"
    target = install / "lang" / "english" / "sldmaterials"
    target.parent.mkdir(parents=True)
    _library_folder(tmp_path).rename(target)
    exe = str(install / exe_name) if exe_name else str(install)

    result = await _Harness(
        app=_app("", exe=exe, language=None)
    ).list_available_materials()

    assert len(result.data) == 3


@pytest.mark.asyncio
async def test_list_available_materials_without_libraries(tmp_path) -> None:
    result = await _Harness(app=_app(str(tmp_path))).list_available_materials()
    assert "No .sldmat libraries found in:" in result.error


@pytest.mark.asyncio
async def test_list_available_materials_needs_solidworks() -> None:
    result = await _Harness().list_available_materials()
    assert result.error == "Not connected to SolidWorks"


# ---- custom properties ----------------------------------------------------------


class _PropertyManager:
    def __init__(self, store: dict[str, str], keep: bool = True) -> None:
        self._store = store
        self._keep = keep
        self.GetNames = lambda: tuple(store)

    def Get6(self, name, _cached):  # noqa: N802 - COM name
        return (0, self._store[name], self._store[name].upper())

    def Get(self, name):  # noqa: N802 - COM name
        return self._store.get(name)

    def Add3(self, name, _kind, value, _option):  # noqa: N802 - COM name
        if self._keep:
            self._store[name] = value
        return 1


def _with_properties(manager: _PropertyManager) -> SimpleNamespace:
    return SimpleNamespace(
        GetType=lambda: 1,
        Extension=SimpleNamespace(CustomPropertyManager=lambda _config: manager),
    )


@pytest.mark.asyncio
async def test_get_custom_properties_reads_every_name() -> None:
    model = _with_properties(_PropertyManager({"PartNo": "p-1", "Rev": "a"}))

    result = await _Harness(model).get_custom_properties()

    assert result.data == {
        "configuration": "",
        "properties": {
            "PartNo": {"value": "p-1", "resolved": "P-1"},
            "Rev": {"value": "a", "resolved": "A"},
        },
    }


@pytest.mark.asyncio
async def test_set_custom_property_reads_it_back() -> None:
    model = _with_properties(_PropertyManager({}))

    result = await _Harness(model).set_custom_property("DrawnBy", "ab", "Default")

    assert result.data == {
        "name": "DrawnBy",
        "value": "ab",
        "resolved": "AB",
        "configuration": "Default",
    }


@pytest.mark.asyncio
async def test_set_custom_property_reports_a_value_that_was_not_stored() -> None:
    model = _with_properties(_PropertyManager({"DrawnBy": "old"}, keep=False))
    result = await _Harness(model).set_custom_property("DrawnBy", "new")
    assert "'DrawnBy' was not stored (Add3 returned 1, read back 'old')" in result.error


@pytest.mark.asyncio
async def test_set_custom_property_needs_a_name() -> None:
    result = await _Harness(_with_properties(_PropertyManager({}))).set_custom_property(
        " ", "x"
    )
    assert result.error == "name is required"


@pytest.mark.asyncio
async def test_custom_properties_need_an_active_model() -> None:
    assert (await _Harness().get_custom_properties()).error == "No active model"
    assert (await _Harness().set_custom_property("A", "b")).error == "No active model"


# ---- export_flat_pattern -----------------------------------------------------


def _sheet_metal_part(sheet_metal: bool, writes: bool = True) -> SimpleNamespace:
    def export(out, *_args):
        if writes:
            Path(out).write_bytes(b"0\nSECTION\n")
        return writes

    body = SimpleNamespace(IsSheetMetal=lambda: sheet_metal)
    return SimpleNamespace(
        GetType=lambda: 1,
        GetBodies2=lambda _kind, _visible: (body,),
        GetPathName=lambda: "C:/parts/bracket.sldprt",
        ExportToDWG2=export,
    )


@pytest.mark.asyncio
async def test_export_flat_pattern_writes_the_file(tmp_path) -> None:
    out = tmp_path / "flat" / "bracket.dxf"

    result = await _Harness(_sheet_metal_part(True)).export_flat_pattern(str(out))

    assert result.data == {"file_path": str(out), "size_bytes": os.path.getsize(out)}


@pytest.mark.asyncio
async def test_export_flat_pattern_needs_a_sheet_metal_body(tmp_path) -> None:
    result = await _Harness(_sheet_metal_part(False)).export_flat_pattern(
        str(tmp_path / "x.dxf")
    )
    assert "has no sheet-metal body" in result.error


@pytest.mark.asyncio
async def test_export_flat_pattern_reports_a_failed_export(tmp_path) -> None:
    result = await _Harness(_sheet_metal_part(True, writes=False)).export_flat_pattern(
        str(tmp_path / "x.dwg")
    )
    assert "ExportToDWG2 did not write" in result.error


@pytest.mark.asyncio
async def test_export_flat_pattern_needs_dxf_or_dwg(tmp_path) -> None:
    result = await _Harness(_sheet_metal_part(True)).export_flat_pattern(
        str(tmp_path / "x.pdf")
    )
    assert result.error == "file_path must end in .dxf or .dwg"


@pytest.mark.asyncio
async def test_export_flat_pattern_guard(tmp_path) -> None:
    result = await _Harness().export_flat_pattern(str(tmp_path / "x.dxf"))
    assert result.error == "No active model"


# ---- the author's helper tests (moved from tests/solidworks_mcp/tools) ----


class TestHelpers:
    """Pure parsing helpers - no COM involved."""

    def test_measure_spec_forms(self) -> None:
        assert _parse_measure_spec("face:0,0.01,0") == ("", 0.0, 0.01, 0.0, "FACE")
        assert _parse_measure_spec("vertex:0.1,0,0") == ("", 0.1, 0.0, 0.0, "VERTEX")
        assert _parse_measure_spec("edge:0,0,0.02") == ("", 0.0, 0.0, 0.02, "EDGE")
        assert _parse_measure_spec("0,0,0.02") == ("", 0.0, 0.0, 0.02, "EDGE")
        assert _parse_measure_spec("Edge<1>") == ("Edge<1>", 0.0, 0.0, 0.0, "EDGE")

    def test_material_library_parses_namespaced_xml(self, tmp_path: Path) -> None:
        sldmat = tmp_path / "my materials.sldmat"
        sldmat.write_text(
            '<?xml version="1.0"?>'
            '<mstns:materials xmlns:mstns="http://www.solidworks.com/sldmaterials">'
            '<classification name="Steel"><material name="AISI 1020"/>'
            '<material name="AISI 304"/></classification>'
            '<classification name="Plastics"><material name="ABS"/></classification>'
            "</mstns:materials>",
            encoding="utf-8",
        )
        found = _parse_material_library(str(sldmat))
        assert [m["name"] for m in found] == ["AISI 1020", "AISI 304", "ABS"]
        assert found[2]["classification"] == "Plastics"
        assert found[0]["database"] == "my materials"

    def test_material_library_bad_file_is_empty(self, tmp_path: Path) -> None:
        bad = tmp_path / "broken.sldmat"
        bad.write_text("<not closed", encoding="utf-8")
        assert _parse_material_library(str(bad)) == []

    def test_unpack_custom_property_shapes(self) -> None:
        assert _unpack_custom_property((0, "$PRP:x", "1.5 kg", True, False)) == (
            "$PRP:x",
            "1.5 kg",
        )
        assert _unpack_custom_property(("P-001", "P-001", False)) == ("P-001", "P-001")
        assert _unpack_custom_property(None) == ("", "")
