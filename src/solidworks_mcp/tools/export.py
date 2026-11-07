"""Export tools for SolidWorks MCP Server.

Provides tools for exporting SolidWorks models to various formats including STEP, IGES,
STL, PDF, DWG, and image formats.
"""

from typing import Any, TypeVar

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    UnsupportedOperationError,
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

TInput = TypeVar("TInput", bound=BaseModel)


# Input schemas using Python 3.14 built-in types


class ExportFileInput(CompatInput):
    """Input schema for exporting files.

    Attributes:
        file_path (str): The file path value.
        format_type (str): The format type value.
        options (dict[str, Any] | None): The options value.
    """

    file_path: str = Field(description="Full path for the exported file")
    format_type: str = Field(
        description="Export format (step, iges, stl, pdf, dwg, jpg, png)"
    )
    options: dict[str, Any] | None = Field(
        default=None, description="Format-specific export options"
    )


class ExportImageInput(CompatInput):
    """Input schema for exporting images.

    Attributes:
        file_path (str | None): The file path value.
        format (str | None): The format value.
        format_type (str): The format type value.
        height (int): The height value.
        image_format (str | None): The image format value.
        model_path (str | None): The model path value.
        orientation (str | None): The orientation value.
        output_path (str | None): The output path value.
        resolution (str | None): The resolution value.
        view_orientation (str): The view orientation value.
        width (int): The width value.
    """

    file_path: str | None = Field(
        default=None, description="Full path for the exported image"
    )
    output_path: str | None = Field(default=None, description="Alternative output path")
    model_path: str | None = Field(default=None, description="Path to the model file")
    format_type: str = Field(
        default="jpg", description="Image format (jpg, png, bmp, tiff)"
    )
    format: str | None = Field(default=None, description="Alternative format field")
    image_format: str | None = Field(default=None, description="Image format alias")
    width: int = Field(default=1920, description="Image width in pixels")
    height: int = Field(default=1080, description="Image height in pixels")
    resolution: str | None = Field(default=None, description="Resolution alias")
    view_orientation: str = Field(
        default="isometric",
        description="View orientation (front, top, right, isometric, current)",
    )
    orientation: str | None = Field(
        default=None, description="Alternative orientation field"
    )

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the export image input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.file_path is None:
            self.file_path = self.output_path
        if self.image_format is not None:
            self.format_type = self.image_format.lower()
        if self.resolution and "x" in self.resolution.lower():
            width, height = self.resolution.lower().split("x", 1)
            self.width = int(width)
            self.height = int(height)


class ExportSTEPInput(CompatInput):
    """Input schema for STEP export.

    Attributes:
        file_path (str | None): The file path value.
        model_path (str | None): The model path value.
        output_path (str | None): The output path value.
        precision (float): The precision value.
        step_version (str | None): The step version value.
        units (str): The units value.
        version (str): The version value.
    """

    file_path: str | None = Field(
        default=None, description="Output file path for STEP file"
    )
    model_path: str | None = Field(default=None, description="Path to the model file")
    output_path: str | None = Field(default=None, description="Alternative output path")
    precision: float = Field(default=0.01, description="Export precision")
    units: str = Field(default="mm", description="Units for export")
    version: str = Field(default="AP214", description="STEP version")
    step_version: str | None = Field(
        default=None, description="Alternative STEP version"
    )

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the export stepinput.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.file_path is None:
            self.file_path = self.output_path


class ExportIGESInput(CompatInput):
    """Input schema for IGES export.

    Attributes:
        file_path (str | None): The file path value.
        iges_version (str | None): The iges version value.
        model_path (str | None): The model path value.
        output_path (str | None): The output path value.
        precision (float): The precision value.
        surface_type (str): The surface type value.
        units (str): The units value.
    """

    file_path: str | None = Field(
        default=None, description="Output file path for IGES file"
    )
    model_path: str | None = Field(default=None, description="Path to the model file")
    output_path: str | None = Field(default=None, description="Alternative output path")
    precision: float = Field(default=0.01, description="Export precision")
    units: str = Field(default="mm", description="Units for export")
    surface_type: str = Field(default="NURBS", description="Surface type")
    iges_version: str | None = Field(
        default=None, description="Alternative IGES version"
    )

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the export igesinput.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.file_path is None:
            self.file_path = self.output_path


