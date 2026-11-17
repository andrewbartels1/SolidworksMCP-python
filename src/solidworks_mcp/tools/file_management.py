"""File management tools for SolidWorks MCP Server.

Provides tools for managing SolidWorks files including save, save as, file properties,
and reference management.
"""

import os
import shutil
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from ..utils.feature_tree_classifier import (
    build_component_tree,
    classify_feature_tree_snapshot,
)
from ..utils.sw_dependencies import dependency_paths
from .input_compat import CompatInput
from .tool_boundary import (
    InvalidInputError,
    ToolOperationError,
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

# Input schemas using Python 3.14 built-in types


class SaveFileInput(CompatInput):
    """Input schema for saving a file.

    Attributes:
        file_path (str | None): A new path to save to; None saves in place.
        overwrite (bool): Whether a file already at ``file_path`` may be replaced.
    """

    file_path: str | None = Field(
        default=None,
        description=(
            "Optional new path, ending in the active document's extension "
            "(.sldprt, .sldasm or .slddrw). If omitted, saves the active document "
            "to its own path."
        ),
    )
    overwrite: bool = Field(
        default=False,
        description="Replace a file already at file_path. Off by default.",
    )


#: The file extension each document type saves to.
_DOC_EXTENSIONS = {"Part": ".sldprt", "Assembly": ".sldasm", "Drawing": ".slddrw"}

#: Characters Windows doesn't allow in a file name.
_RESERVED_NAME_CHARACTERS = frozenset('\\/:*?"<>|')


class SaveAsTemplateInput(CompatInput):
    """Input schema for saving the active document as a template.

    Attributes:
        file_path (str | None): The template's full path.
        name (str | None): A file name for SolidWorks' template folder.
        overwrite (bool): Whether an existing template may be replaced.
    """

    file_path: str | None = Field(
        default=None,
        description="The template's full path, ending in .prtdot (part), .asmdot "
        "(assembly) or .drwdot (drawing). Give this or `name`",
    )
    name: str | None = Field(
        default=None,
        description="A name, e.g. 'Bracket MMGS': saved with the right extension "
        "in SolidWorks' first template folder, so it shows in File > New. Give "
        "this or `file_path`",
    )
    overwrite: bool = Field(
        default=False, description="Replace a template already there. Off by default."
    )

    def model_post_init(self, __context: Any) -> None:
        """Exactly one of ``file_path`` and ``name``; a name is a plain file name.

        Raises:
            ValueError: When both or neither are given, or the name has a path
                separator or a character Windows doesn't allow.
        """
        if (self.file_path is None) == (self.name is None):
            raise ValueError("give either file_path or name, not both or neither")
        if self.name is not None:
            self.name = self.name.strip()
            bad = sorted(set(self.name) & _RESERVED_NAME_CHARACTERS)
            if not self.name or bad:
                raise ValueError(
                    "name is a file name with no folder and none of "
                    f"{' '.join(sorted(_RESERVED_NAME_CHARACTERS))} (got {self.name!r})"
                )


def file_details(raw_path: str) -> dict[str, Any]:
    """The size and times of the file at ``raw_path``, read from the disk.

    Args:
        raw_path: The document's path; empty for a document never saved.

    Returns:
        dict[str, Any]: ``size_bytes``, ``created`` and ``modified`` (Unix
        timestamps); each None when no file is there.
    """
    path = Path(raw_path) if raw_path else None
    if path is None or not path.is_file():
        return {"size_bytes": None, "created": None, "modified": None}
    stat = path.stat()
    return {
        "size_bytes": stat.st_size,
        "created": stat.st_ctime,
        "modified": stat.st_mtime,
    }


class SaveAsInput(CompatInput):
    """Input schema for save as operation.

    Attributes:
        file_path (str): The file path value.
        format_type (str): The format type value.
        overwrite (bool): The overwrite value.
    """

    file_path: str = Field(description="Full path for the new file")
    format_type: str = Field(
        default="solidworks", description="File format (solidworks, step, iges, etc.)"
    )
    overwrite: bool = Field(default=False, description="Overwrite existing file")


class LoadPartInput(CompatInput):
    """Input schema for loading a part file.

    Attributes:
        file_path (str): The file path value.
    """

    file_path: str = Field(description="Full path to the .sldprt file")


class LoadAssemblyInput(CompatInput):
    """Input schema for loading an assembly file.

    Attributes:
        file_path (str): The file path value.
    """

    file_path: str = Field(description="Full path to the .sldasm file")


class SavePartInput(CompatInput):
    """Input schema for saving a part file.

    Attributes:
        file_path (str | None): The file path value.
        overwrite (bool): The overwrite value.
    """

    file_path: str | None = Field(
        default=None,
        description="Optional output path. If omitted, saves the active part to its existing location.",
    )
    overwrite: bool = Field(default=False, description="Overwrite existing file")


class SaveAssemblyInput(CompatInput):
    """Input schema for saving an assembly file.

    Attributes:
        file_path (str | None): The file path value.
        overwrite (bool): The overwrite value.
    """

    file_path: str | None = Field(
        default=None,
        description="Optional output path. If omitted, saves the active assembly to its existing location.",
    )
    overwrite: bool = Field(default=False, description="Overwrite existing file")
    include_references: bool = Field(
        default=False,
        description="When true and file_path is set, copy referenced assembly files into the target folder.",
    )


class PackAndGoInput(CompatInput):
    """Input schema for Pack-and-Go assembly copy.

    Attributes:
        source_path (str): Path to the source assembly file.
        target_dir (str): Destination directory for the self-contained copy.
        export_preview (bool): Whether to export an isometric PNG preview.
        overwrite (bool): Whether to overwrite files already in target_dir.
    """

    source_path: str = Field(description="Absolute path to the source .sldasm file")
    target_dir: str = Field(
        description="Directory where the assembly and all referenced parts will be copied"
    )
    export_preview: bool = Field(
        default=False,
        description="Export an isometric PNG preview next to the copied files",
    )
    overwrite: bool = Field(
        default=False,
        description=(
            "Pack into a target_dir that already holds files, replacing the ones "
            "Pack and Go writes; other files there are kept"
        ),
    )


class ListFeaturesInput(CompatInput):
    """Input schema for feature tree listing.

    Attributes:
        include_suppressed (bool): The include suppressed value.
        max_assembly_depth (int): Sub-assembly recursion depth for Assembly
            documents.
    """

    include_suppressed: bool = Field(
        default=False,
        description="Include suppressed features in the returned list",
    )
    max_assembly_depth: int = Field(
        default=2,
        description=(
            "For Assembly documents, how many levels of sub-assembly to "
            "recurse into when flattening component features. Ignored for "
            "Part documents."
        ),
    )


class ClassifyFeatureTreeInput(CompatInput):
    """Input schema for feature-family classification.

    Attributes:
        features (list[dict[str, Any]] | None): The features value.
        include_suppressed (bool): The include suppressed value.
        model_info (dict[str, Any] | None): The model info value.
    """

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


class ActivateDocumentInput(CompatInput):
    """Input schema for activating an already-open document.

    Attributes:
        title_or_path (str): Window title, full path, or file name of a
            document that is already open in SolidWorks.
    """

    title_or_path: str = Field(
        description=(
            "Window title (e.g. 'bracket.SLDPRT'), full path, or bare file "
            "name of a document that is already open"
        )
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.title_or_path.strip():
            raise ValueError("title_or_path is required")


class SaveBodyAsPartInput(CompatInput):
    """Input schema for extracting a solid body to its own part file.

    Attributes:
        body_name (str): Name of a solid body in the active multibody part.
        file_path (str): Absolute path for the new ``.sldprt``.
    """

    body_name: str = Field(
        description="Name of a solid body in the active part, e.g. 'Boss-Extrude1'"
    )
    file_path: str = Field(
        description="Absolute path for the new .sldprt (parent directory must exist)"
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.body_name.strip():
            raise ValueError("body_name is required")
        if not self.file_path.strip():
            raise ValueError("file_path is required")


class CreateConfigurationInput(CompatInput):
    """Input schema for adding a configuration.

    Attributes:
        name (str): The new configuration's name.
        parent (str | None): A configuration to derive it from.
        description (str): Its description.
        activate (bool): Leave it active.
    """

    name: str = Field(description="The new configuration's name, e.g. 'Long'")
    parent: str | None = Field(
        default=None, description="A configuration to derive it from (a child)"
    )
    description: str = Field(default="", description="Its description")
    activate: bool = Field(
        default=False,
        description="Leave it active; otherwise the current one stays active",
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.name.strip():
            raise ValueError("name is required")


class ConfigurationNameInput(CompatInput):
    """Input schema naming one configuration.

    Attributes:
        name (str): The configuration's name.
    """

    name: str = Field(description="The configuration's name, e.g. 'Default'")

    def model_post_init(self, __context: Any) -> None:
        if not self.name.strip():
            raise ValueError("name is required")


async def register_file_management_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register file management tools with FastMCP.

    Registers essential file operations for SolidWorks document management including save
    operations, file format conversions, and file property access. These tools provide
    fundamental document lifecycle management capabilities.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (dict[str, Any]): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

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
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    def _coerce_input(model_cls: Any, payload: Any) -> Any:
        """Accept legacy dict payloads from compatibility wrapper as well as model instances.

        Args:
            model_cls (Any): The model cls value.
            payload (Any): The payload value.

        Returns:
            Any: The result produced by the operation.
        """
        return (
            payload
            if isinstance(payload, model_cls)
            else model_cls.model_validate(payload)
        )

    def _result_value(payload: Any, *keys: str, default: Any = None) -> Any:
        """Read a value from adapter result payloads that may be dicts or model objects.

        Args:
            payload (Any): The payload value.
            *keys (str): Additional positional arguments forwarded to the call.
            default (Any): Fallback value returned when the operation fails. Defaults to None.

        Returns:
            Any: The result produced by the operation.
        """
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

    def _prepare_save_target(
        raw_path: str,
        *,
        required_extension: str,
        overwrite: bool,
        refuse_wrong_extension: bool = False,
    ) -> str:
        """Normalize and validate a save target before adapter/COM calls.

        Enforces pre-save guardrails used by save convenience tools so invalid paths are
        rejected consistently in both mock and real adapter modes. The helper performs:
        path trimming, extension normalization, parent-directory existence check,
        directory writability check, and overwrite policy enforcement.

        Args:
            raw_path (str): User-supplied path where the file should be saved.
            required_extension (str): Required extension for the target document type
                (for example, ``.sldprt`` or ``.sldasm``).
            overwrite (bool): Whether saving is allowed to replace an existing file.
            refuse_wrong_extension (bool): Refuse a path with another extension
                instead of changing it to ``required_extension``.

        Returns:
            str: The normalized save path.

        Raises:
            InvalidInputError: When the path is empty, has the wrong extension, its
                directory is missing or not writable, or it exists and overwrite is
                False.

        Example:
            ```python
            target = _prepare_save_target(
                r"C:/Exports/bracket.step",
                required_extension=".sldprt",
                overwrite=False,
            )

            # target == "C:/Exports/bracket.sldprt" when valid; raises
            # InvalidInputError when the directory is missing/not writable,
            # or when the target exists and overwrite is False.
            ```

        Note:
            Validation is intentionally executed before adapter calls to avoid opaque COM
            failures and to provide deterministic, user-friendly error messages.
        """
        file_path = raw_path.strip()
        if not file_path:
            raise InvalidInputError("Invalid file_path: path is empty or whitespace.")

        cleaned = file_path.strip()
        extension_name = required_extension.lstrip(".")
        if (
            cleaned.count(".") == 1
            and cleaned.startswith(".")
            and cleaned[1:].lower() == extension_name
        ):
            # Reject extension-only input such as ".sldprt".
            raise InvalidInputError(
                "Invalid file_path: missing base filename before extension."
            )

        target = Path(file_path)
        if target.suffix.lower() != required_extension.lower():
            if refuse_wrong_extension:
                raise InvalidInputError(
                    f"file_path must end in {required_extension} for the active "
                    f"document; got {target.name!r}. Nothing was saved."
                )
            # Normalize extension so save_part/save_assembly always use their canonical type.
            target = target.with_suffix(required_extension)

        target_dir = target.parent
        if not target_dir.exists():
            raise InvalidInputError(f"Target directory does not exist: {target_dir}")

        if not target_dir.is_dir():
            raise InvalidInputError(
                f"Target parent path is not a directory: {target_dir}"
            )

        if not os.access(target_dir, os.W_OK):
            raise InvalidInputError(f"Target directory is not writable: {target_dir}")

        if target.exists() and target.is_dir():
            raise InvalidInputError(
                f"Target path is a directory, expected file path: {target}"
            )

        if target.exists() and not overwrite:
            raise InvalidInputError(
                f"File already exists and overwrite=False: {target}. Set overwrite=True to replace it."
            )

        return str(target)

    async def _checked_new_path(raw_path: str, *, overwrite: bool) -> str:
        """Check a new save path against the active document's type.

        Args:
            raw_path: The path the caller gave.
            overwrite: Whether a file already there may be replaced.

        Returns:
            str: The path to save to.

        Raises:
            ToolOperationError: If the active document's type can't be read.
            InvalidInputError: If the path fails a check (see
                ``_prepare_save_target``).
        """
        info = await adapter.get_model_info()
        doc_type = (
            info.data.get("type")
            if info.is_success and isinstance(info.data, dict)
            else None
        )
        extension = _DOC_EXTENSIONS.get(str(doc_type))
        if extension is None:
            raise ToolOperationError(
                "Could not tell the active document's type "
                f"({info.error or doc_type!r}), so file_path was not checked and "
                "nothing was saved."
            )
        return _prepare_save_target(
            raw_path,
            required_extension=extension,
            overwrite=overwrite,
            refuse_wrong_extension=True,
        )

    def _get_attr_or_call(obj: Any, name: str, default: Any = None) -> Any:
        """Read COM values that may be exposed as either properties or methods."""
        candidate = getattr(obj, name, None)
        if candidate is None:
            return default
        if callable(candidate):
            try:
                value = candidate()
            except Exception:
                return default
            return default if value is None else value
        return candidate

    def _copy_with_collision_handling(source_path: Path, target_dir: Path) -> Path:
        """Copy a source file into target_dir, suffixing when name collisions occur."""
        destination = target_dir / source_path.name
        try:
            same_target = destination.exists() and source_path.resolve(
                strict=False
            ) == destination.resolve(strict=False)
        except Exception:
            same_target = False
        if same_target:
            return destination

        if not destination.exists():
            shutil.copy2(source_path, destination)
            return destination

        stem = source_path.stem
        suffix = source_path.suffix
        index = 1
        while True:
            candidate = target_dir / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                shutil.copy2(source_path, candidate)
                return candidate
            index += 1

    def _copy_active_assembly_with_references(
        target_assembly_path: str,
    ) -> dict[str, Any]:
        """Copy active assembly and resolved dependencies into target folder."""
        current_model = getattr(adapter, "currentModel", None)
        if current_model is None:
            raise ToolOperationError("No active model available to copy references.")

        source_assembly_raw = _get_attr_or_call(current_model, "GetPathName")
        source_assembly = (
            Path(str(source_assembly_raw)) if source_assembly_raw else None
        )
        if source_assembly is None or not source_assembly.exists():
            raise ToolOperationError(
                "Active assembly must be saved before include_references=True can copy dependencies."
            )

        target_assembly = Path(target_assembly_path)
        target_dir = target_assembly.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        dependency_callable = getattr(current_model, "GetDependencies2", None)
        if not callable(dependency_callable):
            raise ToolOperationError(
                "Adapter does not expose GetDependencies2; cannot copy assembly references in this mode."
            )

        try:
            raw_dependencies = dependency_callable(True, True, False)
        except Exception as exc:
            raise ToolOperationError(
                f"Failed to enumerate assembly dependencies: {exc}"
            ) from exc

        unique_sources: list[Path] = [source_assembly]
        for dep in dependency_paths(raw_dependencies):
            if dep not in unique_sources:
                unique_sources.append(dep)

        copied_files: list[str] = []
        missing_sources: list[str] = []

        for source in unique_sources:
            if not source.exists():
                missing_sources.append(str(source))
                continue

            if source.resolve(strict=False) == source_assembly.resolve(strict=False):
                shutil.copy2(source, target_assembly)
                copied_files.append(str(target_assembly))
            else:
                copied_target = _copy_with_collision_handling(source, target_dir)
                copied_files.append(str(copied_target))

        copied_files = sorted(copied_files)
        return {
            "status": "success",
            "message": f"Assembly and references copied to: {target_dir}",
            "file_path": str(target_assembly),
            "copied_file_count": len(copied_files),
            "copied_files": copied_files,
            "missing_source_files": missing_sources,
            "copy_method": "tool_dependency_copy",
        }

    @mcp.tool()
    async def save_file(input_data: SaveFileInput) -> dict[str, Any]:
        """Save the active part, assembly or drawing, to its own path or to a new path in its own format.

        Use it after changes you want to keep. A new `file_path` is checked before
        SolidWorks is asked: its folder must exist and be writable, it must end in
        the document's extension (.sldprt, .sldasm, .slddrw), and a file already there
        is kept unless `overwrite` is on. To write another format, use `save_as` or an
        `export_*` tool; to copy an assembly with its parts, `pack_and_go_assembly`.
        Needs: an open, active document, already saved once unless you give a path.
        Changes: writes the file. Returns: `file_path` (when given) and `data` from
        the save.

        Args:
            input_data: The save. Nothing is required: give `file_path` to save to a
                new path, or omit it to save in place; `overwrite` is off.

        Returns:
            dict[str, Any]: The save result.
        """
        input_data = _coerce_input(SaveFileInput, input_data)
        require_capability(
            adapter,
            "save_file",
            "Active adapter does not support save_file; the file was not saved.",
        )
        target = input_data.file_path
        if target is not None:
            target = await _checked_new_path(target, overwrite=input_data.overwrite)
        result = await adapter.save_file(target)
        require_success(result, "Failed to save file")
        return {
            "status": "success",
            "message": "File saved successfully",
            **({"file_path": target} if target is not None else {}),
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def save_as(input_data: SaveAsInput) -> dict[str, Any]:
        """Save the active document under a new path, as a SolidWorks file or in an exchange format such as STEP or IGES.

        For a SolidWorks format (solidworks, sldprt, sldasm, slddrw) it saves a copy
        like File > Save As; any other `format_type` is passed to the exporter. For one
        known format with its options, prefer `export_step`, `export_stl` and the other
        `export_*` tools. Needs: an open, active document. Changes: writes the file. A
        file already at `file_path` is kept and the call refused, unless `overwrite`
        is on. Returns: `file_path` and `format`.

        Args:
            input_data: The target. `file_path` is required; `format_type` defaults
                to "solidworks", and `overwrite` is off.

        Returns:
            dict[str, Any]: The path written.
        """
        input_data = _coerce_input(SaveAsInput, input_data)
        if Path(input_data.file_path).exists() and not input_data.overwrite:
            raise InvalidInputError(
                f"A file already exists at {input_data.file_path}; it was left "
                "untouched. Pass overwrite: true to replace it, or choose another path."
            )
        if hasattr(adapter, "save_file") and input_data.format_type.lower() in {
            "solidworks",
            "sldprt",
            "sldasm",
            "slddrw",
        }:
            result = await adapter.save_file(input_data.file_path)
            require_success(result, "Failed to save file")
            return {
                "status": "success",
                "message": f"File saved as: {input_data.file_path}",
                "file_path": input_data.file_path,
                "format": input_data.format_type,
                "execution_time": result.execution_time,
            }

        require_capability(
            adapter,
            "export_file",
            "Active adapter does not support save_file or export_file; "
            f"no file was saved as {input_data.file_path}.",
        )
        result = await adapter.export_file(
            input_data.file_path,
            input_data.format_type,
        )
        require_success(result, "Failed to export file")
        return {
            "status": "success",
            "message": f"File exported as: {input_data.file_path}",
            "file_path": input_data.file_path,
            "format": input_data.format_type,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def save_as_template(input_data: SaveAsTemplateInput) -> dict[str, Any]:
        """Save the active part, assembly or drawing as a template, so new documents start from it.

        Use it after setting up a document once (units with `set_units`, a material,
        custom properties) to start the next one the same way: pass the template to
        `create_part`, `create_assembly` or `create_drawing` as `template`. A part
        saves as .prtdot, an assembly as .asmdot, a drawing as .drwdot. Give
        `file_path`, or `name` to save in SolidWorks' first template folder so it also
        shows in File > New. Afterwards SolidWorks has the template open in place of
        the document, as File > Save As does (a saved document's file is left as last
        saved); the reply's `warning` says so. Save from a part with no features when only its settings should carry
        over. The path is checked before SolidWorks is asked: the extension must
        match, the folder must exist, and a file already there is kept unless
        `overwrite` is on. Needs: an open, active document. Changes: writes the
        template. Returns: `data` with `file_path`, `document_type`,
        `in_template_folder`, `template_folders` and `document_became_template`.

        Args:
            input_data: `file_path` or `name` (one is required); `overwrite` is off.

        Returns:
            dict[str, Any]: The template written.
        """
        input_data = _coerce_input(SaveAsTemplateInput, input_data)
        require_capability(
            adapter,
            "save_as_template",
            "Active adapter does not support save_as_template; nothing was saved.",
        )
        found = await adapter.get_template_folders()
        require_success(found, "Failed to read SolidWorks' template folders")
        extension = (found.data or {}).get("extension")
        if extension is None:
            raise ToolOperationError(
                "No active model: open or create the document to save as a template."
            )
        raw = input_data.file_path
        if input_data.name is not None:
            folders = (found.data or {}).get("folders") or []
            if not folders:
                raise InvalidInputError(
                    "SolidWorks lists no document template folder (Options > File "
                    "Locations > Document Templates); give file_path instead."
                )
            stem = input_data.name
            if stem.lower().endswith(extension):
                stem = stem[: -len(extension)]
            raw = os.path.join(folders[0], stem + extension)
        target = _prepare_save_target(
            str(raw),
            required_extension=extension,
            overwrite=input_data.overwrite,
            refuse_wrong_extension=True,
        )
        result = await adapter.save_as_template(target)
        require_success(result, "Failed to save the template")
        data = result.data or {}
        reply: dict[str, Any] = {
            "status": "success",
            "message": f"Saved the {data.get('document_type', 'document')} template "
            f"{target}; start a new one from it with template: {target!r}",
            "file_path": target,
            "data": data,
            "execution_time": result.execution_time,
        }
        if data.get("document_became_template"):
            original = data.get("document_path")
            kept = (
                f"{original} is unchanged on disk, as last saved."
                if original
                else "The document had never been saved, so it now exists only "
                "as this template."
            )
            reply["warning"] = (
                f"SolidWorks now has the template {target} open in place of the "
                f"document, as File > Save As does, so save_file would change the "
                f"template. {kept} Start the next part with create_part and this "
                "template."
            )
        return reply

    @mcp.tool()
    async def get_file_properties() -> dict[str, Any]:
        """Report the active document's file details: name, path, size, dates, type, configuration and unsaved changes.

        Use it to check what is open and whether it has unsaved changes before saving or
        closing. For the model itself (rebuild status included), use `get_model_info`;
        for custom properties, use `get_custom_properties`. Needs: an open, active
        document. Read-only. Returns: `properties` with `file_name`, `file_path`,
        `file_size_bytes`, `created_date` and `modified_date` (Unix timestamps; empty
        for a document never saved), `document_type`, `configuration`, `is_dirty` and
        `feature_count`.
        """
        require_capability(
            adapter, "get_model_info", "Active adapter does not support model metadata"
        )

        result = await adapter.get_model_info()
        if not result.is_success or not isinstance(result.data, dict):
            raise ToolOperationError(result.error or "No active SolidWorks document")

        model_info = dict(result.data)
        raw_path = str(model_info.get("path") or "")
        file_path = Path(raw_path) if raw_path else None
        properties: dict[str, Any] = {
            "file_name": (
                file_path.name
                if file_path is not None
                else str(model_info.get("title") or "")
            ),
            "file_path": raw_path,
            "file_size_bytes": None,
            "created_date": None,
            "modified_date": None,
            "document_type": model_info.get("type"),
            "configuration": model_info.get("configuration"),
            "is_dirty": model_info.get("is_dirty"),
            "feature_count": model_info.get("feature_count"),
        }

        details = file_details(raw_path)
        properties.update(
            {
                "file_size_bytes": details["size_bytes"],
                "created_date": details["created"],
                "modified_date": details["modified"],
            }
        )

        return {
            "status": "success",
            "properties": properties,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def get_model_info() -> dict[str, Any]:
        """Report the active document's title, path, type, configuration, unsaved changes, feature count, rebuild status and file details.

        Use it first in a session, to see which document is active (it follows a switch
        made in the SolidWorks window). For every open document, use
        `list_open_documents`; for custom properties, `get_custom_properties`. Needs: an
        open document. Read-only. Returns: `model_info` with `title`, `path`, `type`,
        `configuration`, `is_dirty`, `feature_count`, `rebuild_status` (0 rebuilt, 1
        needs a rebuild), and the file's `size_bytes`, `created` and `modified` (Unix
        timestamps; null for a document never saved).
        """
        require_capability(
            adapter, "get_model_info", "Active adapter does not support get_model_info"
        )
        result = await adapter.get_model_info()
        require_success(result, "Failed to get model info")
        info = dict(result.data or {})
        info.update(file_details(str(info.get("path") or "")))
        return {
            "status": "success",
            "model_info": info,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def list_features(input_data: ListFeaturesInput) -> dict[str, Any]:
        """List the feature tree of the active part or assembly, in order.

        Use it before editing a model, to find a feature's exact name for
        `delete_feature`, `suppress_feature` or `rename_feature`. For an assembly it
        also lists each component's features, down to `max_assembly_depth` levels.
        Needs: an open part or assembly. Read-only. Returns: `features` (each with
        `name`, `type`, `suppressed` and, in an assembly, `component`), `count`, and
        `assembly_tree`, the same list grouped by component.

        Args:
            input_data: What to list. Nothing is required: `include_suppressed`
                (off) and `max_assembly_depth` (2) have defaults.

        Returns:
            dict[str, Any]: The feature list.
        """
        input_data = _coerce_input(ListFeaturesInput, input_data)
        require_capability(
            adapter, "list_features", "Active adapter does not support list_features"
        )
        result = await adapter.list_features(
            include_suppressed=input_data.include_suppressed,
            max_assembly_depth=input_data.max_assembly_depth,
        )
        require_success(result, "Failed to list features")
        return {
            "status": "success",
            "features": result.data or [],
            "count": len(result.data or []),
            # Additive, derived view of the same flat "features"
            # list above - grouped by component/sub-component
            # for callers that want the assembly structure
            # rather than a flat tag-and-scan. Does not change
            # the meaning of "features"/"count".
            "assembly_tree": build_component_tree(result.data),
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def get_selected_entities() -> dict[str, Any]:
        """Describe the faces, edges and vertices selected in the SolidWorks window right now.

        Use it when the user has clicked something and says "this face": it reads the
        selection instead of guessing from a screenshot. To select edges yourself, use
        `select_face_edges`. Needs: an open document. Read-only. Returns: `entities`
        (each with `index` and `type`; a face adds `bounding_box_mm`, `center_mm`,
        `area_mm2` and `normal` when flat, an edge `start_mm`, `end_mm` and
        straight-line `length_mm`, a vertex `point_mm`) and `count`.
        """
        require_capability(
            adapter,
            "get_selected_entities",
            "Active adapter does not support get_selected_entities",
        )
        result = await adapter.get_selected_entities()
        require_success(result, "Failed to get selected entities")
        return {
            "status": "success",
            "entities": result.data or [],
            "count": len(result.data or []),
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def classify_feature_tree(
        input_data: ClassifyFeatureTreeInput,
    ) -> dict[str, Any]:
        """Classify the active model's kind (part, sheet metal, assembly, drawing and so on) from its feature tree, and suggest how to work on it.

        Use it before rebuilding or editing an unfamiliar model, to pick a workflow. It
        reads the model unless you pass `model_info` and `features` you already have
        (from `get_model_info` and `list_features`). Needs: an open document, unless
        both are passed. Read-only. Returns: `classification` with `family`,
        `recommended_workflow`, `confidence`, `needs_vba`, `evidence`, `warnings`,
        `next_actions` and `feature_count`, plus the `model_info` and `features` used.

        Args:
            input_data: What to classify. Nothing is required: pass `model_info`
                and `features` to classify them without reading the model;
                `include_suppressed` is off by default.

        Returns:
            dict[str, Any]: The classification.
        """
        input_data = _coerce_input(ClassifyFeatureTreeInput, input_data)
        model_info = input_data.model_info
        features = input_data.features
        execution_time = 0.0

        # Reading the model can fail (nothing open); classifying an empty
        # model instead would give a confident wrong answer.
        if model_info is None:
            require_capability(
                adapter,
                "get_model_info",
                "Active adapter does not support get_model_info",
            )
            model_result = await adapter.get_model_info()
            require_success(
                model_result, context="Failed to read the model to classify"
            )
            model_info = model_result.data
            execution_time = max(execution_time, model_result.execution_time or 0.0)

        if features is None:
            require_capability(
                adapter,
                "list_features",
                "Active adapter does not support list_features",
            )
            feature_result = await adapter.list_features(
                include_suppressed=input_data.include_suppressed
            )
            require_success(
                feature_result, context="Failed to list features to classify"
            )
            features = feature_result.data or []
            execution_time = max(execution_time, feature_result.execution_time or 0.0)

        classification = classify_feature_tree_snapshot(model_info, features or [])  # type: ignore[arg-type]
        return {
            "status": "success",
            "classification": classification,
            "model_info": model_info or {},
            "features": features or [],
            "execution_time": execution_time,
        }

    @mcp.tool()
    async def list_configurations() -> dict[str, Any]:
        """List the names of the active model's configurations, and which one is active.

        Use it to see which configurations a part or assembly has before
        `activate_configuration` or `delete_configuration`. Needs: an open part or
        assembly. Read-only. Returns: `configurations` (names), `count` and
        `active` (null when it can't be read).
        """
        require_capability(
            adapter,
            "list_configurations",
            "Active adapter does not support list_configurations",
        )
        result = await adapter.list_configurations()
        require_success(result, "Failed to list configurations")
        active: str | None = None
        if callable(getattr(adapter, "active_configuration", None)):
            read = await adapter.active_configuration()
            active = read.data if read.is_success else None
        return {
            "status": "success",
            "configurations": result.data or [],
            "count": len(result.data or []),
            "active": active,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def load_part(input_data: LoadPartInput) -> dict[str, Any]:
        """Open a part (.sldprt) from disk and make it the active document.

        Use it to start work on an existing part; for any document type, use
        `open_model`, and to switch to a document that is already open, use
        `activate_document`. A path that isn't a .sldprt is refused. Needs: the file on
        disk. Changes: opens the part (no file is written). Returns: `model` with
        `name`, `type`, `path` and `configuration` (the one SolidWorks opened, or
        null when it can't be read).

        Args:
            input_data: The part. `file_path` (a .sldprt) is required.

        Returns:
            dict[str, Any]: The opened part.
        """
        input_data = _coerce_input(LoadPartInput, input_data)
        # Ensure file path ends with .sldprt
        file_path = input_data.file_path
        if not file_path.lower().endswith(".sldprt"):
            raise InvalidInputError(f"File must be a .sldprt part file: {file_path}")

        result = await adapter.open_model(file_path)
        require_success(result, context="Failed to load part")
        model = result.data
        title = _result_value(model, "title", "name", default=file_path)
        path = _result_value(model, "path", "file_path", default=file_path)
        configuration = _result_value(model, "configuration")
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

    @mcp.tool()
    async def load_assembly(input_data: LoadAssemblyInput) -> dict[str, Any]:
        """Open an assembly (.sldasm) from disk and make it the active document.

        Use it to start work on an existing assembly; for any document type, use
        `open_model`, and to switch to a document that is already open, use
        `activate_document`. A path that isn't a .sldasm is refused. Needs: the file on
        disk. Changes: opens the assembly (no file is written). Returns: `model` with
        `name`, `type`, `path` and `configuration` (the one SolidWorks opened, or
        null when it can't be read).

        Args:
            input_data: The assembly. `file_path` (a .sldasm) is required.

        Returns:
            dict[str, Any]: The opened assembly.
        """
        input_data = _coerce_input(LoadAssemblyInput, input_data)
        # Ensure file path ends with .sldasm
        file_path = input_data.file_path
        if not file_path.lower().endswith(".sldasm"):
            raise InvalidInputError(
                f"File must be a .sldasm assembly file: {file_path}"
            )

        result = await adapter.open_model(file_path)
        require_success(result, context="Failed to load assembly")
        model = result.data
        title = _result_value(model, "title", "name", default=file_path)
        path = _result_value(model, "path", "file_path", default=file_path)
        configuration = _result_value(model, "configuration")
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

    @mcp.tool()
    async def save_part(input_data: SavePartInput | None = None) -> dict[str, Any]:
        """Save the active part in place, or as a new .sldprt with the target path checked first.

        Before writing to a new path it checks the folder exists and is writable,
        changes the extension to .sldprt, and refuses an existing file unless
        `overwrite` is on. For other formats, use `save_as` or an `export_*` tool. Needs: an open, active part. Changes: writes
        the part file. Returns: `file_path` when saved to a new path.

        Args:
            input_data: The save. Nothing is required: give `file_path` for a new
                path or omit it to save in place; `overwrite` is off.

        Returns:
            dict[str, Any]: The save result.
        """
        if input_data is None:
            input_data = SavePartInput()
        else:
            input_data = _coerce_input(SavePartInput, input_data)

        # If file_path provided, use save_as; otherwise use regular save
        if input_data.file_path:
            file_path = _prepare_save_target(
                input_data.file_path,
                required_extension=".sldprt",
                overwrite=input_data.overwrite,
            )

            result = await adapter.save_file(file_path)
            require_success(result, context="Failed to save part")
            return {
                "status": "success",
                "message": f"Part saved as: {file_path}",
                "file_path": file_path,
                "execution_time": result.execution_time,
            }
        else:
            # Save to current location
            result = await adapter.save_file(None)
            require_success(result, context="Failed to save part")
            return {
                "status": "success",
                "message": "Part saved successfully",
                "execution_time": result.execution_time,
            }

    @mcp.tool()
    async def save_assembly(
        input_data: SaveAssemblyInput | None = None,
    ) -> dict[str, Any]:
        """Save the active assembly in place, or as a new .sldasm, optionally copying the parts it uses alongside.

        Before writing to a new path it checks the folder exists and is writable,
        changes the extension to .sldasm, and refuses an existing file unless
        `overwrite` is on. With `include_references`, it instead copies the assembly
        file as last saved, and the files it references, into the new folder; unsaved
        changes are left out and references are not updated. To copy an assembly with
        its referenced parts, use `pack_and_go_assembly`. Needs: an open, active assembly, saved once for
        `include_references`. Changes: writes the assembly file (and copies). Returns:
        `file_path`, plus `copied_files` and `missing_source_files` when copying
        references.

        Args:
            input_data: The save. Nothing is required: give `file_path` for a new
                path or omit it to save in place; `overwrite` and
                `include_references` are off.

        Returns:
            dict[str, Any]: The save result.
        """
        if input_data is None:
            input_data = SaveAssemblyInput()
        else:
            input_data = _coerce_input(SaveAssemblyInput, input_data)

        # If file_path provided, use save_as; otherwise use regular save
        if input_data.file_path:
            file_path = _prepare_save_target(
                input_data.file_path,
                required_extension=".sldasm",
                overwrite=input_data.overwrite,
            )

            if input_data.include_references:
                return _copy_active_assembly_with_references(file_path)

            result = await adapter.save_file(file_path)
            require_success(result, context="Failed to save assembly")
            return {
                "status": "success",
                "message": f"Assembly saved as: {file_path}",
                "file_path": file_path,
                "execution_time": result.execution_time,
            }
        else:
            # Save to current location
            result = await adapter.save_file(None)
            require_success(result, context="Failed to save assembly")
            return {
                "status": "success",
                "message": "Assembly saved successfully",
                "execution_time": result.execution_time,
            }

    @mcp.tool()
    async def pack_and_go_assembly(input_data: PackAndGoInput) -> dict[str, Any]:
        """Copy an assembly and every file it uses into one folder that opens on its own.

        Use it to hand over or archive an assembly. SolidWorks lists the files the
        assembly uses; each is copied under its own name, as saved on disk, so save
        first: a `warning` names any open file whose unsaved changes the copy doesn't
        have. The copy opens with its own parts, since SolidWorks looks in the
        assembly's folder first. It fails, copying nothing, when a file is missing,
        two files share a name, or `target_dir` holds the originals. It refuses a
        folder that already has files unless `overwrite` is on, and then replaces only
        the files it copies. It never closes or changes a document. It can add an
        isometric PNG preview. Needs: the .sldasm on disk. Changes: writes the copies
        into `target_dir`, creating it if needed. Returns: `source_assembly`,
        `target_dir`, `copied_files`, `source_files`, `unsaved_changes` and, with a
        preview, `preview_image`.

        Args:
            input_data: The copy. `source_path` (a .sldasm) and `target_dir` are
                required; `export_preview` and `overwrite` are off.

        Returns:
            dict[str, Any]: The files copied.
        """
        input_data = _coerce_input(PackAndGoInput, input_data)

        from pathlib import Path as _Path

        source = _Path(input_data.source_path)
        out_dir = _Path(input_data.target_dir)

        if not source.exists():
            raise ToolOperationError(f"Source assembly not found: {source}")

        if not source.suffix.lower() == ".sldasm":
            raise InvalidInputError(
                f"source_path must be a .sldasm file, got: {source.suffix}"
            )

        if not input_data.overwrite and out_dir.exists() and any(out_dir.iterdir()):
            raise InvalidInputError(
                f"target_dir already contains files: {out_dir}. "
                "Set overwrite=True to replace them."
            )

        result = await adapter.pack_and_go_assembly(  # type: ignore[attr-defined]
            source_path=str(source),
            target_dir=str(out_dir),
        )

        require_success(result)

        report: dict[str, Any] = {
            "status": "success",
            "method": "dependency_copy",
            "execution_time": result.execution_time,
            **result.data,
        }
        warnings: list[str] = []
        unsaved = result.data.get("unsaved_changes") or []
        if unsaved:
            warnings.append(
                f"{', '.join(unsaved)} had unsaved changes, which are not in the "
                "copy; save, then pack again to include them."
            )

        if input_data.export_preview:
            preview_path = out_dir / "assembly_preview.png"
            img_result = await adapter.export_image(
                {
                    "file_path": str(preview_path),
                    "format_type": "png",
                    "width": 1600,
                    "height": 1000,
                    "view_orientation": "isometric",
                }
            )
            report["preview_image"] = (
                str(preview_path) if img_result.is_success else None
            )
            if not img_result.is_success:
                warnings.append(
                    f"The copy is complete, but the preview couldn't be written: "
                    f"{img_result.error}"
                )

        if warnings:
            report["warning"] = " ".join(warnings)
        return report

    @mcp.tool()
    async def list_open_documents() -> dict[str, Any]:
        """List every document open in SolidWorks and say which one is active.

        Use it before `activate_document`, or when tool calls seem to act on the wrong
        document. Needs: SolidWorks running. Read-only. Returns: `documents` (each with
        `title`, `path`, `type` and `is_active`) and `count`.
        """
        result = await adapter.list_open_documents()
        require_success(result, context="Failed to list open documents")
        docs = result.data if isinstance(result.data, list) else []
        active = next((d.get("title") for d in docs if d.get("is_active")), None)
        return {
            "status": "success",
            "message": (
                f"{len(docs)} document(s) open"
                + (f"; active: {active}" if active else "")
            ),
            "documents": docs,
            "count": len(docs),
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def activate_document(
        input_data: ActivateDocumentInput,
    ) -> dict[str, Any]:
        """Make an already-open document the active one, so the next tools act on it.

        Match it by window title, full path or file name (not case-sensitive); see
        `list_open_documents`. To open a file that isn't open yet, use `open_model`.
        Needs: the document open in SolidWorks. Changes: the active document. Returns:
        `data` with `activated` (the title) and `verified` (read back from SolidWorks;
        null when it couldn't be read). No match is an error that lists the open
        documents.

        Args:
            input_data: The document. `title_or_path` is required.

        Returns:
            dict[str, Any]: The activated document.
        """
        input_data = _coerce_input(ActivateDocumentInput, input_data)
        result = await adapter.activate_document(input_data.title_or_path)
        require_success(result, context="Failed to activate document")
        data = result.data if isinstance(result.data, dict) else {}
        activated = data.get("activated", input_data.title_or_path)
        message = f"Activated {activated}"
        if data.get("verified") is None:
            message += " (could not be read back to confirm)"
        return {
            "status": "success",
            "message": message,
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def save_body_as_part(
        input_data: SaveBodyAsPartInput,
    ) -> dict[str, Any]:
        """Save one solid body of the active multibody part as a new part file (Insert > Features > Save Bodies).

        Use it to split a multibody part into parts, e.g. after `create_extrusion`
        without merging. Needs: an open, active part with the named body and an existing
        target folder. Changes: adds a Save Bodies feature to the part and writes the
        new .sldprt. Returns: `data` with `body`, `file_path`, `feature` and
        `solid_bodies` (every body name, to correct a wrong one).

        Args:
            input_data: The body. `body_name` and `file_path` (a .sldprt) are
                required.

        Returns:
            dict[str, Any]: The file written.
        """
        require_capability(
            adapter,
            "save_body_as_part",
            "Active adapter does not support save_body_as_part; no file was written.",
        )
        input_data = _coerce_input(SaveBodyAsPartInput, input_data)
        result = await adapter.save_body_as_part(
            input_data.body_name, input_data.file_path
        )
        require_success(result, context="Failed to save body as part")
        data = result.data if isinstance(result.data, dict) else {}
        return {
            "status": "success",
            "message": (
                f"Saved body {input_data.body_name} to "
                f"{data.get('file_path', input_data.file_path)}"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_configuration(
        input_data: CreateConfigurationInput,
    ) -> dict[str, Any]:
        """Add a configuration to the active part or assembly, e.g. a long and a short version of one part.

        A configuration holds its own dimension values and suppressed features;
        give `parent` to derive it from another. The configuration that was active
        stays active unless `activate` is on. Needs: an open part or assembly.
        Changes: adds a configuration. Returns: `configuration` with `name`,
        `parent`, `active` and every name in `configurations`.

        Args:
            input_data: The configuration. `name` is required; `parent`,
                `description` and `activate` are optional.

        Returns:
            dict[str, Any]: The configuration added.
        """
        input_data = normalize_input(input_data, CreateConfigurationInput)
        require_capability(
            adapter, "create_configuration", "Active adapter can't add configurations"
        )
        result = await adapter.create_configuration(
            input_data.name,
            input_data.parent,
            input_data.description,
            input_data.activate,
        )
        require_success(result, "Failed to create configuration")
        return {
            "status": "success",
            "message": f"Added configuration {input_data.name}",
            "configuration": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def activate_configuration(
        input_data: ConfigurationNameInput,
    ) -> dict[str, Any]:
        """Make a configuration of the active model the active one, and rebuild.

        Dimensions and suppression then read and change in that configuration.
        Needs: an open part or assembly with that configuration. Changes: the
        active configuration. Returns: `active` and `previous`.

        Args:
            input_data: `name`, the configuration to show.

        Returns:
            dict[str, Any]: The active configuration.
        """
        input_data = normalize_input(input_data, ConfigurationNameInput)
        require_capability(
            adapter,
            "activate_configuration",
            "Active adapter can't switch configurations",
        )
        result = await adapter.activate_configuration(input_data.name)
        require_success(result, "Failed to activate configuration")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Activated configuration {input_data.name}",
            "active": data.get("active"),
            "previous": data.get("previous"),
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def delete_configuration(
        input_data: ConfigurationNameInput,
    ) -> dict[str, Any]:
        """Delete a configuration of the active model; not the active one or the only one.

        Activate another configuration first to delete the active one. Needs: an
        open part or assembly with that configuration. Changes: removes it.
        Returns: `deleted` and the `configurations` left.

        Args:
            input_data: `name`, the configuration to delete.

        Returns:
            dict[str, Any]: What was deleted.
        """
        input_data = normalize_input(input_data, ConfigurationNameInput)
        require_capability(
            adapter,
            "delete_configuration",
            "Active adapter can't delete configurations",
        )
        result = await adapter.delete_configuration(input_data.name)
        require_success(result, "Failed to delete configuration")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Deleted configuration {input_data.name}",
            "deleted": data.get("deleted"),
            "configurations": data.get("configurations", []),
            "execution_time": result.execution_time,
        }

    tool_count = 20  # Total number of registered tools in this module
    return tool_count
