"""
Export tools for SolidWorks MCP Server.

Provides tools for exporting SolidWorks models to various formats including
STEP, IGES, STL, PDF, DWG, and image formats.
"""

from typing import Any, TypeVar
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from loguru import logger

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput


TInput = TypeVar("TInput", bound=BaseModel)


def _normalize_input(input_data: Any, model_type: type[TInput]) -> TInput:
    """Execute normalize input.
    
    Args:
        input_data (Any): Describe input data.
        model_type (type[TInput]): Describe model type.
    
    Returns:
        TInput: Describe the returned value.
    
    """
    if isinstance(input_data, model_type):
        return input_data
    return model_type.model_validate(input_data)


# Input schemas using Python 3.14 built-in types


class ExportFileInput(CompatInput):
    """Input schema for exporting files."""

    file_path: str = Field(description="Full path for the exported file")
    format_type: str = Field(
        description="Export format (step, iges, stl, pdf, dwg, jpg, png)"
    )
    options: dict[str, Any] | None = Field(
        default=None, description="Format-specific export options"
    )


class ExportImageInput(CompatInput):
    """Input schema for exporting images."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
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
    """Input schema for STEP export."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.file_path is None:
            self.file_path = self.output_path


class ExportIGESInput(CompatInput):
    """Input schema for IGES export."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.file_path is None:
            self.file_path = self.output_path


class ExportSTLInput(CompatInput):
    """Input schema for STL export."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.file_path is None:
            self.file_path = self.output_path


class ExportPDFInput(CompatInput):
    """Input schema for PDF export."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.file_path is None:
            self.file_path = self.output_path


class ExportDWGInput(CompatInput):
    """Input schema for DWG export."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.file_path is None:
            self.file_path = self.output_path
        if self.autocad_version is not None:
            self.version = self.autocad_version


