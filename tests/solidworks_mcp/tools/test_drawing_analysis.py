"""Tests for SolidWorks drawing analysis tools."""

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
from solidworks_mcp.tools.drawing import (
    AnnotationInput,
    DrawingCreationInput,
    DrawingViewInput,
    register_drawing_tools,
)
from solidworks_mcp.tools.drawing_analysis import (
    AnnotationAnalysisInput,
    ComplianceCheckInput,
    DimensionAnalysisInput,
    DrawingAnalysisInput,
    register_drawing_analysis_tools,
)


class TestDrawingAnalysisTools:
    """Test suite for drawing analysis tools."""

    @pytest.mark.asyncio
    async def test_register_drawing_analysis_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that drawing analysis tools register correctly."""
        tool_count = await register_drawing_analysis_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 8

    @pytest.mark.asyncio
    async def test_analyze_drawing_comprehensive_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful comprehensive drawing analysis."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_drawing_comprehensive = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "drawing_file": "part_drawing.slddrw",
                    "analysis_summary": {
                        "total_views": 4,
                        "total_dimensions": 28,
                        "total_annotations": 12,
                        "compliance_score": 85.5,
                        "completeness_score": 92.3,
                        "quality_rating": "Good",
                    },
                    "view_analysis": [
                        {
                            "view_name": "Drawing View1",
                            "type": "Front",
                            "scale": "1:1",
                            "status": "Complete",
                        },
                        {
                            "view_name": "Drawing View2",
                            "type": "Right",
                            "scale": "1:1",
                            "status": "Complete",
                        },
                        {
                            "view_name": "Drawing View3",
                            "type": "Top",
                            "scale": "1:1",
                            "status": "Missing dimensions",
                        },
                        {
                            "view_name": "Drawing View4",
                            "type": "Isometric",
                            "scale": "1:2",
                            "status": "Complete",
                        },
                    ],
                    "dimension_analysis": {
                        "critical_dimensions": 18,
                        "reference_dimensions": 10,
                        "missing_dimensions": ["Overall height", "Hole diameter"],
                        "dimension_tolerances": "Standard",
                    },
                    "annotation_analysis": {
                        "surface_finish_symbols": 6,
                        "geometric_tolerances": 4,
                        "notes": 8,
                        "missing_annotations": [
                            "Material specification",
                            "Heat treatment note",
                        ],
                    },
                    "issues_found": [
                        {
                            "severity": "Medium",
                            "type": "Missing dimension",
                            "description": "Overall height not dimensioned",
                        },
                        {
                            "severity": "Low",
                            "type": "Missing note",
                            "description": "Material specification note missing",
                        },
                    ],
                },
                execution_time=3.2,
            )
        )

        input_data = DrawingAnalysisInput(
            drawing_path="part_drawing.slddrw",
            analysis_depth="Comprehensive",
            check_dimensions=True,
            check_annotations=True,
            check_compliance=True,
            standards=["ISO", "ASME"],
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_comprehensive":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["analysis_summary"]["total_views"] == 4
        assert result["data"]["analysis_summary"]["compliance_score"] == 85.5
        assert len(result["data"]["view_analysis"]) == 4
        assert len(result["data"]["issues_found"]) == 2
        mock_adapter.analyze_drawing_comprehensive.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_drawing_dimensions_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful drawing dimension analysis."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_drawing_dimensions = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "drawing_file": "part_drawing.slddrw",
                    "dimension_summary": {
                        "total_dimensions": 28,
                        "linear_dimensions": 18,
                        "angular_dimensions": 4,
                        "radial_dimensions": 6,
                        "toleranced_dimensions": 15,
                        "reference_dimensions": 8,
                    },
                    "dimension_quality": {
                        "placement_score": 88.5,
                        "readability_score": 91.2,
                        "standards_compliance": 85.0,
                        "completeness": 92.8,
                    },
                    "dimension_issues": [
                        {"type": "Overlapping", "count": 2, "severity": "Medium"},
                        {"type": "Missing tolerance", "count": 3, "severity": "High"},
                        {"type": "Poor placement", "count": 1, "severity": "Low"},
                    ],
                    "recommendations": [
                        "Add tolerances to critical dimensions",
                        "Reposition overlapping dimensions",
                        "Consider adding reference dimensions for manufacturing",
                    ],
                    "standards_analysis": {
                        "iso_compliance": 87.5,
                        "asme_compliance": 82.0,
                        "company_standards": 90.0,
                    },
                },
                execution_time=1.8,
            )
        )

        input_data = DimensionAnalysisInput(
            drawing_path="part_drawing.slddrw",
            analysis_type="Quality assessment",
            check_tolerances=True,
            check_placement=True,
            standards_compliance=True,
            reference_standards=["ISO 129", "ASME Y14.5"],
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_dimensions":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["dimension_summary"]["total_dimensions"] == 28
        assert result["data"]["dimension_quality"]["placement_score"] == 88.5
        assert len(result["data"]["dimension_issues"]) == 3
        assert len(result["data"]["recommendations"]) == 3
        mock_adapter.analyze_drawing_dimensions.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_drawing_annotations_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful drawing annotation analysis."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_drawing_annotations = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "drawing_file": "part_drawing.slddrw",
                    "annotation_summary": {
                        "total_annotations": 15,
                        "surface_finish_symbols": 8,
                        "geometric_tolerances": 5,
                        "welding_symbols": 0,
                        "notes_and_labels": 12,
                        "balloons": 0,
                    },
                    "annotation_quality": {
                        "symbol_correctness": 95.0,
                        "placement_quality": 87.5,
                        "readability": 92.0,
                        "standards_compliance": 88.0,
                    },
                    "annotation_issues": [
                        {
                            "type": "Symbol placement",
                            "description": "Surface finish symbol too close to dimension",
                            "severity": "Low",
                        },
                        {
                            "type": "Missing symbol",
                            "description": "Geometric tolerance needed for hole position",
                            "severity": "Medium",
                        },
                        {
                            "type": "Text size",
                            "description": "Note text too small for standard",
                            "severity": "Low",
                        },
                    ],
                    "missing_annotations": [
                        "Material specification note",
                        "Heat treatment requirements",
                        "Inspection notes",
                    ],
                    "standards_analysis": {
                        "symbol_standards": "ISO 1302",
                        "geometric_tolerance_standards": "ISO 1101",
                        "compliance_level": "Good",
                    },
                },
                execution_time=1.5,
            )
        )

        input_data = AnnotationAnalysisInput(
            drawing_path="part_drawing.slddrw",
            analysis_scope="All annotations",
            check_symbols=True,
            check_geometric_tolerances=True,
            check_surface_finish=True,
            standards_verification=True,
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_annotations":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["annotation_summary"]["total_annotations"] == 15
        assert result["data"]["annotation_quality"]["symbol_correctness"] == 95.0
        assert len(result["data"]["annotation_issues"]) == 3
        assert len(result["data"]["missing_annotations"]) == 3
        mock_adapter.analyze_drawing_annotations.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_drawing_compliance_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful drawing compliance checking."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.check_drawing_compliance = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "drawing_file": "part_drawing.slddrw",
                    "compliance_overview": {
                        "overall_compliance": 87.5,
                        "iso_compliance": 89.0,
                        "asme_compliance": 85.5,
                        "company_compliance": 88.0,
                        "status": "Compliant with minor issues",
                    },
                    "compliance_details": {
                        "title_block": {"score": 95.0, "issues": 1},
                        "dimensions": {"score": 85.0, "issues": 3},
                        "annotations": {"score": 90.0, "issues": 2},
                        "views": {"score": 88.0, "issues": 2},
                        "line_weights": {"score": 92.0, "issues": 1},
                        "text_standards": {"score": 87.0, "issues": 2},
                    },
                    "violations": [
                        {
                            "standard": "ISO 5807",
                            "rule": "Title block completeness",
                            "severity": "Medium",
                            "description": "Missing revision date in title block",
                        },
                        {
                            "standard": "ASME Y14.5",
                            "rule": "Dimension tolerances",
                            "severity": "High",
                            "description": "Critical dimensions missing tolerances",
                        },
                        {
                            "standard": "Company Standard",
                            "rule": "Material callout",
                            "severity": "Medium",
                            "description": "Material specification note required",
                        },
                    ],
                    "recommendations": [
                        "Add revision date to title block",
                        "Add tolerances to critical dimensions",
                        "Include material specification note",
                        "Review dimension placement standards",
                    ],
                },
                execution_time=2.1,
            )
        )

        input_data = ComplianceCheckInput(
            drawing_path="part_drawing.slddrw",
            standards_to_check=["ISO 5807", "ASME Y14.5", "Company Standard"],
            compliance_level="Standard",
            generate_report=True,
            check_title_block=True,
            check_dimensions=True,
            check_annotations=True,
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "check_drawing_compliance":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["compliance_overview"]["overall_compliance"] == 87.5
        assert (
            result["data"]["compliance_overview"]["status"]
            == "Compliant with minor issues"
        )
        assert len(result["data"]["violations"]) == 3
        assert len(result["data"]["recommendations"]) == 4
        mock_adapter.check_drawing_compliance.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_drawing_views_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful drawing views analysis."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_drawing_views = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "drawing_file": "part_drawing.slddrw",
                    "view_analysis": {
                        "total_views": 6,
                        "standard_views": 4,
                        "auxiliary_views": 1,
                        "detail_views": 1,
                        "section_views": 0,
                        "broken_out_sections": 0,
                    },
                    "view_quality": {
                        "arrangement_score": 88.5,
                        "clarity_score": 91.0,
                        "completeness_score": 85.0,
                        "efficiency_score": 87.5,
                    },
                    "view_details": [
                        {
                            "view_name": "Drawing View1",
                            "type": "Front",
                            "scale": "1:1",
                            "position": [100, 200],
                            "quality_score": 92.0,
                            "issues": [],
                        },
                        {
                            "view_name": "Drawing View2",
                            "type": "Right",
                            "scale": "1:1",
                            "position": [250, 200],
                            "quality_score": 89.0,
                            "issues": ["Minor dimension overlap"],
                        },
                    ],
                    "optimization_suggestions": [
                        "Consider adding section view for internal features",
                        "Improve spacing between views for clarity",
                        "Add detail view for small features",
                    ],
                    "missing_views": [
                        "Section A-A for internal features",
                        "Detail view for threaded holes",
                    ],
                },
                execution_time=1.4,
            )
        )

        input_data = {
            "drawing_path": "part_drawing.slddrw",
            "analysis_type": "View optimization",
            "check_arrangement": True,
            "check_completeness": True,
            "suggest_improvements": True,
        }

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_views":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["view_analysis"]["total_views"] == 6
        assert result["data"]["view_quality"]["arrangement_score"] == 88.5
        assert len(result["data"]["view_details"]) == 2
        assert len(result["data"]["optimization_suggestions"]) == 3
        mock_adapter.analyze_drawing_views.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_drawing_report_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful drawing report generation."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_drawing_report = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "drawing_file": "part_drawing.slddrw",
                    "report_file": "drawing_analysis_report.pdf",
                    "report_sections": [
                        "Executive Summary",
                        "Drawing Overview",
                        "Dimension Analysis",
                        "Annotation Review",
                        "Compliance Check",
                        "Quality Assessment",
                        "Recommendations",
                    ],
                    "report_statistics": {
                        "total_pages": 8,
                        "charts_included": 5,
                        "images_included": 12,
                        "tables_included": 6,
                    },
                    "key_findings": [
                        "Overall compliance: 87.5%",
                        "28 dimensions analyzed",
                        "15 annotations reviewed",
                        "3 compliance violations found",
                        "Quality rating: Good",
                    ],
                    "export_formats": ["PDF", "HTML", "Excel"],
                    "generation_time": 4.2,
                },
                execution_time=4.2,
            )
        )

        input_data = {
            "drawing_path": "part_drawing.slddrw",
            "report_type": "Comprehensive",
            "include_images": True,
            "include_charts": True,
            "export_format": "PDF",
            "output_path": "reports/drawing_analysis_report.pdf",
        }

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "generate_drawing_report":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["report_file"] == "drawing_analysis_report.pdf"
        assert result["data"]["report_statistics"]["total_pages"] == 8
        assert len(result["data"]["key_findings"]) == 5
        mock_adapter.generate_drawing_report.assert_called_once()

    @pytest.mark.asyncio
    async def test_drawing_analysis_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in drawing analysis."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_drawing_comprehensive = AsyncMock(
            return_value=Mock(
                is_success=False,
                error="Drawing file is corrupted or invalid",
                execution_time=0.1,
            )
        )

        input_data = DrawingAnalysisInput(
            drawing_path="corrupted_drawing.slddrw", analysis_depth="Basic"
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_comprehensive":
                tool_func = tool.fn
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "corrupted or invalid" in result["message"]

    @pytest.mark.asyncio
    async def test_drawing_analysis_fallback_paths_refuse(self, mcp_server, mock_config):
        """Drawing analysis tools refuse rather than inventing results when the
        adapter has no matching capability."""
        await register_drawing_analysis_tools(mcp_server, object(), mock_config)

        comprehensive_tool = None
        dimension_tool = None
        annotation_tool = None
        compliance_tool = None
        completeness_tool = None

        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_comprehensive":
                comprehensive_tool = tool.fn
            if tool.name == "analyze_drawing_dimensions":
                dimension_tool = tool.fn
            if tool.name == "analyze_drawing_annotations":
                annotation_tool = tool.fn
            if tool.name == "check_drawing_compliance":
                compliance_tool = tool.fn
            if tool.name == "validate_drawing_completeness":
                completeness_tool = tool.fn

        assert comprehensive_tool is not None
        assert dimension_tool is not None
        assert annotation_tool is not None
        assert compliance_tool is not None
        assert completeness_tool is not None

        comprehensive_result = await comprehensive_tool(
            input_data=DrawingAnalysisInput(drawing_path="demo.slddrw")
        )
        assert comprehensive_result["status"] == "error"
        assert "does not support analyze_drawing_comprehensive" in (
            comprehensive_result["message"]
        )

        dimension_result = await dimension_tool(
            input_data=DimensionAnalysisInput(drawing_path="demo.slddrw")
        )
        assert dimension_result["status"] == "error"
        assert "does not support analyze_drawing_dimensions" in (
            dimension_result["message"]
        )

        annotation_result = await annotation_tool(
            input_data=AnnotationAnalysisInput(drawing_path="demo.slddrw")
        )
        assert annotation_result["status"] == "error"
        assert "does not support analyze_drawing_annotations" in (
            annotation_result["message"]
        )

        compliance_result = await compliance_tool(
            input_data=ComplianceCheckInput(drawing_path="demo.slddrw", standard="ISO")
        )
        assert compliance_result["status"] == "error"
        assert "does not support check_drawing_compliance" in (
            compliance_result["message"]
        )

        completeness_result = await completeness_tool(
            input_data={
                "drawing_path": "demo.slddrw",
                "manufacturing_type": "machining",
            }
        )
        assert completeness_result["status"] == "error"
        assert "does not support validate_drawing_completeness" in (
            completeness_result["message"]
        )

    @pytest.mark.asyncio
    async def test_compare_drawing_versions_reads_real_files(
        self, mcp_server, mock_config, tmp_path
    ):
        """compare_drawing_versions reports honest filesystem facts instead of
        a fabricated geometric/dimension/annotation diff."""
        await register_drawing_analysis_tools(mcp_server, object(), mock_config)

        compare_tool = next(
            t.fn
            for t in await mcp_server.list_tools()
            if t.name == "compare_drawing_versions"
        )

        # Missing paths refuse outright.
        missing_paths = await compare_tool(input_data={})
        assert missing_paths["status"] == "error"
        assert "requires both" in missing_paths["message"]

        # Non-existent files refuse with a clear message naming them.
        rev_a = tmp_path / "rev_a.slddrw"
        rev_b = tmp_path / "rev_b.slddrw"
        not_found = await compare_tool(
            input_data={
                "drawing_version_1": str(rev_a),
                "drawing_version_2": str(rev_b),
            }
        )
        assert not_found["status"] == "error"
        assert "not found on disk" in not_found["message"]

        # Two identical files compare as identical.
        rev_a.write_bytes(b"same content")
        rev_b.write_bytes(b"same content")
        identical = await compare_tool(
            input_data={
                "drawing_version_1": str(rev_a),
                "drawing_version_2": str(rev_b),
            }
        )
        assert identical["status"] == "success"
        assert identical["comparison"]["identical"] is True
        assert identical["comparison"]["size_delta_bytes"] == 0

        # Two different files compare as different, with an honest size delta.
        rev_b.write_bytes(b"different content, longer")
        different = await compare_tool(
            input_data={
                "drawing_version_1": str(rev_a),
                "drawing_version_2": str(rev_b),
            }
        )
        assert different["status"] == "success"
        assert different["comparison"]["identical"] is False
        assert different["comparison"]["size_delta_bytes"] == len(
            b"different content, longer"
        ) - len(b"same content")

    @pytest.mark.asyncio
    async def test_drawing_analysis_adapter_error_and_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test adapter error returns and exception handlers across drawing analysis tools."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_drawing_views = AsyncMock(
            return_value=Mock(is_success=False, error="view analysis failed")
        )
        mock_adapter.generate_drawing_report = AsyncMock(
            return_value=Mock(is_success=False, error="report generation failed")
        )

        view_tool = None
        report_tool = None
        compare_tool = None
        completeness_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_views":
                view_tool = tool.fn
            if tool.name == "generate_drawing_report":
                report_tool = tool.fn
            if tool.name == "compare_drawing_versions":
                compare_tool = tool.fn
            if tool.name == "validate_drawing_completeness":
                completeness_tool = tool.fn

        assert view_tool is not None
        assert report_tool is not None
        assert compare_tool is not None
        assert completeness_tool is not None

        view_error = await view_tool(input_data={"drawing_path": "demo.slddrw"})
        assert view_error["status"] == "error"
        assert "view analysis failed" in view_error["message"]

        report_error = await report_tool(input_data={"drawing_path": "demo.slddrw"})
        assert report_error["status"] == "error"
        assert "report generation failed" in report_error["message"]

        # "a" and "b" are not real files on disk, so compare_drawing_versions
        # must refuse rather than inventing a diff.
        compare_missing_files = await compare_tool(
            input_data={"drawing_version_1": "a", "drawing_version_2": "b"}
        )
        assert compare_missing_files["status"] == "error"
        assert "not found on disk" in compare_missing_files["message"]

        # mock_adapter has no validate_drawing_completeness method, so the
        # tool must refuse rather than inventing a completeness score.
        completeness_refuses = await completeness_tool(
            input_data={"drawing_path": "demo.slddrw"}
        )
        assert completeness_refuses["status"] == "error"
        assert (
            "does not support validate_drawing_completeness"
            in completeness_refuses["message"]
        )

    @pytest.mark.asyncio
    async def test_drawing_analysis_annotation_and_compliance_adapter_errors(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover adapter error branches for annotation and compliance tools."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_drawing_annotations = AsyncMock(
            return_value=Mock(is_success=False, error="annotation analysis failed")
        )
        mock_adapter.check_drawing_compliance = AsyncMock(
            return_value=Mock(is_success=False, error="compliance failed")
        )

        annotation_tool = None
        compliance_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_annotations":
                annotation_tool = tool.fn
            if tool.name == "check_drawing_compliance":
                compliance_tool = tool.fn

        assert annotation_tool is not None
        assert compliance_tool is not None

        annotation_error = await annotation_tool(
            input_data=AnnotationAnalysisInput(drawing_path="demo.slddrw")
        )
        assert annotation_error["status"] == "error"
        assert "annotation analysis failed" in annotation_error["message"]

        compliance_error = await compliance_tool(
            input_data=ComplianceCheckInput(drawing_path="demo.slddrw", standard="ISO")
        )
        assert compliance_error["status"] == "error"
        assert "compliance failed" in compliance_error["message"]

    @pytest.mark.asyncio
    async def test_drawing_analysis_exception_handlers(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test exception branches for view/report/version/completeness tools."""
        await register_drawing_analysis_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_drawing_views = AsyncMock(
            side_effect=RuntimeError("views crashed")
        )
        mock_adapter.generate_drawing_report = AsyncMock(
            side_effect=RuntimeError("report crashed")
        )

        view_tool = None
        report_tool = None
        compare_tool = None
        completeness_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "analyze_drawing_views":
                view_tool = tool.fn
            if tool.name == "generate_drawing_report":
                report_tool = tool.fn
            if tool.name == "compare_drawing_versions":
                compare_tool = tool.fn
            if tool.name == "validate_drawing_completeness":
                completeness_tool = tool.fn

        view_exception = await view_tool(input_data={"drawing_path": "demo.slddrw"})
        assert view_exception["status"] == "error"
        assert view_exception["error_type"] == "internal"

        report_exception = await report_tool(input_data={"drawing_path": "demo.slddrw"})
        assert report_exception["status"] == "error"
        assert report_exception["error_type"] == "internal"

        compare_exception = await compare_tool(input_data=[])
        assert compare_exception["status"] == "error"
        assert compare_exception["error_type"] == "internal"

        completeness_exception = await completeness_tool(input_data=[])
        assert completeness_exception["status"] == "error"
        assert completeness_exception["error_type"] == "internal"

    @pytest.mark.unit
    def test_drawing_analysis_input_validation(self):
        """Test input validation for drawing analysis."""
        # Valid input
        valid_input = DrawingAnalysisInput(
            drawing_path="test.slddrw", analysis_depth="Basic"
        )
        assert valid_input.drawing_path == "test.slddrw"
        assert valid_input.analysis_depth == "Basic"

        # Test with optional parameters
        full_input = DrawingAnalysisInput(
            drawing_path="test.slddrw",
            analysis_depth="Comprehensive",
            check_dimensions=True,
            check_annotations=False,
            standards=["ISO", "ASME"],
        )
        assert full_input.check_dimensions is True
        assert full_input.check_annotations is False
        assert "ISO" in full_input.standards

    @pytest.mark.unit
    def test_compliance_check_input_validation(self):
        """Test input validation for compliance checking."""
        # Valid input
        valid_input = ComplianceCheckInput(
            drawing_path="test.slddrw", standards_to_check=["ISO 5807"]
        )
        assert valid_input.drawing_path == "test.slddrw"
        assert len(valid_input.standards_to_check) == 1

        # Test with optional parameters
        full_input = ComplianceCheckInput(
            drawing_path="test.slddrw",
            standards_to_check=["ISO 5807", "ASME Y14.5"],
            compliance_level="Strict",
            generate_report=True,
            check_title_block=False,
        )
        assert full_input.compliance_level == "Strict"
        assert full_input.generate_report is True
        assert full_input.check_title_block is False


