"""Advanced Drawing Analysis tools for SolidWorks MCP Server.

Provides advanced analysis capabilities for drawing documents including dimension
analysis, view analysis, annotation checking, and compliance verification.
"""

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .file_facts import file_fact_snapshot
from .input_compat import CompatInput
from .tool_boundary import (
    ToolOperationError,
    UnsupportedOperationError,
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

# Input schemas for drawing analysis


class DrawingAnalysisInput(CompatInput):
    """Input schema for drawing analysis operations.

    Attributes:
        analysis_depth (str): The analysis depth value.
        analysis_type (str): The analysis type value.
        drawing_path (str): The drawing path value.
        generate_report (bool): The generate report value.
        standards_check (bool): The standards check value.
    """

    drawing_path: str = Field(description="Path to drawing file (.slddrw)")
    analysis_type: str = Field(
        default="comprehensive",
        description="Analysis type (comprehensive, dimensions, views, annotations)",
    )
    analysis_depth: str = Field(default="Basic", description="Analysis depth level")
    standards_check: bool = Field(
        default=True, description="Check against drafting standards"
    )
    generate_report: bool = Field(default=True, description="Generate detailed report")


class DimensionAnalysisInput(CompatInput):
    """Input schema for dimension analysis.

    Attributes:
        check_completeness (bool): The check completeness value.
        check_precision (bool): The check precision value.
        check_tolerances (bool): The check tolerances value.
        drawing_path (str): The drawing path value.
    """

    drawing_path: str = Field(description="Path to drawing file")
    check_precision: bool = Field(
        default=True, description="Check dimension precision consistency"
    )
    check_tolerances: bool = Field(
        default=True, description="Check tolerance formatting"
    )
    check_completeness: bool = Field(
        default=True, description="Check dimension completeness"
    )


class AnnotationAnalysisInput(CompatInput):
    """Input schema for annotation analysis.

    Attributes:
        check_annotations (bool): The check annotations value.
        check_notes (bool): The check notes value.
        check_symbols (bool): The check symbols value.
        check_text_styles (bool): The check text styles value.
        drawing_path (str): The drawing path value.
    """

    drawing_path: str = Field(description="Path to drawing file")
    check_notes: bool = Field(
        default=True, description="Check note formatting and content"
    )
    check_symbols: bool = Field(
        default=True, description="Check symbol usage and placement"
    )
    check_text_styles: bool = Field(
        default=True, description="Check text style consistency"
    )
    check_annotations: bool = Field(default=True, description="Alias used by tests")


class ComplianceCheckInput(CompatInput):
    """Input schema for standards compliance checking.

    Attributes:
        check_sheet_format (bool): The check sheet format value.
        check_title_block (bool): The check title block value.
        drawing_path (str): The drawing path value.
        standard (str): The standard value.
        standards_to_check (list[str]): The standards to check value.
    """

    drawing_path: str = Field(description="Path to drawing file")
    standard: str = Field(
        default="ISO", description="Standard to check against (ISO, ANSI, DIN)"
    )
    standards_to_check: list[str] = Field(
        default_factory=lambda: ["ISO"], description="Standards list alias"
    )
    check_title_block: bool = Field(
        default=True, description="Check title block compliance"
    )
    check_sheet_format: bool = Field(
        default=True, description="Check sheet format compliance"
    )


class DrawingVersionsInput(CompatInput):
    """Input schema for comparing two saved versions of a drawing.

    Attributes:
        drawing_version_1 (str): The first drawing file.
        drawing_version_2 (str): The second drawing file.
    """

    drawing_version_1: str = Field(
        min_length=1, description="Full path to the first drawing file"
    )
    drawing_version_2: str = Field(
        min_length=1, description="Full path to the second drawing file"
    )


async def register_drawing_analysis_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register advanced drawing analysis tools with FastMCP.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (Any): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        >>> tool_count = await register_drawing_analysis_tools(mcp, adapter, config)
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def analyze_drawing_comprehensive(
        input_data: DrawingAnalysisInput,
    ) -> dict[str, Any]:
        """Run every drawing check (dimensions, views, annotations, standards) on a drawing file in one call.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. To see what a
        drawing holds today, use `list_drawing_views`. Read-only. Returns: once
        available, the combined findings under `data`.

        Args:
            input_data: The drawing to check. `drawing_path` (.slddrw) is required;
                `analysis_type`, `analysis_depth`, `standards_check` and
                `generate_report` have defaults.

        Returns:
            dict[str, Any]: The findings, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "analyze_drawing_comprehensive",
            "Active adapter does not support "
            "analyze_drawing_comprehensive; no analysis of "
            f"{input_data.drawing_path} was performed.",
        )
        result = await adapter.analyze_drawing_comprehensive(input_data.model_dump())
        require_success(result, "Failed to analyze drawing")
        return {
            "status": "success",
            "message": "Comprehensive drawing analysis completed",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def analyze_drawing_dimensions(
        input_data: DimensionAnalysisInput,
    ) -> dict[str, Any]:
        """Check a drawing's dimensions for consistent precision, tolerance formatting and completeness.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. To bring the
        model's dimensions into a drawing, use `insert_model_dimensions`. Read-only.
        Returns: once available, the dimension findings under `data`.

        Args:
            input_data: The drawing to check. `drawing_path` is required; the
                `check_precision`, `check_tolerances` and `check_completeness`
                switches default to on.

        Returns:
            dict[str, Any]: The findings, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "analyze_drawing_dimensions",
            "Active adapter does not support analyze_drawing_dimensions; "
            f"no analysis of {input_data.drawing_path} was performed.",
        )
        result = await adapter.analyze_drawing_dimensions(input_data.model_dump())
        require_success(result, "Failed to analyze dimensions")
        return {
            "status": "success",
            "message": "Dimension analysis completed",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def analyze_drawing_annotations(
        input_data: AnnotationAnalysisInput,
    ) -> dict[str, Any]:
        """Check a drawing's notes, symbols and text styles for consistency.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Read-only.
        Returns: once available, the annotation findings under `data`.

        Args:
            input_data: The drawing to check. `drawing_path` is required; the
                `check_notes`, `check_symbols`, `check_text_styles` and
                `check_annotations` switches default to on.

        Returns:
            dict[str, Any]: The findings, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "analyze_drawing_annotations",
            "Active adapter does not support analyze_drawing_annotations; "
            f"no analysis of {input_data.drawing_path} was performed.",
        )
        result = await adapter.analyze_drawing_annotations(input_data.model_dump())
        require_success(result, "Failed to analyze annotations")
        return {
            "status": "success",
            "message": "Annotation analysis completed",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def check_drawing_compliance(
        input_data: ComplianceCheckInput,
    ) -> dict[str, Any]:
        """Check a drawing's title block and sheet format against a drafting standard (ISO, ANSI or DIN).

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. For the same
        check on the active drawing, `check_drawing_standards` is also not available
        yet. Read-only. Returns: once available, the compliance findings under `data`.

        Args:
            input_data: The drawing and standard. `drawing_path` is required;
                `standard` defaults to "ISO", and `check_title_block` and
                `check_sheet_format` default to on.

        Returns:
            dict[str, Any]: The findings, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "check_drawing_compliance",
            "Active adapter does not support check_drawing_compliance; "
            f"no {input_data.standard} compliance check was performed.",
        )
        result = await adapter.check_drawing_compliance(input_data.model_dump())
        require_success(result, "Compliance check failed")
        return {
            "status": "success",
            "message": f"Standards compliance check completed for {input_data.standard}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def analyze_drawing_views(input_data: dict[str, Any]) -> dict[str, Any]:
        """Check how a drawing's views are chosen and laid out.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. To list the
        views on the active drawing today, use `list_drawing_views`. Read-only. Returns:
        once available, the view findings under `data`.

        Args:
            input_data: A mapping with the `drawing_path` of the drawing to check.

        Returns:
            dict[str, Any]: The findings, or a `not_supported` error.
        """
        if hasattr(adapter, "analyze_drawing_views"):
            result = await adapter.analyze_drawing_views(input_data)
            require_success(result, "Failed to analyze drawing views")
            return {
                "status": "success",
                "message": "Drawing view analysis completed",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        drawing_path = input_data.get("drawing_path", "")

        raise UnsupportedOperationError(
            "Active adapter does not support analyze_drawing_views; "
            f"no analysis of {drawing_path} was performed."
        )

    @mcp.tool()
    async def generate_drawing_report(input_data: dict[str, Any]) -> dict[str, Any]:
        """Write a quality report that combines every drawing check.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Read-only.
        Returns: once available, the report under `data`.

        Args:
            input_data: A mapping with the `drawing_path` of the drawing to report
                on.

        Returns:
            dict[str, Any]: The report, or a `not_supported` error.
        """
        if hasattr(adapter, "generate_drawing_report"):
            result = await adapter.generate_drawing_report(input_data)
            require_success(result, "Failed to generate drawing report")
            return {
                "status": "success",
                "message": "Drawing quality report generated successfully",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        drawing_path = input_data.get("drawing_path", "")

        raise UnsupportedOperationError(
            "Active adapter does not support generate_drawing_report; "
            f"no report for {drawing_path} was generated."
        )

    @mcp.tool()
    async def compare_drawing_versions(
        input_data: DrawingVersionsInput,
    ) -> dict[str, Any]:
        """Compare two drawing files on disk: whether they are byte-identical, and how their sizes differ.

        Use it to tell whether a drawing changed between two saved versions. It does not
        open SolidWorks, so it can't say which views, dimensions or notes differ.
        Identical files mean nothing changed, but different files may not: SolidWorks
        writes a different file each time it saves, even with no change. Needs:
        both files on disk. Read-only. Returns: `comparison` with `file_1` and `file_2`
        (size, modified time, SHA-256), `identical` and `size_delta_bytes`.

        Args:
            input_data: Both full paths, `drawing_version_1` and
                `drawing_version_2`; both are required.

        Returns:
            dict[str, Any]: The comparison.
        """
        input_data = normalize_input(input_data, DrawingVersionsInput)
        drawing_v1 = input_data.drawing_version_1
        drawing_v2 = input_data.drawing_version_2

        file_1 = file_fact_snapshot(drawing_v1)
        file_2 = file_fact_snapshot(drawing_v2)

        missing = [
            path
            for path, snapshot in ((drawing_v1, file_1), (drawing_v2, file_2))
            if snapshot is None
        ]
        if missing:
            raise ToolOperationError(
                "Cannot compare drawing versions; file(s) not found "
                f"on disk: {', '.join(missing)}. No SolidWorks-level "
                "diff was performed."
            )

        assert file_1 is not None
        assert file_2 is not None
        identical = file_1["sha256"] == file_2["sha256"]

        return {
            "status": "success",
            "message": (
                "Drawing files are byte-identical"
                if identical
                else "Drawing files differ on disk"
            ),
            "comparison": {
                "file_1": file_1,
                "file_2": file_2,
                "identical": identical,
                "size_delta_bytes": file_2["size_bytes"] - file_1["size_bytes"],
            },
            "note": (
                "This is a filesystem-level comparison only; no "
                "SolidWorks session was opened, so geometric, "
                "dimension, and annotation differences were not "
                "analyzed."
            ),
        }

    @mcp.tool()
    async def validate_drawing_completeness(
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Check that a drawing carries everything needed to manufacture the part.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Read-only.
        Returns: once available, the missing items under `data`.

        Args:
            input_data: A mapping with the `drawing_path` of the drawing to check.

        Returns:
            dict[str, Any]: The findings, or a `not_supported` error.
        """
        drawing_path = input_data.get("drawing_path", "")

        require_capability(
            adapter,
            "validate_drawing_completeness",
            "Active adapter does not support "
            "validate_drawing_completeness; no validation of "
            f"{drawing_path} was performed.",
        )
        result = await adapter.validate_drawing_completeness(input_data)
        require_success(result, "Failed to validate completeness")
        return {
            "status": "success",
            "message": "Drawing completeness validation completed",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    tool_count = 8  # Legacy count expected by tests
    return tool_count