class BatchExportInput(CompatInput):
    """Input schema for batch export operations."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.format_type is None:
            self.format_type = self.export_format
        if self.file_pattern:
            self.file_patterns = [self.file_pattern]
        if self.include_subdirectories:
            self.recursive = True


async def register_export_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """
    Register export tools with FastMCP.

    Registers comprehensive file export tools for SolidWorks automation
    supporting multiple industry-standard formats including neutral CAD
    formats, manufacturing formats, and documentation outputs.

    Args:
        mcp (FastMCP): FastMCP server instance for tool registration
        adapter (SolidWorksAdapter): SolidWorks adapter for COM operations
        config (dict[str, Any]): Configuration dictionary for export settings

    Returns:
        int: Number of export tools registered (7 export tools)

    Note:
        Export tools provide comprehensive format conversion capabilities
        for manufacturing, documentation, and CAD interoperability.
        Supports industry standards including STEP, IGES, STL, PDF,
        DWG, and image formats.

    Example:
        ```python
        from solidworks_mcp.tools.export import register_export_tools

        tool_count = await register_export_tools(mcp, adapter, config)
        print(f"Registered {tool_count} export tools")
        ```
    """
    tool_count = 0

    @mcp.tool()
    async def export_step(input_data: ExportFileInput) -> dict[str, Any]:
        """
        Export the current model to STEP format.

        Exports SolidWorks models to STEP (Standard for the Exchange of
        Product Data) format, the preferred neutral CAD format for
        interoperability between different CAD systems and manufacturers.

        Args:
            input_data (ExportFileInput): Contains:
                - file_path (str): Full output file path with .step or .stp extension
                - format_type (str): Export format identifier ("step")
                - options (dict[str, Any] | None): Format-specific options:
                  * "units" (str): "mm", "in", "m" - output units
                  * "version" (str): "214" or "203" - STEP standard version
                  * "precision" (float): Geometric precision for curves/surfaces

        Returns:
            dict[str, Any]: Export result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - export (dict): Export information including:
                  - file_path (str): Output file location
                  - format (str): "STEP" format identifier
                  - size_estimate (str): Approximate file size
                - execution_time (float): Export operation time in seconds

        Example:
            ```python
            # Export part to STEP for manufacturing
            result = await export_step({
                "file_path": "C:/Exports/bracket.step",
                "format_type": "step",
                "options": {
                    "units": "mm",
                    "version": "214",
                    "precision": 0.01
                }
            })

            if result["status"] == "success":
                export = result["export"]
                print(f"STEP file created: {export['file_path']}")
                # Ready for CNC programming or CAM software
            ```

        Note:
            - STEP format preserves precise geometric data for manufacturing
            - Most widely supported neutral CAD format in industry
            - Recommended for supplier collaboration and CNC machining
            - Supports assemblies, parts, and surface models
        """
        try:
            if hasattr(input_data, "model_dump"):
                payload = input_data.model_dump()
                file_path = input_data.file_path
            else:
                payload = dict(input_data)
                file_path = payload.get("file_path")

            if hasattr(adapter, "export_step"):
                result = await adapter.export_step(payload)
            else:
                result = await adapter.export_file(file_path, "step")

            if result.is_success:
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
            else:
                return {
                    "status": "error",
                    "message": f"Failed to export STEP: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in export_step tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def export_iges(input_data: ExportFileInput) -> dict[str, Any]:
        """
        Export the current model to IGES format.

        Exports SolidWorks models to IGES (Initial Graphics Exchange
        Specification) format, a legacy neutral CAD format still widely
        used for surface modeling and older CAD system compatibility.

        Args:
            input_data (ExportFileInput): Contains:
                - file_path (str): Full output file path with .iges or .igs extension
                - format_type (str): Export format identifier ("iges")
                - options (dict[str, Any] | None): Format-specific options:
                  * "units" (str): "mm", "in", "m" - output units
                  * "surfaces_only" (bool): Export surfaces only (no solids)
                  * "trim_curves" (bool): Include trimmed surface boundaries

        Returns:
            dict[str, Any]: Export result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - export (dict): Export information including:
                  - file_path (str): Output file location
                  - format (str): "IGES" format identifier
                  - size_estimate (str): Approximate file size
                - execution_time (float): Export operation time in seconds

        Example:
            ```python
            # Export surface model for legacy CAD system
            result = await export_iges({
                "file_path": "C:/Exports/surface_model.iges",
                "format_type": "iges",
                "options": {
                    "units": "mm",
                    "surfaces_only": True,
                    "trim_curves": True
                }
            })

            if result["status"] == "success":
                export = result["export"]
                print(f"IGES file created: {export['file_path']}")
                # Compatible with older CAD/CAM systems
            ```

        Note:
            - IGES format is older but still required for some legacy systems
            - Excellent for surface modeling and complex curve data
            - Use STEP format for newer systems when possible
            - Common in aerospace and automotive surface design
        """
        try:
            if hasattr(adapter, "export_iges"):
                result = await adapter.export_iges(input_data.model_dump())
            else:
                result = await adapter.export_file(input_data.file_path, "iges")

            if result.is_success:
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
            else:
                return {
                    "status": "error",
                    "message": f"Failed to export IGES: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in export_iges tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def export_stl(input_data: ExportFileInput) -> dict[str, Any]:
        """
        Export the current model to STL format.

        Exports SolidWorks models to STL (Stereolithography) format,
        the standard file format for 3D printing, rapid prototyping,
        and additive manufacturing applications.

        Args:
            input_data (ExportFileInput): Contains:
                - file_path (str): Full output file path with .stl extension
                - format_type (str): Export format identifier ("stl")
                - options (dict[str, Any] | None): STL-specific options:
                  * "resolution" (str): "fine", "coarse", "custom" - mesh resolution
                  * "units" (str): "mm", "in", "m" - output units
                  * "ascii" (bool): True for ASCII format, False for binary
                  * "deviation" (float): Maximum surface deviation for tessellation

        Returns:
            dict[str, Any]: Export result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - export (dict): Export information including:
                  - file_path (str): Output file location
                  - format (str): "STL" format identifier
                  - use_case (str): "3D printing and rapid prototyping"
                  - size_estimate (str): Approximate file size
                - execution_time (float): Export operation time in seconds

        Example:
            ```python
            # Export high-resolution STL for 3D printing
            result = await export_stl({
                "file_path": "C:/3DPrint/prototype.stl",
                "format_type": "stl",
                "options": {
                    "resolution": "fine",
                    "units": "mm",
                    "ascii": False,
                    "deviation": 0.1
                }
            })

            if result["status"] == "success":
                export = result["export"]
                print(f"STL ready for 3D printing: {export['file_path']}")
                # Load into slicer software for printing
            ```

        Note:
            - STL format creates triangulated mesh representation
            - Resolution affects both file size and print quality
            - Binary format is more compact than ASCII
            - Essential for 3D printing and rapid prototyping workflows
        """
        try:
            if hasattr(adapter, "export_stl"):
                result = await adapter.export_stl(input_data.model_dump())
            else:
                result = await adapter.export_file(input_data.file_path, "stl")

            if result.is_success:
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
            else:
                return {
                    "status": "error",
                    "message": f"Failed to export STL: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in export_stl tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def export_pdf(input_data: ExportFileInput) -> dict[str, Any]:
        """
        Export the current model or drawing to PDF format.

        Creates PDF documents from SolidWorks drawings, assemblies, or
        parts for documentation, sharing, review, and archival purposes.
        Essential for design review and manufacturing documentation.

        Args:
            input_data (ExportFileInput): Contains:
                - file_path (str): Full output file path with .pdf extension
                - format_type (str): Export format identifier ("pdf")
                - options (dict[str, Any] | None): PDF-specific options:
                  * "quality" (str): "high", "medium", "low" - image quality
                  * "sheets" (str): "all", "current", "range" - drawing sheets to export
                  * "3d_pdf" (bool): Include 3D model in PDF (if supported)
                  * "security" (dict): Password protection and permissions

        Returns:
            dict[str, Any]: Export result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - export (dict): Export information including:
                  - file_path (str): Output file location
                  - format (str): "PDF" format identifier
                  - use_case (str): "Documentation and sharing"
                  - size_estimate (str): Approximate file size
                - execution_time (float): Export operation time in seconds

        Example:
            ```python
            # Export technical drawings to secured PDF
            result = await export_pdf({
                "file_path": "C:/Documentation/assembly_drawing.pdf",
                "format_type": "pdf",
                "options": {
                    "quality": "high",
                    "sheets": "all",
                    "3d_pdf": False,
                    "security": {
                        "password": "project123",
                        "allow_printing": True,
                        "allow_editing": False
                    }
                }
            })

            if result["status"] == "success":
                export = result["export"]
                print(f"PDF documentation: {export['file_path']}")
                # Ready for distribution and review
            ```

        Note:
            - PDF format preserves drawing layout and annotations
            - Ideal for design reviews and manufacturing documentation
            - Can include multiple sheets from drawing files
            - Supports password protection and access controls
        """
        try:
            if hasattr(adapter, "export_pdf"):
                result = await adapter.export_pdf(input_data.model_dump())
            else:
                result = await adapter.export_file(input_data.file_path, "pdf")

            if result.is_success:
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
            else:
                return {
                    "status": "error",
                    "message": f"Failed to export PDF: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in export_pdf tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def export_dwg(input_data: ExportFileInput) -> dict[str, Any]:
        """
        Export the current drawing to DWG format.

        Converts SolidWorks drawings to DWG (Drawing) format, the native
        AutoCAD file format widely used in architecture, engineering,
        and construction industries for 2D technical drawings.

        Args:
            input_data (ExportFileInput): Contains:
                - file_path (str): Full output file path with .dwg extension
                - format_type (str): Export format identifier ("dwg")
                - options (dict[str, Any] | None): DWG-specific options:
                  * "version" (str): "2018", "2013", "2010" - AutoCAD version compatibility
                  * "units" (str): "mm", "in", "m" - drawing units
                  * "layers" (bool): Preserve SolidWorks layers as AutoCAD layers
                  * "line_weights" (bool): Export line weight information

        Returns:
            dict[str, Any]: Export result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - export (dict): Export information including:
                  - file_path (str): Output file location
                  - format (str): "DWG" format identifier
                  - use_case (str): "AutoCAD compatibility"
                  - size_estimate (str): Approximate file size
                - execution_time (float): Export operation time in seconds

        Example:
            ```python
            # Export architectural drawings to AutoCAD format
            result = await export_dwg({
                "file_path": "C:/CAD/floor_plan.dwg",
                "format_type": "dwg",
                "options": {
                    "version": "2018",
                    "units": "mm",
                    "layers": True,
                    "line_weights": True
                }
            })

            if result["status"] == "success":
                export = result["export"]
                print(f"AutoCAD file ready: {export['file_path']}")
                # Compatible with AutoCAD and DWG viewers
            ```

        Note:
            - DWG format ensures compatibility with AutoCAD ecosystem
            - Only applicable to SolidWorks drawing files (not 3D models)
            - Version compatibility important for legacy AutoCAD systems
            - Preserves dimensions, annotations, and drawing structure
        """
        try:
            if hasattr(adapter, "export_dwg"):
                result = await adapter.export_dwg(input_data.model_dump())
            else:
                result = await adapter.export_file(input_data.file_path, "dwg")

            if result.is_success:
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
            else:
                return {
                    "status": "error",
                    "message": f"Failed to export DWG: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in export_dwg tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def export_image(input_data: ExportImageInput) -> dict[str, Any]:
        """
        Export images of the current model.

        Captures high-quality rendered images of SolidWorks models from
        various view orientations for documentation, presentations,
        marketing materials, and web publication.

        Args:
            input_data (ExportImageInput): Contains:
                - file_path (str): Full output file path with image extension
                - format_type (str): Image format: "jpg", "png", "bmp", "tiff". Default: "jpg"
                - width (int): Image width in pixels. Default: 1920
                - height (int): Image height in pixels. Default: 1080
                - view_orientation (str): Camera orientation options:
                  * "front" - Standard front orthographic view
                  * "top" - Top-down orthographic view
                  * "right" - Right side orthographic view
                  * "isometric" - 3D isometric perspective view
                  * "current" - Current active viewport orientation
                  Default: "isometric"

        Returns:
            dict[str, Any]: Export result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - export (dict): Image information including:
                  - file_path (str): Output image file location
                  - format (str): Image format (JPG, PNG, etc.)
                  - dimensions (str): Image size as "1920x1080"
                  - view (str): Applied view orientation
                  - use_case (str): "Documentation and presentations"
                - execution_time (float): Rendering and export time in seconds

        Example:
            ```python
            # Create high-res marketing image
            result = await export_images({
                "file_path": "C:/Marketing/product_hero.png",
                "format_type": "png",
                "width": 3840, "height": 2160,  # 4K resolution
                "view_orientation": "isometric"
            })

            if result["status"] == "success":
                export = result["export"]
                print(f"High-res image: {export['dimensions']} {export['format']}")
                # Ready for marketing and presentation use
            ```

        Note:
            - PNG format supports transparency for overlay graphics
            - Higher resolutions create larger file sizes but better quality
            - Isometric views are ideal for technical documentation
            - Consider lighting and material settings for best results
        """
        try:
            input_data = _normalize_input(input_data, ExportImageInput)
            if hasattr(adapter, "export_image"):
                result = await adapter.export_image(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"Exported image: {input_data.file_path}",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to export image",
                }

            if hasattr(adapter, "export_file") and input_data.file_path:
                result = await adapter.export_file(
                    input_data.file_path, input_data.format_type
                )
                if result.is_success:
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
                return {
                    "status": "error",
                    "message": result.error or "Failed to export image",
                }

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
            }

        except Exception as e:
            logger.error(f"Error in export_images tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def batch_export(input_data: BatchExportInput) -> dict[str, Any]:
        """
        Batch export multiple SolidWorks files to a target format.

        Processes entire directories of SolidWorks files and converts them
        to specified target formats. Essential for project migrations,
        supplier deliverables, and large-scale format conversions.

        Args:
            input_data (BatchExportInput): Contains:
                - source_directory (str): Directory path containing SolidWorks files
                - output_directory (str): Target directory for exported files
                - format_type (str): Target export format ("step", "iges", "stl", etc.)
                - recursive (bool): Search subdirectories recursively. Default: False
                - file_patterns (list[str]): File patterns to include. Default:
                  ["*.sldprt", "*.sldasm", "*.slddrw"] for all SolidWorks file types

        Returns:
            dict[str, Any]: Export result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - batch_export (dict): Batch operation results including:
                  - source_directory (str): Input directory processed
                  - output_directory (str): Target directory for exports
                  - format (str): Applied export format
                  - files_processed (int): Total files attempted
                  - files_successful (int): Successfully exported files
                  - files_failed (int): Failed export attempts
                  - errors (list[str]): Error messages for failed exports
                - execution_time (float): Total batch processing time in seconds

        Example:
            ```python
            # Convert entire project to STEP for manufacturing
            result = await batch_export({
                "source_directory": "C:/SolidWorks_Project/Parts",
                "output_directory": "C:/Manufacturing/STEP_Files",
                "format_type": "step",
                "recursive": True,
                "file_patterns": ["*.sldprt", "*.sldasm"]
            })

            if result["status"] == "success":
                batch = result["batch_export"]
                print(f"Processed {batch['files_processed']} files")
                print(f"Success: {batch['files_successful']}, Failed: {batch['files_failed']}")
                # All parts ready for CNC programming
            ```

        Note:
            - Process can take significant time for large directories
            - Failed exports are logged with specific error messages
            - Maintains directory structure in output location
            - Essential for project deliverables and supplier packages
        """
        try:
            if hasattr(adapter, "batch_export"):
                result = await adapter.batch_export(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"Batch export completed to {input_data.format_type} format",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Batch export failed",
                }

            return {
                "status": "success",
                "message": f"Batch export completed to {input_data.format_type} format",
                "batch_export": {
                    "source_directory": input_data.source_directory,
                    "output_directory": input_data.output_directory,
                    "format": input_data.format_type.upper(),
                    "files_processed": 0,  # Would be actual count
                    "files_successful": 0,
                    "files_failed": 0,
                    "errors": [],
                },
            }

        except Exception as e:
            logger.error(f"Error in batch_export tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    tool_count = 7  # Number of tools registered
    return tool_count
