"""Tests for SolidWorks drawing tools."""

import re
from unittest.mock import AsyncMock, Mock

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.tools.drawing import (
    AutoCenterMarksInput,
    DimensionInput,
    DrawingCreationInput,
    DrawingViewInput,
    register_drawing_tools,
)


class TestDrawingTools:
    """Test suite for drawing tools."""

    @pytest.mark.asyncio
    async def test_register_drawing_tools(self, mcp_server, mock_adapter, mock_config):
        """The reported count matches the number of tools actually registered."""
        tool_count = await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        registered_tool_names = {tool.name for tool in await mcp_server.list_tools()}
        assert tool_count == len(registered_tool_names)

    @pytest.mark.asyncio
    async def test_create_technical_drawing_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful technical drawing creation."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_technical_drawing = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "drawing_path": "part_drawing.slddrw",
                    "template_used": "A_size_template.drwdot",
                    "views_created": ["Front", "Right", "Top", "Isometric"],
                    "sheet_format": "A (ANSI) Landscape",
                    "scale": "1:1",
                },
                execution_time=2.1,
            )
        )

        input_data = DrawingCreationInput(model_file="test_part.sldprt")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "create_technical_drawing":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["drawing_path"] == "part_drawing.slddrw"
        assert len(result["data"]["views_created"]) == 4
        mock_adapter.create_technical_drawing.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_drawing_view_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful drawing view addition."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.add_drawing_view = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "view_name": "Detail A",
                    "view_type": "Detail",
                    "position": [150.0, 100.0],
                    "scale": "2:1",
                    "orientation": "Front",
                },
                execution_time=0.8,
            )
        )

        input_data = DrawingViewInput(
            drawing_path="part_drawing.slddrw",
            view_type="Detail",
            view_name="Detail A",
            parent_view="Front",
            position=[150.0, 100.0],
            scale="2:1",
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "add_drawing_view":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["view_name"] == "Detail A"
        assert result["data"]["scale"] == "2:1"
        mock_adapter.add_drawing_view.assert_called_once()

    @pytest.mark.asyncio
    async def test_drawing_creation_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in drawing creation."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_technical_drawing = AsyncMock(
            return_value=Mock(
                is_success=False, error="Template file not found", execution_time=0.1
            )
        )

        input_data = DrawingCreationInput(model_file="test_part.sldprt")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "create_technical_drawing":
                tool_func = tool.fn
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Template file not found" in result["message"]

    @pytest.mark.asyncio
    async def test_view_addition_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in view addition."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.add_drawing_view = AsyncMock(
            return_value=Mock(
                is_success=False, error="Parent view not found", execution_time=0.1
            )
        )

        input_data = DrawingViewInput(
            drawing_path="part_drawing.slddrw",
            view_type="Section",
            parent_view="NonExistentView",
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "add_drawing_view":
                tool_func = tool.fn
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Parent view not found" in result["message"]

    @pytest.mark.asyncio
    async def test_auto_center_marks_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """auto_center_marks reports the before/after centre-mark delta."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.auto_center_marks = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "view": "Drawing View1",
                    "feature_types": ["holes"],
                    "center_marks_before": 0,
                    "center_marks_after": 4,
                    "center_marks_added": 4,
                },
                execution_time=0.1,
            )
        )

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "auto_center_marks"
        )
        result = await tool_func(
            input_data=AutoCenterMarksInput(view_name="Drawing View1")
        )
        from_dict = await tool_func(input_data={"view_name": "Drawing View1"})

        assert result["status"] == "success"
        assert "4 centre mark(s)" in result["message"]
        assert result["data"]["center_marks_added"] == 4
        assert from_dict["status"] == "success"
        mock_adapter.auto_center_marks.assert_awaited_with(
            "Drawing View1", True, False, True
        )

    @pytest.mark.asyncio
    async def test_auto_center_marks_surfaces_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """An unknown view surfaces the adapter's error message."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.auto_center_marks = AsyncMock(
            return_value=Mock(
                is_success=False, error="No view named 'Ghost'", execution_time=0.0
            )
        )

        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "auto_center_marks"
        )
        result = await tool_func(input_data=AutoCenterMarksInput(view_name="Ghost"))

        assert result["status"] == "error"
        assert "No view named 'Ghost'" in result["message"]

    @pytest.mark.asyncio
    async def test_auto_center_marks_error_without_adapter_method(
        self, mcp_server, mock_config
    ):
        """A bare object() adapter reports an error, not a fabrication."""
        await register_drawing_tools(mcp_server, object(), mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "auto_center_marks"
        )
        result = await tool_func(
            input_data=AutoCenterMarksInput(view_name="Drawing View1")
        )
        assert result["status"] == "error"
        assert "does not support auto_center_marks" in result["message"]

    def test_auto_center_marks_input_rejects_blank_view(self):
        """AutoCenterMarksInput.model_post_init rejects a blank view name."""
        with pytest.raises(ValueError, match="view_name is required"):
            AutoCenterMarksInput(view_name="   ")

    @pytest.mark.unit
    def test_drawing_creation_input_validation(self):
        """Test input validation for drawing creation."""
        # Valid input
        valid_input = DrawingCreationInput(model_file="test.sldprt")
        assert valid_input.model_file == "test.sldprt"
        assert valid_input.projection == "third_angle"

        first = DrawingCreationInput(model_file="test.sldprt", projection="first_angle")
        assert first.projection == "first_angle"
        with pytest.raises(ValueError):
            DrawingCreationInput(model_file="test.sldprt", projection="isometric")

    @pytest.mark.asyncio
    async def test_technical_drawing_refuses_removed_inputs(
        self, mcp_server, mock_adapter, mock_config
    ):
        """A removed input is refused with a pointer, before the adapter runs."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.create_technical_drawing = AsyncMock()
        tool = next(
            t.fn
            for t in await mcp_server.list_tools()
            if t.name == "create_technical_drawing"
        )

        result = await tool(
            input_data={"model_file": "p.sldprt", "template": "a.drwdot", "title": "T"}
        )

        assert result["error_type"] == "invalid_input"
        assert "`template`" in result["message"] and "`title`" in result["message"]
        assert "generate_drawing_package" in result["message"]
        mock_adapter.create_technical_drawing.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_drawing_view_refuses_other_operations(
        self, mcp_server, mock_adapter, mock_config
    ):
        """It only adds views; update or remove is refused, not ignored."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.add_drawing_view = AsyncMock()
        tool = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "add_drawing_view"
        )

        result = await tool(input_data={"operation": "remove", "view_name": "Front"})

        assert result["error_type"] == "invalid_input"
        assert "only adds views" in result["message"]
        mock_adapter.add_drawing_view.assert_not_awaited()

    @pytest.mark.unit
    def test_dimension_input_validation(self):
        """Test input validation for dimension operations."""
        # Valid input
        valid_input = DimensionInput(
            drawing_path="test.slddrw",
            dimension_type="Linear",
            entities=["Line1", "Line2"],
        )
        assert valid_input.drawing_path == "test.slddrw"
        assert valid_input.dimension_type == "Linear"
        assert len(valid_input.entities) == 2


