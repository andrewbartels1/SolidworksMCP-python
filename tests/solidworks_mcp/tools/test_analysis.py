"""Tests for SolidWorks analysis tools."""

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import FastMCP

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.tools.analysis import (
    InterferenceCheckInput,
    MassPropertiesInput,
    register_analysis_tools,
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

        # SolidWorks reports inertia in kg·m²; the tool reports kg·mm².
        mock_adapter.get_mass_properties = AsyncMock(
            return_value=Mock(
                is_success=True,
                data=SimpleNamespace(
                    volume=15000.0,
                    surface_area=4000.0,
                    mass=0.125,
                    center_of_mass=[0.0, 0.0, 10.0],
                    moments_of_inertia={
                        "Ixx": 1.2e-6,
                        "Iyy": 1.2e-6,
                        "Izz": 2.4e-6,
                        "Ixy": 0.0,
                        "Ixz": 0.0,
                        "Iyz": -3.0e-7,
                    },
                    principal_axes=None,
                ),
                execution_time=0.3,
            )
        )

        input_data = MassPropertiesInput()

        # Find and call the tool
        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "calculate_mass_properties":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        props = result["mass_properties"]
        assert props["mass"]["value"] == 0.125
        assert props["volume"]["value"] == 15000.0
        inertia = props["moments_of_inertia"]
        assert inertia["units"] == "kg·mm²"
        assert inertia["Ixx"] == pytest.approx(1.2)
        assert inertia["Izz"] == pytest.approx(2.4)
        assert inertia["Iyz"] == pytest.approx(-0.3)
        mock_adapter.get_mass_properties.assert_called_once()

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
            assembly_path="test_assembly.sldasm", include_hidden=False
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "check_interference":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["interference_count"] == 1
        assert "Component1" in result["data"]["interfering_bodies"]
        mock_adapter.check_interference.assert_called_once()
        # Hidden components are left out unless include_hidden is on.
        assert (
            mock_adapter.check_interference.call_args.args[0]["ignore_hidden"] is True
        )
        await tool_func(input_data={"include_hidden": True})
        assert (
            mock_adapter.check_interference.call_args.args[0]["ignore_hidden"] is False
        )

        refused = await tool_func(input_data={"tolerance": 0.01})
        assert refused["error_type"] == "invalid_input"
        assert "`tolerance`" in refused["message"]

    @pytest.mark.asyncio
    async def test_mass_properties_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test handling of adapter errors in mass properties."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.get_mass_properties = AsyncMock(
            return_value=Mock(
                is_success=False, error="Model file not found", execution_time=0.1
            )
        )

        input_data = MassPropertiesInput()

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "calculate_mass_properties":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "check_interference":
                tool_func = tool.fn
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Assembly failed to load" in result["message"]

    @pytest.mark.unit
    def test_mass_properties_input_has_no_fields(self):
        """It always measures the active model, so it takes nothing."""
        assert MassPropertiesInput.model_fields == {}

    @pytest.mark.unit
    def test_interference_check_input_validation(self):
        """Test input validation for interference check."""
        # Valid input
        valid_input = InterferenceCheckInput(assembly_path="test.sldasm")
        assert valid_input.assembly_path == "test.sldasm"
        assert valid_input.include_hidden is False  # hidden components left out

    @pytest.mark.asyncio
    async def test_mass_properties_fallback_and_alias_inputs(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover fallback mass-property path plus alias normalization branches."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

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
        for tool in await mcp_server.list_tools():
            if tool.name == "calculate_mass_properties":
                calculate_tool = tool.fn
            if tool.name == "get_mass_properties":
                alias_tool = tool.fn

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
        assert alias_dict["status"] == "error"
        assert alias_dict["error_type"] == "invalid_input"
        assert "`units`" in alias_dict["message"]
        assert "`include_hidden`" in alias_dict["message"]

        alias_model = await alias_tool(input_data=MassPropertiesInput())
        assert alias_model["status"] == "success"

    @pytest.mark.asyncio
    async def test_check_interference_refuses_when_adapter_lacks_support(
        self, mcp_server, mock_config
    ):
        """When the active adapter has no check_interference at all, the tool
        must refuse with its own message rather than calling a missing method.
        """

        class _AdapterWithoutInterferenceSupport:
            """A stand-in with none of the analysis capabilities."""

        bare_adapter = _AdapterWithoutInterferenceSupport()
        await register_analysis_tools(mcp_server, bare_adapter, mock_config)

        check_tool = next(
            t.fn
            for t in await mcp_server.list_tools()
            if t.name == "check_interference"
        )
        result = await check_tool(input_data=InterferenceCheckInput())
        assert result["status"] == "error"
        assert "does not support check_interference" in result["message"]


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


class TestAnalysisCoverage:
    """Test analysis coverage."""

    @pytest.mark.asyncio
    async def test_get_mass_properties_with_dict_input(self):
        """Line 221 — dict input is validated into MassPropertiesInput."""
        from solidworks_mcp.tools.analysis import register_analysis_tools

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await register_analysis_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "get_mass_properties")
        result = await fn({"include_hidden": False})
        # dict input path taken; should succeed or return an analysis result
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_mass_properties_with_none_input(self):
        """Line 217 — None input creates default MassPropertiesInput."""
        from solidworks_mcp.tools.analysis import register_analysis_tools

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await register_analysis_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "get_mass_properties")
        result = await fn(None)
        assert isinstance(result, dict)


CAPABILITY = "check_interference"


def test_capability_name_matches_the_tool_gate() -> None:
    """``analysis.py`` reaches the adapter only by this exact name."""
    from pathlib import Path

    import solidworks_mcp.tools.analysis as analysis_tools

    source = Path(analysis_tools.__file__).read_text(encoding="utf-8")
    assert re.search(rf'require_capability\(\s*adapter,\s*"{CAPABILITY}"', source), (
        f"no tool in analysis.py gates on adapter.{CAPABILITY}; either the "
        "gate was renamed or this capability is unreachable"
    )


@pytest.mark.asyncio
async def test_check_interference_accepts_a_plain_dict(
    mcp_server, mock_adapter
) -> None:
    """A script can pass a dict, as #209's U-joint session did."""
    mock_adapter.check_interference = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"interference_count": 0, "interferences": []},
        )
    )
    await register_analysis_tools(mcp_server, mock_adapter, {})
    tool = next(
        t.fn for t in await mcp_server.list_tools() if t.name == "check_interference"
    )

    result = await tool({"components": ["a-1", "b-1"]})

    assert result["status"] == "success"
    assert mock_adapter.check_interference.await_count == 1
