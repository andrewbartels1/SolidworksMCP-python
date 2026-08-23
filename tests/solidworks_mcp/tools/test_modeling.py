"""Tests for SolidWorks modeling tools."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.tools.modeling import (
    AddFilletInput,
    AddMateInput,
    CloseModelInput,
    CreateAssemblyInput,
    CreateAxisInput,
    CreateCutExtrudeInput,
    CreateDrawingInput,
    CreateExtrusionInput,
    CreateLoftInput,
    CreatePartInput,
    CreateReferencePlaneInput,
    CreateRevolveInput,
    CreateSweepInput,
    DeleteFeatureInput,
    GetDimensionInput,
    InsertComponentInput,
    MirrorFeatureInput,
    OpenModelInput,
    PatternCircularInput,
    SetDimensionInput,
    SuppressFeatureInput,
    UndoInput,
    _result_value,
    register_modeling_tools,
)


class TestModelingTools:
    """Test suite for modeling tools."""

    @pytest.mark.asyncio
    async def test_register_modeling_tools(self, mcp_server, mock_adapter, mock_config):
        """Test that modeling tools register correctly."""
        tool_count = await register_modeling_tools(
            mcp_server, mock_adapter, mock_config
        )
        # Asserted against the registry rather than a literal, so the count
        # cannot drift out of step with what was actually registered again.
        names = {tool.name for tool in await mcp_server.list_tools()}
        assert tool_count == len(names), (
            f"register_modeling_tools reported {tool_count} tools but "
            f"registered {len(names)}"
        )
        # The Phase 1 sweep/loft tools must be registered alongside the rest.
        names = {tool.name for tool in await mcp_server.list_tools()}
        assert {"create_sweep", "create_loft"} <= names
        # Assembly component/mate tools must be registered too.
        assert {"insert_component", "add_mate", "list_components"} <= names
        # Feature editing.
        assert {"delete_feature", "suppress_feature", "undo"} <= names

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
        for tool in await mcp_server.list_tools():
            if tool.name == "open_model":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "open_model":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "create_part":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "create_assembly":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "create_drawing":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "create_extrusion":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "create_revolve":
                tool_func = tool.fn
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
    async def test_create_sweep_success(self, mcp_server, mock_adapter, mock_config):
        """create_sweep wires the path/twist params and reports success."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_sweep = AsyncMock(
            return_value=Mock(
                is_success=True, data={"feature_name": "Sweep1"}, execution_time=1.2
            )
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "create_sweep":
                tool_func = tool.fn
                break
        assert tool_func is not None, "create_sweep tool was not registered"

        input_data = CreateSweepInput(
            path="Sketch2", twist_along_path=True, twist_angle=90.0
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["sweep"]["name"] == "Sweep1"
        assert result["sweep"]["path"] == "Sketch2"
        assert result["sweep"]["twist_along_path"] is True
        assert result["sweep"]["twist_angle"] == 90.0
        # Adapter received the translated SweepParameters.
        params = mock_adapter.create_sweep.await_args.args[0]
        assert params.path == "Sketch2"
        assert params.twist_along_path is True
        assert params.twist_angle == 90.0

    @pytest.mark.asyncio
    async def test_create_sweep_failure(self, mcp_server, mock_adapter, mock_config):
        """create_sweep surfaces the adapter error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_sweep = AsyncMock(
            return_value=Mock(is_success=False, error="no path sketch")
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "create_sweep":
                tool_func = tool.fn
                break

        result = await tool_func(CreateSweepInput(path="Sketch2"))
        assert result["status"] == "error"
        assert "no path sketch" in result["message"]

    @pytest.mark.asyncio
    async def test_create_loft_success(self, mcp_server, mock_adapter, mock_config):
        """create_loft wires the profile/guide params and reports success."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_loft = AsyncMock(
            return_value=Mock(
                is_success=True, data={"feature_name": "Loft1"}, execution_time=1.5
            )
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "create_loft":
                tool_func = tool.fn
                break
        assert tool_func is not None, "create_loft tool was not registered"

        input_data = CreateLoftInput(
            profiles=["Sketch1", "Sketch2"], guide_curves=["Sketch3"]
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["loft"]["name"] == "Loft1"
        assert result["loft"]["profiles"] == ["Sketch1", "Sketch2"]
        assert result["loft"]["guide_curves"] == ["Sketch3"]
        params = mock_adapter.create_loft.await_args.args[0]
        assert params.profiles == ["Sketch1", "Sketch2"]
        assert params.guide_curves == ["Sketch3"]

    @pytest.mark.asyncio
    async def test_create_loft_failure(self, mcp_server, mock_adapter, mock_config):
        """create_loft surfaces the adapter error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_loft = AsyncMock(
            return_value=Mock(is_success=False, error="need 2 profiles")
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "create_loft":
                tool_func = tool.fn
                break

        result = await tool_func(CreateLoftInput(profiles=["Sketch1", "Sketch2"]))
        assert result["status"] == "error"
        assert "need 2 profiles" in result["message"]

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
        for tool in await mcp_server.list_tools():
            if tool.name == "get_dimension":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "set_dimension":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "create_part":
                tool_func = tool.fn
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

        # InsertComponentInput requires a non-empty file_path
        with pytest.raises(ValueError):
            InsertComponentInput(file_path="")

        # AddMateInput requires non-empty component names
        with pytest.raises(ValueError):
            AddMateInput(component_a="", component_b="part-2")
        with pytest.raises(ValueError):
            AddMateInput(component_a="part-1", component_b="")

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
        for tool in await mcp_server.list_tools():
            if tool.name == "create_part":
                tool_func = tool.fn
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

        tool = {
            registered.name: registered.fn
            for registered in await mcp_server.list_tools()
        }

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

        tool = {
            registered.name: registered.fn
            for registered in await mcp_server.list_tools()
        }

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

    @pytest.mark.asyncio
    async def test_dimension_empty_name_validation(
        self, mcp_server, mock_adapter, mock_config
    ):
        """get_dimension and set_dimension return error when name is empty string."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        tool = {
            registered.name: registered.fn
            for registered in await mcp_server.list_tools()
        }

        import solidworks_mcp.tools.modeling as _modeling_mod

        # model_post_init raises for empty name, so we patch _normalize_input to return
        # a mock with name="" to exercise the handler's own guard (lines 920-921, 966-967).
        fake_get = MagicMock(spec=["name", "dimension_name"])
        fake_get.name = ""
        with patch.object(_modeling_mod, "_normalize_input", return_value=fake_get):
            get_result = await tool["get_dimension"]({})
        assert get_result["status"] == "error"
        assert "Dimension name is required" in get_result["message"]

        fake_set = MagicMock(spec=["name", "dimension_name", "value", "units"])
        fake_set.name = ""
        fake_set.value = 5.0
        with patch.object(_modeling_mod, "_normalize_input", return_value=fake_set):
            set_result = await tool["set_dimension"]({})
        assert set_result["status"] == "error"
        assert "Dimension name is required" in set_result["message"]

    @pytest.mark.asyncio
    async def test_create_cut_extrude_and_add_fillet_failure_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """create_cut_extrude and add_fillet surface adapter error messages."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_cut_extrude = AsyncMock(
            return_value=Mock(is_success=False, error="cut blocked by geometry")
        )
        mock_adapter.add_fillet = AsyncMock(
            return_value=Mock(is_success=False, error="fillet radius too large")
        )

        tool = {
            registered.name: registered.fn
            for registered in await mcp_server.list_tools()
        }

        cut_result = await tool["create_cut_extrude"](CreateCutExtrudeInput(depth=5.0))
        assert cut_result["status"] == "error"
        assert "cut blocked by geometry" in cut_result["message"]

        fillet_result = await tool["add_fillet"](
            AddFilletInput(radius=10.0, edge_names=["Edge<1>"])
        )
        assert fillet_result["status"] == "error"
        assert "fillet radius too large" in fillet_result["message"]


class TestAssemblyTools:
    """Test suite for insert_component / list_components / add_mate tools."""

    @pytest.mark.asyncio
    async def test_insert_component_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """insert_component returns success with the expected payload shape."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_assembly()

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "insert_component"
        )
        result = await tool_func(InsertComponentInput(file_path="C:/parts/a.sldprt"))

        assert result["status"] == "success"
        assert result["component"]["component"] == "component-1"
        assert result["component"]["components_before"] == 0
        assert result["component"]["components_after"] == 1
        assert "execution_time" in result

    @pytest.mark.asyncio
    async def test_add_mate_success(self, mcp_server, mock_adapter, mock_config):
        """add_mate returns success with mate details in the payload."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_assembly()

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "add_mate"
        )
        result = await tool_func(
            AddMateInput(
                component_a="part-1", component_b="part-2", mate_type="coincident"
            )
        )

        assert result["status"] == "success"
        assert result["mate"]["components"] == ["part-1", "part-2"]
        assert result["mate"]["mate_type"] == "coincident"

    @pytest.mark.asyncio
    async def test_list_components_success_and_reflects_inserts(
        self, mcp_server, mock_adapter, mock_config
    ):
        """list_components returns exactly what insert_component actually inserted."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_assembly()

        tool = {
            registered.name: registered.fn
            for registered in await mcp_server.list_tools()
        }

        await tool["insert_component"](InsertComponentInput(file_path="C:/parts/a.sldprt"))
        await tool["insert_component"](InsertComponentInput(file_path="C:/parts/b.sldprt"))

        result = await tool["list_components"]()

        assert result["status"] == "success"
        assert result["components"] == ["component-1", "component-2"]
        assert result["message"] == "2 component(s) in the assembly"

    @pytest.mark.asyncio
    async def test_insert_component_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no insert_component - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "insert_component"
        )
        result = await tool_func(InsertComponentInput(file_path="C:/parts/a.sldprt"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_add_mate_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no add_mate - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "add_mate"
        )
        result = await tool_func(AddMateInput(component_a="a-1", component_b="b-1"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_list_components_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no list_components - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "list_components"
        )
        result = await tool_func()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_insert_component_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A failed adapter result surfaces the adapter's own error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.insert_component = AsyncMock(
            return_value=Mock(is_success=False, error="no solid geometry")
        )

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "insert_component"
        )
        result = await tool_func(InsertComponentInput(file_path="C:/parts/empty.sldprt"))

        assert result["status"] == "error"
        assert "no solid geometry" in result["message"]

    @pytest.mark.asyncio
    async def test_add_mate_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A failed add_mate adapter result surfaces the adapter's own error."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.add_mate = AsyncMock(
            return_value=Mock(is_success=False, error="mate rejected by SolidWorks")
        )

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "add_mate"
        )
        result = await tool_func(
            AddMateInput(component_a="part-1", component_b="part-2")
        )

        assert result["status"] == "error"
        assert "mate rejected by SolidWorks" in result["message"]

    @pytest.mark.asyncio
    async def test_list_components_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A failed list_components adapter result surfaces the adapter's own error."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.list_components = AsyncMock(
            return_value=Mock(is_success=False, error="not an assembly document")
        )

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "list_components"
        )
        result = await tool_func()

        assert result["status"] == "error"


