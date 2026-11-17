"""Save the active document as a template (queue item 21).

``IModelDoc2.SaveAs3`` with ``swSaveAsOptions_Copy`` writes a ``.prtdot``,
``.asmdot`` or ``.drwdot`` and leaves the open document on its own path.
The template folders are SolidWorks' ``swFileLocationsDocumentTemplates``
preference, the folders File > New shows.
"""

from __future__ import annotations

import ntpath
import os
from typing import Any, cast

from ..base import AdapterResult, AdapterResultStatus
from .io import _doc_type

#: The template extension for each document type (1 part, 2 assembly,
#: 3 drawing).
TEMPLATE_EXTENSIONS: dict[int, str] = {1: ".prtdot", 2: ".asmdot", 3: ".drwdot"}
#: The document type's name, for replies.
DOCUMENT_TYPES: dict[int, str] = {1: "part", 2: "assembly", 3: "drawing"}
#: ``swUserPreferenceStringValue_e.swFileLocationsDocumentTemplates``.
_SW_PREF_TEMPLATE_FOLDERS = 6
#: ``swSaveAsOptions_Silent | swSaveAsOptions_Copy``.
_SAVE_AS_SILENT_COPY = 1 | 2
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
        """Save a copy of the active document as a template at ``file_path``.

        The open document keeps its own path: ``SaveAs3`` runs with the copy
        option, and the path is read before and after to prove it.

        Args:
            file_path: The template's full path, with the document's template
                extension.

        Returns:
            AdapterResult[dict[str, Any]]: ``file_path``, ``document_type``,
            ``in_template_folder``, ``template_folders`` and
            ``document_path`` (the open document's own path, unchanged).
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

        def _save() -> dict[str, Any]:
            model = adapter.currentModel
            before = adapter._attempt(
                lambda: adapter._get_attr_or_call(model, "GetPathName"), default=""
            )
            code = model.SaveAs3(
                file_path, _SAVE_AS_CURRENT_VERSION, _SAVE_AS_SILENT_COPY
            )
            if code not in (0, True) or not os.path.isfile(file_path):
                raise RuntimeError(
                    f"SolidWorks didn't write the template {file_path!r} "
                    f"(SaveAs3 returned {code!r})."
                )
            after = adapter._attempt(
                lambda: adapter._get_attr_or_call(model, "GetPathName"), default=""
            )
            if (before or "") != (after or ""):
                raise RuntimeError(
                    f"The template was written, but the open document is now "
                    f"{after!r} instead of {before!r}; reopen the original."
                )
            folders = self._template_folders()
            return {
                "file_path": file_path,
                "document_type": DOCUMENT_TYPES[kind],
                "in_template_folder": in_folders(file_path, folders),
                "template_folders": folders,
                "document_path": before or None,
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            adapter._handle_com_operation("save_as_template", _save),
        )
