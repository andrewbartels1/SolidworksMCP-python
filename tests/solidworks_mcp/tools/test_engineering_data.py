"""Tests for engineering-data tools and their pure helpers."""

from __future__ import annotations

from typing import Any

import pytest

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


@pytest.mark.asyncio
async def test_export_flat_pattern_reports_the_written_file(
    mcp_server, mock_adapter, mock_config
) -> None:
    await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
    await mock_adapter.create_part()

    result = await (await _tool(mcp_server, "export_flat_pattern"))(
        {"file_path": "C:/out/flat.dxf"}
    )

    assert result["status"] == "success"
    assert result["message"] == "Exported the flat pattern to C:/out/flat.dxf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "payload", "setup", "error_type"),
    [
        ("get_material", {}, "create_drawing", "wrong_document_type"),
        (
            "list_model_dimensions",
            {"feature_name": "Fillet9"},
            "create_part",
            "not_found",
        ),
        ("set_material", {"material_name": "AISI 1020"}, None, "wrong_document_type"),
        ("measure_entities", {"entities": []}, "create_part", "invalid_input"),
    ],
)
async def test_failures_carry_an_actionable_error_type(
    mcp_server, mock_adapter, mock_config, tool, payload, setup, error_type
) -> None:
    await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
    if setup:
        await getattr(mock_adapter, setup)()

    result = await (await _tool(mcp_server, tool))(payload)

    assert result["status"] == "error"
    assert result["error_type"] == error_type, result
    assert result["hint"]


@pytest.mark.asyncio
async def test_list_available_materials_says_what_it_searched(
    mcp_server, mock_config
) -> None:
    from types import SimpleNamespace

    from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

    async def list_available_materials(_search):
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=[],
            metadata={"folders": ["C:/a", "C:/b"], "total": 12},
        )

    adapter = SimpleNamespace(list_available_materials=list_available_materials)
    await register_engineering_data_tools(mcp_server, adapter, mock_config)

    result = await (await _tool(mcp_server, "list_available_materials"))(
        {"search": "1020"}
    )

    assert result["message"] == "Found 0 material(s) of 12 in C:/a; C:/b"
