"""Template Management tools for SolidWorks MCP Server.

Provides tools for managing SolidWorks templates including extraction, application,
comparison, and library management.
"""

from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..adapters.base import SolidWorksAdapter
from .file_facts import file_fact_snapshot
from .input_compat import CompatInput
from .tool_boundary import (
    ToolOperationError,
    UnsupportedOperationError,
    require_capability,
    require_success,
    with_tool_boundary,
)

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
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def extract_template(input_data: TemplateExtractionInput) -> dict[str, Any]:
        """Capture a model's settings (custom properties, dimensions, units) as a reusable template file.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Changes: once
        available, writes the template to `save_path`, replacing any file there.
        Returns: once available, the captured settings under `data`.

        Args:
            input_data: The extraction. `source_model`, `template_name`,
                `template_type` and `save_path` are required;
                `include_custom_properties` and `include_dimensions` default to on.

        Returns:
            dict[str, Any]: The template, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "extract_template",
            "Active adapter does not support extract_template; no "
            f"template was extracted from {input_data.source_model}.",
        )
        result = await adapter.extract_template(input_data.model_dump())
        require_success(result, "Failed to extract template")
        return {
            "status": "success",
            "message": f"Template '{input_data.template_name}' extracted from {input_data.source_model}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def apply_template(input_data: TemplateApplicationInput) -> dict[str, Any]:
        """Apply a saved template's properties, dimensions and materials to a model.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. To set a
        material or a property today, use `set_material` or `set_custom_property`.
        Changes: once available, overwrites the target model's matching settings.
        Returns: once available, what changed under `data`.

        Args:
            input_data: The application. `template_path` and `target_model` are
                required; `overwrite_existing`, `apply_dimensions` and
                `apply_materials` have defaults.

        Returns:
            dict[str, Any]: The changes, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "apply_template",
            "Active adapter does not support apply_template; "
            f"{input_data.target_model} was not changed.",
        )
        result = await adapter.apply_template(input_data.model_dump())
        require_success(result, "Failed to apply template")
        return {
            "status": "success",
            "message": f"Template applied to {input_data.target_model}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def batch_apply_template(input_data: TemplateBatchInput) -> dict[str, Any]:
        """Apply one template to every matching model in a folder.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Changes: once
        available, overwrites settings in each matching file, optionally keeping
        backups. Returns: once available, a per-file result under `data`.

        Args:
            input_data: The batch. `template_path` and `source_folder` are
                required; `file_pattern`, `recursive` and `backup_originals` have
                defaults.

        Returns:
            dict[str, Any]: The results, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "batch_apply_template",
            "Active adapter does not support batch_apply_template; "
            f"no files in {input_data.source_folder} were changed.",
        )
        result = await adapter.batch_apply_template(input_data.model_dump())
        require_success(result, "Failed batch template application")
        return {
            "status": "success",
            "message": "Batch template application completed",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def compare_templates(input_data: TemplateComparisonInput) -> dict[str, Any]:
        """Compare two template files on disk: whether they are byte-identical, and how their sizes differ.

        Use it to tell whether two templates are the same file. It does not read the
        templates' settings, so it can't say which properties or dimensions differ.
        Needs: both files on disk. Read-only. Returns: `comparison` with `file_1` and
        `file_2` (size, modified time, SHA-256), `identical` and `size_delta_bytes`.

        Args:
            input_data: The two templates. `template1_path` and `template2_path`
                are required; the comparison switches have defaults and are not used
                yet.

        Returns:
            dict[str, Any]: The comparison.
        """
        if hasattr(adapter, "compare_templates"):
            result = await adapter.compare_templates(input_data.model_dump())
            require_success(result, "Failed to compare templates")
            return {
                "status": "success",
                "message": "Template comparison completed",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        file_1 = file_fact_snapshot(input_data.template1_path)
        file_2 = file_fact_snapshot(input_data.template2_path)

        missing = [
            path
            for path, snapshot in (
                (input_data.template1_path, file_1),
                (input_data.template2_path, file_2),
            )
            if snapshot is None
        ]
        if missing:
            raise ToolOperationError(
                "Cannot compare templates; file(s) not found on "
                f"disk: {', '.join(missing)}. No template-property "
                "diff was performed."
            )

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

    @mcp.tool()
    async def save_to_template_library(input_data: dict[str, Any]) -> dict[str, Any]:
        """Add a template to a shared, categorised template library.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Changes: once
        available, copies the template into the library, replacing an entry with the
        same name. Returns: once available, the library entry under `data`.

        Args:
            input_data: A mapping with the `template_name` and the template's path.

        Returns:
            dict[str, Any]: The entry, or a `not_supported` error.
        """
        if hasattr(adapter, "save_to_template_library"):
            result = await adapter.save_to_template_library(input_data)
            require_success(result, "Failed to save to library")
            return {
                "status": "success",
                "message": "Template saved to library",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        template_name = input_data.get("template_name", "")

        raise UnsupportedOperationError(
            "Active adapter does not support save_to_template_library; "
            f"'{template_name}' was not saved to any library. There is "
            "no local template registry — this tool needs a real "
            "adapter-backed library service."
        )

    @mcp.tool()
    async def list_template_library(input_data: dict[str, Any]) -> dict[str, Any]:
        """List the templates in the shared template library.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Read-only.
        Returns: once available, the library's templates under `data`.

        Args:
            input_data: A mapping of optional filters; none is required.

        Returns:
            dict[str, Any]: The templates, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "list_template_library",
            "Active adapter does not support list_template_library; "
            "there is no local template registry to list.",
        )
        result = await adapter.list_template_library(input_data)
        require_success(result, "Failed to list template library")
        return {
            "status": "success",
            "message": "Template library listed successfully",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    tool_count = 6  # Template management tools
    return tool_count