class TestDrawingToolsBranchCoverage:
    """Branch coverage for uncovered drawing tool paths."""

    # ── Input model normalization ────────────────────────────────────────

    def test_dimension_input_entities_and_position_normalization(self):
        """DimensionInput.model_post_init extracts entity1/entity2 from entities list."""
        inp = DimensionInput(
            dimension_type="linear",
            entities=["EdgeA", "EdgeB"],
            position=[10.0, 20.0],
        )
        assert inp.entity1 == "EdgeA"
        assert inp.entity2 == "EdgeB"
        assert inp.position_x == 10.0
        assert inp.position_y == 20.0

    def test_dimension_input_single_entity_normalization(self):
        """DimensionInput with only one entity in list sets entity1, leaves entity2 None."""
        inp = DimensionInput(
            dimension_type="radial",
            entities=["Circle1"],
            position=[5.0, 15.0],
        )
        assert inp.entity1 == "Circle1"
        assert inp.entity2 is None
        assert inp.position_x == 5.0

    # ── add_dimension: simulation path + exception ───────────────────────

    # ── create_technical_drawing: no-adapter path with auto_populate_views=False ──

    @pytest.mark.asyncio
    async def test_create_technical_drawing_reports_the_real_outcome(
        self, mcp_server, mock_adapter, mock_config, monkeypatch
    ):
        """An adapter that cannot do the job produces an error, not a fake success.

        This asserted the tool's own refusal message, which is reached only
        when the adapter has no ``create_technical_drawing`` at all. The base
        adapter now defines a default for it, so the ``hasattr`` gate always
        passes and the adapter's error surfaces instead — still an error, and
        still naming the capability, just raised one layer deeper.

        Hiding the method on the mock leaves that inherited base default in
        place, which is exactly the path being asserted.
        """
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        monkeypatch.delattr(
            type(mock_adapter), "create_technical_drawing", raising=False
        )

        input_data = DrawingCreationInput(model_file="part.sldprt")
        tool_func = next(
            (
                t.fn
                for t in await mcp_server.list_tools()
                if t.name == "create_technical_drawing"
            ),
            None,
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "create_technical_drawing" in result["message"]

    @pytest.mark.asyncio
    async def test_create_technical_drawing_adapter_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Create_technical_drawing uses adapter when available and succeeds."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.create_technical_drawing = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"drawing_path": "out.slddrw"},
                execution_time=1.0,
            )
        )
        input_data = DrawingCreationInput(model_file="part.sldprt")
        tool_func = next(
            (
                t.fn
                for t in await mcp_server.list_tools()
                if t.name == "create_technical_drawing"
            ),
            None,
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "success"
        assert result["data"]["drawing_path"] == "out.slddrw"

    # ── add_drawing_view: no-adapter simulation path ──────────────────────

    @pytest.mark.asyncio
    async def test_add_drawing_view_reports_the_real_outcome(
        self, mcp_server, mock_adapter, mock_config, monkeypatch
    ):
        """A view that was never placed is an error, not an echo of the input.

        The base adapter now defines a default for ``add_drawing_view``, so
        the tool's ``hasattr`` gate always passes and the adapter's own error
        surfaces rather than the tool's refusal message. Both are errors and
        both name the capability; the assertion is narrowed to the part that
        still holds either way.
        """
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        monkeypatch.delattr(type(mock_adapter), "add_drawing_view", raising=False)

        input_data = DrawingViewInput(
            drawing_path="part.slddrw",
            view_type="Front",
            view_name="Front View",
        )
        tool_func = next(
            (
                t.fn
                for t in await mcp_server.list_tools()
                if t.name == "add_drawing_view"
            ),
            None,
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "add_drawing_view" in result["message"]

    # ── update_title_block: adapter error + no-adapter paths ───────────────

    @pytest.mark.asyncio
    async def test_update_title_block_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Update_title_block returns error when adapter returns is_success=False."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.update_title_block = AsyncMock(
            return_value=Mock(
                is_success=False, error="title failed", execution_time=0.1
            )
        )
        tool_func = next(
            (
                t.fn
                for t in await mcp_server.list_tools()
                if t.name == "update_title_block"
            ),
            None,
        )
        result = await tool_func(
            input_data={"drawing_path": "d.slddrw", "title": "Widget"}
        )
        assert result["status"] == "error"

    # ── additional drawing tool branches (legacy tool set) ───────────────


async def _tool(mcp_server, name: str):
    """Test helper for tool."""
    for registered in await mcp_server.list_tools():
        if registered.name == name:
            return registered.fn
    raise AssertionError(f"Tool not found: {name}")


#: Capabilities a tool on this branch already reaches. ``tools/drawing.py``
#: guards each tool with ``require_capability(adapter, "<name>", ...)``, so a rename here
#: leaves the tool refusing forever with every adapter test still green.
GATED_ON_THIS_BRANCH = [
    "add_drawing_view",
    "create_technical_drawing",
    "auto_center_marks",
]


@pytest.mark.parametrize("capability", GATED_ON_THIS_BRANCH)
def test_capability_names_match_the_tool_gates(capability: str) -> None:
    """A tool on this branch must reach the adapter by this exact name."""
    from pathlib import Path

    import solidworks_mcp.tools.drawing as drawing_tools

    source = Path(drawing_tools.__file__).read_text(encoding="utf-8")
    assert re.search(rf'require_capability\(\s*adapter,\s*"{capability}"', source), (
        f"no tool in drawing.py gates on adapter.{capability}; either the tool "
        "gate was renamed or this capability is unreachable"
    )


async def _tool_issue106_tools(mcp_server, name: str):  # noqa: ANN001, ANN202
    return next(t.fn for t in await mcp_server.list_tools() if t.name == name)


@pytest.mark.asyncio
async def test_list_drawing_views_tool(mcp_server, mock_adapter, mock_config) -> None:
    """Views are listed with a count; adapter errors are reported."""
    await register_drawing_tools(mcp_server, mock_adapter, mock_config)
    tool = await _tool_issue106_tools(mcp_server, "list_drawing_views")

    mock_adapter.list_drawing_views = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=["Drawing View1", "Drawing View2"]
        )
    )
    ok = await tool()
    assert ok["status"] == "success"
    assert ok["count"] == 2 and ok["views"] == ["Drawing View1", "Drawing View2"]

    mock_adapter.list_drawing_views = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data=[])
    )
    assert (await tool())["message"] == "The drawing has no views"

    mock_adapter.list_drawing_views = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="This operation requires a drawing document",
        )
    )
    err = await tool()
    assert err["status"] == "error" and "drawing document" in err["message"]

    mock_adapter.list_drawing_views = AsyncMock(side_effect=RuntimeError("boom"))
    crashed = await tool()
    assert crashed["error_type"] == "internal"
    assert crashed["message"] == "list_drawing_views failed: RuntimeError: boom"


@pytest.mark.asyncio
async def test_add_note_places_a_note(mcp_server, mock_adapter, mock_config) -> None:
    await register_drawing_tools(mcp_server, mock_adapter, mock_config)
    tool = next(t.fn for t in await mcp_server.list_tools() if t.name == "add_note")
    mock_adapter.add_note = AsyncMock(
        return_value=Mock(
            is_success=True, data={"text": "MATERIAL"}, execution_time=0.1
        )
    )

    result = await tool({"text": "MATERIAL: 6061", "position_x": 20, "position_y": 30})

    assert result["status"] == "success"
    assert result["message"] == "Added note: MATERIAL: 6061..."


@pytest.mark.asyncio
async def test_add_note_refuses_without_the_capability(mcp_server, mock_config) -> None:
    await register_drawing_tools(mcp_server, object(), mock_config)
    tool = next(t.fn for t in await mcp_server.list_tools() if t.name == "add_note")

    result = await tool({"text": "X", "position_x": 1, "position_y": 1})

    assert result["error_type"] == "not_supported"
