"""Tests for SolidWorks automation tools."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import FastMCP

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.tools.automation import (
    DesignTableInput,
    GenerateVBAInput,
    VBAGenerationInput,
    register_automation_tools,
)


class TestAutomationTools:
    """Test suite for automation tools."""

    @pytest.mark.asyncio
    async def test_register_automation_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that automation tools register correctly."""
        tool_count = await register_automation_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 2

    @pytest.mark.asyncio
    async def test_generate_vba_code_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """The skeleton names its Sub, checks the document type, never blocks."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "generate_vba_code"
        )

        result = await tool_func(
            input_data=VBAGenerationInput(
                operation_type="Add 3 holes (M6), then save", target_document="part"
            )
        )

        vba = result["vba_code"]
        assert result["status"] == "success"
        assert vba["sub_name"] == "Add_3_holes_M6_then_save"
        assert "Sub Add_3_holes_M6_then_save()" in vba["code"]
        # SolidWorks runs a .swb macro only through main, which calls the Sub.
        assert "Sub main()\n    Add_3_holes_M6_then_save\nEnd Sub" in vba["code"]
        assert "If swModel.GetType <> 1 Then" in vba["code"]
        assert "MsgBox" not in vba["code"]
        assert "On Error GoTo ErrorHandler" in vba["code"]
        assert vba["target_document"] == "Part"
        assert vba["lines_of_code"] == len(vba["code"].split("\n"))
        assert "style" not in vba

    @pytest.mark.asyncio
    async def test_manage_design_table_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful design table management."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.manage_design_table = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "design_table_file": "part_configurations.xls",
                    "configurations_created": 5,
                    "parameters_linked": 12,
                    "operation": "Link Excel table",
                    "table_rows": 6,  # Including header
                    "table_columns": 8,
                },
                execution_time=1.5,
            )
        )

        input_data = DesignTableInput(
            model_path="configurable_part.sldprt",
            table_file="part_configurations.xls",
            operation="Link Excel table",
            auto_update=True,
            create_configurations=True,
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "manage_design_table":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["configurations_created"] == 5
        assert result["data"]["parameters_linked"] == 12
        mock_adapter.manage_design_table.assert_called_once()

    @pytest.mark.asyncio
    async def test_automation_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in automation operations."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "generate_vba_code"
        )

        result = await tool_func(
            input_data={"operation_type": "Invalid Operation", "parameters": {}}
        )

        assert result["status"] == "error"
        assert result["error_type"] == "invalid_input"
        assert "`parameters` is no longer an input" in result["message"]

    @pytest.mark.unit
    def test_vba_generation_input_validation(self):
        """Test input validation for VBA generation."""
        # Valid input
        valid_input = GenerateVBAInput(
            operation_type="Extrusion", parameters={"depth": 25.0}
        )
        assert valid_input.operation_type == "Extrusion"
        assert valid_input.parameters["depth"] == 25.0


def _make_mcp():
    """Create a plain FastMCP instance."""
    mcp = FastMCP("test")
    return mcp


def _make_config():
    """Test make config."""

    return SolidWorksMCPConfig(
        deployment_mode=DeploymentMode.LOCAL,
        security_level=SecurityLevel.MINIMAL,
        adapter_type=AdapterType.MOCK,
        mock_solidworks=True,
    )


async def _get_tool(mcp, name: str):
    """Test get tool."""

    for tool in await mcp.list_tools():
        if tool.name == name:
            return tool.fn
    raise KeyError(f"Tool {name!r} not registered in list_tools()")


class TestAutomationExceptionPaths:
    """Test automation exception paths."""

    @pytest.mark.asyncio
    async def test_manage_design_table_exception(self):
        """Line 506 — exception in manage_design_table."""
        from solidworks_mcp.tools.automation import (
            DesignTableInput,
            register_automation_tools,
        )

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        adapter.manage_design_table = AsyncMock(side_effect=RuntimeError("dt boom"))
        await register_automation_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "manage_design_table")
        result = await fn(DesignTableInput(table_type="create", excel_file="test.xlsx"))
        assert result["status"] == "error"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Add 3 holes (M6), then save", "Add_3_holes_M6_then_save"),
        ("3D export", "Macro_3D_export"),
        ("___", "Macro"),
        ("x" * 300, "x" * 255),
    ],
)
def test_the_sub_name_is_a_valid_vba_name(description: str, expected: str) -> None:
    from solidworks_mcp.tools.automation import _vba_sub_name

    assert _vba_sub_name(description) == expected


@pytest.mark.parametrize(
    ("document", "doc_type"), [("Part", 1), ("Assembly", 2), ("Drawing", 3)]
)
def test_the_macro_checks_its_document_type(document: str, doc_type: int) -> None:
    from solidworks_mcp.tools.automation import _vba_skeleton

    code = _vba_skeleton("Go", "two\nlines", document, error_handling=False)

    assert f"If swModel.GetType <> {doc_type} Then" in code
    assert f"not a {document}" in code
    assert "' Generated VBA code for: two lines" in code  # one comment line
    assert "ErrorHandler" not in code


def test_an_unknown_document_type_is_refused() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VBAGenerationInput(target_document="Sketch")
    with pytest.raises(ValidationError):
        VBAGenerationInput(target_document=3)
    assert VBAGenerationInput(target_document=" drawing ").target_document == "Drawing"


@pytest.mark.parametrize("name", ["main", "Main"])
def test_a_sub_named_main_is_not_wrapped(name: str) -> None:
    """A second main would be a duplicate definition; VBA names ignore case."""
    from solidworks_mcp.tools.automation import _vba_skeleton

    code = _vba_skeleton(name, name, "Part", error_handling=False)

    assert code.lower().count("sub main()") == 1
