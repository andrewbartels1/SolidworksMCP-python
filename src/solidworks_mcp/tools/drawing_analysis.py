"""Advanced Drawing Analysis tools for SolidWorks MCP Server.

Provides advanced analysis capabilities for drawing documents including dimension
analysis, view analysis, annotation checking, and compliance verification.
"""

import hashlib
import pathlib
from typing import Any

from fastmcp import FastMCP
from loguru import logger
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput


def _file_fact_snapshot(path_str: str) -> dict[str, Any] | None:
    """Read basic, honest filesystem facts about a file: size, mtime, hash.

    Returns None if the path is empty or does not point at an existing file.
    """
    if not path_str:
        return None
    path = pathlib.Path(path_str)
    if not path.is_file():
        return None
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_time": stat.st_mtime,
        "sha256": digest.hexdigest(),
    }


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
    tool_count = 0

    @mcp.tool()
    async def analyze_drawing_comprehensive(
        input_data: DrawingAnalysisInput,
    ) -> dict[str, Any]:
        """Handle analyze drawing comprehensive.

        Args:
            input_data (DrawingAnalysisInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await analyze_drawing_comprehensive(analysis_input)
        """
        try:
            if hasattr(adapter, "analyze_drawing_comprehensive"):
                result = await adapter.analyze_drawing_comprehensive(
                    input_data.model_dump()
                )
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Comprehensive drawing analysis completed",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to analyze drawing",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support "
                    "analyze_drawing_comprehensive; no analysis of "
                    f"{input_data.drawing_path} was performed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in analyze_drawing_comprehensive tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to analyze drawing: {str(e)}",
            }

    @mcp.tool()
    async def analyze_drawing_dimensions(
        input_data: DimensionAnalysisInput,
    ) -> dict[str, Any]:
        """Analyze dimensions in a SolidWorks drawing for consistency and completeness.

        This tool performs detailed dimensional analysis including precision, tolerances, and
        completeness checking.

        Args:
            input_data (DimensionAnalysisInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await analyze_drawing_dimensions(dimension_input)
        """

        try:
            if hasattr(adapter, "analyze_drawing_dimensions"):
                result = await adapter.analyze_drawing_dimensions(
                    input_data.model_dump()
                )
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Dimension analysis completed",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to analyze dimensions",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support analyze_drawing_dimensions; "
                    f"no analysis of {input_data.drawing_path} was performed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in analyze_drawing_dimensions tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to analyze dimensions: {str(e)}",
            }

    @mcp.tool()
    async def analyze_drawing_annotations(
        input_data: AnnotationAnalysisInput,
    ) -> dict[str, Any]:
        """Analyze drawing annotations and notes quality.

        Args:
            input_data (AnnotationAnalysisInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await analyze_drawing_annotations(annotation_input)
        """
        """
        Analyze annotations in a SolidWorks drawing for consistency and standards compliance.

        This tool examines notes, symbols, and text formatting for quality and compliance.
        """
        try:
            if hasattr(adapter, "analyze_drawing_annotations"):
                result = await adapter.analyze_drawing_annotations(
                    input_data.model_dump()
                )
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Annotation analysis completed",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to analyze annotations",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support analyze_drawing_annotations; "
                    f"no analysis of {input_data.drawing_path} was performed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in analyze_drawing_annotations tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to analyze annotations: {str(e)}",
            }

    @mcp.tool()
    async def check_drawing_compliance(
        input_data: ComplianceCheckInput,
    ) -> dict[str, Any]:
        """Check drawing compliance with company standards.

        Args:
            input_data (ComplianceCheckInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await check_drawing_compliance(compliance_input)
        """
        """
        Check drawing compliance against specified drafting standards.

        This tool verifies compliance with ISO, ANSI, DIN, or other drafting standards.
        """
        try:
            if hasattr(adapter, "check_drawing_compliance"):
                result = await adapter.check_drawing_compliance(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"Standards compliance check completed for {input_data.standard}",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Compliance check failed",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support check_drawing_compliance; "
                    f"no {input_data.standard} compliance check was performed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in check_drawing_compliance tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to check compliance: {str(e)}",
            }

    @mcp.tool()
    async def analyze_drawing_views(input_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze drawing views arrangement and quality.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await analyze_drawing_views(view_input)
        """
        """
        Analyze drawing views for clarity, completeness, and optimal presentation.

        This tool examines view selection, placement, and clarity.
        """
        try:
            if hasattr(adapter, "analyze_drawing_views"):
                result = await adapter.analyze_drawing_views(input_data)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Drawing view analysis completed",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to analyze drawing views",
                }

            drawing_path = input_data.get("drawing_path", "")

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support analyze_drawing_views; "
                    f"no analysis of {drawing_path} was performed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in analyze_drawing_views tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to analyze views: {str(e)}",
            }

    @mcp.tool()
    async def generate_drawing_report(input_data: dict[str, Any]) -> dict[str, Any]:
        """Generate comprehensive drawing analysis report.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await generate_drawing_report(report_input)
        """
        """
        Generate a comprehensive quality report for a drawing.

        This tool creates a detailed report combining all analysis results.
        """
        try:
            if hasattr(adapter, "generate_drawing_report"):
                result = await adapter.generate_drawing_report(input_data)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Drawing quality report generated successfully",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to generate drawing report",
                }

            drawing_path = input_data.get("drawing_path", "")

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support generate_drawing_report; "
                    f"no report for {drawing_path} was generated."
                ),
            }

        except Exception as e:
            logger.error(f"Error in generate_drawing_report tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate report: {str(e)}",
            }

    @mcp.tool()
    async def compare_drawing_versions(input_data: dict[str, Any]) -> dict[str, Any]:
        """Compare different versions of drawing files.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await compare_drawing_versions(version_input)
        """
        """
        Compare two drawing files on disk using real filesystem facts.

        This tool cannot parse SLDDRW internals (no SolidWorks session is
        opened), so it does not report geometric/dimension/annotation
        differences. It reports what it can honestly determine from the
        filesystem: whether each file exists, its size, modified time, and
        whether the two files are byte-for-byte identical.
        """
        try:
            drawing_v1 = input_data.get("drawing_version_1", "")
            drawing_v2 = input_data.get("drawing_version_2", "")

            if not drawing_v1 or not drawing_v2:
                return {
                    "status": "error",
                    "message": (
                        "compare_drawing_versions requires both "
                        "drawing_version_1 and drawing_version_2 paths."
                    ),
                }

            file_1 = _file_fact_snapshot(drawing_v1)
            file_2 = _file_fact_snapshot(drawing_v2)

            missing = [
                path
                for path, snapshot in ((drawing_v1, file_1), (drawing_v2, file_2))
                if snapshot is None
            ]
            if missing:
                return {
                    "status": "error",
                    "message": (
                        "Cannot compare drawing versions; file(s) not found "
                        f"on disk: {', '.join(missing)}. No SolidWorks-level "
                        "diff was performed."
                    ),
                }

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

        except Exception as e:
            logger.error(f"Error in compare_drawing_versions tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to compare versions: {str(e)}",
            }

    @mcp.tool()
    async def validate_drawing_completeness(
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate drawing completeness for production readiness.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await validate_drawing_completeness(validation_input)
        """
        """
        Validate that a drawing contains all necessary information for manufacturing.

        This tool checks for completeness from a manufacturing perspective.
        """
        try:
            drawing_path = input_data.get("drawing_path", "")

            if hasattr(adapter, "validate_drawing_completeness"):
                result = await adapter.validate_drawing_completeness(input_data)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Drawing completeness validation completed",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to validate completeness",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support "
                    "validate_drawing_completeness; no validation of "
                    f"{drawing_path} was performed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in validate_drawing_completeness tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to validate completeness: {str(e)}",
            }

    tool_count = 8  # Legacy count expected by tests
    return tool_count