@pytest.mark.asyncio
async def test_validate_drawing_completeness_success(mcp_server, mock_config) -> None:
    """An adapter that can validate returns its data and timing unchanged."""
    from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

    adapter = Mock()
    adapter.validate_drawing_completeness = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"complete": True, "missing": []},
            execution_time=0.2,
        )
    )
    await register_drawing_analysis_tools(mcp_server, adapter, mock_config)
    tool = next(
        t.fn
        for t in await mcp_server.list_tools()
        if t.name == "validate_drawing_completeness"
    )

    result = await tool({"drawing_path": "a.slddrw"})

    assert result == {
        "status": "success",
        "message": "Drawing completeness validation completed",
        "data": {"complete": True, "missing": []},
        "execution_time": 0.2,
    }


def _ok(data):
    """Test helper for ok."""
    return SimpleNamespace(
        is_success=True,
        data=data,
        error=None,
        execution_time=0.01,
    )


async def _tool(mcp_server, name: str):
    """Test helper for tool."""
    for registered in await mcp_server.list_tools():
        if registered.name == name:
            return registered.fn
    raise AssertionError(f"Tool not found: {name}")


class _DrawingAndAnalysisAdapterStub:
    """Test suite for DrawingAndAnalysisAdapterStub."""

    async def create_technical_drawing(self, *_args, **_kwargs):
        """Test helper for create technical drawing."""
        return _ok({"drawing_path": "d.slddrw"})

    async def add_drawing_view(self, *_args, **_kwargs):
        """Test helper for add drawing view."""
        return _ok({"view_name": "Front"})

    async def add_annotation(self, *_args, **_kwargs):
        """Test helper for add annotation."""
        return _ok({"annotation": "ok"})

    async def update_title_block(self, *_args, **_kwargs):
        """Test helper for update title block."""
        return _ok({"title": "T"})

    async def analyze_drawing_comprehensive(self, *_args, **_kwargs):
        """Test helper for analyze drawing comprehensive."""
        return _ok({"score": 90})

    async def analyze_drawing_dimensions(self, *_args, **_kwargs):
        """Test helper for analyze drawing dimensions."""
        return _ok({"dims": 10})

    async def analyze_drawing_annotations(self, *_args, **_kwargs):
        """Test helper for analyze drawing annotations."""
        return _ok({"notes": 3})

    async def check_drawing_compliance(self, *_args, **_kwargs):
        """Test helper for check drawing compliance."""
        return _ok({"compliant": True})

    async def analyze_drawing_views(self, *_args, **_kwargs):
        """Test helper for analyze drawing views."""
        return _ok({"views": 4})

    async def generate_drawing_report(self, *_args, **_kwargs):
        """Test helper for generate drawing report."""
        return _ok({"report": "ok"})