class TestFeatureEditingTools:
    """Test suite for delete_feature / suppress_feature / undo tools."""

    async def _part_with_extrusion(self, mock_adapter) -> str:
        """Create a part with one extrusion feature; return the feature name."""
        await mock_adapter.create_part()
        result = await mock_adapter.create_extrusion(ExtrusionParameters(depth=10.0))
        return result.data.name

    @pytest.mark.asyncio
    async def test_delete_feature_success(self, mcp_server, mock_adapter, mock_config):
        """delete_feature removes the named feature and reports it."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        name = await self._part_with_extrusion(mock_adapter)

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "delete_feature"
        )
        result = await tool_func(DeleteFeatureInput(name=name))

        assert result["status"] == "success"
        assert name in result["message"]
        assert result["data"]["deleted"] == name
        assert "execution_time" in result

    @pytest.mark.asyncio
    async def test_delete_feature_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no delete_feature - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "delete_feature"
        )
        result = await tool_func(DeleteFeatureInput(name="Boss-Extrude1"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_delete_feature_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A failed adapter result surfaces the adapter's own error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.delete_feature = AsyncMock(
            return_value=Mock(is_success=False, error="Feature not found: Ghost1")
        )

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "delete_feature"
        )
        result = await tool_func(DeleteFeatureInput(name="Ghost1"))

        assert result["status"] == "error"
        assert "Feature not found: Ghost1" in result["message"]

    @pytest.mark.asyncio
    async def test_suppress_feature_success(self, mcp_server, mock_adapter, mock_config):
        """suppress_feature suppresses a known feature and reports the verb used."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        name = await self._part_with_extrusion(mock_adapter)

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "suppress_feature"
        )
        result = await tool_func(SuppressFeatureInput(name=name, suppress=True))

        assert result["status"] == "success"
        assert result["message"] == f"Suppressed {name}"
        assert result["data"]["suppressed"] is True

    @pytest.mark.asyncio
    async def test_unsuppress_feature_success_reports_unsuppress_verb(
        self, mcp_server, mock_adapter, mock_config
    ):
        """suppress_feature(suppress=False) reports 'Unsuppressed', not 'Suppressed'."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        name = await self._part_with_extrusion(mock_adapter)

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "suppress_feature"
        )
        result = await tool_func(SuppressFeatureInput(name=name, suppress=False))

        assert result["status"] == "success"
        assert result["message"] == f"Unsuppressed {name}"

    @pytest.mark.asyncio
    async def test_suppress_feature_reports_when_state_unreadable(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A None 'suppressed' readback appends the disclosure to the message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.suppress_feature = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"feature": "Fillet1", "suppressed": None},
                execution_time=0.1,
            )
        )

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "suppress_feature"
        )
        result = await tool_func(SuppressFeatureInput(name="Fillet1"))

        assert result["status"] == "success"
        assert "state could not be read back" in result["message"]

    @pytest.mark.asyncio
    async def test_suppress_feature_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no suppress_feature - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "suppress_feature"
        )
        result = await tool_func(SuppressFeatureInput(name="Fillet1"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_suppress_feature_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A failed adapter result surfaces the adapter's own error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.suppress_feature = AsyncMock(
            return_value=Mock(is_success=False, error="Feature not found: Ghost1")
        )

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "suppress_feature"
        )
        result = await tool_func(SuppressFeatureInput(name="Ghost1"))

        assert result["status"] == "error"
        assert "Feature not found: Ghost1" in result["message"]

    @pytest.mark.asyncio
    async def test_undo_success_reports_steps_undone(
        self, mcp_server, mock_adapter, mock_config
    ):
        """undo removes the last feature and reports the step count."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await self._part_with_extrusion(mock_adapter)

        tool_func = next(t.fn for t in await mcp_server.list_tools() if t.name == "undo")
        result = await tool_func(UndoInput(count=1))

        assert result["status"] == "success"
        assert result["message"] == "Undid 1 step(s)"
        assert result["data"]["tree_changed"] is True

    @pytest.mark.asyncio
    async def test_undo_with_nothing_to_undo_reports_unchanged_tree(
        self, mcp_server, mock_adapter, mock_config
    ):
        """undo on an empty feature tree succeeds but reports nothing changed."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()

        tool_func = next(t.fn for t in await mcp_server.list_tools() if t.name == "undo")
        result = await tool_func(UndoInput(count=1))

        assert result["status"] == "success"
        assert "nothing to undo" in result["message"]
        assert result["data"]["tree_changed"] is False

    @pytest.mark.asyncio
    async def test_undo_defaults_to_one_step_when_no_input_given(
        self, mcp_server, mock_adapter, mock_config
    ):
        """undo() with no input_data still works, defaulting count to 1."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await self._part_with_extrusion(mock_adapter)

        tool_func = next(t.fn for t in await mcp_server.list_tools() if t.name == "undo")
        result = await tool_func(None)

        assert result["status"] == "success"
        assert result["data"]["requested_steps"] == 1

    @pytest.mark.asyncio
    async def test_undo_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no undo - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(t.fn for t in await mcp_server.list_tools() if t.name == "undo")
        result = await tool_func(UndoInput())
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_undo_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A failed adapter result surfaces the adapter's own error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.undo = AsyncMock(
            return_value=Mock(is_success=False, error="nothing to undo here")
        )

        tool_func = next(t.fn for t in await mcp_server.list_tools() if t.name == "undo")
        result = await tool_func(UndoInput())

        assert result["status"] == "error"
        assert "nothing to undo here" in result["message"]


