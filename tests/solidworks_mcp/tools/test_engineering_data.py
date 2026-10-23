"""Tests for engineering-data tools and their pure helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from solidworks_mcp.adapters.solidworks.documentation import (
    _parse_material_library,
    _parse_measure_spec,
    _unpack_custom_property,
)
from solidworks_mcp.tools.engineering_data import (
    CustomPropertiesInput,
    ExportFlatPatternInput,
    GetMaterialInput,
    ListMaterialsInput,
    ListModelDimensionsInput,
    MeasureEntitiesInput,
    SetCustomPropertyInput,
    SetMaterialInput,
    register_engineering_data_tools,
)


async def _tool(mcp_server: Any, name: str) -> Any:
    return next(t.fn for t in await mcp_server.list_tools() if t.name == name)


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


class TestEngineeringDataTools:
    """Tools exercised end to end against the mock adapter."""

    @pytest.mark.asyncio
    async def test_register_count(self, mcp_server, mock_adapter, mock_config) -> None:
        count = await register_engineering_data_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert count == len(await mcp_server.list_tools()) == 8

    @pytest.mark.asyncio
    async def test_material_round_trip(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        set_result = await (await _tool(mcp_server, "set_material"))(
            input_data=SetMaterialInput(material_name="AISI 1020")
        )
        assert set_result["status"] == "success"
        got = await (await _tool(mcp_server, "get_material"))(
            input_data=GetMaterialInput()
        )
        assert got["data"]["material"] == "AISI 1020"

    @pytest.mark.asyncio
    async def test_unknown_material_is_an_error(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        result = await (await _tool(mcp_server, "set_material"))(
            input_data=SetMaterialInput(material_name="Unobtainium")
        )
        assert result["status"] == "error"
        assert "not applied" in result["message"]

    @pytest.mark.asyncio
    async def test_list_materials_filter(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        result = await (await _tool(mcp_server, "list_available_materials"))(
            input_data=ListMaterialsInput(search="steel")
        )
        assert {m["classification"] for m in result["data"]} == {"Steel"}

    @pytest.mark.asyncio
    async def test_custom_property_round_trip(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        await (await _tool(mcp_server, "set_custom_property"))(
            input_data=SetCustomPropertyInput(name="PartNo", value="P-001")
        )
        result = await (await _tool(mcp_server, "get_custom_properties"))(
            input_data=CustomPropertiesInput()
        )
        assert result["data"]["properties"]["PartNo"]["value"] == "P-001"

    @pytest.mark.asyncio
    async def test_dimensions_and_measure(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        dims = await (await _tool(mcp_server, "list_model_dimensions"))(
            input_data=ListModelDimensionsInput()
        )
        assert dims["status"] == "success"
        assert all("@" in d["full_name"] for d in dims["data"])
        measured = await (await _tool(mcp_server, "measure_entities"))(
            input_data=MeasureEntitiesInput(entities=["face:0,0.01,0", "face:0,0,0"])
        )
        assert "distance_m" in measured["data"]

    @pytest.mark.asyncio
    async def test_part_only_tools_refuse_drawings(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_drawing()
        result = await (await _tool(mcp_server, "export_flat_pattern"))(
            input_data=ExportFlatPatternInput(file_path="C:/out/flat.dxf")
        )
        assert result["status"] == "error"
        assert "part" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_adapter_method_is_reported(
        self, mcp_server, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, object(), mock_config)
        result = await (await _tool(mcp_server, "get_material"))(
            input_data=GetMaterialInput()
        )
        assert result["status"] == "error"
        assert "does not support get_material" in result["message"]