@pytest.mark.asyncio
async def test_drawing_analysis_refuses_without_adapter_support(
    mcp_server, mock_config
):
    """Drawing analysis tools refuse rather than inventing a result when the
    adapter (a plain `object()` here) has no matching capability."""
    await register_drawing_analysis_tools(mcp_server, object(), mock_config)

    assert (
        await (await _tool(mcp_server, "analyze_drawing_comprehensive"))(
            input_data=DrawingAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "error"
    assert (
        await (await _tool(mcp_server, "analyze_drawing_dimensions"))(
            input_data=DimensionAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "error"
    assert (
        await (await _tool(mcp_server, "analyze_drawing_annotations"))(
            input_data=AnnotationAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "error"
    assert (
        await (await _tool(mcp_server, "check_drawing_compliance"))(
            input_data=ComplianceCheckInput(drawing_path="a.slddrw")
        )
    )["status"] == "error"
    assert (
        await (await _tool(mcp_server, "analyze_drawing_views"))(
            input_data={"drawing_path": "a.slddrw"}
        )
    )["status"] == "error"
    assert (
        await (await _tool(mcp_server, "generate_drawing_report"))(
            input_data={"drawing_path": "a.slddrw", "report_type": "summary"}
        )
    )["status"] == "error"


@pytest.mark.asyncio
async def test_drawing_and_analysis_adapter_passthrough_success(
    mcp_server, mock_config
):
    """Test drawing and analysis adapter passthrough success."""
    adapter = _DrawingAndAnalysisAdapterStub()
    await register_drawing_tools(mcp_server, adapter, mock_config)
    await register_drawing_analysis_tools(mcp_server, adapter, mock_config)

    assert (
        await (await _tool(mcp_server, "create_technical_drawing"))(
            input_data=DrawingCreationInput(output_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await (await _tool(mcp_server, "add_drawing_view"))(
            input_data=DrawingViewInput(view_name="Front")
        )
    )["status"] == "success"
    assert (
        await (await _tool(mcp_server, "add_annotation"))(
            input_data=AnnotationInput(text="n", annotation_type="Note")
        )
    )["status"] == "success"
    assert (
        await (await _tool(mcp_server, "update_title_block"))(input_data={"title": "T"})
    )["status"] == "success"

    assert (
        await (await _tool(mcp_server, "analyze_drawing_comprehensive"))(
            input_data=DrawingAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await (await _tool(mcp_server, "analyze_drawing_dimensions"))(
            input_data=DimensionAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await (await _tool(mcp_server, "analyze_drawing_annotations"))(
            input_data=AnnotationAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await (await _tool(mcp_server, "check_drawing_compliance"))(
            input_data=ComplianceCheckInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await (await _tool(mcp_server, "analyze_drawing_views"))(
            input_data={"drawing_path": "a.slddrw"}
        )
    )["status"] == "success"
    assert (
        await (await _tool(mcp_server, "generate_drawing_report"))(
            input_data={"drawing_path": "a.slddrw"}
        )
    )["status"] == "success"


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


class TestDrawingAnalysisExceptionPaths:
    """Test drawing analysis exception paths."""

    @pytest.mark.asyncio
    async def test_analyze_drawing_dimensions_adapter_error(self):
        """Line 294 — adapter returns error result."""
        from solidworks_mcp.tools.drawing_analysis import (
            DimensionAnalysisInput,
            register_drawing_analysis_tools,
        )

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        adapter.analyze_drawing_dimensions = AsyncMock(
            return_value=AdapterResult(
                status=AdapterResultStatus.ERROR, error="dim error"
            )
        )
        await register_drawing_analysis_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "analyze_drawing_dimensions")
        result = await fn(DimensionAnalysisInput(drawing_path="test.slddrw"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_analyze_drawing_dimensions_exception(self):
        """Lines 376-378 — exception in analyze_drawing_dimensions."""
        from solidworks_mcp.tools.drawing_analysis import (
            DimensionAnalysisInput,
            register_drawing_analysis_tools,
        )

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        adapter.analyze_drawing_dimensions = AsyncMock(
            side_effect=RuntimeError("dim boom")
        )
        await register_drawing_analysis_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "analyze_drawing_dimensions")
        result = await fn(DimensionAnalysisInput(drawing_path="test.slddrw"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_analyze_drawing_annotations_exception(self):
        """Line 415 — exception in analyze_drawing_annotations."""
        from solidworks_mcp.tools.drawing_analysis import (
            AnnotationAnalysisInput,
            register_drawing_analysis_tools,
        )

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        adapter.analyze_drawing_annotations = AsyncMock(
            side_effect=RuntimeError("ann boom")
        )
        await register_drawing_analysis_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "analyze_drawing_annotations")
        result = await fn(AnnotationAnalysisInput(drawing_path="test.slddrw"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_check_drawing_compliance_exception(self):
        """Lines 512-514 — exception in check_drawing_compliance."""
        from solidworks_mcp.tools.drawing_analysis import (
            ComplianceCheckInput,
            register_drawing_analysis_tools,
        )

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        adapter.check_drawing_compliance = AsyncMock(
            side_effect=RuntimeError("comp boom")
        )
        await register_drawing_analysis_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "check_drawing_compliance")
        result = await fn(
            ComplianceCheckInput(drawing_path="test.slddrw", standard="ASME")
        )
        assert result["status"] == "error"
