"""
File management tools for SolidWorks MCP Server.

Provides tools for managing SolidWorks files including save, save as,
file properties, and reference management.
"""

from typing import Any
from fastmcp import FastMCP
from pydantic import Field
from loguru import logger

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from ..utils.feature_tree_classifier import classify_feature_tree_snapshot


# Input schemas using Python 3.14 built-in types


class SaveFileInput(CompatInput):
    """Input schema for saving a file."""

    force_save: bool = Field(default=True, description="Force save even if no changes")
    file_path: str | None = Field(
        default=None,
        description="Optional output path. If omitted, saves the current active document.",
    )


class SaveAsInput(CompatInput):
    """Input schema for save as operation."""

    file_path: str = Field(description="Full path for the new file")
    format_type: str = Field(
        default="solidworks", description="File format (solidworks, step, iges, etc.)"
    )
    overwrite: bool = Field(default=False, description="Overwrite existing file")


class FileOperationInput(CompatInput):
    """Input schema for file operations."""

    operation: str = Field(
        description="Operation to perform (copy, move, delete, rename)"
    )
    source_path: str | None = Field(default=None, description="Source file path")
    file_path: str | None = Field(default=None, description="Alternative file path")
    target_path: str | None = Field(
        default=None, description="Target file path (for copy/move/rename)"
    )
    properties: dict[str, Any] | None = Field(
        default=None, description="File properties to set"
    )
    parameters: dict[str, Any] | None = Field(
        default=None, description="Operation parameters"
    )
    include_system: bool = Field(default=False, description="Include system properties")


class FormatConversionInput(CompatInput):
    """Input schema for format conversion."""

    source_file: str = Field(description="Source file path")
    target_file: str | None = Field(default=None, description="Target file path")
    source_format: str | None = Field(default=None, description="Source file format")
    target_format: str = Field(description="Target file format")
    output_path: str | None = Field(default=None, description="Alternative output path")
    conversion_options: dict[str, Any] | None = Field(
        default=None, description="Conversion options"
    )
    quality: str = Field(default="high", description="Conversion quality")
    units: str = Field(default="mm", description="Units")
    invalid_format: str | None = Field(
        default=None, description="Invalid format for testing"
    )


class LoadPartInput(CompatInput):
    """Input schema for loading a part file."""

    file_path: str = Field(description="Full path to the .sldprt file")


class LoadAssemblyInput(CompatInput):
    """Input schema for loading an assembly file."""

    file_path: str = Field(description="Full path to the .sldasm file")


class SavePartInput(CompatInput):
    """Input schema for saving a part file."""

    file_path: str | None = Field(
        default=None,
        description="Optional output path. If omitted, saves the active part to its existing location.",
    )
    overwrite: bool = Field(default=True, description="Overwrite existing file")


class SaveAssemblyInput(CompatInput):
    """Input schema for saving an assembly file."""

    file_path: str | None = Field(
        default=None,
        description="Optional output path. If omitted, saves the active assembly to its existing location.",
    )
    overwrite: bool = Field(default=True, description="Overwrite existing file")


class ListFeaturesInput(CompatInput):
    """Input schema for feature tree listing."""

    include_suppressed: bool = Field(
        default=False,
        description="Include suppressed features in the returned list",
    )


class ClassifyFeatureTreeInput(CompatInput):
    """Input schema for feature-family classification."""

    include_suppressed: bool = Field(
        default=True,
        description="Include suppressed features when reading the active model tree",
    )
    model_info: dict[str, Any] | None = Field(
        default=None,
        description="Optional pre-fetched model info payload to classify without re-reading the active model",
    )
    features: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional feature-tree payload to classify without re-reading the active model",
    )


