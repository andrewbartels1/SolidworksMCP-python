"""
Tests for SolidWorks template management tools.

Comprehensive test suite covering template extraction, application,
comparison, and library management operations.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.solidworks_mcp.tools.template_management import (
    TemplateApplicationInput,
    TemplateBatchInput,
    TemplateComparisonInput,
    TemplateExtractionInput,
    register_template_management_tools,
)


class TestTemplateManagementTools:
    """Test suite for template management tools."""

    @pytest.mark.asyncio
    async def test_register_template_management_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that template management tools register correctly."""
        tool_count = await register_template_management_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 6

    @pytest.mark.asyncio
    async def test_extract_template_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful template extraction from model."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.extract_template = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "template_file": "extracted_template.prtdot",
                    "template_type": "Part",
                    "source_model": "reference_part.sldprt",
                    "extracted_elements": [
                        "Custom properties",
                        "Material assignment",
                        "Dimension styles",
                        "Feature tree structure",
                    ],
                    "properties_count": 12,
                    "template_size": "250 KB",
                },
                execution_time=1.8,
            )
        )

        input_data = TemplateExtractionInput(
            source_model="reference_part.sldprt",
            template_name="Engineering Part Template",
            template_type="part",
            save_path="templates/extracted_template.prtdot",
            include_custom_properties=True,
            include_dimensions=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "extract_template":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["template_file"] == "extracted_template.prtdot"
        assert result["data"]["properties_count"] == 12
        assert "Custom properties" in result["data"]["extracted_elements"]
        mock_adapter.extract_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_template_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful template application to model."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.apply_template = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "target_model": "new_part.sldprt",
                    "template_applied": "engineering_template.prtdot",
                    "applied_elements": [
                        "Custom properties",
                        "Material assignment",
                        "Dimension formatting",
                        "Units system",
                    ],
                    "properties_applied": 8,
                    "overwritten_properties": 2,
                    "application_time": 1.2,
                },
                execution_time=1.2,
            )
        )

        input_data = TemplateApplicationInput(
            template_path="templates/engineering_template.prtdot",
            target_model="new_part.sldprt",
            overwrite_existing=True,
            apply_dimensions=True,
            apply_materials=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "apply_template":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["template_applied"] == "engineering_template.prtdot"
        assert result["data"]["properties_applied"] == 8
        assert "Material assignment" in result["data"]["applied_elements"]
        mock_adapter.apply_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_apply_template_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful batch template application."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.batch_apply_template = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "template_used": "standard_template.prtdot",
                    "total_files": 15,
                    "processed_files": 14,
                    "failed_files": 1,
                    "processing_time": 18.5,
                    "results": [
                        {
                            "file": "part1.sldprt",
                            "status": "success",
                            "properties_applied": 6,
                        },
                        {
                            "file": "part2.sldprt",
                            "status": "success",
                            "properties_applied": 6,
                        },
                        {
                            "file": "part3.sldprt",
                            "status": "failed",
                            "error": "File locked",
                        },
                        # ... more results
                    ],
                    "average_properties_per_file": 6.2,
                },
                execution_time=18.5,
            )
        )

        input_data = TemplateBatchInput(
            template_path="templates/standard_template.prtdot",
            source_folder="./parts/",
            output_folder="./parts_updated/",
            file_pattern="*.sldprt",
            include_subdirectories=True,
            overwrite_existing=True,
            create_backup=True,
            parallel_processing=False,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "batch_apply_template":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["total_files"] == 15
        assert result["data"]["processed_files"] == 14
        assert result["data"]["failed_files"] == 1
        mock_adapter.batch_apply_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_compare_templates_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful template comparison."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.compare_templates = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "template1": "old_template.prtdot",
                    "template2": "new_template.prtdot",
                    "differences_found": 8,
                    "similarity_percentage": 75.5,
                    "added_properties": ["MaterialDensity", "CostCenter"],
                    "removed_properties": ["OldRevision"],
                    "modified_properties": ["Description", "PartNumber", "Author"],
                    "identical_properties": [
                        "Title",
                        "Subject",
                        "Keywords",
                        "Comments",
                    ],
                    "comparison_details": {
                        "units_different": False,
                        "dimensions_different": True,
                        "materials_different": False,
                        "custom_properties_different": True,
                    },
                },
                execution_time=0.9,
            )
        )

        input_data = TemplateComparisonInput(
            template1_path="templates/old_template.prtdot",
            template2_path="templates/new_template.prtdot",
            comparison_depth="Detailed",
            include_properties=True,
            include_dimensions=True,
            include_materials=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "compare_templates":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["differences_found"] == 8
        assert result["data"]["similarity_percentage"] == 75.5
        assert "MaterialDensity" in result["data"]["added_properties"]
        assert (
            result["data"]["comparison_details"]["custom_properties_different"] is True
        )
        mock_adapter.compare_templates.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_to_template_library_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful template library save."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.save_to_template_library = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "library_name": "Engineering Templates",
                    "template_name": "Standard Part Template v2.1",
                    "library_path": "C:\\Templates\\Library\\",
                    "template_id": "TPL_001_v21",
                    "category": "Mechanical Parts",
                    "tags": ["Standard", "Engineering", "ISO"],
                    "version": "2.1",
                    "created_date": "2024-03-15",
                    "file_size": "180 KB",
                },
                execution_time=0.6,
            )
        )

        input_data = {
            "template_file": "new_template.prtdot",
            "library_name": "Engineering Templates",
            "template_name": "Standard Part Template v2.1",
            "template_description": "Standard engineering part template with updated properties",
            "category": "Mechanical Parts",
            "tags": ["Standard", "Engineering", "ISO"],
            "version": "2.1",
            "author": "Engineering Team",
            "replace_existing": False,
        }

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "save_to_template_library":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["template_name"] == "Standard Part Template v2.1"
        assert result["data"]["template_id"] == "TPL_001_v21"
        assert "Engineering" in result["data"]["tags"]
        mock_adapter.save_to_template_library.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_template_library_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful template library listing."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.list_template_library = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "library_name": "Engineering Templates",
                    "total_templates": 25,
                    "categories": [
                        "Mechanical Parts",
                        "Electrical",
                        "Structural",
                        "Assemblies",
                    ],
                    "templates": [
                        {
                            "id": "TPL_001",
                            "name": "Standard Part Template",
                            "category": "Mechanical Parts",
                            "version": "2.1",
                            "created": "2024-01-15",
                            "tags": ["Standard", "Engineering"],
                        },
                        {
                            "id": "TPL_002",
                            "name": "Assembly Template",
                            "category": "Assemblies",
                            "version": "1.8",
                            "created": "2024-02-10",
                            "tags": ["Assembly", "Standard"],
                        },
                        # ... more templates
                    ],
                    "library_size": "12.5 MB",
                    "last_updated": "2024-03-15",
                },
                execution_time=0.4,
            )
        )

        input_data = {
            "library_path": "C:\\Templates\\Library\\",
            "filter_category": "",
            "filter_tags": [],
            "sort_by": "created_date",
            "sort_order": "desc",
            "include_details": True,
        }

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "list_template_library":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["total_templates"] == 25
        assert len(result["data"]["categories"]) == 4
        assert "Mechanical Parts" in result["data"]["categories"]
        assert len(result["data"]["templates"]) >= 2
        mock_adapter.list_template_library.assert_called_once()

    @pytest.mark.asyncio
    async def test_template_extraction_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in template extraction."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.extract_template = AsyncMock(
            return_value=Mock(
                is_success=False,
                error="Source model file not found",
                execution_time=0.1,
            )
        )

        input_data = TemplateExtractionInput(
            source_model="missing_file.sldprt",
            template_name="Test Template",
            template_type="part",
            save_path="templates/test.prtdot",
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "extract_template":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Source model file not found" in result["message"]

    @pytest.mark.asyncio
    async def test_template_management_fallback_paths(self, mcp_server, mock_config):
        """Test fallback simulation payloads when adapter methods are unavailable."""
        await register_template_management_tools(mcp_server, object(), mock_config)

        extract_tool = None
        apply_tool = None
        batch_tool = None
        compare_tool = None
        save_tool = None
        list_tool = None

        for tool in mcp_server._tools:
            if tool.name == "extract_template":
                extract_tool = tool.handler
            if tool.name == "apply_template":
                apply_tool = tool.handler
            if tool.name == "batch_apply_template":
                batch_tool = tool.handler
            if tool.name == "compare_templates":
                compare_tool = tool.handler
            if tool.name == "save_to_template_library":
                save_tool = tool.handler
            if tool.name == "list_template_library":
                list_tool = tool.handler

        assert extract_tool is not None
        assert apply_tool is not None
        assert batch_tool is not None
        assert compare_tool is not None
        assert save_tool is not None
        assert list_tool is not None

        extract_result = await extract_tool(
            input_data=TemplateExtractionInput(
                source_model="part.sldprt",
                template_name="Fallback Template",
                template_type="part",
                save_path="templates/fallback.prtdot",
            )
        )
        assert extract_result["status"] == "success"
        assert extract_result["template"]["name"] == "Fallback Template"

        apply_result = await apply_tool(
            input_data=TemplateApplicationInput(
                template_path="templates/fallback.prtdot",
                target_model="target.sldprt",
                overwrite_existing=True,
            )
        )
        assert apply_result["status"] == "success"
        assert apply_result["template_application"]["target_model"] == "target.sldprt"

        batch_result = await batch_tool(
            input_data=TemplateBatchInput(
                template_path="templates/fallback.prtdot",
                source_folder="./parts",
                file_pattern="*.sldprt",
                recursive=False,
                backup_originals=False,
            )
        )
        assert batch_result["status"] == "success"
        assert batch_result["batch_operation"]["summary"]["total_scanned"] == 4

        compare_result = await compare_tool(
            input_data=TemplateComparisonInput(
                template1_path="templates/a.prtdot",
                template2_path="templates/b.prtdot",
                comparison_type="full",
            )
        )
        assert compare_result["status"] == "success"
        assert compare_result["comparison"]["similarity_score"] == 85.5

        save_result = await save_tool(
            input_data={
                "template_name": "Library Fallback",
                "template_path": "templates/fallback.prtdot",
                "category": "parts",
                "author": "QA",
            }
        )
        assert save_result["status"] == "success"
        assert "library_entry" in save_result

        list_result = await list_tool(
            input_data={"category": "all", "search_term": "", "sort_by": "name"}
        )
        assert list_result["status"] == "success"
        assert len(list_result["templates"]) >= 1

    @pytest.mark.asyncio
    async def test_template_management_adapter_error_and_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test adapter error returns and exception handlers for template tools."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.apply_template = AsyncMock(
            return_value=Mock(is_success=False, error="template apply failed")
        )
        mock_adapter.compare_templates = AsyncMock(
            return_value=Mock(is_success=False, error="template compare failed")
        )
        mock_adapter.save_to_template_library = AsyncMock(
            side_effect=RuntimeError("library storage down")
        )
        mock_adapter.list_template_library = AsyncMock(
            side_effect=RuntimeError("index unavailable")
        )

        apply_tool = None
        compare_tool = None
        save_tool = None
        list_tool = None
        for tool in mcp_server._tools:
            if tool.name == "apply_template":
                apply_tool = tool.handler
            if tool.name == "compare_templates":
                compare_tool = tool.handler
            if tool.name == "save_to_template_library":
                save_tool = tool.handler
            if tool.name == "list_template_library":
                list_tool = tool.handler

        assert apply_tool is not None
        assert compare_tool is not None
        assert save_tool is not None
        assert list_tool is not None

        apply_error = await apply_tool(
            input_data=TemplateApplicationInput(
                template_path="templates/fallback.prtdot", target_model="target.sldprt"
            )
        )
        assert apply_error["status"] == "error"
        assert "template apply failed" in apply_error["message"]

        compare_error = await compare_tool(
            input_data=TemplateComparisonInput(
                template1_path="templates/a.prtdot", template2_path="templates/b.prtdot"
            )
        )
        assert compare_error["status"] == "error"
        assert "template compare failed" in compare_error["message"]

        save_exception = await save_tool(input_data={"template_name": "bad"})
        assert save_exception["status"] == "error"
        assert "Failed to save to library" in save_exception["message"]

        list_exception = await list_tool(input_data={"category": "all"})
        assert list_exception["status"] == "error"
        assert "Failed to list library" in list_exception["message"]

    @pytest.mark.unit
    def test_template_extraction_input_validation(self):
        """Test input validation for template extraction."""
        # Valid input
        valid_input = TemplateExtractionInput(
            source_model="test.sldprt",
            template_name="Test Template",
            template_type="part",
            save_path="templates/test.prtdot",
        )
        assert valid_input.source_model == "test.sldprt"
        assert valid_input.template_type == "part"

        # Test with optional parameters
        full_input = TemplateExtractionInput(
            source_model="test.sldprt",
            template_name="Test Template",
            template_type="part",
            save_path="templates/test.prtdot",
            include_custom_properties=True,
            include_dimensions=False,
        )
        assert full_input.include_custom_properties is True
        assert full_input.include_dimensions is False

    @pytest.mark.unit
    def test_template_application_input_validation(self):
        """Test input validation for template application."""
        # Valid input
        valid_input = TemplateApplicationInput(
            template_path="template.prtdot", target_model="model.sldprt"
        )
        assert valid_input.template_path == "template.prtdot"
        assert valid_input.target_model == "model.sldprt"

        # Test default values
        assert valid_input.overwrite_existing is False
        assert valid_input.apply_dimensions is True
        assert valid_input.apply_materials is True

    @pytest.mark.unit
    def test_template_comparison_input_validation(self):
        """Test input validation for template comparison."""
        # Valid input
        valid_input = TemplateComparisonInput(
            template1_path="template1.prtdot", template2_path="template2.prtdot"
        )
        assert valid_input.template1_path == "template1.prtdot"
        assert valid_input.template2_path == "template2.prtdot"

        # Test optional parameters
        full_input = TemplateComparisonInput(
            template1_path="template1.prtdot",
            template2_path="template2.prtdot",
            comparison_depth="Detailed",
            include_properties=True,
            include_dimensions=False,
        )
        assert full_input.comparison_depth == "Detailed"
        assert full_input.include_properties is True
        assert full_input.include_dimensions is False