class TestReferenceGeometryTools:
    """Test suite for create_reference_plane / create_axis tools."""

    @pytest.mark.asyncio
    async def test_create_reference_plane_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """create_reference_plane returns the new plane's details."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()

        tool_func = next(
            t.fn
            for t in await mcp_server.list_tools()
            if t.name == "create_reference_plane"
        )
        result = await tool_func(
            CreateReferencePlaneInput(reference="Front Plane", offset=76.2)
        )

        assert result["status"] == "success"
        assert result["plane"]["name"] == "Plane1"
        assert result["plane"]["offset"] == 76.2
        assert "Plane1" in result["message"]

    @pytest.mark.asyncio
    async def test_create_reference_plane_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no create_reference_plane - report error."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn
            for t in await mcp_server.list_tools()
            if t.name == "create_reference_plane"
        )
        result = await tool_func(
            CreateReferencePlaneInput(reference="Front Plane", offset=10.0)
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_create_reference_plane_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A failed adapter result (e.g. zero offset) surfaces the adapter's own error."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()

        tool_func = next(
            t.fn
            for t in await mcp_server.list_tools()
            if t.name == "create_reference_plane"
        )
        result = await tool_func(
            CreateReferencePlaneInput(reference="Front Plane", offset=0.0)
        )

        assert result["status"] == "error"
        assert "non-zero offset" in result["message"]

    def test_create_reference_plane_input_rejects_blank_reference(self):
        """CreateReferencePlaneInput.model_post_init rejects a blank reference."""
        with pytest.raises(ValueError, match="reference is required"):
            CreateReferencePlaneInput(reference="   ", offset=10.0)

    @pytest.mark.asyncio
    async def test_create_axis_success(self, mcp_server, mock_adapter, mock_config):
        """create_axis returns the new axis's plane pair."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "create_axis"
        )
        result = await tool_func(CreateAxisInput(reference="z"))

        assert result["status"] == "success"
        assert result["axis"]["name"] == "Axis1"
        assert result["axis"]["planes"] == ["Top Plane", "Right Plane"]
        assert "z axis" in result["message"]

    @pytest.mark.asyncio
    async def test_create_axis_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no create_axis - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "create_axis"
        )
        result = await tool_func(CreateAxisInput(reference="x"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_create_axis_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """An unknown axis reference surfaces the adapter's own error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "create_axis"
        )
        result = await tool_func(CreateAxisInput(reference="w"))

        assert result["status"] == "error"
        assert "Unknown axis reference" in result["message"]

    def test_create_axis_input_rejects_blank_reference(self):
        """CreateAxisInput.model_post_init rejects a blank reference."""
        with pytest.raises(ValueError, match="reference is required"):
            CreateAxisInput(reference="   ")


class TestMirrorAndPatternTools:
    """Test suite for mirror_feature / pattern_circular tools."""

    @pytest.mark.asyncio
    async def test_mirror_feature_success(self, mcp_server, mock_adapter, mock_config):
        """mirror_feature mirrors a known body about a built-in plane."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        extruded = await mock_adapter.create_extrusion(ExtrusionParameters(depth=10.0))

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "mirror_feature"
        )
        result = await tool_func(
            MirrorFeatureInput(
                features=[extruded.data.name], mirror_plane="Right Plane"
            )
        )

        assert result["status"] == "success"
        assert result["mirror"]["mirror_plane"] == "Right Plane"
        assert result["mirror"]["volume_ratio"] == pytest.approx(2.0)
        assert extruded.data.name in result["message"]

    @pytest.mark.asyncio
    async def test_mirror_feature_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no mirror_feature - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "mirror_feature"
        )
        result = await tool_func(
            MirrorFeatureInput(features=["Loft1"], mirror_plane="Right Plane")
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_mirror_feature_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """An unknown source name surfaces the adapter's own error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "mirror_feature"
        )
        result = await tool_func(
            MirrorFeatureInput(features=["Ghost1"], mirror_plane="Right Plane")
        )

        assert result["status"] == "error"
        assert "Failed to select" in result["message"]

    def test_mirror_feature_input_rejects_empty_features(self):
        """MirrorFeatureInput.model_post_init rejects an empty features list."""
        with pytest.raises(ValueError, match="features must contain at least one name"):
            MirrorFeatureInput(features=[], mirror_plane="Right Plane")

    def test_mirror_feature_input_rejects_blank_mirror_plane(self):
        """MirrorFeatureInput.model_post_init rejects a blank mirror_plane."""
        with pytest.raises(ValueError, match="mirror_plane is required"):
            MirrorFeatureInput(features=["Loft1"], mirror_plane="   ")

    @pytest.mark.asyncio
    async def test_pattern_circular_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """pattern_circular patterns a feature around a known axis."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        extruded = await mock_adapter.create_extrusion(ExtrusionParameters(depth=10.0))
        axis = await mock_adapter.create_axis("z")

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "pattern_circular"
        )
        result = await tool_func(
            PatternCircularInput(
                features=[extruded.data.name], axis=axis.data["name"], count=4
            )
        )

        assert result["status"] == "success"
        assert result["pattern"]["axis"] == axis.data["name"]
        assert result["pattern"]["count"] == 4
        assert "4 instances" in result["message"]

    @pytest.mark.asyncio
    async def test_pattern_circular_error_when_adapter_lacks_capability(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter has no pattern_circular - report error, not a fabrication."""
        await register_modeling_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "pattern_circular"
        )
        result = await tool_func(
            PatternCircularInput(features=["Boss-Extrude1"], axis="Axis1", count=4)
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_pattern_circular_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """An unknown axis name surfaces the adapter's own error message."""
        await register_modeling_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "pattern_circular"
        )
        result = await tool_func(
            PatternCircularInput(
                features=["Boss-Extrude1"], axis="NoSuchAxis", count=4
            )
        )

        assert result["status"] == "error"
        assert "Failed to select axis" in result["message"]

    def test_pattern_circular_input_rejects_empty_features(self):
        """PatternCircularInput.model_post_init rejects an empty features list."""
        with pytest.raises(ValueError, match="features must contain at least one name"):
            PatternCircularInput(features=[], axis="Axis1", count=4)

    def test_pattern_circular_input_rejects_blank_axis(self):
        """PatternCircularInput.model_post_init rejects a blank axis."""
        with pytest.raises(ValueError, match="axis is required"):
            PatternCircularInput(features=["Boss-Extrude1"], axis="   ", count=4)

    def test_pattern_circular_input_rejects_count_below_two(self):
        """PatternCircularInput.model_post_init rejects a count under 2."""
        with pytest.raises(ValueError, match="count must be at least 2"):
            PatternCircularInput(features=["Boss-Extrude1"], axis="Axis1", count=1)