class ExportSTLInput(CompatInput):
    """Input schema for STL export.

    Attributes:
        binary_format (bool): The binary format value.
        file_format (str | None): The file format value.
        file_path (str | None): The file path value.
        format_type (str): The format type value.
        model_path (str | None): The model path value.
        output_path (str | None): The output path value.
        resolution (str): The resolution value.
        units (str): The units value.
    """

    file_path: str | None = Field(
        default=None, description="Output file path for STL file"
    )
    model_path: str | None = Field(default=None, description="Path to the model file")
    output_path: str | None = Field(default=None, description="Alternative output path")
    resolution: str = Field(
        default="fine", description="Mesh resolution (coarse, fine, custom)"
    )
    binary_format: bool = Field(default=True, description="Use binary STL format")
    format_type: str = Field(default="Binary", description="STL format type")
    file_format: str | None = Field(
        default=None, description="Alternative STL format field"
    )
    units: str = Field(default="mm", description="Units for export")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the export stlinput.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.file_path is None:
            self.file_path = self.output_path


class ExportPDFInput(CompatInput):
    """Input schema for PDF export.

    Attributes:
        color_mode (str): The color mode value.
        drawing_path (str | None): The drawing path value.
        file_path (str | None): The file path value.
        include_3d (bool): The include 3d value.
        output_path (str | None): The output path value.
        quality (str): The quality value.
    """

    file_path: str | None = Field(
        default=None, description="Output file path for PDF file"
    )
    drawing_path: str | None = Field(
        default=None, description="Path to the drawing file"
    )
    output_path: str | None = Field(default=None, description="Alternative output path")
    quality: str = Field(default="high", description="PDF quality (low, medium, high)")
    include_3d: bool = Field(default=False, description="Include 3D PDF content")
    color_mode: str = Field(default="Color", description="Color mode")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the export pdfinput.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.file_path is None:
            self.file_path = self.output_path


class ExportDWGInput(CompatInput):
    """Input schema for DWG export.

    Attributes:
        autocad_version (str | None): The autocad version value.
        drawing_path (str | None): The drawing path value.
        dwg_version (str): The dwg version value.
        file_path (str | None): The file path value.
        layer_mapping (bool): The layer mapping value.
        output_path (str | None): The output path value.
        units (str): The units value.
        version (str): The version value.
    """

    file_path: str | None = Field(
        default=None, description="Output file path for DWG file"
    )
    drawing_path: str | None = Field(
        default=None, description="Path to the drawing file"
    )
    output_path: str | None = Field(default=None, description="Alternative output path")
    version: str = Field(
        default="2018", description="AutoCAD version (2018, 2014, 2010, etc.)"
    )
    autocad_version: str | None = Field(
        default=None, description="AutoCAD version alias"
    )
    units: str = Field(default="mm", description="Units for export")
    dwg_version: str = Field(default="2018", description="DWG version")
    layer_mapping: bool = Field(default=False, description="Enable layer mapping")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the export dwginput.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.file_path is None:
            self.file_path = self.output_path
        if self.autocad_version is not None:
            self.version = self.autocad_version


