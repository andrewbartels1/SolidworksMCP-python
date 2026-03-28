"""
Tests for SolidWorks sketching tools.

Comprehensive test suite covering sketch creation, geometric entities,
constraints, and sketch-based operations.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.solidworks_mcp.tools.sketching import (
    AddArcInput,
    AddCircleInput,
    AddDimensionInput,
    AddLineInput,
    AddRectangleInput,
    AddRelationInput,
    AddSplineInput,
    CreateSketchInput,
    TutorialSimpleHoleInput,
    register_sketching_tools,
)


class TestSketchingTools:
    """Test suite for sketching tools."""

    @pytest.mark.asyncio
    async def test_register_sketching_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that sketching tools register correctly."""
        tool_count = await register_sketching_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 6

    @pytest.mark.asyncio
    async def test_create_sketch_on_plane(self, mcp_server, mock_adapter, mock_config):
        """Test creating a sketch on a reference plane."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_sketch = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"sketch_name": "Sketch1", "plane": "Front Plane"},
                execution_time=0.3,
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_sketch":
                tool_func = tool.func
                break

        assert tool_func is not None

        input_data = CreateSketchInput(plane="Front Plane", sketch_name="TestSketch")
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["sketch"]["name"] == "TestSketch"
        assert result["sketch"]["plane"] == "Front Plane"
        assert result["execution_time"] == 0.3

    @pytest.mark.asyncio
    async def test_create_sketch_on_face(self, mcp_server, mock_adapter, mock_config):
        """Test creating a sketch on a model face."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_sketch = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"sketch_name": "Sketch2", "plane": "Face<1>"},
                execution_time=0.4,
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_sketch":
                tool_func = tool.func
                break

        input_data = CreateSketchInput(plane="Face<1>", sketch_name="FaceSketch")
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["sketch"]["plane"] == "Face<1>"

    @pytest.mark.asyncio
    async def test_add_line_with_coordinates(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test adding a line with start and end coordinates."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.add_sketch_line = AsyncMock(
            return_value=Mock(
                is_success=True, data={"entity_id": "Line1"}, execution_time=0.2
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "add_line":
                tool_func = tool.func
                break

        input_data = AddLineInput(
            start_x=0.0, start_y=0.0, end_x=50.0, end_y=50.0, construction=False
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["line"]["start"] == {"x": 0.0, "y": 0.0}
        assert result["line"]["end"] == {"x": 50.0, "y": 50.0}
        assert result["line"]["construction"] is False

    @pytest.mark.asyncio
    async def test_add_construction_line(self, mcp_server, mock_adapter, mock_config):
        """Test adding a construction line."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.add_sketch_line = AsyncMock(
            return_value=Mock(
                is_success=True, data={"entity_id": "Line2"}, execution_time=0.2
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "add_line":
                tool_func = tool.func
                break

        input_data = AddLineInput(
            start_x=0.0, start_y=0.0, end_x=100.0, end_y=0.0, construction=True
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["line"]["construction"] is True

    @pytest.mark.asyncio
    async def test_add_circle_center_radius(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test adding a circle with center point and radius."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.add_sketch_circle = AsyncMock(
            return_value=Mock(
                is_success=True, data={"entity_id": "Circle1"}, execution_time=0.3
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "add_circle":
                tool_func = tool.func
                break

        input_data = AddCircleInput(
            center_x=25.0, center_y=25.0, radius=10.0, construction=False
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["circle"]["center"] == {"x": 25.0, "y": 25.0}
        assert result["circle"]["radius"] == 10.0
        assert result["circle"]["construction"] is False

    @pytest.mark.asyncio
    async def test_add_rectangle_corners(self, mcp_server, mock_adapter, mock_config):
        """Test adding a rectangle with corner coordinates."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.add_sketch_rectangle = AsyncMock(
            return_value=Mock(
                is_success=True, data={"entity_id": "Rectangle1"}, execution_time=0.4
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "add_rectangle":
                tool_func = tool.func
                break

        input_data = AddRectangleInput(
            corner1_x=0.0,
            corner1_y=0.0,
            corner2_x=40.0,
            corner2_y=30.0,
            construction=False,
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["rectangle"]["corner1"] == {"x": 0.0, "y": 0.0}
        assert result["rectangle"]["corner2"] == {"x": 40.0, "y": 30.0}
        assert result["rectangle"]["width"] == 40.0
        assert result["rectangle"]["height"] == 30.0

    @pytest.mark.asyncio
    async def test_exit_sketch_mode(self, mcp_server, mock_adapter, mock_config):
        """Test exiting sketch editing mode."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.exit_sketch = AsyncMock(
            return_value=Mock(
                is_success=True, data={"sketch_name": "Sketch1"}, execution_time=0.1
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "exit_sketch":
                tool_func = tool.func
                break

        result = await tool_func({})

        assert result["status"] == "success"
        assert "Exited sketch editing mode" in result["message"]

    @pytest.mark.asyncio
    async def test_tutorial_simple_hole(self, mcp_server, mock_adapter, mock_config):
        """Test the complete tutorial for creating a simple hole."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        # Mock all the operations in sequence
        mock_adapter.create_sketch = AsyncMock(
            return_value=Mock(
                is_success=True, data={"sketch_name": "HoleSketch"}, execution_time=0.3
            )
        )
        mock_adapter.add_sketch_circle = AsyncMock(
            return_value=Mock(
                is_success=True, data={"entity_id": "HoleCircle"}, execution_time=0.2
            )
        )
        mock_adapter.exit_sketch = AsyncMock(
            return_value=Mock(
                is_success=True, data={"sketch_name": "HoleSketch"}, execution_time=0.1
            )
        )
        mock_adapter.create_cut = AsyncMock(
            return_value=Mock(
                is_success=True, data={"cut_name": "Cut-Extrude1"}, execution_time=0.8
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "tutorial_simple_hole":
                tool_func = tool.func
                break

        input_data = TutorialSimpleHoleInput(
            plane="Front Plane", center_x=0.0, center_y=0.0, diameter=8.0, depth=15.0
        )
        result = await tool_func(input_data)

        assert result["status"] == "success"
        assert result["tutorial"]["plane"] == "Front Plane"
        assert result["tutorial"]["diameter"] == 8.0
        assert result["tutorial"]["depth"] == 15.0
        assert len(result["tutorial"]["steps"]) == 4

        # Check that all steps were completed
        step_names = [step["step"] for step in result["tutorial"]["steps"]]
        expected_steps = [
            "Create sketch",
            "Add circle",
            "Exit sketch",
            "Create cut extrude",
        ]
        assert step_names == expected_steps

    @pytest.mark.asyncio
    async def test_sketch_failure_handling(self, mcp_server, mock_adapter, mock_config):
        """Test error handling when sketch operations fail."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_sketch = AsyncMock(
            return_value=Mock(
                is_success=False, error="Cannot create sketch on selected plane"
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_sketch":
                tool_func = tool.func
                break

        input_data = CreateSketchInput(plane="Invalid Plane")
        result = await tool_func(input_data)

        assert result["status"] == "error"
        assert "Cannot create sketch on selected plane" in result["message"]

    @pytest.mark.asyncio
    async def test_exception_handling(self, mcp_server, mock_adapter, mock_config):
        """Test exception handling in sketching tools."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        # Mock adapter that raises exception
        mock_adapter.add_sketch_circle = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "add_circle":
                tool_func = tool.func
                break

        input_data = AddCircleInput(center_x=0, center_y=0, radius=5)
        result = await tool_func(input_data)

        assert result["status"] == "error"
        assert "Unexpected error" in result["message"]

    @pytest.mark.asyncio
    async def test_input_validation_sketching(self):
        """Test input validation for sketching tools."""
        # Test negative radius
        with pytest.raises(ValueError):
            AddCircleInput(center_x=0, center_y=0, radius=-5)

        # Test empty plane name
        with pytest.raises(ValueError):
            CreateSketchInput(plane="")

        # Test invalid rectangle (same corners)
        with pytest.raises(ValueError):
            AddRectangleInput(corner1_x=0, corner1_y=0, corner2_x=0, corner2_y=0)

    @pytest.mark.asyncio
    async def test_sketch_performance(
        self, mcp_server, mock_adapter, mock_config, perf_monitor
    ):
        """Test performance of sketch operations."""
        await register_sketching_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_sketch = AsyncMock(
            return_value=Mock(
                is_success=True, data={"sketch_name": "PerfSketch"}, execution_time=0.05
            )
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_sketch":
                tool_func = tool.func
                break

        perf_monitor.start()
        input_data = CreateSketchInput(plane="Top Plane")
        result = await tool_func(input_data)
        perf_monitor.stop()

        assert result["status"] == "success"
        # Sketch operations should be very fast
        perf_monitor.assert_max_time(0.5)


class TestSketchingToolsBranchCoverage:
    """Branch coverage for uncovered sketching paths."""

    # ── Input model aliases & validation ──────────────────────────────────

    def test_add_line_input_alias_resolution(self):
        """Test add line input alias resolution."""
        inp = AddLineInput(start_x=1.0, start_y=2.0, end_x=3.0, end_y=4.0)
        assert inp.x1 == 1.0 and inp.y1 == 2.0 and inp.x2 == 3.0 and inp.y2 == 4.0

    def test_add_rectangle_input_alias_resolution(self):
        """Test add rectangle input alias resolution."""
        inp = AddRectangleInput(
            corner1_x=0.0, corner1_y=0.0, corner2_x=5.0, corner2_y=6.0
        )
        assert inp.x1 == 0.0 and inp.y1 == 0.0 and inp.x2 == 5.0 and inp.y2 == 6.0

    def test_tutorial_hole_input_validation_errors(self):
        """Test tutorial hole input validation errors."""
        with pytest.raises(ValueError):
            TutorialSimpleHoleInput(
                plane="Top", center_x=0, center_y=0, diameter=0, depth=5
            )
        with pytest.raises(ValueError):
            TutorialSimpleHoleInput(
                plane="Top", center_x=0, center_y=0, diameter=5, depth=0
            )

    # ── Fallback adapter paths ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_add_line_fallback_path(self, mcp_server, mock_config):
        """add_line must use adapter.add_line when add_sketch_line is absent."""
        stub = SimpleNamespace()
        stub.add_line = AsyncMock(
            return_value=Mock(is_success=True, data="Line1", execution_time=0.1)
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(t.func for t in mcp_server._tools if t.name == "add_line")
        result = await tool_func(AddLineInput(x1=0, y1=0, x2=10, y2=10))
        assert result["status"] == "success"
        stub.add_line.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_circle_fallback_path(self, mcp_server, mock_config):
        """add_circle must use adapter.add_circle when add_sketch_circle is absent."""
        stub = SimpleNamespace()
        stub.add_circle = AsyncMock(
            return_value=Mock(is_success=True, data="Circle1", execution_time=0.1)
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(t.func for t in mcp_server._tools if t.name == "add_circle")
        result = await tool_func(AddCircleInput(center_x=0, center_y=0, radius=5))
        assert result["status"] == "success"
        stub.add_circle.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_rectangle_fallback_path(self, mcp_server, mock_config):
        """add_rectangle must use adapter.add_rectangle when add_sketch_rectangle is absent."""
        stub = SimpleNamespace()
        stub.add_rectangle = AsyncMock(
            return_value=Mock(is_success=True, data="Rect1", execution_time=0.1)
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(t.func for t in mcp_server._tools if t.name == "add_rectangle")
        result = await tool_func(AddRectangleInput(x1=0, y1=0, x2=10, y2=10))
        assert result["status"] == "success"
        stub.add_rectangle.assert_called_once()

    # ── Error return paths (is_success=False) ────────────────────────────

    @pytest.mark.asyncio
    async def test_sketch_tools_error_paths(self, mcp_server, mock_config):
        """All sketch adapter tools return status=error when adapter returns is_success=False."""
        err = Mock(is_success=False, error="adapter error")
        stub = SimpleNamespace()
        stub.add_arc = AsyncMock(return_value=err)
        stub.add_spline = AsyncMock(return_value=err)
        stub.add_centerline = AsyncMock(return_value=err)
        stub.add_polygon = AsyncMock(return_value=err)
        stub.add_ellipse = AsyncMock(return_value=err)
        stub.add_sketch_constraint = AsyncMock(return_value=err)
        stub.add_sketch_dimension = AsyncMock(return_value=err)
        stub.sketch_linear_pattern = AsyncMock(return_value=err)
        stub.sketch_circular_pattern = AsyncMock(return_value=err)
        stub.sketch_mirror = AsyncMock(return_value=err)
        stub.sketch_offset = AsyncMock(return_value=err)

        await register_sketching_tools(mcp_server, stub, mock_config)
        by_name = {t.name: t.func for t in mcp_server._tools}

        cases = [
            (
                "add_arc",
                AddArcInput(
                    center_x=0, center_y=0, start_x=5, start_y=0, end_x=0, end_y=5
                ),
            ),
            ("add_spline", AddSplineInput(points=[{"x": 0, "y": 0}, {"x": 5, "y": 5}])),
            ("add_centerline", AddLineInput(x1=0, y1=0, x2=0, y2=10)),
            ("add_polygon", {"center_x": 0, "center_y": 0, "radius": 10, "sides": 6}),
            (
                "add_ellipse",
                {"center_x": 0, "center_y": 0, "major_axis": 20, "minor_axis": 10},
            ),
            (
                "add_sketch_constraint",
                AddRelationInput(entity1="Line1", relation_type="horizontal"),
            ),
            (
                "add_sketch_dimension",
                AddDimensionInput(entity1="Line1", dimension_type="linear", value=10.0),
            ),
            ("sketch_linear_pattern", {"entities": ["Circle1"], "count": 3}),
            ("sketch_circular_pattern", {"entities": ["Circle1"], "count": 6}),
            ("sketch_mirror", {"entities": ["Line1"], "mirror_line": "CL1"}),
            ("sketch_offset", {"entities": ["Line1"], "offset_distance": 5.0}),
        ]
        for name, arg in cases:
            result = await by_name[name](arg)
            assert result["status"] == "error", f"{name} should return error"

    # ── Exception paths ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sketch_tools_exception_paths(self, mcp_server, mock_config):
        """All sketch adapter tools return status=error when adapter raises an exception."""
        exc = RuntimeError("unexpected")
        stub = SimpleNamespace()
        stub.add_arc = AsyncMock(side_effect=exc)
        stub.add_spline = AsyncMock(side_effect=exc)
        stub.add_centerline = AsyncMock(side_effect=exc)
        stub.add_polygon = AsyncMock(side_effect=exc)
        stub.add_ellipse = AsyncMock(side_effect=exc)
        stub.add_sketch_constraint = AsyncMock(side_effect=exc)
        stub.add_sketch_dimension = AsyncMock(side_effect=exc)
        stub.sketch_linear_pattern = AsyncMock(side_effect=exc)
        stub.sketch_circular_pattern = AsyncMock(side_effect=exc)
        stub.sketch_mirror = AsyncMock(side_effect=exc)
        stub.sketch_offset = AsyncMock(side_effect=exc)

        await register_sketching_tools(mcp_server, stub, mock_config)
        by_name = {t.name: t.func for t in mcp_server._tools}

        cases = [
            (
                "add_arc",
                AddArcInput(
                    center_x=0, center_y=0, start_x=5, start_y=0, end_x=0, end_y=5
                ),
            ),
            ("add_spline", AddSplineInput(points=[{"x": 0, "y": 0}])),
            ("add_centerline", AddLineInput(x1=0, y1=0, x2=0, y2=10)),
            ("add_polygon", {"center_x": 0}),
            ("add_ellipse", {"center_x": 0}),
            (
                "add_sketch_constraint",
                AddRelationInput(entity1="L1", relation_type="parallel"),
            ),
            (
                "add_sketch_dimension",
                AddDimensionInput(entity1="L1", dimension_type="linear", value=5.0),
            ),
            ("sketch_linear_pattern", {"entities": []}),
            ("sketch_circular_pattern", {"entities": []}),
            ("sketch_mirror", {"entities": []}),
            ("sketch_offset", {"entities": []}),
        ]
        for name, arg in cases:
            result = await by_name[name](arg)
            assert result["status"] == "error", (
                f"{name} should return error on exception"
            )

    # ── sketch_mirror / sketch_offset success paths ───────────────────────

    @pytest.mark.asyncio
    async def test_sketch_mirror_success_path(self, mcp_server, mock_config):
        """Test sketch mirror success path."""
        stub = SimpleNamespace()
        stub.sketch_mirror = AsyncMock(
            return_value=Mock(is_success=True, data="Mirror1", execution_time=0.1)
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(t.func for t in mcp_server._tools if t.name == "sketch_mirror")
        result = await tool_func({"entities": ["Line1", "Arc1"], "mirror_line": "CL1"})
        assert result["status"] == "success"
        assert result["mirror"]["entities"] == ["Line1", "Arc1"]

    @pytest.mark.asyncio
    async def test_sketch_offset_outward_and_inward(self, mcp_server, mock_config):
        """Test sketch offset outward and inward."""
        stub = SimpleNamespace()
        stub.sketch_offset = AsyncMock(
            return_value=Mock(is_success=True, data="Offset1", execution_time=0.1)
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(t.func for t in mcp_server._tools if t.name == "sketch_offset")

        r1 = await tool_func(
            {"entities": ["R1"], "offset_distance": 3.0, "reverse_direction": False}
        )
        assert r1["status"] == "success" and r1["offset"]["direction"] == "outward"

        stub.sketch_offset = AsyncMock(
            return_value=Mock(is_success=True, data="Offset2", execution_time=0.1)
        )
        r2 = await tool_func(
            {"entities": ["R1"], "offset_distance": 3.0, "reverse_direction": True}
        )
        assert r2["status"] == "success" and r2["offset"]["direction"] == "inward"

    # ── sketch_tutorial_simple_hole no-arg failure paths ─────────────────

    @pytest.mark.asyncio
    async def test_sketch_tutorial_hole_create_sketch_failure(
        self, mcp_server, mock_config
    ):
        """Test sketch tutorial hole create sketch failure."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(
            return_value=Mock(is_success=False, error="sketch failed")
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "sketch_tutorial_simple_hole"
        )
        result = await tool_func()
        assert result["status"] == "error" and "sketch failed" in result["message"]

    @pytest.mark.asyncio
    async def test_sketch_tutorial_hole_add_circle_failure(
        self, mcp_server, mock_config
    ):
        """Test sketch tutorial hole add circle failure."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(
            return_value=Mock(is_success=True, data="S1", execution_time=0.1)
        )
        stub.add_circle = AsyncMock(
            return_value=Mock(is_success=False, error="circle failed")
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "sketch_tutorial_simple_hole"
        )
        result = await tool_func()
        assert result["status"] == "error" and "circle failed" in result["message"]

    @pytest.mark.asyncio
    async def test_sketch_tutorial_hole_exit_sketch_failure(
        self, mcp_server, mock_config
    ):
        """Test sketch tutorial hole exit sketch failure."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(
            return_value=Mock(is_success=True, data="S1", execution_time=0.1)
        )
        stub.add_circle = AsyncMock(
            return_value=Mock(is_success=True, data="C1", execution_time=0.1)
        )
        stub.exit_sketch = AsyncMock(
            return_value=Mock(is_success=False, error="exit failed")
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "sketch_tutorial_simple_hole"
        )
        result = await tool_func()
        assert result["status"] == "error" and "exit failed" in result["message"]

    @pytest.mark.asyncio
    async def test_sketch_tutorial_hole_exception(self, mcp_server, mock_config):
        """Test sketch tutorial hole exception."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(side_effect=RuntimeError("boom"))
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "sketch_tutorial_simple_hole"
        )
        result = await tool_func()
        assert result["status"] == "error"

    # ── tutorial_simple_hole failure paths ────────────────────────────────

    @pytest.mark.asyncio
    async def test_tutorial_hole_circle_failure(self, mcp_server, mock_config):
        """Test tutorial hole circle failure."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(
            return_value=Mock(is_success=True, data="S1", execution_time=0.1)
        )
        stub.add_sketch_circle = AsyncMock(
            return_value=Mock(is_success=False, error="circle failed")
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "tutorial_simple_hole"
        )
        result = await tool_func(
            TutorialSimpleHoleInput(
                plane="Top", center_x=0, center_y=0, diameter=8, depth=10
            )
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_tutorial_hole_exit_failure(self, mcp_server, mock_config):
        """Test tutorial hole exit failure."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(
            return_value=Mock(is_success=True, data="S1", execution_time=0.1)
        )
        stub.add_sketch_circle = AsyncMock(
            return_value=Mock(is_success=True, data="C1", execution_time=0.1)
        )
        stub.exit_sketch = AsyncMock(
            return_value=Mock(is_success=False, error="exit failed")
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "tutorial_simple_hole"
        )
        result = await tool_func(
            TutorialSimpleHoleInput(
                plane="Top", center_x=0, center_y=0, diameter=8, depth=10
            )
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_tutorial_hole_cut_failure(self, mcp_server, mock_config):
        """Test tutorial hole cut failure."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(
            return_value=Mock(is_success=True, data="S1", execution_time=0.1)
        )
        stub.add_sketch_circle = AsyncMock(
            return_value=Mock(is_success=True, data="C1", execution_time=0.1)
        )
        stub.exit_sketch = AsyncMock(
            return_value=Mock(is_success=True, data=None, execution_time=0.1)
        )
        stub.create_cut = AsyncMock(
            return_value=Mock(is_success=False, error="cut failed")
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "tutorial_simple_hole"
        )
        result = await tool_func(
            TutorialSimpleHoleInput(
                plane="Top", center_x=0, center_y=0, diameter=8, depth=10
            )
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_tutorial_hole_depth_none_uses_diameter(
        self, mcp_server, mock_config
    ):
        """When depth is None, cut_depth equals diameter."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(
            return_value=Mock(is_success=True, data="S1", execution_time=0.1)
        )
        stub.add_sketch_circle = AsyncMock(
            return_value=Mock(is_success=True, data="C1", execution_time=0.1)
        )
        stub.exit_sketch = AsyncMock(
            return_value=Mock(is_success=True, data=None, execution_time=0.1)
        )
        stub.create_cut = AsyncMock(
            return_value=Mock(
                is_success=True, data={"cut_name": "Cut1"}, execution_time=0.5
            )
        )
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "tutorial_simple_hole"
        )
        result = await tool_func(
            TutorialSimpleHoleInput(
                plane="Top", center_x=0, center_y=0, diameter=8, depth=None
            )
        )
        assert result["status"] == "success"
        assert result["tutorial"]["depth"] is None
        stub.create_cut.assert_called_once_with("HoleSketch", 8.0)

    @pytest.mark.asyncio
    async def test_tutorial_hole_exception_path(self, mcp_server, mock_config):
        """Test tutorial hole exception path."""
        stub = SimpleNamespace()
        stub.create_sketch = AsyncMock(side_effect=RuntimeError("boom"))
        await register_sketching_tools(mcp_server, stub, mock_config)
        tool_func = next(
            t.func for t in mcp_server._tools if t.name == "tutorial_simple_hole"
        )
        result = await tool_func(
            TutorialSimpleHoleInput(
                plane="Top", center_x=0, center_y=0, diameter=5, depth=10
            )
        )
        assert result["status"] == "error"