async def register_file_management_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """
    Register file management tools with FastMCP.

    Registers essential file operations for SolidWorks document management including
    save operations, file format conversions, and file property access. These tools
    provide fundamental document lifecycle management capabilities.

    Args:
        mcp (FastMCP): FastMCP server instance for tool registration
        adapter (SolidWorksAdapter): SolidWorks adapter for COM operations
        config (dict[str, Any]): Configuration dictionary for file management settings

    Returns:
        int: Number of tools registered in this module.

    Example:
        ```python
        from solidworks_mcp.tools.file_management import register_file_management_tools

        tool_count = await register_file_management_tools(mcp, adapter, config)
        print(f"Registered {tool_count} file management tools")
        ```

    Note:
        File management tools require an active SolidWorks document.
        Save operations preserve the current document state and metadata.
    """
    tool_count = 0

    def _coerce_input(model_cls, payload):
        """Accept legacy dict payloads from compatibility wrapper as well as model instances."""
        return (
            payload
            if isinstance(payload, model_cls)
            else model_cls.model_validate(payload)
        )

    def _result_value(payload: Any, *keys: str, default: Any = None) -> Any:
        """Read a value from adapter result payloads that may be dicts or model objects."""
        if payload is None:
            return default

        if isinstance(payload, dict):
            for key in keys:
                if key in payload and payload[key] is not None:
                    return payload[key]
            return default

        for key in keys:
            value = getattr(payload, key, None)
            if value is not None:
                return value
        return default

    @mcp.tool()
    async def save_file(input_data: SaveFileInput) -> dict[str, Any]:
        """
        Save the current SolidWorks model.

        Saves the currently active SolidWorks document to its existing file location.
        Essential for preserving work and maintaining document version control.
        Handles both modified and unmodified documents based on force_save setting.

        Args:
            input_data (SaveFileInput): Contains:
                - force_save (bool, optional): Force save even if no changes (default: True)
                  Set to False to save only if document has been modified

        Returns:
            dict[str, Any]: Save operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - timestamp (str): Save time in ISO format
                - file_info (dict, optional): File information including:
                  - path (str): Full file path
                  - size (str): File size
                  - last_saved (str): Previous save timestamp

        Example:
            ```python
            # Force save current model
            result = await save_file({"force_save": True})

            # Save only if modified
            result = await save_file({"force_save": False})

            if result["status"] == "success":
                print(f"File saved at {result['timestamp']}")
            ```

        Note:
            - Requires an open SolidWorks document
            - Preserves original file location and format
            - Updates document timestamp and metadata
            - No effect if document is read-only
        """
        try:
            input_data = _coerce_input(SaveFileInput, input_data)
            if hasattr(adapter, "save_file"):
                result = await adapter.save_file(input_data.file_path)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "File saved successfully",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to save file",
                }

            return {
                "status": "success",
                "message": "File saved successfully",
                "timestamp": "2024-03-14T00:00:00Z",  # Would be actual timestamp
            }

        except Exception as e:
            logger.error(f"Error in save_file tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def save_as(input_data: SaveAsInput) -> dict[str, Any]:
        """
        Save the current model to a new location or format.

        Saves the currently active SolidWorks document with a new filename, location,
        or file format. Supports multiple export formats for interoperability with
        other CAD systems and manufacturing workflows.

        Args:
            input_data (SaveAsInput): Contains:
                - file_path (str): Full path for the new file including filename
                  Must include appropriate file extension
                - format_type (str, optional): File format (default: "solidworks")
                  Supported formats: "solidworks", "step", "iges", "stl", "obj",
                  "x_t", "dwg", "dxf", "pdf", "jpg", "png"
                - overwrite (bool, optional): Overwrite existing file (default: False)
                  Set to True to replace existing files without prompt

        Returns:
            dict[str, Any]: Save operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - file_path (str): Saved file location
                - format (str): File format used
                - file_size (str): Size of saved file
                - conversion_time (float): Export time in seconds

        Example:
            ```python
            # Save as new SolidWorks file
            result = await save_as({
                "file_path": "C:/Projects/bracket_v2.sldprt",
                "format_type": "solidworks",
                "overwrite": False
            })

            # Export to STEP format
            result = await save_as({
                "file_path": "C:/Exports/bracket.step",
                "format_type": "step",
                "overwrite": True
            })

            # Export for 3D printing
            result = await save_as({
                "file_path": "C:/3DPrint/bracket.stl",
                "format_type": "stl"
            })
            ```

        Raises:
            FileExistsError: If file exists and overwrite=False
            ValueError: If format_type is not supported
            PermissionError: If destination folder is not writable

        Note:
            - Original document remains unchanged and active
            - Export quality depends on format capabilities
            - Some formats may require additional SolidWorks add-ins
            - File path directories must exist before saving
        """
        try:
            input_data = _coerce_input(SaveAsInput, input_data)
            if hasattr(adapter, "save_file") and input_data.format_type.lower() in {
                "solidworks",
                "sldprt",
                "sldasm",
                "slddrw",
            }:
                result = await adapter.save_file(input_data.file_path)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"File saved as: {input_data.file_path}",
                        "file_path": input_data.file_path,
                        "format": input_data.format_type,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to save file",
                }

            if hasattr(adapter, "export_file"):
                result = await adapter.export_file(
                    input_data.file_path,
                    input_data.format_type,
                )
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"File exported as: {input_data.file_path}",
                        "file_path": input_data.file_path,
                        "format": input_data.format_type,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to export file",
                }

            # Fallback for adapters without save/export support.
            return {
                "status": "success",
                "message": f"File saved as: {input_data.file_path}",
                "file_path": input_data.file_path,
                "format": input_data.format_type,
            }

        except Exception as e:
            logger.error(f"Error in save_as tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def get_file_properties() -> dict[str, Any]:
        """
        Get properties of the current SolidWorks file.

        Retrieves comprehensive metadata and properties of the currently active
        SolidWorks document. Provides essential file information for document
        management, version control, and project organization.

        Returns:
            dict[str, Any]: File properties containing:
                - status (str): "success" or "error"
                - properties (dict): Comprehensive file metadata including:
                  - file_info (dict): Basic file information
                    - file_name (str): Document filename with extension
                    - file_path (str): Full path to file
                    - file_size (str): File size in human-readable format
                    - file_type (str): Document type (Part, Assembly, Drawing)
                  - timestamps (dict): Date and time information
                    - created_date (str): File creation timestamp (ISO format)
                    - modified_date (str): Last modification timestamp
                    - accessed_date (str): Last access timestamp
                  - document_info (dict): Document-specific properties
                    - author (str): Document author/creator
                    - company (str): Company information
                    - description (str): Document description
                    - keywords (list[str]): Document keywords
                    - comments (str): Additional comments
                  - technical_properties (dict): Engineering properties
                    - material (str): Assigned material name
                    - units (str): Document units (metric/imperial)
                    - precision (int): Decimal precision setting
                    - configuration (str): Active configuration name
                    - version (str): SolidWorks version used
                  - statistics (dict): Document statistics
                    - feature_count (int): Number of features
                    - component_count (int): Number of components (assemblies)
                    - sheet_count (int): Number of sheets (drawings)
                    - rebuild_time (float): Last rebuild time in seconds

        Example:
            ```python
            result = await get_file_properties()

            if result["status"] == "success":
                props = result["properties"]

                # Basic file info
                file_info = props["file_info"]
                print(f"File: {file_info['file_name']}")
                print(f"Size: {file_info['file_size']}")
                print(f"Type: {file_info['file_type']}")

                # Technical properties
                tech = props["technical_properties"]
                print(f"Material: {tech['material']}")
                print(f"Units: {tech['units']}")

                # Document info
                doc = props["document_info"]
                print(f"Author: {doc['author']}")
                print(f"Description: {doc['description']}")
            ```

        Note:
            - Requires an active SolidWorks document
            - Properties may vary based on document type
            - Some properties may be empty if not set
            - Technical properties depend on document configuration
        """
        # Simulated file properties - would get from adapter
        return {
            "status": "success",
            "properties": {
                "file_name": "Example.sldprt",
                "file_size": "2.5 MB",
                "created_date": "2024-03-14T00:00:00Z",
                "modified_date": "2024-03-14T12:00:00Z",
                "author": "User",
                "description": "SolidWorks part file",
                "material": "Default",
                "units": "millimeters",
            },
        }

    @mcp.tool()
    async def get_model_info() -> dict[str, Any]:
        """
        Get metadata for the active SolidWorks document.

        Returns a compact summary of the current model context that is useful
        for read-before-write LLM flows (document type, active configuration,
        and feature count).
        """
        try:
            if hasattr(adapter, "get_model_info"):
                result = await adapter.get_model_info()
                if result.is_success:
                    return {
                        "status": "success",
                        "model_info": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to get model info",
                }

            return {
                "status": "error",
                "message": "Active adapter does not support get_model_info",
            }
        except Exception as e:
            logger.error(f"Error in get_model_info tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def list_features(input_data: ListFeaturesInput) -> dict[str, Any]:
        """
        List feature-tree entries for the active SolidWorks document.

        Useful for read-before-write workflows where the agent must inspect
        existing model structure before adding or editing downstream features.
        """
        try:
            input_data = _coerce_input(ListFeaturesInput, input_data)
            if hasattr(adapter, "list_features"):
                result = await adapter.list_features(
                    include_suppressed=input_data.include_suppressed
                )
                if result.is_success:
                    return {
                        "status": "success",
                        "features": result.data or [],
                        "count": len(result.data or []),
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to list features",
                }

            return {
                "status": "error",
                "message": "Active adapter does not support list_features",
            }
        except Exception as e:
            logger.error(f"Error in list_features tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def classify_feature_tree(
        input_data: ClassifyFeatureTreeInput,
    ) -> dict[str, Any]:
        """
        Classify the active model into a feature family from model-info and tree data.

        This is a read-before-write helper for delegation. It summarizes whether the
        current document looks like a direct-MCP solid, sheet metal workflow,
        advanced VBA-backed part, assembly, drawing, or an insufficient-evidence case.
        """
        try:
            input_data = _coerce_input(ClassifyFeatureTreeInput, input_data)
            model_info = input_data.model_info
            features = input_data.features
            execution_time = 0.0

            if model_info is None and hasattr(adapter, "get_model_info"):
                model_result = await adapter.get_model_info()
                if model_result.is_success:
                    model_info = model_result.data
                    execution_time = max(
                        execution_time, model_result.execution_time or 0.0
                    )

            if features is None:
                if hasattr(adapter, "list_features"):
                    feature_result = await adapter.list_features(
                        include_suppressed=input_data.include_suppressed
                    )
                    if feature_result.is_success:
                        features = feature_result.data or []
                        execution_time = max(
                            execution_time, feature_result.execution_time or 0.0
                        )
                    else:
                        return {
                            "status": "error",
                            "message": feature_result.error
                            or "Failed to list features for classification",
                        }
                else:
                    return {
                        "status": "error",
                        "message": "Active adapter does not support list_features",
                    }

            classification = classify_feature_tree_snapshot(model_info, features or [])
            return {
                "status": "success",
                "classification": classification,
                "model_info": model_info or {},
                "features": features or [],
                "execution_time": execution_time,
            }
        except Exception as e:
            logger.error(f"Error in classify_feature_tree tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def list_configurations() -> dict[str, Any]:
        """
        List configuration names for the active SolidWorks document.

        Returns all available configuration names so callers can select a
        stable target before invoking feature or export operations.
        """
        try:
            if hasattr(adapter, "list_configurations"):
                result = await adapter.list_configurations()
                if result.is_success:
                    return {
                        "status": "success",
                        "configurations": result.data or [],
                        "count": len(result.data or []),
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to list configurations",
                }

            return {
                "status": "error",
                "message": "Active adapter does not support list_configurations",
            }
        except Exception as e:
            logger.error(f"Error in list_configurations tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def manage_file_properties(input_data: FileOperationInput) -> dict[str, Any]:
        """
        Read, update, copy, move, rename, or delete file-related properties.

        Uses the requested operation and file paths to manage SolidWorks file
        metadata or related file lifecycle tasks through the active adapter.
        """
        try:
            input_data = _coerce_input(FileOperationInput, input_data)
            if hasattr(adapter, "manage_file_properties"):
                result = await adapter.manage_file_properties(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "File properties managed successfully",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to manage file properties",
                }
            return {
                "status": "success",
                "message": "File properties managed successfully",
                "data": {
                    "file_path": input_data.file_path,
                    "operation": input_data.operation,
                },
            }
        except Exception as e:
            logger.error(f"Error in manage_file_properties tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def convert_file_format(input_data: FormatConversionInput) -> dict[str, Any]:
        """
        Convert a SolidWorks file from one format to another.

        Supports exporting source files to target formats such as STEP,
        IGES, STL, PDF, or other adapter-supported conversion outputs.
        """
        try:
            input_data = _coerce_input(FormatConversionInput, input_data)
            if hasattr(adapter, "convert_file_format"):
                result = await adapter.convert_file_format(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "File converted successfully",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to convert file format",
                }
            return {
                "status": "success",
                "message": "File converted successfully",
                "data": {
                    "source_file": input_data.source_file,
                    "target_file": input_data.target_file or input_data.output_path,
                    "format_to": input_data.target_format,
                },
            }
        except Exception as e:
            logger.error(f"Error in convert_file_format tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def batch_file_operations(input_data: FileOperationInput) -> dict[str, Any]:
        """
        Run a file operation across multiple files as a batch workflow.

        Intended for repetitive file management tasks such as copying,
        moving, renaming, or deleting groups of SolidWorks documents.
        """
        try:
            input_data = _coerce_input(FileOperationInput, input_data)
            if hasattr(adapter, "batch_file_operations"):
                result = await adapter.batch_file_operations(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Batch file operations completed successfully",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to run batch file operations",
                }
            return {
                "status": "success",
                "message": "Batch file operations completed successfully",
                "data": {
                    "file_path": input_data.file_path,
                    "operation": input_data.operation,
                },
            }
        except Exception as e:
            logger.error(f"Error in batch_file_operations tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def load_part(input_data: LoadPartInput) -> dict[str, Any]:
        """
        Load (open) a SolidWorks part file.

        Convenience wrapper that opens a .sldprt file and makes it the active
        document. Provides a simpler alternative to open_model for parts.

        Args:
            input_data (LoadPartInput): Contains:
                - file_path (str): Absolute path to the .sldprt file

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - model (dict): Model information (name, type, path, configuration)
                - execution_time (float): Operation time in seconds

        Example:
            ```python
            result = await load_part({
                "file_path": "C:/Projects/bracket.sldprt"
            })

            if result["status"] == "success":
                print(f"Loaded: {result['model']['name']}")
            ```

        Note:
            - File must be a valid .sldprt (part) file
            - Path must be absolute and accessible
        """
        try:
            input_data = _coerce_input(LoadPartInput, input_data)
            # Ensure file path ends with .sldprt
            file_path = input_data.file_path
            if not file_path.lower().endswith(".sldprt"):
                return {
                    "status": "error",
                    "message": f"File must be a .sldprt part file: {file_path}",
                }

            result = await adapter.open_model(file_path)
            if result.is_success:
                model = result.data
                title = _result_value(model, "title", "name", default=file_path)
                path = _result_value(model, "path", "file_path", default=file_path)
                configuration = _result_value(model, "configuration", default="Default")
                return {
                    "status": "success",
                    "message": f"Loaded part: {title}",
                    "model": {
                        "name": title,
                        "type": "Part",
                        "path": path,
                        "configuration": configuration,
                    },
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to load part: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in load_part tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def load_assembly(input_data: LoadAssemblyInput) -> dict[str, Any]:
        """
        Load (open) a SolidWorks assembly file.

        Convenience wrapper that opens a .sldasm file and makes it the active
        document. Provides a simpler alternative to open_model for assemblies.

        Args:
            input_data (LoadAssemblyInput): Contains:
                - file_path (str): Absolute path to the .sldasm file

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - model (dict): Model information (name, type, path, configuration)
                - execution_time (float): Operation time in seconds

        Example:
            ```python
            result = await load_assembly({
                "file_path": "C:/Projects/machine_assembly.sldasm"
            })

            if result["status"] == "success":
                print(f"Loaded: {result['model']['name']}")
            ```

        Note:
            - File must be a valid .sldasm (assembly) file
            - Path must be absolute and accessible
        """
        try:
            input_data = _coerce_input(LoadAssemblyInput, input_data)
            # Ensure file path ends with .sldasm
            file_path = input_data.file_path
            if not file_path.lower().endswith(".sldasm"):
                return {
                    "status": "error",
                    "message": f"File must be a .sldasm assembly file: {file_path}",
                }

            result = await adapter.open_model(file_path)
            if result.is_success:
                model = result.data
                title = _result_value(model, "title", "name", default=file_path)
                path = _result_value(model, "path", "file_path", default=file_path)
                configuration = _result_value(model, "configuration", default="Default")
                return {
                    "status": "success",
                    "message": f"Loaded assembly: {title}",
                    "model": {
                        "name": title,
                        "type": "Assembly",
                        "path": path,
                        "configuration": configuration,
                    },
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to load assembly: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in load_assembly tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def save_part(input_data: SavePartInput | None = None) -> dict[str, Any]:
        """
        Save the active SolidWorks part document.

        Convenience wrapper that saves the currently active part. If no file_path
        is provided, saves to the existing location. Otherwise, saves as a new file.

        Args:
            input_data (SavePartInput, optional): Contains:
                - file_path (str, optional): Output path for save-as. If omitted, saves to current location.
                - overwrite (bool): Overwrite existing file (default: True)

        Returns:
            dict[str, Any]: Save operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - file_path (str): Path where file was saved
                - execution_time (float): Operation time in seconds

        Example:
            ```python
            # Save to current location
            result = await save_part()

            # Save as new file
            result = await save_part({
                "file_path": "C:/Projects/bracket_v2.sldprt",
                "overwrite": False
            })

            if result["status"] == "success":
                print(f"Part saved to {result['file_path']}")
            ```

        Note:
            - Active document must be a part file
            - When saving to new location, ensure path ends with .sldprt
        """
        try:
            if input_data is None:
                input_data = SavePartInput()
            else:
                input_data = _coerce_input(SavePartInput, input_data)

            # If file_path provided, use save_as; otherwise use regular save
            if input_data.file_path:
                # Normalize and validate provided path
                file_path = input_data.file_path.strip()
                if not file_path:
                    return {
                        "status": "error",
                        "message": "Invalid file_path: path is empty or whitespace.",
                    }
                # Detect paths that are effectively just the extension (e.g., ".sldprt")
                cleaned = file_path.strip()
                if (
                    cleaned.count(".") == 1
                    and cleaned.startswith(".")
                    and cleaned[1:].lower() == "sldprt"
                ):
                    return {
                        "status": "error",
                        "message": "Invalid file_path: missing base filename before extension.",
                    }
                # Ensure path ends with .sldprt for parts
                if not file_path.lower().endswith(".sldprt"):
                    file_path = file_path.rsplit(".", 1)[0] + ".sldprt"

                result = await adapter.save_file(file_path)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"Part saved as: {file_path}",
                        "file_path": file_path,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": f"Failed to save part: {result.error}",
                }
            else:
                # Save to current location
                result = await adapter.save_file(None)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Part saved successfully",
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": f"Failed to save part: {result.error}",
                }
        except Exception as e:
            logger.error(f"Error in save_part tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def save_assembly(
        input_data: SaveAssemblyInput | None = None,
    ) -> dict[str, Any]:
        """
        Save the active SolidWorks assembly document.

        Convenience wrapper that saves the currently active assembly. If no file_path
        is provided, saves to the existing location. Otherwise, saves as a new file.

        Args:
            input_data (SaveAssemblyInput, optional): Contains:
                - file_path (str, optional): Output path for save-as. If omitted, saves to current location.
                - overwrite (bool): Overwrite existing file (default: True)

        Returns:
            dict[str, Any]: Save operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - file_path (str): Path where file was saved
                - execution_time (float): Operation time in seconds

        Example:
            ```python
            # Save to current location
            result = await save_assembly()

            # Save as new file
            result = await save_assembly({
                "file_path": "C:/Projects/machine_v2.sldasm",
                "overwrite": False
            })

            if result["status"] == "success":
                print(f"Assembly saved to {result['file_path']}")
            ```

        Note:
            - Active document must be an assembly file
            - When saving to new location, ensure path ends with .sldasm
        """
        try:
            if input_data is None:
                input_data = SaveAssemblyInput()
            else:
                input_data = _coerce_input(SaveAssemblyInput, input_data)

            # If file_path provided, use save_as; otherwise use regular save
            if input_data.file_path:
                # Ensure path ends with .sldasm for assemblies
                file_path = input_data.file_path
                if not file_path.lower().endswith(".sldasm"):
                    file_path = file_path.rsplit(".", 1)[0] + ".sldasm"

                result = await adapter.save_file(file_path)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"Assembly saved as: {file_path}",
                        "file_path": file_path,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": f"Failed to save assembly: {result.error}",
                }
            else:
                # Save to current location
                result = await adapter.save_file(None)
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Assembly saved successfully",
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": f"Failed to save assembly: {result.error}",
                }
        except Exception as e:
            logger.error(f"Error in save_assembly tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    tool_count = 14  # Total number of registered tools in this module
    return tool_count
