"""The mock adapter's templates: saved in memory, carried into new documents.

A template records the document's units, material and custom properties,
which is what a real template carries; ``create_part`` with that template
starts the new part with them, as SolidWorks' ``NewDocument`` does.
"""

from __future__ import annotations

from typing import Any

from .base import AdapterResult, AdapterResultStatus
from .solidworks.templates import TEMPLATE_EXTENSIONS, in_folders

#: The mock's document types by the numbers the real adapter uses.
_MOCK_TYPES: dict[str, int] = {"Part": 1, "Assembly": 2, "Drawing": 3}


class MockTemplatesMixin:
    """``get_template_folders`` and ``save_as_template`` for the mock."""

    _current_model: Any
    #: Template folders, as SolidWorks' File Locations would list them; none
    #: by default, so a template saved by name is refused unless a test sets
    #: one.
    _mock_template_folders: tuple[str, ...] = ()

    def _mock_templates(self) -> dict[str, dict[str, Any]]:
        """The templates saved so far, by path."""
        if "_templates" not in self.__dict__:
            self._templates: dict[str, dict[str, Any]] = {}
        return self._templates

    async def get_template_folders(self) -> AdapterResult[dict[str, Any]]:
        """The mock's template folders and the active document's extension.

        Returns:
            AdapterResult[dict[str, Any]]: ``folders``, ``document_type`` and
            ``extension`` (both ``None`` with no document).
        """
        model = self._current_model
        kind = _MOCK_TYPES.get(getattr(model, "type", ""), 0)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "folders": list(self._mock_template_folders),
                "document_type": str(model.type).lower() if kind else None,
                "extension": TEMPLATE_EXTENSIONS.get(kind),
            },
        )

    async def save_as_template(self, file_path: str) -> AdapterResult[dict[str, Any]]:
        """Record the active document's settings as a template at ``file_path``.

        Args:
            file_path: The template's path, with the document's extension.

        Returns:
            AdapterResult[dict[str, Any]]: The same shape as the real adapter's.
        """
        model = self._current_model
        if model is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        extension = TEMPLATE_EXTENSIONS[_MOCK_TYPES[model.type]]
        if not file_path.lower().endswith(extension):
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"{model.type} templates are {extension}; "
                f"{file_path!r} isn't one.",
            )
        key = str(model.path)
        adapter: Any = self
        self._mock_templates()[file_path] = {
            "units": (model.properties or {}).get("units"),
            "material": getattr(adapter, "_materials", {}).get(key),
            "properties": dict(
                getattr(adapter, "_custom_properties", {}).get((key, ""), {})
            ),
        }
        # As in SolidWorks, the template is now the open document: its state
        # moves to the template's path.
        for store, old, new in (
            ("_materials", key, file_path),
            ("_custom_properties", (key, ""), (file_path, "")),
            ("_models", key, file_path),
        ):
            held = adapter.__dict__.get(store, {})
            if old in held:
                held[new] = held.pop(old)
        model.path = file_path
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "file_path": file_path,
                "document_type": model.type.lower(),
                "in_template_folder": in_folders(
                    file_path, list(self._mock_template_folders)
                ),
                "template_folders": list(self._mock_template_folders),
                # Mock documents are never on disk.
                "document_path": None,
                "document_became_template": True,
            },
        )

    def _mock_apply_template(self, model: Any, template: str | None) -> None:
        """Start ``model`` with a saved template's units, material and properties.

        Args:
            model: The new mock document.
            template: The template path ``create_part`` was given, if any.
        """
        saved = self._mock_templates().get(template or "")
        if saved is None:
            return
        adapter: Any = self
        if saved["units"]:
            model.properties["units"] = saved["units"]
        # A template only holds a material or properties when the document it
        # was saved from had them, so the adapter's stores already exist.
        if saved["material"]:
            adapter._materials[str(model.path)] = saved["material"]
        if saved["properties"]:
            adapter._custom_properties[(str(model.path), "")] = dict(
                saved["properties"]
            )
