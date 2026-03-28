"""
Tests for SolidWorks modeling tools.

Comprehensive test suite covering all modeling operations including
part creation, extrusions, revolves, and dimensional modifications.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from src.solidworks_mcp.tools.modeling import (
    register_modeling_tools,
    _result_value,
    OpenModelInput,
    CreatePartInput,
    CreateAssemblyInput,
    CreateDrawingInput,
    CloseModelInput,
    CreateExtrusionInput,
    CreateRevolveInput,
    CreateSweepInput,
    CreateLoftInput,
    GetDimensionInput,
    SetDimensionInput,
)


class TestModelingTools:
    """Test suite for modeling tools."""

    @pytest.mark.asyncio
    async def test_register_modeling_tools(self, mcp_server, mock_adapter, mock_config):
        """Test that modeling tools register correctly."""
        tool_count = await register_modeling_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 8

    @pytest.mark.asyncio
    async def test_open_model_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful model opening."""
        # Register tools
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        # Mock successful operation
        mock_adapter.open_model = AsyncMock(
            return_value=Mock(
                is_success=True, data={"title": "test_part.sldprt"}, execution_time=0.5
            )
        )

        # Find and call the tool
        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "open_model":
                tool_func = tool.func
                break

        assert tool_func is not None

        input_data = OpenModelInput(file_path="C:\\test\\test_part.sldprt")
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert "test_part.sldprt" in result["message"]
        assert result["model"]["title"] == "test_part.sldprt"
        assert result["execution_time"] == 0.5

    @pytest.mark.asyncio
    async def test_open_model_failure(self, mcp_server, mock_adapter, mock_config):
        """Test failed model opening."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.open_model = AsyncMock(
            return_value=Mock(is_success=False, error="File not found")
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "open_model":
                tool_func = tool.func
                break

        input_data = OpenModelInput(file_path="nonexistent.sldprt")
        result = await tool_func(input_data)

        assert result["status"] == "error"
        assert "File not found" in result["message"]

    @pytest.mark.asyncio
    async def test_create_part_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful part creation."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_part = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"name": "new_part", "units": "mm"},
                execution_time=1.2,
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_part":
                tool_func = tool.func
                break

        input_data = CreatePartInput(
            name="new_part", template="standard_part", units="mm", material="Steel"
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["part"]["name"] == "new_part"
        assert result["part"]["units"] == "mm"
        assert result["part"]["material"] == "Steel"

    @pytest.mark.asyncio
    async def test_create_assembly_with_components(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test assembly creation with components."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_assembly = AsyncMock(
            return_value=Mock(
                is_success=True, data={"name": "test_assembly"}, execution_time=2.1
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_assembly":
                tool_func = tool.func
                break

        input_data = CreateAssemblyInput(
            name="test_assembly",
            template="standard_assembly",
            components=["part1.sldprt", "part2.sldprt"],
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["assembly"]["name"] == "test_assembly"
        assert len(result["assembly"]["components"]) == 2

    @pytest.mark.asyncio
    async def test_create_drawing_from_model(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test drawing creation from model."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_drawing = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"name": "test_drawing", "sheet_format": "A3"},
                execution_time=1.8,
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_drawing":
                tool_func = tool.func
                break

        input_data = CreateDrawingInput(
            name="test_drawing",
            model_path="test_part.sldprt",
            sheet_format="A3",
            template="standard_drawing",
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["drawing"]["name"] == "test_drawing"
        assert result["drawing"]["model_path"] == "test_part.sldprt"
        assert result["drawing"]["sheet_format"] == "A3"

    @pytest.mark.asyncio
    async def test_create_extrusion_blind(self, mcp_server, mock_adapter, mock_config):
        """Test blind extrusion creation."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_extrusion = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"feature_name": "Boss-Extrude1"},
                execution_time=0.8,
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_extrusion":
                tool_func = tool.func
                break

        input_data = CreateExtrusionInput(
            sketch_name="Sketch1", depth=25.0, direction="blind", reverse=False
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["extrusion"]["sketch"] == "Sketch1"
        assert result["extrusion"]["depth"] == 25.0
        assert result["extrusion"]["direction"] == "blind"

    @pytest.mark.asyncio
    async def test_create_revolve_full(self, mcp_server, mock_adapter, mock_config):
        """Test full revolution creation."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_revolve = AsyncMock(
            return_value=Mock(
                is_success=True, data={"feature_name": "Revolve1"}, execution_time=1.1
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_revolve":
                tool_func = tool.func
                break

        input_data = CreateRevolveInput(
            sketch_name="Sketch1",
            axis_entity="centerline",
            angle=360.0,
            direction="one_direction",
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["revolve"]["angle"] == 360.0
        assert result["revolve"]["direction"] == "one_direction"

    @pytest.mark.asyncio
    async def test_get_dimension_value(self, mcp_server, mock_adapter, mock_config):
        """Test getting dimension value."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.get_dimension = AsyncMock(
            return_value=Mock(
                is_success=True, data={"value": 15.5, "units": "mm"}, execution_time=0.3
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "get_dimension":
                tool_func = tool.func
                break

        input_data = GetDimensionInput(dimension_name="D1@Sketch1")
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["dimension"]["value"] == 15.5
        assert result["dimension"]["units"] == "mm"

    @pytest.mark.asyncio
    async def test_set_dimension_value(self, mcp_server, mock_adapter, mock_config):
        """Test setting dimension value."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.set_dimension = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"old_value": 15.5, "new_value": 20.0},
                execution_time=0.4,
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "set_dimension":
                tool_func = tool.func
                break

        input_data = SetDimensionInput(
            dimension_name="D1@Sketch1", value=20.0, units="mm"
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["dimension_update"]["name"] == "D1@Sketch1"
        assert result["dimension_update"]["old_value"] == 15.5
        assert result["dimension_update"]["new_value"] == 20.0

    @pytest.mark.asyncio
    async def test_error_handling(self, mcp_server, mock_adapter, mock_config):
        """Test error handling in modeling tools."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        # Mock adapter that raises exception
        mock_adapter.create_part = AsyncMock(side_effect=Exception("Test exception"))

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_part":
                tool_func = tool.func
                break

        input_data = CreatePartInput(name="test_part")
        result = await tool_func(input_data)

        assert result["status"] == "error"
        assert "Test exception" in result["message"]

    @pytest.mark.asyncio
    async def test_input_validation(self):
        """Test input validation for modeling tools."""
        # Test missing required fields
        with pytest.raises(ValueError):
            CreatePartInput()  # name is required

        # Test invalid values
        with pytest.raises(ValueError):
            CreateExtrusionInput(
                sketch_name="",  # Empty string not allowed
                depth=-5.0,  # Negative depth should be invalid
            )

    @pytest.mark.asyncio
    async def test_performance_monitoring(
        self, mcp_server, mock_adapter, mock_config, perf_monitor
    ):
        """Test performance of modeling operations."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_part = AsyncMock(
            return_value=Mock(
                is_success=True, data={"name": "perf_test_part"}, execution_time=0.1
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_part":
                tool_func = tool.func
                break

        perf_monitor.start()
        input_data = CreatePartInput(name="perf_test_part")
        result = await tool_func(input_data)
        perf_monitor.stop()

        assert result["status"] == "success"
        # Tool should complete quickly in test environment
        perf_monitor.assert_max_time(1.0)

    def test_modeling_helper_and_input_branch_coverage(self):
        """Cover helper and model_post_init branches not exercised by normal flow."""
        assert (
            _result_value({"name": None, "title": "PartA"}, "name", "title") == "PartA"
        )
        assert _result_value({"name": None}, "name", default="fallback") == "fallback"

        class _Obj:
            """Test suite for Obj."""
            name = None
            title = "ObjTitle"

        assert _result_value(_Obj(), "name", "title") == "ObjTitle"
        assert _result_value(_Obj(), "missing", default="def") == "def"

        with pytest.raises(ValueError):
            CreatePartInput(name="   ")

        extrusion = CreateExtrusionInput(sketch_name="S1", depth=5, reverse=True)
        assert extrusion.reverse_direction is True

        with pytest.raises(ValueError):
            CreateRevolveInput(sketch_name="S1", axis_entity="Axis", angle=0)

        with pytest.raises(ValueError):
            GetDimensionInput()

        with pytest.raises(ValueError):
            SetDimensionInput(value=1.0)

        sweep = CreateSweepInput(path="Path1")
        assert sweep.path == "Path1"

        loft = CreateLoftInput(profiles=["P1", "P2"])
        assert loft.profiles == ["P1", "P2"]

    @pytest.mark.asyncio
    async def test_modeling_tool_error_result_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover is_success=False branches across multiple modeling tools."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_assembly = AsyncMock(
            return_value=Mock(is_success=False, error="assembly failed")
        )
        mock_adapter.create_drawing = AsyncMock(
            return_value=Mock(is_success=False, error="drawing failed")
        )
        mock_adapter.close_model = AsyncMock(
            return_value=Mock(is_success=False, error="close failed")
        )
        mock_adapter.create_extrusion = AsyncMock(
            return_value=Mock(is_success=False, error="extrude failed")
        )
        mock_adapter.create_revolve = AsyncMock(
            return_value=Mock(is_success=False, error="revolve failed")
        )
        mock_adapter.get_dimension = AsyncMock(
            return_value=Mock(is_success=False, error="dimension missing")
        )
        mock_adapter.set_dimension = AsyncMock(
            return_value=Mock(is_success=False, error="set failed")
        )

        tool = {registered.name: registered.func for registered in mcp_server._tools}

        assert (await tool["create_assembly"](CreateAssemblyInput(name="A1")))[
            "status"
        ] == "error"
        assert (await tool["create_drawing"](CreateDrawingInput(name="D1")))[
            "status"
        ] == "error"
        assert (await tool["close_model"](CloseModelInput(save=False)))[
            "status"
        ] == "error"
        assert (
            await tool["create_extrusion"](
                CreateExtrusionInput(sketch_name="S1", depth=2.0)
            )
        )["status"] == "error"
        assert (
            await tool["create_revolve"](
                CreateRevolveInput(sketch_name="S1", axis_entity="Axis", angle=45)
            )
        )["status"] == "error"
        assert (await tool["get_dimension"](GetDimensionInput(name="D1@Sketch1")))[
            "status"
        ] == "error"
        assert (
            await tool["set_dimension"](SetDimensionInput(name="D1@Sketch1", value=3))
        )["status"] == "error"

    @pytest.mark.asyncio
    async def test_modeling_tool_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover exception handlers in modeling tool functions."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.open_model = AsyncMock(side_effect=RuntimeError("open boom"))
        mock_adapter.create_part = AsyncMock(side_effect=RuntimeError("part boom"))
        mock_adapter.create_assembly = AsyncMock(side_effect=RuntimeError("asm boom"))
        mock_adapter.create_drawing = AsyncMock(side_effect=RuntimeError("drw boom"))
        mock_adapter.close_model = AsyncMock(side_effect=RuntimeError("close boom"))
        mock_adapter.create_extrusion = AsyncMock(side_effect=RuntimeError("ext boom"))
        mock_adapter.create_revolve = AsyncMock(side_effect=RuntimeError("rev boom"))
        mock_adapter.get_dimension = AsyncMock(side_effect=RuntimeError("getd boom"))
        mock_adapter.set_dimension = AsyncMock(side_effect=RuntimeError("setd boom"))

        tool = {registered.name: registered.func for registered in mcp_server._tools}

        assert (await tool["open_model"](OpenModelInput(file_path="C:/x.sldprt")))[
            "status"
        ] == "error"
        assert (await tool["create_part"](CreatePartInput(name="P1")))[
            "status"
        ] == "error"
        assert (await tool["create_assembly"](CreateAssemblyInput(name="A1")))[
            "status"
        ] == "error"
        assert (await tool["create_drawing"](CreateDrawingInput(name="D1")))[
            "status"
        ] == "error"
        assert (await tool["close_model"](CloseModelInput(save=True)))[
            "status"
        ] == "error"
        assert (
            await tool["create_extrusion"](
                CreateExtrusionInput(sketch_name="S1", depth=2.0)
            )
        )["status"] == "error"
        assert (
            await tool["create_revolve"](
                CreateRevolveInput(sketch_name="S1", axis_entity="Axis", angle=90)
            )
        )["status"] == "error"
        assert (await tool["get_dimension"](GetDimensionInput(name="D1@Sketch1")))[
            "status"
        ] == "error"
        assert (
            await tool["set_dimension"](SetDimensionInput(name="D1@Sketch1", value=2.5))
        )["status"] == "error"
