"""Template Management tools for SolidWorks MCP Server.

Provides tools for managing SolidWorks templates including extraction, application,
comparison, and library management.
"""

import hashlib
import pathlib
from typing import Any

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field

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


# Input schemas for template management


class TemplateExtractionInput(BaseModel):
    """Input schema for extracting template from model.

    Attributes:
        include_custom_properties (bool): The include custom properties value.
        include_dimensions (bool): The include dimensions value.
        save_path (str): The save path value.
        source_model (str): The source model value.
        template_name (str): The template name value.
        template_type (str): The template type value.
    """

    source_model: str = Field(description="Path to source model file")
    template_name: str = Field(description="Name for the extracted template")
    template_type: str = Field(description="Template type (part, assembly, drawing)")
    save_path: str = Field(description="Path to save the template file")
    include_custom_properties: bool = Field(
        default=True, description="Include custom properties"
    )
    include_dimensions: bool = Field(default=True, description="Include dimensions")


class TemplateApplicationInput(BaseModel):
    """Input schema for applying template to model.

    Attributes:
        apply_dimensions (bool): The apply dimensions value.
        apply_materials (bool): The apply materials value.
        overwrite_existing (bool): The overwrite existing value.
        target_model (str): The target model value.
        template_path (str): The template path value.
    """

    template_path: str = Field(description="Path to template file")
    target_model: str = Field(description="Path to target model")
    overwrite_existing: bool = Field(
        default=False, description="Overwrite existing properties"
    )
    apply_dimensions: bool = Field(
        default=True, description="Apply dimension formatting"
    )
    apply_materials: bool = Field(default=True, description="Apply material settings")


class TemplateBatchInput(BaseModel):
    """Input schema for batch template operations.

    Attributes:
        backup_originals (bool): The backup originals value.
        file_pattern (str): The file pattern value.
        recursive (bool): The recursive value.
        source_folder (str): The source folder value.
        template_path (str): The template path value.
    """

    template_path: str = Field(description="Path to template file")
    source_folder: str = Field(description="Folder containing target models")
    file_pattern: str = Field(default="*.sldprt", description="File pattern to match")
    recursive: bool = Field(default=True, description="Process subfolders")
    backup_originals: bool = Field(default=True, description="Create backup copies")


class TemplateComparisonInput(CompatInput):
    """Input schema for comparing templates.

    Attributes:
        comparison_depth (str): The comparison depth value.
        comparison_type (str): The comparison type value.
        generate_report (bool): The generate report value.
        include_dimensions (bool): The include dimensions value.
        include_materials (bool): The include materials value.
        include_properties (bool): The include properties value.
        template1_path (str): The template1 path value.
        template2_path (str): The template2 path value.
    """

    template1_path: str = Field(description="Path to first template")
    template2_path: str = Field(description="Path to second template")
    comparison_type: str = Field(
        default="full", description="Comparison type (full, properties, dimensions)"
    )
    comparison_depth: str = Field(default="full", description="Comparison depth alias")
    include_properties: bool = Field(default=True, description="Include properties")
    include_dimensions: bool = Field(default=True, description="Include dimensions")
    include_materials: bool = Field(default=True, description="Include materials")
    generate_report: bool = Field(
        default=True, description="Generate comparison report"
    )


