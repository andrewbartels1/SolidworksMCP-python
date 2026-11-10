"""Shared input model compatibility helpers for tool schemas.

This module centralizes test/backward-compat parsing behavior so individual tool modules
stay focused on domain fields.
"""

from pydantic import BaseModel, ConfigDict


class CompatInput(BaseModel):
    """Base schema allowing legacy/extra fields used by existing tests.

    Attributes:
        model_config (Any): The model config value.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


_DRAWING_PACKAGE = "use `generate_drawing_package` for a complete drawing"
_FILE_EXTENSION = "the file extension sets the format and its options"
_ACTIVE_MODEL = "it measures the active model; open and activate the one you want"

#: Inputs a tool used to advertise but never applied, by input model name.
#: Each maps to what to use instead. A call that still sends one is refused
#: (``removed_inputs``) rather than silently ignored.
REMOVED_INPUTS: dict[str, dict[str, str]] = {
    "CreateExtrusionInput": {"direction": "use `end_condition`"},
    "CreateRevolveInput": {"direction": "use `both_directions`"},
    "CreateAssemblyInput": {
        "components": "call `insert_component` for each part",
    },
    "CreateDrawingInput": {
        "model_path": "place views with `create_drawing_view`, or " + _DRAWING_PACKAGE,
        "sheet_format": _DRAWING_PACKAGE,
    },
    "DrawingCreationInput": {
        "template": _DRAWING_PACKAGE,
        "sheet_size": _DRAWING_PACKAGE,
        "sheet_format": _DRAWING_PACKAGE,
        "title": _DRAWING_PACKAGE,
        "output_path": "save the drawing with `save_file`",
        "scale": "set it afterwards with `set_sheet_scale`",
        "auto_populate_views": "the tool always places the three standard views",
    },
    "SaveFileInput": {"force_save": "the tool always saves"},
    "ExportFileInput": {"options": _FILE_EXTENSION},
    "InterferenceCheckInput": {
        "tolerance": "the check has no tolerance",
        "check_all_components": "it checks the whole assembly, or `components`",
    },
    "MacroPlaybackInput": {
        "parameters": "the macro takes no arguments; have it read a file you write",
        "execution_parameters": "the macro takes no arguments; have it read a file",
        "target_file": "open the document first with `open_model`",
        "execution_mode": "the macro runs in the running SolidWorks session",
        "pause_on_error": "it stops at the first run that fails",
        "log_execution": "the reply reports every run",
    },
    "MassPropertiesInput": {
        "model_path": _ACTIVE_MODEL,
        "units": "volumes are mm³, masses kg and inertia kg·mm²",
        "include_hidden": _ACTIVE_MODEL,
        "reference_coordinate_system": "it reports about the centre of mass",
    },
}


def removed_inputs(model: BaseModel) -> list[str]:
    """The removed inputs ``model`` was given, each with what to use instead.

    Args:
        model: A validated tool input.

    Returns:
        list[str]: One sentence per removed field present, e.g.
        "`components` is no longer an input: call `insert_component` for each
        part". Empty when none was sent.
    """
    removed = REMOVED_INPUTS.get(type(model).__name__, {})
    extras = model.model_extra or {}
    return [
        f"`{field}` is no longer an input: {pointer}"
        for field, pointer in removed.items()
        if field in extras
    ]
