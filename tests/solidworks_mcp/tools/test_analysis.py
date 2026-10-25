"""Tests for SolidWorks analysis tools."""

import re
from types import SimpleNamespace
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
from solidworks_mcp.tools.analysis import (
    GeometryAnalysisInput,
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
        for tool in await mcp_server.list_tools():
            if tool.name == "calculate_mass_properties":
                tool_func = tool.fn
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
    def test_mass_properties_input_validation(self):
        """Test input validation for mass properties."""
        # Valid input
        valid_input = MassPropertiesInput(model_path="test.sldprt", units="kg")
        assert valid_input.model_path == "test.sldprt"
        assert valid_input.units == "kg"

        # Invalid units should be handled by Pydantic validation
        with pytest.raises(ValueError):  # Pydantic validation error
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
        assert alias_dict["status"] == "success"

        alias_model = await alias_tool(input_data=MassPropertiesInput())
        assert alias_model["status"] == "success"

    @pytest.mark.asyncio
    async def test_analysis_tools_exception_and_fallback_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover adapter exceptions plus non-adapter fallback branches."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        check_tool = None
        geometry_tool = None
        material_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "check_interference":
                check_tool = tool.fn
            if tool.name == "analyze_geometry":
                geometry_tool = tool.fn
            if tool.name == "get_material_properties":
                material_tool = tool.fn

        assert check_tool is not None
        assert geometry_tool is not None
        assert material_tool is not None

        # This asserted the tool's own refusal message, reached only when the
        # adapter has no check_interference at all. The adapter implements it
        # now, so the hasattr gate resolves to a real capability and the
        # adapter's answer surfaces instead. Still an error, and still never
        # a fabricated clean result: the mock refuses because the assembly
        # has fewer than two components, which is the honest answer.
        fallback = await check_tool(input_data=InterferenceCheckInput())
        assert fallback["status"] == "error"
        assert "at least two components" in fallback["message"]
        # The critical property: never a clean bill of health for an assembly
        # nothing examined.
        assert fallback.get("interference_found") is not False

        # Exception branch for adapter check_interference.
        mock_adapter.check_interference = AsyncMock(side_effect=RuntimeError("boom"))
        errored = await check_tool(input_data=InterferenceCheckInput())
        assert errored["status"] == "error"
        assert errored["error_type"] == "internal"

        class _BadGeometryInput:
            """Test bad geometry input."""

            @property
            def analysis_type(self):
                """Test helper for analysis type."""
                raise RuntimeError("bad analysis type")

            parameters = None

        bad_geo = await geometry_tool(input_data=_BadGeometryInput())
        assert bad_geo["status"] == "error"
        assert "bad analysis type" in bad_geo["message"]

        # get_material_properties must refuse rather than invent a material,
        # since mock_adapter has no get_material_properties method.
        material = await material_tool()
        assert material["status"] == "error"
        assert "does not support get_material_properties" in material["message"]

        # Exception branch for adapter get_material_properties.
        mock_adapter.get_material_properties = AsyncMock(
            side_effect=RuntimeError("material boom")
        )
        material_errored = await material_tool()
        assert material_errored["status"] == "error"
        assert material_errored["error_type"] == "internal"

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

    @pytest.mark.asyncio
    async def test_analyze_geometry_and_material_properties_adapter_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover the real-adapter success/error paths once analyze_geometry and
        get_material_properties are wired to an adapter that implements them."""
        await register_analysis_tools(mcp_server, mock_adapter, mock_config)

        geometry_tool = None
        material_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_geometry":
                geometry_tool = tool.fn
            if tool.name == "get_material_properties":
                material_tool = tool.fn

        assert geometry_tool is not None
        assert material_tool is not None

        mock_adapter.analyze_geometry = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"analysis_type": "draft", "findings": []},
                execution_time=0.1,
            )
        )
        geometry_success = await geometry_tool(
            input_data=GeometryAnalysisInput(analysis_type="draft")
        )
        assert geometry_success["status"] == "success"
        assert geometry_success["data"]["analysis_type"] == "draft"

        mock_adapter.analyze_geometry = AsyncMock(
            return_value=Mock(is_success=False, error="geometry analysis failed")
        )
        geometry_error = await geometry_tool(
            input_data=GeometryAnalysisInput(analysis_type="draft")
        )
        assert geometry_error["status"] == "error"
        assert "geometry analysis failed" in geometry_error["message"]

        mock_adapter.get_material_properties = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"name": "Steel"},
                execution_time=0.1,
            )
        )
        material_success = await material_tool()
        assert material_success["status"] == "success"
        assert material_success["data"]["name"] == "Steel"

        mock_adapter.get_material_properties = AsyncMock(
            return_value=Mock(is_success=False, error="no material assigned")
        )
        material_error = await material_tool()
        assert material_error["status"] == "error"
        assert "no material assigned" in material_error["message"]


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

    @pytest.mark.asyncio
    async def test_get_material_properties_returns_success(self):
        """get_material_properties refuses when the adapter has no matching
        capability, rather than returning static material data."""
        from solidworks_mcp.tools.analysis import register_analysis_tools

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        await register_analysis_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "get_material_properties")
        result = await fn()
        assert result["status"] == "error"
        assert "does not support get_material_properties" in result["message"]


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
