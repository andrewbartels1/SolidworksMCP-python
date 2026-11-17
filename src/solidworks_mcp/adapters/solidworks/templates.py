"""Save the active document as a template (queue item 21).

``IModelDocExtension.SaveAs`` writes a ``.prtdot``, ``.asmdot`` or
``.drwdot``. SolidWorks then has the template open in place of the
document, as File > Save As does: seen live on SolidWorks 2026 for a part
never saved and for a saved one, and ``swSaveAsOptions_Copy`` doesn't
change it. The template folders are SolidWorks'
``swFileLocationsDocumentTemplates`` preference, the folders File > New
shows.
"""

from __future__ import annotations

import ntpath
import os
from typing import Any, cast

from .. import sw_type_info as _sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .features import _null_callout
from .io import _byref_int, _doc_type

#: The template extension for each document type (1 part, 2 assembly,
#: 3 drawing).
TEMPLATE_EXTENSIONS: dict[int, str] = {1: ".prtdot", 2: ".asmdot", 3: ".drwdot"}
#: The document type's name, for replies.
DOCUMENT_TYPES: dict[int, str] = {1: "part", 2: "assembly", 3: "drawing"}
#: ``swUserPreferenceStringValue_e.swFileLocationsDocumentTemplates``.
_SW_PREF_TEMPLATE_FOLDERS = 6
#: ``swSaveAsOptions_Silent``.
_SAVE_AS_SILENT = 1
#: ``swSaveAsCurrentVersion``.
_SAVE_AS_CURRENT_VERSION = 0


def split_folders(text: Any) -> list[str]:
    """The folders in a ``;``-separated SolidWorks location preference.

    Args:
        text: The preference's value; anything not a string means none.

    Returns:
        list[str]: The folders, in order, blanks dropped.
    """
    if not isinstance(text, str):
        return []
    return [folder.strip() for folder in text.split(";") if folder.strip()]


def in_folders(path: str, folders: list[str]) -> bool:
    """Whether ``path`` sits directly in one of ``folders``.

    Compared as Windows paths (case and separators ignored), on any OS.

    Args:
        path: A file path.
        folders: Folder paths.

    Returns:
        bool: True when the file's folder is one of them.
    """
    parent = ntpath.normcase(ntpath.normpath(ntpath.dirname(path)))
    return any(ntpath.normcase(ntpath.normpath(folder)) == parent for folder in folders)


def _error(message: str) -> AdapterResult[dict[str, Any]]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


class SolidWorksTemplatesMixin:
    """``get_template_folders`` and ``save_as_template`` for the real adapter."""

    def _template_folders(self) -> list[str]:
        """SolidWorks' document template folders, in its order.

        Returns:
            list[str]: The folders; empty when the preference can't be read.
        """
        adapter = cast("Any", self)
        app = getattr(adapter, "swApp", None)
        if app is None:
            return []
        return split_folders(
            adapter._attempt(
                lambda: app.GetUserPreferenceStringValue(_SW_PREF_TEMPLATE_FOLDERS),
                default="",
            )
        )

    async def get_template_folders(self) -> AdapterResult[dict[str, Any]]:
        """The template folders, and the active document's template extension.

        Returns:
            AdapterResult[dict[str, Any]]: ``folders``, and ``document_type``
            and ``extension`` (both ``None`` with no document open).
        """
        adapter = cast("Any", self)
        kind = _doc_type(adapter) if adapter.currentModel is not None else None
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "folders": self._template_folders(),
                "document_type": DOCUMENT_TYPES.get(kind or 0),
                "extension": TEMPLATE_EXTENSIONS.get(kind or 0),
            },
        )

    async def save_as_template(self, file_path: str) -> AdapterResult[dict[str, Any]]:
        """Save the active document as a template at ``file_path``.

        SolidWorks then has the template open in place of the document (see
        the module docstring); the document's file, if it had one, is left
        as last saved. The title and path are read before and after, so the
        reply says what is open now.

        Args:
            file_path: The template's full path, with the document's template
                extension.

        Returns:
            AdapterResult[dict[str, Any]]: ``file_path``, ``document_type``,
            ``in_template_folder``, ``template_folders``, ``document_path``
            (the open document's path before the save, ``None`` if never
            saved) and ``document_became_template``.
        """
        adapter = cast("Any", self)
        if adapter.currentModel is None:
            return _error("No active model")
        kind = _doc_type(adapter) or 0
        extension = TEMPLATE_EXTENSIONS.get(kind)
        if extension is None:
            return _error("save_as_template needs an active part, assembly or drawing")
        if not file_path.lower().endswith(extension):
            return _error(
                f"{DOCUMENT_TYPES[kind].capitalize()} templates are {extension}; "
                f"{file_path!r} isn't one."
            )

        def _read(model: Any, name: str) -> str:
            """A string member of the document; empty when unreadable."""
            value = adapter._attempt(
                lambda: adapter._get_attr_or_call(model, name), default=""
            )
            return str(value or "")

        def _identity(model: Any) -> tuple[str, str]:
            """The document's path and title."""
            return _read(model, "GetPathName"), _read(model, "GetTitle")

        def _save() -> dict[str, Any]:
            model = adapter.currentModel
            before = _identity(model)
            ext = _sw_type_info.flagged(model.Extension, "IModelDocExtension")
            errors, warnings = _byref_int(), _byref_int()
            ok = ext.SaveAs(
                file_path,
                _SAVE_AS_CURRENT_VERSION,
                _SAVE_AS_SILENT,
                _null_callout(),
                errors,
                warnings,
            )
            if not ok or not os.path.isfile(file_path):
                raise RuntimeError(
                    f"SolidWorks didn't write the template {file_path!r} "
                    f"(SaveAs returned {ok!r}, error code "
                    f"{getattr(errors, 'value', errors)!r})."
                )
            folders = self._template_folders()
            return {
                "file_path": file_path,
                "document_type": DOCUMENT_TYPES[kind],
                "in_template_folder": in_folders(file_path, folders),
                "template_folders": folders,
                "document_path": before[0] or None,
                "document_became_template": _identity(model) != before,
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            adapter._handle_com_operation("save_as_template", _save),
        )
