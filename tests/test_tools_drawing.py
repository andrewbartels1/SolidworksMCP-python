"""
Tests for SolidWorks drawing tools.

Comprehensive test suite covering drawing creation, view management,
dimensioning, and annotation operations.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.solidworks_mcp.tools.drawing import (
    AddDimensionInput,
    AddNoteInput,
    AnnotationInput,
    CreateDetailViewInput,
    CreateDrawingViewInput,
    CreateSectionViewInput,
    DimensionInput,
    DrawingCreationInput,
    DrawingViewInput,
    UpdateSheetFormatInput,
    register_drawing_tools,
)


class TestDrawingTools:
    """Test suite for drawing tools."""

    @pytest.mark.asyncio
    async def test_register_drawing_tools(self, mcp_server, mock_adapter, mock_config):
        """Test that drawing tools register correctly."""
        tool_count = await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        assert tool_count == 8

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

        input_data = DrawingCreationInput(
            model_file="test_part.sldprt",
            template="A_size_template.drwdot",
            output_path="drawings/part_drawing.slddrw",
            sheet_format="A (ANSI) Landscape",
            scale="1:1",
            auto_populate_views=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_technical_drawing":
                tool_func = tool.handler
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
        for tool in mcp_server._tools:
            if tool.name == "add_drawing_view":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["view_name"] == "Detail A"
        assert result["data"]["scale"] == "2:1"
        mock_adapter.add_drawing_view.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_dimension_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful dimension addition."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.add_dimension = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "dimension_type": "Linear",
                    "dimension_value": "25.00",
                    "dimension_unit": "mm",
                    "position": [75.0, 45.0],
                    "tolerance": "±0.1",
                },
                execution_time=0.3,
            )
        )

        input_data = DimensionInput(
            drawing_path="part_drawing.slddrw",
            dimension_type="Linear",
            entities=["Line1", "Line2"],
            position=[75.0, 45.0],
            tolerance="±0.1",
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "add_dimension":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["dimension_value"] == "25.00"
        assert result["data"]["tolerance"] == "±0.1"
        mock_adapter.add_dimension.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_annotation_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful annotation addition."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.add_annotation = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "annotation_text": "Material: Steel AISI 1020",
                    "annotation_type": "Note",
                    "position": [200.0, 280.0],
                    "font_size": 12,
                    "leader_attached": False,
                },
                execution_time=0.2,
            )
        )

        input_data = AnnotationInput(
            drawing_path="part_drawing.slddrw",
            annotation_type="Note",
            text="Material: Steel AISI 1020",
            position=[200.0, 280.0],
            font_size=12,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "add_annotation":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["annotation_text"] == "Material: Steel AISI 1020"
        assert result["data"]["font_size"] == 12
        mock_adapter.add_annotation.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_title_block_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful title block update."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.update_title_block = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "title": "Test Part Drawing",
                    "part_number": "SW-001-A",
                    "revision": "REV A",
                    "drawn_by": "Engineer",
                    "checked_by": "Manager",
                    "date": "2024-03-15",
                },
                execution_time=0.4,
            )
        )

        input_data = {
            "drawing_path": "part_drawing.slddrw",
            "title": "Test Part Drawing",
            "part_number": "SW-001-A",
            "revision": "REV A",
            "drawn_by": "Engineer",
            "checked_by": "Manager",
        }

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "update_title_block":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["title"] == "Test Part Drawing"
        assert result["data"]["revision"] == "REV A"
        mock_adapter.update_title_block.assert_called_once()

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

        input_data = DrawingCreationInput(
            model_file="test_part.sldprt", template="missing_template.drwdot"
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_technical_drawing":
                tool_func = tool.handler
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
        for tool in mcp_server._tools:
            if tool.name == "add_drawing_view":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Parent view not found" in result["message"]

    @pytest.mark.unit
    def test_drawing_creation_input_validation(self):
        """Test input validation for drawing creation."""
        # Valid input
        valid_input = DrawingCreationInput(
            model_file="test.sldprt", template="template.drwdot"
        )
        assert valid_input.model_file == "test.sldprt"
        assert valid_input.template == "template.drwdot"

        # Test optional parameters
        full_input = DrawingCreationInput(
            model_file="test.sldprt",
            template="template.drwdot",
            scale="1:2",
            auto_populate_views=True,
        )
        assert full_input.scale == "1:2"
        assert full_input.auto_populate_views is True

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

    @pytest.mark.unit
    def test_annotation_input_validation(self):
        """Test input validation for annotation operations."""
        # Valid input
        valid_input = AnnotationInput(
            drawing_path="test.slddrw", annotation_type="Note", text="Test note"
        )
        assert valid_input.drawing_path == "test.slddrw"
        assert valid_input.annotation_type == "Note"
        assert valid_input.text == "Test note"


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

    def test_annotation_input_position_normalization(self):
        """AnnotationInput.model_post_init extracts position_x/y from position list."""
        inp = AnnotationInput(
            annotation_type="Note",
            text="Hello",
            position=[30.0, 40.0],
        )
        assert inp.position_x == 30.0
        assert inp.position_y == 40.0

    # ── add_dimension: simulation path + exception ───────────────────────

    @pytest.mark.asyncio
    async def test_add_dimension_simulation_no_adapter_method(
        self, mcp_server, mock_adapter, mock_config
    ):
        """add_dimension falls back to simulation when adapter has no add_dimension."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        # Verify adapter does NOT have add_dimension; if it does, delete it.
        if hasattr(mock_adapter, "add_dimension"):
            del mock_adapter.add_dimension

        tool_func = next(
            (t.handler for t in mcp_server._tools if t.name == "add_dimension"), None
        )
        assert tool_func is not None

        input_data = AddDimensionInput(
            dimension_type="linear",
            entity1="Line1",
            position_x=50.0,
            position_y=60.0,
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_add_dimension_adapter_error_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """add_dimension returns error when adapter.add_dimension returns is_success=False."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.add_dimension = AsyncMock(
            return_value=Mock(is_success=False, error="dim failed", execution_time=0.1)
        )
        tool_func = next(
            (t.handler for t in mcp_server._tools if t.name == "add_dimension"), None
        )
        input_data = AddDimensionInput(
            dimension_type="linear",
            entity1="Line1",
            position_x=50.0,
            position_y=60.0,
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"

    # ── create_technical_drawing: no-adapter path with auto_populate_views=False ──

    @pytest.mark.asyncio
    async def test_create_technical_drawing_no_adapter_no_views(
        self, mcp_server, mock_adapter, mock_config
    ):
        """create_technical_drawing simulation path with auto_populate_views=False."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        if hasattr(mock_adapter, "create_technical_drawing"):
            del mock_adapter.create_technical_drawing

        input_data = DrawingCreationInput(
            model_file="part.sldprt",
            template="template.drwdot",
            auto_populate_views=False,
        )
        tool_func = next(
            (
                t.handler
                for t in mcp_server._tools
                if t.name == "create_technical_drawing"
            ),
            None,
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "success"
        assert result["data"]["views_created"] == []

    @pytest.mark.asyncio
    async def test_create_technical_drawing_adapter_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """create_technical_drawing uses adapter when available and succeeds."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.create_technical_drawing = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"drawing_path": "out.slddrw"},
                execution_time=1.0,
            )
        )
        input_data = DrawingCreationInput(
            model_file="part.sldprt", auto_populate_views=True
        )
        tool_func = next(
            (
                t.handler
                for t in mcp_server._tools
                if t.name == "create_technical_drawing"
            ),
            None,
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "success"
        assert result["data"]["drawing_path"] == "out.slddrw"

    # ── add_drawing_view: no-adapter simulation path ──────────────────────

    @pytest.mark.asyncio
    async def test_add_drawing_view_no_adapter_simulation(
        self, mcp_server, mock_adapter, mock_config
    ):
        """add_drawing_view simulation path when adapter lacks add_drawing_view."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        if hasattr(mock_adapter, "add_drawing_view"):
            del mock_adapter.add_drawing_view

        input_data = DrawingViewInput(
            drawing_path="part.slddrw",
            view_type="Front",
            view_name="Front View",
        )
        tool_func = next(
            (t.handler for t in mcp_server._tools if t.name == "add_drawing_view"), None
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "success"
        assert result["data"]["view_name"] == "Front View"

    # ── add_annotation: adapter error + no-adapter simulation paths ────────

    @pytest.mark.asyncio
    async def test_add_annotation_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """add_annotation returns error when adapter.add_annotation returns is_success=False."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.add_annotation = AsyncMock(
            return_value=Mock(
                is_success=False, error="annotation failed", execution_time=0.1
            )
        )
        input_data = AnnotationInput(
            annotation_type="Note",
            text="Test",
            position_x=10.0,
            position_y=20.0,
        )
        tool_func = next(
            (t.handler for t in mcp_server._tools if t.name == "add_annotation"), None
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_add_annotation_no_adapter_simulation(
        self, mcp_server, mock_adapter, mock_config
    ):
        """add_annotation falls back to simulation when adapter lacks add_annotation."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        if hasattr(mock_adapter, "add_annotation"):
            del mock_adapter.add_annotation

        input_data = AnnotationInput(
            annotation_type="Note",
            text="MaterialSpec",
            position_x=100.0,
            position_y=200.0,
        )
        tool_func = next(
            (t.handler for t in mcp_server._tools if t.name == "add_annotation"), None
        )
        result = await tool_func(input_data=input_data)
        assert result["status"] == "success"
        assert result["data"]["annotation_text"] == "MaterialSpec"

    # ── update_title_block: adapter error + no-adapter paths ───────────────

    @pytest.mark.asyncio
    async def test_update_title_block_adapter_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """update_title_block returns error when adapter returns is_success=False."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.update_title_block = AsyncMock(
            return_value=Mock(
                is_success=False, error="title failed", execution_time=0.1
            )
        )
        tool_func = next(
            (t.handler for t in mcp_server._tools if t.name == "update_title_block"),
            None,
        )
        result = await tool_func(
            input_data={"drawing_path": "d.slddrw", "title": "Widget"}
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_update_title_block_no_adapter_simulation(
        self, mcp_server, mock_adapter, mock_config
    ):
        """update_title_block simulation path when adapter lacks the method."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        if hasattr(mock_adapter, "update_title_block"):
            del mock_adapter.update_title_block

        payload = {"drawing_path": "d.slddrw", "title": "Widget", "revision": "A"}
        tool_func = next(
            (t.handler for t in mcp_server._tools if t.name == "update_title_block"),
            None,
        )
        result = await tool_func(input_data=payload)
        assert result["status"] == "success"
        assert result["data"]["title"] == "Widget"

    @pytest.mark.asyncio
    async def test_typed_drawing_tools_default_error_messages(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Covers fallback error message branches when adapter returns no error text."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_technical_drawing = AsyncMock(
            return_value=Mock(is_success=False, error=None, execution_time=0.1)
        )
        mock_adapter.add_drawing_view = AsyncMock(
            return_value=Mock(is_success=False, error=None, execution_time=0.1)
        )
        mock_adapter.add_annotation = AsyncMock(
            return_value=Mock(is_success=False, error=None, execution_time=0.1)
        )
        mock_adapter.update_title_block = AsyncMock(
            return_value=Mock(is_success=False, error=None, execution_time=0.1)
        )

        by_name = {t.name: t.handler for t in mcp_server._tools}

        r1 = await by_name["create_technical_drawing"](
            input_data=DrawingCreationInput(model_file="part.sldprt")
        )
        r2 = await by_name["add_drawing_view"](
            input_data=DrawingViewInput(
                drawing_path="d.slddrw",
                view_type="Front",
                view_name="Front",
            )
        )
        r3 = await by_name["add_annotation"](
            input_data=AnnotationInput(
                annotation_type="Note",
                text="x",
                position_x=1.0,
                position_y=2.0,
            )
        )
        r4 = await by_name["update_title_block"](input_data={"title": "Widget"})

        assert r1["status"] == "error"
        assert r1["message"] == "Failed to create technical drawing"
        assert r2["status"] == "error"
        assert r2["message"] == "Failed to add drawing view"
        assert r3["status"] == "error"
        assert r3["message"] == "Failed to add annotation"
        assert r4["status"] == "error"
        assert r4["message"] == "Failed to update title block"

    @pytest.mark.asyncio
    async def test_typed_drawing_tools_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover exception handlers for typed drawing tools."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_technical_drawing = AsyncMock(
            side_effect=RuntimeError("create boom")
        )
        mock_adapter.add_drawing_view = AsyncMock(side_effect=RuntimeError("view boom"))
        mock_adapter.add_annotation = AsyncMock(side_effect=RuntimeError("note boom"))
        mock_adapter.update_title_block = AsyncMock(
            side_effect=RuntimeError("title boom")
        )

        by_name = {t.name: t.handler for t in mcp_server._tools}

        r1 = await by_name["create_technical_drawing"](
            input_data=DrawingCreationInput(model_file="part.sldprt")
        )
        r2 = await by_name["add_drawing_view"](
            input_data=DrawingViewInput(
                drawing_path="d.slddrw",
                view_type="Front",
                view_name="Front",
            )
        )
        r3 = await by_name["add_annotation"](
            input_data=AnnotationInput(
                annotation_type="Note",
                text="x",
                position_x=1.0,
                position_y=2.0,
            )
        )
        r4 = await by_name["update_title_block"](input_data={"title": "Widget"})

        for result in (r1, r2, r3, r4):
            assert result["status"] == "error"
            assert "Unexpected error" in result["message"]

    # ── additional drawing tool branches (legacy tool set) ───────────────

    @pytest.mark.asyncio
    async def test_add_dimension_raw_dict_payload_normalization(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Covers dict payload branch with entities/position alias mapping."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        if hasattr(mock_adapter, "add_dimension"):
            del mock_adapter.add_dimension

        tool_func = next(
            (t.func for t in mcp_server._tools if t.name == "add_dimension"), None
        )
        result = await tool_func(
            {
                "dimension_type": "linear",
                "entities": ["Edge1", "Edge2"],
                "position": [11.0, 22.0],
                "precision": 3,
            }
        )

        assert result["status"] == "success"
        assert result["data"]["entity1"] == "Edge1"
        assert result["data"]["entity2"] == "Edge2"
        assert result["data"]["position"] == {"x": 11.0, "y": 22.0}
        assert result["data"]["precision"] == 3

    @pytest.mark.asyncio
    async def test_legacy_drawing_tools_success_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Covers success branches for legacy drawing utility tools."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        by_name = {t.name: t.func for t in mcp_server._tools}

        view = await by_name["create_drawing_view"](
            CreateDrawingViewInput(model_path="m.sldprt", view_type="isometric")
        )
        note = await by_name["add_note"](
            AddNoteInput(text="abc", position_x=1.0, position_y=2.0)
        )
        section = await by_name["create_section_view"](
            CreateSectionViewInput(
                section_line_start=(0.0, 0.0),
                section_line_end=(1.0, 1.0),
                view_position_x=10.0,
                view_position_y=20.0,
            )
        )
        detail = await by_name["create_detail_view"](
            CreateDetailViewInput(
                center_x=0.0,
                center_y=0.0,
                radius=2.0,
                view_position_x=3.0,
                view_position_y=4.0,
            )
        )
        sheet = await by_name["update_sheet_format"](
            UpdateSheetFormatInput(format_file="fmt.slddrt")
        )
        auto_dim = await by_name["auto_dimension_view"]({"view_name": "Front"})
        std = await by_name["check_drawing_standards"]({"standard": "ANSI"})

        assert view["status"] == "success"
        assert note["status"] == "success"
        assert section["status"] == "success"
        assert detail["status"] == "success"
        assert sheet["status"] == "success"
        assert auto_dim["status"] == "success"
        assert std["status"] == "success"

    @pytest.mark.asyncio
    async def test_legacy_drawing_tools_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Covers exception handlers in legacy drawing utility tools."""
        await register_drawing_tools(mcp_server, mock_adapter, mock_config)
        by_name = {t.name: t.func for t in mcp_server._tools}

        r1 = await by_name["create_drawing_view"]({"bad": True})
        r2 = await by_name["add_note"]({"bad": True})
        r3 = await by_name["create_section_view"]({"bad": True})
        r4 = await by_name["create_detail_view"]({"bad": True})
        r5 = await by_name["update_sheet_format"]({"bad": True})
        r6 = await by_name["auto_dimension_view"](None)
        r7 = await by_name["check_drawing_standards"](None)
        r8 = await by_name["add_dimension"](object())

        for result in (r1, r2, r3, r4, r5, r8):
            assert result["status"] == "error"
        assert r6["status"] == "success"
        assert r7["status"] == "success"
