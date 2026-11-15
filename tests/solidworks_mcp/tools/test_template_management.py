"""Tests for SolidWorks template management tools."""

import pytest

from solidworks_mcp.tools.template_management import (
    TemplateComparisonInput,
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
        assert tool_count == 1

    @pytest.mark.asyncio
    async def test_compare_templates_success(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Two files on disk are compared by content and size."""
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "compare_templates"
        )
        part = tmp_path / "part.prtdot"
        part.write_bytes(b"part template")
        copy = tmp_path / "copy.prtdot"
        copy.write_bytes(b"part template")
        assembly = tmp_path / "assembly.asmdot"
        assembly.write_bytes(b"assembly template, longer")

        same = await tool_func(
            input_data=TemplateComparisonInput(
                template1_path=str(part), template2_path=str(copy)
            )
        )
        other = await tool_func(
            input_data=TemplateComparisonInput(
                template1_path=str(part), template2_path=str(assembly)
            )
        )

        assert same["comparison"]["identical"] is True
        assert same["comparison"]["size_delta_bytes"] == 0
        assert other["comparison"]["identical"] is False
        assert other["comparison"]["size_delta_bytes"] == 12
        assert "only" in other["note"]

    @pytest.mark.asyncio
    async def test_compare_templates_refuses_its_old_switches(
        self, mcp_server, mock_adapter, mock_config
    ):
        await register_template_management_tools(mcp_server, mock_adapter, mock_config)
        tool_func = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "compare_templates"
        )

        result = await tool_func(
            input_data={
                "template1_path": "a.prtdot",
                "template2_path": "b.prtdot",
                "include_properties": True,
            }
        )

        assert result["error_type"] == "invalid_input"
        assert "compares the two files on disk" in result["message"]

    @pytest.mark.asyncio
    async def test_compare_templates_reads_real_files(
        self, mcp_server, mock_config, tmp_path
    ):
        """compare_templates reports honest filesystem facts (existence,
        size, byte-identical check) instead of a fabricated similarity
        score, when no adapter can parse template internals."""
        await register_template_management_tools(mcp_server, object(), mock_config)

        compare_tool = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "compare_templates"
        )

        tpl_a = tmp_path / "a.prtdot"
        tpl_b = tmp_path / "b.prtdot"
        tpl_a.write_bytes(b"template content")
        tpl_b.write_bytes(b"template content")

        identical = await compare_tool(
            input_data=TemplateComparisonInput(
                template1_path=str(tpl_a), template2_path=str(tpl_b)
            )
        )
        assert identical["status"] == "success"
        assert identical["comparison"]["identical"] is True

        tpl_b.write_bytes(b"different template content")
        different = await compare_tool(
            input_data=TemplateComparisonInput(
                template1_path=str(tpl_a), template2_path=str(tpl_b)
            )
        )
        assert different["status"] == "success"
        assert different["comparison"]["identical"] is False

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
async def test_compare_templates_refuses_files_that_are_not_on_disk(
    mcp_server, mock_config
):
    """Two missing paths: an error naming them, not an invented comparison."""
    await register_template_management_tools(mcp_server, object(), mock_config)
    compare = next(
        t.fn for t in await mcp_server.list_tools() if t.name == "compare_templates"
    )

    result = await compare(
        input_data=TemplateComparisonInput(
            template1_path="templates/a.prtdot", template2_path="templates/b.prtdot"
        )
    )

    assert result["status"] == "error"
    assert "not found on disk" in result["message"]