class BatchExportInput(CompatInput):
    """Input schema for batch export operations.

    Attributes:
        export_format (str | None): The export format value.
        file_pattern (str | None): The file pattern value.
        file_patterns (list[str]): The file patterns value.
        format_type (str | None): The format type value.
        include_subdirectories (bool): The include subdirectories value.
        output_directory (str): The output directory value.
        recursive (bool): The recursive value.
        source_directory (str): The source directory value.
    """

    source_directory: str = Field(description="Directory containing SolidWorks files")
    output_directory: str = Field(description="Directory for exported files")
    format_type: str | None = Field(default=None, description="Target export format")
    export_format: str | None = Field(
        default=None, description="Alternative export format"
    )
    file_pattern: str | None = Field(default=None, description="File pattern alias")
    recursive: bool = Field(
        default=False, description="Search subdirectories recursively"
    )
    include_subdirectories: bool = Field(
        default=False, description="Include subdirectories in search"
    )
    file_patterns: list[str] = Field(
        default=["*.sldprt", "*.sldasm", "*.slddrw"],
        description="File patterns to include",
    )

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the batch export input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.format_type is None:
            self.format_type = self.export_format
        if self.file_pattern:
            self.file_patterns = [self.file_pattern]
        if self.include_subdirectories:
            self.recursive = True


def _file_input(input_data: Any, format_type: str) -> Any:
    """Validate a plain-dict argument as ``ExportFileInput``.

    Over MCP the arguments arrive already validated; a script calling the
    tool function directly passes a dict, which has no ``file_path``
    attribute. The tool's own format fills ``format_type`` when the dict
    leaves it out. Models, including the per-format aliases, pass through.
    """
    if isinstance(input_data, dict):
        return normalize_input(
            {"format_type": format_type, **input_data}, ExportFileInput
        )
    return input_data