async def register_template_management_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register template management tools with FastMCP.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (Any): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        >>> tool_count = await register_template_management_tools(mcp, adapter, config)
    """
    tool_count = 0

    @mcp.tool()
    async def extract_template(input_data: TemplateExtractionInput) -> dict[str, Any]:
        """Extract template from existing SolidWorks model.

        Args:
            input_data (TemplateExtractionInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await extract_template(extraction_input)
        """
        try:
            if hasattr(adapter, "extract_template"):
                result = await adapter.extract_template(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"Template '{input_data.template_name}' extracted from {input_data.source_model}",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to extract template",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support extract_template; no "
                    f"template was extracted from {input_data.source_model}."
                ),
            }

        except Exception as e:
            logger.error(f"Error in extract_template tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to extract template: {str(e)}",
            }

    @mcp.tool()
    async def apply_template(input_data: TemplateApplicationInput) -> dict[str, Any]:
        """Apply a template to an existing SolidWorks model.

        This tool applies saved template settings including properties, dimensions, and
        formatting to the target model.

        Args:
            input_data (TemplateApplicationInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await apply_template(application_input)
        """
        try:
            if hasattr(adapter, "apply_template"):
                result = await adapter.apply_template(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"Template applied to {input_data.target_model}",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to apply template",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support apply_template; "
                    f"{input_data.target_model} was not changed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in apply_template tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to apply template: {str(e)}",
            }

    @mcp.tool()
    async def batch_apply_template(input_data: TemplateBatchInput) -> dict[str, Any]:
        """Apply template to multiple models in batch.

        This tool processes multiple SolidWorks files and applies the same template
        configuration to all matching files.

        Args:
            input_data (TemplateBatchInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await batch_apply_template(batch_input)
        """
        try:
            if hasattr(adapter, "batch_apply_template"):
                result = await adapter.batch_apply_template(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Batch template application completed",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed batch template application",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support batch_apply_template; "
                    f"no files in {input_data.source_folder} were changed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in batch_apply_template tool: {e}")
            return {
                "status": "error",
                "message": f"Failed batch template application: {str(e)}",
            }

    @mcp.tool()
    async def compare_templates(input_data: TemplateComparisonInput) -> dict[str, Any]:
        """Compare two templates and generate difference report.

        This tool analyzes differences between templates to help understand variations in
        formatting and properties.

        Args:
            input_data (TemplateComparisonInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await compare_templates(comparison_input)

        Note:
            When no adapter can parse template internals, this falls back to
            a filesystem-level comparison only (existence, size, modified
            time, byte-identical check) — it does not report property,
            dimension, or formatting differences it cannot actually read.
        """
        try:
            if hasattr(adapter, "compare_templates"):
                result = await adapter.compare_templates(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Template comparison completed",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to compare templates",
                }

            file_1 = _file_fact_snapshot(input_data.template1_path)
            file_2 = _file_fact_snapshot(input_data.template2_path)

            missing = [
                path
                for path, snapshot in (
                    (input_data.template1_path, file_1),
                    (input_data.template2_path, file_2),
                )
                if snapshot is None
            ]
            if missing:
                return {
                    "status": "error",
                    "message": (
                        "Cannot compare templates; file(s) not found on "
                        f"disk: {', '.join(missing)}. No template-property "
                        "diff was performed."
                    ),
                }

            assert file_1 is not None
            assert file_2 is not None
            identical = file_1["sha256"] == file_2["sha256"]

            return {
                "status": "success",
                "message": (
                    "Template files are byte-identical"
                    if identical
                    else "Template files differ on disk"
                ),
                "comparison": {
                    "file_1": file_1,
                    "file_2": file_2,
                    "identical": identical,
                    "size_delta_bytes": file_2["size_bytes"] - file_1["size_bytes"],
                },
                "note": (
                    "This is a filesystem-level comparison only; template "
                    "properties, dimensions, and formatting were not "
                    "analyzed."
                ),
            }

        except Exception as e:
            logger.error(f"Error in compare_templates tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to compare templates: {str(e)}",
            }

    @mcp.tool()
    async def save_to_template_library(input_data: dict[str, Any]) -> dict[str, Any]:
        """Save template to the organization's template library.

        This tool manages a centralized template library with categorization and version
        control.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await save_to_template_library(library_input)
        """

        try:
            if hasattr(adapter, "save_to_template_library"):
                result = await adapter.save_to_template_library(input_data)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Template saved to library",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to save to library",
                }

            template_name = input_data.get("template_name", "")

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support save_to_template_library; "
                    f"'{template_name}' was not saved to any library. There is "
                    "no local template registry — this tool needs a real "
                    "adapter-backed library service."
                ),
            }

        except Exception as e:
            logger.error(f"Error in save_to_template_library tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to save to library: {str(e)}",
            }

    @mcp.tool()
    async def list_template_library(input_data: dict[str, Any]) -> dict[str, Any]:
        """List available templates from the template library.

        This tool provides browsing and searching capabilities for the organization's template
        library.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await list_template_library(list_input)
        """
        try:
            if hasattr(adapter, "list_template_library"):
                result = await adapter.list_template_library(input_data)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Template library listed successfully",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to list template library",
                }

            return {
                "status": "error",
                "message": (
                    "Active adapter does not support list_template_library; "
                    "there is no local template registry to list."
                ),
            }

        except Exception as e:
            logger.error(f"Error in list_template_library tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to list library: {str(e)}",
            }

    tool_count = 6  # Template management tools
    return tool_count