class TestTemplateManagementBranchCoverage:
    """Additional branch coverage for template management tools."""

    @pytest.mark.asyncio
    async def test_typed_template_tools_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Exercise exception blocks for typed-input template tools via compat runner."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)
        by_name = {t.name: t.func for t in mcp_server._tools}

        r1 = await by_name["extract_template"]({"bad": True})
        r2 = await by_name["apply_template"]({"bad": True})
        r3 = await by_name["batch_apply_template"]({"bad": True})
        r4 = await by_name["compare_templates"]({"bad": True})

        for result in (r1, r2, r3, r4):
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_batch_apply_template_adapter_error_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover adapter non-success branch for batch_apply_template."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.batch_apply_template = AsyncMock(
            return_value=Mock(is_success=False, error="batch apply failed")
        )

        tool = next(
            t.handler for t in mcp_server._tools if t.name == "batch_apply_template"
        )
        result = await tool(
            input_data=TemplateBatchInput(
                template_path="templates/t.prtdot",
                source_folder="./parts",
                file_pattern="*.sldprt",
            )
        )
        assert result["status"] == "error"
        assert "batch apply failed" in result["message"]

    @pytest.mark.asyncio
    async def test_list_template_library_sort_and_filter_branches(
        self, mcp_server, mock_config
    ):
        """Cover category/search/sort fallback branches in list_template_library."""
        await register_template_management_tools(mcp_server, object(), mock_config)
        tool = next(
            t.handler for t in mcp_server._tools if t.name == "list_template_library"
        )

        usage_sorted = await tool(
            input_data={
                "category": "drawings",
                "search_term": "ISO",
                "sort_by": "usage",
            }
        )
        date_sorted = await tool(
            input_data={
                "category": "all",
                "search_term": "Template",
                "sort_by": "date",
            }
        )

        assert usage_sorted["status"] == "success"
        assert usage_sorted["library_search"]["category_filter"] == "drawings"
        assert usage_sorted["library_search"]["sort_by"] == "usage"
        assert all(t["category"] == "drawings" for t in usage_sorted["templates"])

        assert date_sorted["status"] == "success"
        assert date_sorted["library_search"]["sort_by"] == "date"

    @pytest.mark.asyncio
    async def test_library_adapter_error_result_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover adapter non-success returns for save_to_template_library and list_template_library."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.save_to_template_library = AsyncMock(
            return_value=Mock(is_success=False, error=None)
        )
        mock_adapter.list_template_library = AsyncMock(
            return_value=Mock(is_success=False, error=None)
        )

        save_tool = next(
            t.handler for t in mcp_server._tools if t.name == "save_to_template_library"
        )
        list_tool = next(
            t.handler for t in mcp_server._tools if t.name == "list_template_library"
        )

        save_result = await save_tool(input_data={"template_name": "bad"})
        list_result = await list_tool(input_data={"category": "all"})

        assert save_result["status"] == "error"
        assert "failed to save to library" in save_result["message"].lower()
        assert list_result["status"] == "error"
        assert "failed to list template library" in list_result["message"].lower()