async def register_export_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register export tools with FastMCP.

    Registers comprehensive file export tools for SolidWorks automation supporting multiple
    industry-standard formats including neutral CAD formats, manufacturing formats, and
    documentation outputs.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (dict[str, Any]): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        ```python
                        from solidworks_mcp.tools.export import register_export_tools

                        tool_count = await register_export_tools(mcp, adapter, config)
                        print(f"Registered {tool_count} export tools")
                        ```
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def export_step(input_data: ExportFileInput) -> dict[str, Any]:
        """Export the active document to STEP, like File > Save As with the STEP type.

        Use it to hand a model to another CAD system; it is the most widely read
        exchange format. SolidWorks picks the format from the file's extension, so end
        `file_path` in .step or .stp. Needs: an open, active part or assembly. Changes:
        writes the file, creating its folder and replacing a file already there; the
        open document is unchanged. Returns: `export` with `file_path` and `format`.

        Args:
            input_data: The export. `file_path` (ending in .step or .stp) is required;
                `format_type` is required by the schema but the extension decides the
                format, and `options` is not used yet.

        Returns:
            dict[str, Any]: The file written.
        """
        input_data = _file_input(input_data, "step")
        file_path = input_data.file_path

        if hasattr(adapter, "export_step"):
            result = await adapter.export_step(input_data.model_dump())
        else:
            result = await adapter.export_file(file_path, "step")

        require_success(result, context="Failed to export STEP")
        if hasattr(adapter, "export_step"):
            return {
                "status": "success",
                "message": f"Exported to STEP format: {file_path}",
                "data": result.data,
                "execution_time": result.execution_time,
            }
        return {
            "status": "success",
            "message": f"Exported to STEP format: {file_path}",
            "export": {
                "file_path": file_path,
                "format": "STEP",
                "size_estimate": "Unknown",  # Would get actual file size
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def export_iges(input_data: ExportFileInput) -> dict[str, Any]:
        """Export the active document to IGES, like File > Save As with the IGES type.

        Use it only when the receiver can't read STEP; prefer `export_step`. SolidWorks
        picks the format from the file's extension, so end `file_path` in .igs or .iges.
        Needs: an open, active part or assembly. Changes: writes the file, creating its
        folder and replacing a file already there; the open document is unchanged.
        Returns: `export` with `file_path` and `format`.

        Args:
            input_data: The export. `file_path` (ending in .igs or .iges) is required;
                `format_type` is required by the schema but the extension decides the
                format, and `options` is not used yet.

        Returns:
            dict[str, Any]: The file written.
        """
        input_data = _file_input(input_data, "iges")
        if hasattr(adapter, "export_iges"):
            result = await adapter.export_iges(input_data.model_dump())
        else:
            result = await adapter.export_file(input_data.file_path, "iges")

        require_success(result, context="Failed to export IGES")
        if hasattr(adapter, "export_iges"):
            return {
                "status": "success",
                "message": f"Exported to IGES format: {input_data.file_path}",
                "data": result.data,
                "execution_time": result.execution_time,
            }
        return {
            "status": "success",
            "message": f"Exported to IGES format: {input_data.file_path}",
            "export": {
                "file_path": input_data.file_path,
                "format": "IGES",
                "size_estimate": "Unknown",
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def export_stl(input_data: ExportFileInput) -> dict[str, Any]:
        """Export the active document to STL, like File > Save As with the STL type.

        Use it for 3D printing. An assembly is exported whole, with lightweight
        components resolved first. SolidWorks picks the format from the file's
        extension, so end `file_path` in .stl. Needs: an open, active part or assembly.
        Changes: writes the file, creating its folder and replacing a file already
        there; the open document is unchanged. Returns: `export` with `file_path` and
        `format`.

        Args:
            input_data: The export. `file_path` (ending in .stl) is required;
                `format_type` is required by the schema but the extension decides the
                format, and `options` is not used yet.

        Returns:
            dict[str, Any]: The file written.
        """
        input_data = _file_input(input_data, "stl")
        if hasattr(adapter, "export_stl"):
            result = await adapter.export_stl(input_data.model_dump())
        else:
            result = await adapter.export_file(input_data.file_path, "stl")

        require_success(result, context="Failed to export STL")
        if hasattr(adapter, "export_stl"):
            return {
                "status": "success",
                "message": f"Exported to STL format: {input_data.file_path}",
                "data": result.data,
                "execution_time": result.execution_time,
            }
        return {
            "status": "success",
            "message": f"Exported to STL format: {input_data.file_path}",
            "export": {
                "file_path": input_data.file_path,
                "format": "STL",
                "use_case": "3D printing and rapid prototyping",
                "size_estimate": "Unknown",
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def export_pdf(input_data: ExportFileInput) -> dict[str, Any]:
        """Export the active document to PDF, like File > Save As with the PDF type.

        Use it to share a drawing; `generate_drawing_package` already saves a PDF with
        the drawing it creates. SolidWorks picks the format from the file's extension,
        so end `file_path` in .pdf. Needs: an open, active drawing (a part or assembly
        gives a PDF of the view). Changes: writes the file, creating its folder and
        replacing a file already there; the open document is unchanged. Returns:
        `export` with `file_path` and `format`.

        Args:
            input_data: The export. `file_path` (ending in .pdf) is required;
                `format_type` is required by the schema but the extension decides the
                format, and `options` is not used yet.

        Returns:
            dict[str, Any]: The file written.
        """
        input_data = _file_input(input_data, "pdf")
        if hasattr(adapter, "export_pdf"):
            result = await adapter.export_pdf(input_data.model_dump())
        else:
            result = await adapter.export_file(input_data.file_path, "pdf")

        require_success(result, context="Failed to export PDF")
        if hasattr(adapter, "export_pdf"):
            return {
                "status": "success",
                "message": f"Exported to PDF format: {input_data.file_path}",
                "data": result.data,
                "execution_time": result.execution_time,
            }
        return {
            "status": "success",
            "message": f"Exported to PDF format: {input_data.file_path}",
            "export": {
                "file_path": input_data.file_path,
                "format": "PDF",
                "use_case": "Documentation and sharing",
                "size_estimate": "Unknown",
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def export_dwg(input_data: ExportFileInput) -> dict[str, Any]:
        """Export the active document to DWG, like File > Save As with the DWG type.

        Use it to hand a drawing to AutoCAD users. SolidWorks picks the format from the
        file's extension, so end `file_path` in .dwg. Needs: an open, active drawing.
        Changes: writes the file, creating its folder and replacing a file already
        there; the open document is unchanged. Returns: `export` with `file_path` and
        `format`.

        Args:
            input_data: The export. `file_path` (ending in .dwg) is required;
                `format_type` is required by the schema but the extension decides the
                format, and `options` is not used yet.

        Returns:
            dict[str, Any]: The file written.
        """
        input_data = _file_input(input_data, "dwg")
        if hasattr(adapter, "export_dwg"):
            result = await adapter.export_dwg(input_data.model_dump())
        else:
            result = await adapter.export_file(input_data.file_path, "dwg")

        require_success(result, context="Failed to export DWG")
        if hasattr(adapter, "export_dwg"):
            return {
                "status": "success",
                "message": f"Exported to DWG format: {input_data.file_path}",
                "data": result.data,
                "execution_time": result.execution_time,
            }
        return {
            "status": "success",
            "message": f"Exported to DWG format: {input_data.file_path}",
            "export": {
                "file_path": input_data.file_path,
                "format": "DWG",
                "use_case": "AutoCAD compatibility",
                "size_estimate": "Unknown",
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def export_image(input_data: ExportImageInput) -> dict[str, Any]:
        """Save a picture of the active model in a standard view, as PNG or JPG, at a chosen size.

        Use it to show a result, or to check a model's shape after a change. The view is
        set first (front, back, left, right, top, bottom, isometric, dimetric,
        trimetric, or current to keep the user's view). Needs: an open, active document.
        Changes: writes the image file, and turns the model to the view asked for.
        Returns: `data` with `file_path`, `format`, `dimensions` (the size written),
        `requested_dimensions` and `view`.

        Args:
            input_data: The image. `file_path` (or `output_path`) is needed; the
                format follows its extension. `width`/`height` (or `resolution` as
                "1920x1080") and `view_orientation` (isometric) have defaults.

        Returns:
            dict[str, Any]: The image written.
        """
        input_data = normalize_input(input_data, ExportImageInput)
        if hasattr(adapter, "export_image"):
            result = await adapter.export_image(input_data.model_dump())
            require_success(result, "Failed to export image")
            return {
                "status": "success",
                "message": f"Exported image: {input_data.file_path}",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        if hasattr(adapter, "export_file") and input_data.file_path:
            result = await adapter.export_file(  # type: ignore[assignment]
                input_data.file_path, input_data.format_type
            )
            require_success(result, "Failed to export image")
            return {
                "status": "success",
                "message": f"Exported image: {input_data.file_path}",
                "export": {
                    "file_path": input_data.file_path,
                    "format": input_data.format_type.upper(),
                    "dimensions": f"{input_data.width}x{input_data.height}",
                    "view": input_data.view_orientation,
                    "use_case": "Documentation and presentations",
                },
                "execution_time": result.execution_time,
            }

        raise UnsupportedOperationError(
            "Active adapter does not support export_image or "
            "export_file; no image was exported."
        )

    @mcp.tool()
    async def batch_export(input_data: BatchExportInput) -> dict[str, Any]:
        """Export every matching SolidWorks file in a folder to one format.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Today, open
        each file with `open_model` and use an `export_*` tool. Changes: once available,
        writes one exported file per source file. Returns: once available, a per-file
        result under `data`.

        Args:
            input_data: The batch. `source_directory` and `output_directory` are
                required; `format_type`, `file_pattern` and `recursive` have
                defaults.

        Returns:
            dict[str, Any]: The results, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "batch_export",
            "Active adapter does not support batch_export; no files were exported.",
        )
        result = await adapter.batch_export(input_data.model_dump())
        require_success(result, "Batch export failed")
        return {
            "status": "success",
            "message": f"Batch export completed to {input_data.format_type} format",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    tool_count = 7  # Number of tools registered
    return tool_count
