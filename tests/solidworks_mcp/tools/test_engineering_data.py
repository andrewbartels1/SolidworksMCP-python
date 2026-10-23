"""Tests for the engineering-data tools (``tools/engineering_data.py``).

Every tool has a success case against the mock adapter, at least one failure
with its actionable ``error_type``, and the missing-capability refusal.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
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

_TOOLS = (
    "list_model_dimensions",
    "measure_entities",
    "get_material",
    "set_material",
    "list_available_materials",
    "get_custom_properties",
    "set_custom_property",
    "export_flat_pattern",
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
        names = {t.name for t in await mcp_server.list_tools()}
        assert count == len(names) == len(_TOOLS)
        assert names == set(_TOOLS)

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
        assert set_result["message"] == "Assigned AISI 1020"
        got = await (await _tool(mcp_server, "get_material"))(
            input_data=GetMaterialInput()
        )
        assert got["data"]["material"] == "AISI 1020"
        assert got["message"] == "Material: AISI 1020"

    @pytest.mark.asyncio
    async def test_no_material_assigned(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        got = await (await _tool(mcp_server, "get_material"))({})
        assert got["status"] == "success"
        assert got["message"] == "No material assigned"
        assert got["data"]["material"] is None

    @pytest.mark.asyncio
    async def test_list_materials_filter(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        result = await (await _tool(mcp_server, "list_available_materials"))(
            input_data=ListMaterialsInput(search="steel")
        )
        assert {m["classification"] for m in result["data"]} == {"Steel"}
        assert result["message"] == "Found 2 material(s) of 4 in mock://sldmaterials"

    @pytest.mark.asyncio
    async def test_custom_property_round_trip(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        written = await (await _tool(mcp_server, "set_custom_property"))(
            input_data=SetCustomPropertyInput(name="PartNo", value="P-001")
        )
        assert written["message"] == "Set custom property PartNo"
        result = await (await _tool(mcp_server, "get_custom_properties"))(
            input_data=CustomPropertiesInput()
        )
        assert result["data"]["properties"]["PartNo"]["value"] == "P-001"
        assert result["message"] == "Read 1 custom propert(ies)"

    @pytest.mark.asyncio
    async def test_dimensions_and_measure(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        mock_adapter._dimensions = {"D1@Sketch1": 30.0, "D1@Boss-Extrude1": 15.0}
        dims = await (await _tool(mcp_server, "list_model_dimensions"))(
            input_data=ListModelDimensionsInput()
        )
        assert dims["status"] == "success"
        assert dims["message"] == "Listed 2 dimension(s)"
        assert all("@" in d["full_name"] for d in dims["data"])
        measured = await (await _tool(mcp_server, "measure_entities"))(
            input_data=MeasureEntitiesInput(entities=["face:0,0.01,0", "face:0,0,0"])
        )
        assert "distance_m" in measured["data"]
        assert measured["message"] == "Measured face:0,0.01,0, face:0,0,0"


@pytest.mark.asyncio
async def test_export_flat_pattern_reports_the_written_file(
    mcp_server, mock_adapter, mock_config
) -> None:
    await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
    await mock_adapter.create_part()

    result = await (await _tool(mcp_server, "export_flat_pattern"))(
        input_data=ExportFlatPatternInput(file_path="C:/out/flat.dxf")
    )

    assert result["status"] == "success"
    assert result["message"] == "Exported the flat pattern to C:/out/flat.dxf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "payload", "setup", "error_type"),
    [
        (
            "list_model_dimensions",
            {"feature_name": "Fillet9"},
            "create_part",
            "not_found",
        ),
        ("list_model_dimensions", {}, "create_drawing", "wrong_document_type"),
        ("measure_entities", {"entities": []}, "create_part", "invalid_input"),
        (
            "measure_entities",
            {"entities": ["Edge<1>"]},
            "create_drawing",
            "wrong_document_type",
        ),
        ("get_material", {}, "create_drawing", "wrong_document_type"),
        ("set_material", {"material_name": "AISI 1020"}, None, "wrong_document_type"),
        ("set_material", {"material_name": "Unobtainium"}, "create_part", "not_found"),
        ("set_material", {"material_name": ""}, "create_part", "invalid_input"),
        ("get_custom_properties", {}, None, "no_active_document"),
        (
            "set_custom_property",
            {"name": "PartNo", "value": "1"},
            None,
            "no_active_document",
        ),
        (
            "set_custom_property",
            {"name": "", "value": "1"},
            "create_part",
            "invalid_input",
        ),
        (
            "export_flat_pattern",
            {"file_path": "C:/out/flat.pdf"},
            "create_part",
            "invalid_input",
        ),
        (
            "export_flat_pattern",
            {"file_path": "C:/out/flat.dxf"},
            "create_drawing",
            "wrong_document_type",
        ),
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
    assert isinstance(result["execution_time"], float)


@pytest.mark.asyncio
async def test_list_available_materials_failure_is_reported(
    mcp_server, mock_config
) -> None:
    async def list_available_materials(_search):
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="No .sldmat libraries found in: C:/empty",
        )

    adapter = SimpleNamespace(list_available_materials=list_available_materials)
    await register_engineering_data_tools(mcp_server, adapter, mock_config)

    result = await (await _tool(mcp_server, "list_available_materials"))({})

    assert result["error_type"] == "not_found"
    assert "C:/empty" in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", _TOOLS)
async def test_missing_adapter_method_is_reported(
    mcp_server, mock_config, tool
) -> None:
    payload = {
        "measure_entities": {"entities": ["Edge<1>"]},
        "set_material": {"material_name": "AISI 1020"},
        "set_custom_property": {"name": "PartNo", "value": "1"},
        "export_flat_pattern": {"file_path": "C:/out/flat.dxf"},
    }.get(tool, {})
    await register_engineering_data_tools(mcp_server, object(), mock_config)

    result = await (await _tool(mcp_server, tool))(payload)

    assert result["status"] == "error"
    assert result["error_type"] == "not_supported"
    assert f"does not support {tool}" in result["message"]


@pytest.mark.asyncio
async def test_list_available_materials_says_what_it_searched(
    mcp_server, mock_config
) -> None:
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


@pytest.mark.asyncio
async def test_list_available_materials_without_metadata(
    mcp_server, mock_config
) -> None:
    async def list_available_materials(_search):
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=[{"name": "X"}])

    adapter = SimpleNamespace(list_available_materials=list_available_materials)
    await register_engineering_data_tools(mcp_server, adapter, mock_config)

    result = await (await _tool(mcp_server, "list_available_materials"))({})

    assert result["message"] == "Found 1 material(s)"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", _TOOLS)
async def test_docstrings_follow_the_tool_standard(
    mcp_server, mock_adapter, mock_config, tool
) -> None:
    """Every tool documents Args, Returns and an Example, as the others do."""
    await register_engineering_data_tools(mcp_server, mock_adapter, mock_config)
    doc = (await _tool(mcp_server, tool)).__doc__ or ""
    for section in ("Args:", "Returns:", "Example:"):
        assert section in doc, (tool, section)


def test_export_flat_pattern_input_refuses_other_formats() -> None:
    with pytest.raises(ValueError, match=r"must end in \.dxf or \.dwg"):
        ExportFlatPatternInput(file_path="flat.step")
    assert ExportFlatPatternInput(file_path="FLAT.DWG").file_path == "FLAT.DWG"
