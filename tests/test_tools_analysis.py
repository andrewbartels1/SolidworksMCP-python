"""
Tests for SolidWorks analysis tools.

Comprehensive test suite covering mass properties, interference checking,
and structural analysis operations.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

from src.solidworks_mcp.tools.analysis import (
    register_analysis_tools,
    MassPropertiesInput,
    InterferenceCheckInput,
)


class TestAnalysisTools:
    """Test suite for analysis tools."""

    @pytest.mark.asyncio
    async def test_register_analysis_tools(self, mcp_server, mock_adapter, mock_config):
        """Test that analysis tools register correctly."""
        tool_count = await register_analysis_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 4

    @pytest.mark.asyncio
    async def test_calculate_mass_properties_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful mass properties calculation."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.calculate_mass_properties = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "mass": 0.125,
                    "volume": 1.5e-5,
                    "center_of_mass": [0.0, 0.0, 10.0],
                    "moments_of_inertia": {"Ixx": 1.2e-6, "Iyy": 1.2e-6, "Izz": 2.4e-6},
                },
                execution_time=0.3,
            )
        )

        input_data = MassPropertiesInput(
            model_path="test_part.sldprt",
            units="kg",
            reference_coordinate_system="default",
        )

        # Find and call the tool
        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "calculate_mass_properties":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["mass"] == 0.125
        assert result["data"]["volume"] == 1.5e-5
        mock_adapter.calculate_mass_properties.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_interference_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful interference checking."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.check_interference = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "interference_count": 1,
                    "interfering_bodies": ["Component1", "Component2"],
                    "interference_volume": 2.5e-6,
                    "details": "Overlap detected in assembly",
                },
                execution_time=1.2,
            )
        )

        input_data = InterferenceCheckInput(
            assembly_path="test_assembly.sldasm",
            check_all_components=True,
            include_hidden=False,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "check_interference":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["interference_count"] == 1
        assert "Component1" in result["data"]["interfering_bodies"]
        mock_adapter.check_interference.assert_called_once()

    @pytest.mark.asyncio
    async def test_mass_properties_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test handling of adapter errors in mass properties."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.calculate_mass_properties = AsyncMock(
            return_value=Mock(
                is_success=False, error="Model file not found", execution_time=0.1
            )
        )

        input_data = MassPropertiesInput(model_path="missing_part.sldprt", units="kg")

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "calculate_mass_properties":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Model file not found" in result["message"]

    @pytest.mark.asyncio
    async def test_interference_check_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test handling of adapter errors in interference checking."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.check_interference = AsyncMock(
            return_value=Mock(
                is_success=False, error="Assembly failed to load", execution_time=0.2
            )
        )

        input_data = InterferenceCheckInput(assembly_path="corrupt_assembly.sldasm")

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "check_interference":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Assembly failed to load" in result["message"]

    @pytest.mark.unit
    def test_mass_properties_input_validation(self):
        """Test input validation for mass properties."""
        # Valid input
        valid_input = MassPropertiesInput(model_path="test.sldprt", units="kg")
        assert valid_input.model_path == "test.sldprt"
        assert valid_input.units == "kg"

        # Invalid units should be handled by Pydantic validation
        with pytest.raises(Exception):  # Catching general validation error
            MassPropertiesInput(model_path="test.sldprt", units="invalid_unit")

    @pytest.mark.unit
    def test_interference_check_input_validation(self):
        """Test input validation for interference check."""
        # Valid input
        valid_input = InterferenceCheckInput(
            assembly_path="test.sldasm", check_all_components=True
        )
        assert valid_input.assembly_path == "test.sldasm"
        assert valid_input.check_all_components is True

        # Test optional parameters
        minimal_input = InterferenceCheckInput(assembly_path="test.sldasm")
        assert minimal_input.check_all_components is False  # Default value

    @pytest.mark.asyncio
    async def test_mass_properties_fallback_and_alias_inputs(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover fallback mass-property path plus alias normalization branches."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        # Remove calculate_mass_properties so the tool uses adapter.get_mass_properties().
        if hasattr(mock_adapter, "calculate_mass_properties"):
            delattr(mock_adapter, "calculate_mass_properties")

        mock_adapter.get_mass_properties = AsyncMock(
            return_value=Mock(
                is_success=True,
                data=SimpleNamespace(
                    volume=42.0,
                    surface_area=7.0,
                    mass=1.5,
                    center_of_mass=[1.0, 2.0, 3.0],
                    moments_of_inertia={
                        "Ixx": 1.0,
                        "Iyy": 2.0,
                        "Izz": 3.0,
                        "Ixy": 0.1,
                        "Ixz": 0.2,
                        "Iyz": 0.3,
                    },
                    principal_axes=["X", "Y", "Z"],
                ),
                execution_time=0.2,
            )
        )

        calculate_tool = None
        alias_tool = None
        for tool in mcp_server._tools:
            if tool.name == "calculate_mass_properties":
                calculate_tool = tool.handler
            if tool.name == "get_mass_properties":
                alias_tool = tool.handler

        assert calculate_tool is not None
        assert alias_tool is not None

        fallback = await calculate_tool(input_data=MassPropertiesInput())
        assert fallback["status"] == "success"
        assert fallback["mass_properties"]["volume"]["value"] == 42.0

        alias_none = await alias_tool()
        assert alias_none["status"] == "success"

        alias_dict = await alias_tool(
            input_data={"units": "lb", "include_hidden": True}
        )
        assert alias_dict["status"] == "success"

    @pytest.mark.asyncio
    async def test_analysis_tools_exception_and_fallback_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover adapter exceptions plus non-adapter fallback branches."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        check_tool = None
        geometry_tool = None
        material_tool = None
        for tool in mcp_server._tools:
            if tool.name == "check_interference":
                check_tool = tool.handler
            if tool.name == "analyze_geometry":
                geometry_tool = tool.handler
            if tool.name == "get_material_properties":
                material_tool = tool.handler

        assert check_tool is not None
        assert geometry_tool is not None
        assert material_tool is not None

        # Fallback branch when adapter has no check_interference method.
        if hasattr(mock_adapter, "check_interference"):
            delattr(mock_adapter, "check_interference")
        fallback = await check_tool(input_data=InterferenceCheckInput())
        assert fallback["status"] == "success"
        assert fallback["interference_found"] is False

        # Exception branch for adapter check_interference.
        mock_adapter.check_interference = AsyncMock(side_effect=RuntimeError("boom"))
        errored = await check_tool(input_data=InterferenceCheckInput())
        assert errored["status"] == "error"
        assert "Unexpected error: boom" in errored["message"]

        class _BadGeometryInput:
            @property
            def analysis_type(self):
                """Test helper for analysis type."""
                raise RuntimeError("bad analysis type")

            parameters = None

        bad_geo = await geometry_tool(input_data=_BadGeometryInput())
        assert bad_geo["status"] == "error"
        assert "bad analysis type" in bad_geo["message"]

        material = await material_tool()
        assert material["status"] == "success"
        assert material["material"]["name"]
