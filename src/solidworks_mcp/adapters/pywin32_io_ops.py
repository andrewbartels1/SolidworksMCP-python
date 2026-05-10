"""DEPRECATED: This module has been refactored into mixin classes.

All functionality previously provided by this module has been moved to:
- SolidWorksIOMixin in solidworks/io.py

This file is retained for reference only and is no longer used by PyWin32Adapter.

Migration complete as of current refactoring effort.
"""


def open_model(adapter: Any, file_path: str) -> SolidWorksModel:
    """Open a SolidWorks model file and set it as active on the adapter.

    Args:
        adapter: Connected ``PyWin32Adapter`` instance.
        file_path: Path to a ``.sldprt``, ``.sldasm``, or ``.slddrw`` file.

    Returns:
        SolidWorksModel: Model metadata for the opened document.

    Raises:
        ValueError: If the extension is unsupported.
        Exception: If SolidWorks fails to open the requested document.
    """
    resolved_path = os.path.abspath(file_path)
    file_path_lower = resolved_path.lower()
    if file_path_lower.endswith(".sldprt"):
        doc_type = adapter.constants["swDocPART"]
        model_type = "Part"
    elif file_path_lower.endswith(".sldasm"):
        doc_type = adapter.constants["swDocASSEMBLY"]
        model_type = "Assembly"
    elif file_path_lower.endswith(".slddrw"):
        doc_type = adapter.constants["swDocDRAWING"]
        model_type = "Drawing"
    else:
        raise ValueError(f"Unsupported file type: {resolved_path}")

    app = adapter.swApp
    errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    model = app.OpenDoc6(resolved_path, doc_type, 1, "", errors, warnings)
    if not model:
        raise Exception(f"Failed to open model: {resolved_path}")

    adapter.currentModel = model
    title = read_model_title(adapter, model)
    active_config = adapter._attempt(lambda: model.GetActiveConfiguration())
    config = (
        adapter._attempt(lambda: active_config.GetName(), default="Default")
        if active_config
        else "Default"
    )

    return SolidWorksModel(
        path=resolved_path,
        name=title,
        type=model_type,
        is_active=True,
        configuration=config,
        properties={
            "last_modified": (
                model.GetSaveTime()
                if callable(getattr(model, "GetSaveTime", None))
                else None
            ),
        },
    )


def close_model(adapter: Any, save: bool = False) -> None:
    """Close the current SolidWorks model and optionally save first.

    Args:
        adapter: Connected ``PyWin32Adapter`` instance.
        save: When ``True``, calls ``Save`` before closing.
    """
    model = adapter.currentModel
    app = adapter.swApp
    if save:
        model.Save()
    app.CloseDoc(model.GetTitle())
    adapter.currentModel = None


def resolve_template_path(
    adapter: Any, preferred_indices: list[int], extension: str
) -> str | None:
    """Resolve a template path from SolidWorks user preference slots.

    Args:
        adapter: Connected ``PyWin32Adapter`` instance.
        preferred_indices: Preference indices to probe in order.
        extension: Expected template extension such as ``.prtdot``.

    Returns:
        str | None: First existing template match, otherwise first non-empty
        path candidate, or ``None`` if nothing is configured.
    """
    existing_match: str | None = None
    first_non_empty: str | None = None
    app = adapter.swApp
    if app is None:
        return None

    for index in preferred_indices:
        template = adapter._attempt(
            lambda idx=index: app.GetUserPreferenceStringValue(idx)
        )
        if not template or not isinstance(template, str):
            continue
        if first_non_empty is None:
            first_non_empty = template
        if template.lower().endswith(extension.lower()) and os.path.exists(template):
            existing_match = template
            break

    return existing_match or first_non_empty


def read_model_title(adapter: Any, model: Any) -> str:
    """Read a model title regardless of COM exposing method or property.

    Args:
        adapter: ``PyWin32Adapter`` instance used for safe COM access helpers.
        model: SolidWorks model COM object.

    Returns:
        str: Best-effort model title, defaulting to ``"Untitled"``.
    """
    title = adapter._attempt(lambda: adapter._get_attr_or_call(model, "GetTitle"))
    if isinstance(title, str) and title:
        return title

    title_value = getattr(model, "Title", None)
    if isinstance(title_value, str) and title_value:
        return title_value

    return "Untitled"


def create_part(
    adapter: Any, name: str | None = None, units: str | None = None
) -> SolidWorksModel:
    """Create a new part document and set it as active.

    Args:
        adapter: Connected ``PyWin32Adapter`` instance.
        name: Reserved for future naming policy.
        units: Reserved for future units policy.

    Returns:
        SolidWorksModel: Metadata for the new part document.

    Raises:
        Exception: If no part template is configured or creation fails.
    """
    _ = name, units
    model = None
    app = adapter.swApp
    if app is None:
        raise Exception("SolidWorks application is not connected")

    new_part = getattr(app, "NewPart", None)
    if callable(new_part):
        model = adapter._attempt(new_part)

    if not model:
        part_template = resolve_template_path(adapter, [8, 0, 1, 2, 3], ".prtdot")
        if not part_template:
            raise Exception("No part template configured in SolidWorks")
        model = app.NewDocument(part_template, 0, 0, 0)

    if not model:
        raise Exception("Failed to create new part")

    adapter.currentModel = model
    title = read_model_title(adapter, model)
    return SolidWorksModel(
        path="",
        name=title,
        type="Part",
        is_active=True,
        configuration="Default",
        properties={"created": datetime.now().isoformat()},
    )


def create_assembly(adapter: Any, name: str | None = None) -> SolidWorksModel:
    """Create a new assembly document and set it as active.

    Args:
        adapter: Connected ``PyWin32Adapter`` instance.
        name: Reserved for future naming policy.

    Returns:
        SolidWorksModel: Metadata for the new assembly document.

    Raises:
        Exception: If no assembly template is configured or creation fails.
    """
    _ = name
    model = None
    app = adapter.swApp
    if app is None:
        raise Exception("SolidWorks application is not connected")

    new_assembly = getattr(app, "NewAssembly", None)
    if callable(new_assembly):
        model = adapter._attempt(new_assembly)

    if not model:
        asm_template = resolve_template_path(adapter, [9, 2, 3, 1, 0], ".asmdot")
        if not asm_template:
            raise Exception("No assembly template configured in SolidWorks")
        model = app.NewDocument(asm_template, 0, 0, 0)

    if not model:
        raise Exception("Failed to create new assembly")

    adapter.currentModel = model
    title = read_model_title(adapter, model)
    return SolidWorksModel(
        path="",
        name=title,
        type="Assembly",
        is_active=True,
        configuration="Default",
        properties={"created": datetime.now().isoformat()},
    )


def create_drawing(adapter: Any, name: str | None = None) -> SolidWorksModel:
    """Create a new drawing document and set it as active.

    Args:
        adapter: Connected ``PyWin32Adapter`` instance.
        name: Reserved for future naming policy.

    Returns:
        SolidWorksModel: Metadata for the new drawing document.

    Raises:
        Exception: If creation fails.
    """
    _ = name
    app = adapter.swApp
    if app is None:
        raise Exception("SolidWorks application is not connected")

    drw_template = app.GetUserPreferenceStringValue(1)
    if not drw_template:
        drw_template = app.GetUserPreferenceStringValue(0).replace("Part", "Drawing")

    model = app.NewDocument(drw_template, 12, 0.2794, 0.2159)
    if not model:
        raise Exception("Failed to create new drawing")

    adapter.currentModel = model
    title = read_model_title(adapter, model)
    return SolidWorksModel(
        path="",
        name=title,
        type="Drawing",
        is_active=True,
        configuration="Default",
        properties={"created": datetime.now().isoformat()},
    )


def get_dimension(adapter: Any, name: str) -> float:
    """Read a named model dimension in millimetres.

    Args:
        adapter: ``PyWin32Adapter`` with an active model.
        name: Fully-qualified dimension name.

    Returns:
        float: Dimension value in millimetres.

    Raises:
        Exception: If the dimension does not exist.
    """
    dimension = adapter.currentModel.Parameter(name)
    if not dimension:
        raise Exception(f"Dimension '{name}' not found")
    value = dimension.GetValue3(8, None)
    return value * 1000


def set_dimension(adapter: Any, name: str, value: float) -> None:
    """Set a named model dimension in millimetres and rebuild.

    Args:
        adapter: ``PyWin32Adapter`` with an active model.
        name: Fully-qualified dimension name.
        value: New value in millimetres.

    Raises:
        Exception: If the dimension is missing or update fails.
    """
    dimension = adapter.currentModel.Parameter(name)
    if not dimension:
        raise Exception(f"Dimension '{name}' not found")

    success = dimension.SetValue3(value / 1000.0, 8, None)
    if not success:
        raise Exception(f"Failed to set dimension '{name}'")

    adapter.currentModel.ForceRebuild3(False)


def save_file(adapter: Any, file_path: str | None = None) -> None:
    """Save the active model to its current path or to a new file path.

    Args:
        adapter: ``PyWin32Adapter`` with an active model.
        file_path: Optional target path for Save As.

    Raises:
        Exception: If save operation does not produce a file.
    """
    if file_path:
        resolved_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

        if adapter.swApp:
            adapter._attempt(lambda: adapter.swApp.CloseDoc(resolved_path))

        if os.path.exists(resolved_path):
            adapter._attempt(lambda: os.remove(resolved_path))

        save_as3_result = adapter.currentModel.SaveAs3(resolved_path, 0, 0)
        if not _is_success(save_as3_result):
            save_as = getattr(adapter.currentModel, "SaveAs", None)
            if callable(save_as):
                fallback_result = save_as(resolved_path)
                if not _is_success(fallback_result):
                    raise Exception(f"Failed to save as: {resolved_path}")
            else:
                raise Exception(f"Failed to save as: {resolved_path}")

        if not os.path.exists(resolved_path):
            raise Exception(f"File not written after save: {resolved_path}")
        return

    save_result = adapter._attempt(lambda: adapter.currentModel.Save3(1, None, None))
    if save_result is None:
        save_fn = getattr(adapter.currentModel, "Save", None)
        if callable(save_fn):
            save_result = save_fn()
        else:
            raise Exception("Failed to save file")

    if _is_success(save_result):
        return

    path_attr = getattr(adapter.currentModel, "GetPathName", "")
    model_path = path_attr() if callable(path_attr) else path_attr
    if model_path and os.path.exists(model_path):
        return
    raise Exception("Failed to save file")


def rebuild_model(adapter: Any) -> None:
    """Force a model rebuild.

    Args:
        adapter: ``PyWin32Adapter`` with an active model.

    Raises:
        Exception: If SolidWorks reports rebuild failure.
    """
    success = adapter.currentModel.ForceRebuild3(False)
    if not success:
        raise Exception("Failed to rebuild model")


def get_model_info(adapter: Any) -> dict[str, Any]:
    """Collect summary metadata about the active model.

    Args:
        adapter: ``PyWin32Adapter`` with an active model.

    Returns:
        dict[str, Any]: Model information payload used by tool responses.
    """
    active_config = adapter.currentModel.GetActiveConfiguration()
    return {
        "title": adapter.currentModel.GetTitle(),
        "path": adapter.currentModel.GetPathName(),
        "type": adapter._get_document_type(),
        "configuration": active_config.GetName() if active_config else "Default",
        "is_dirty": adapter.currentModel.GetSaveFlag(),
        "feature_count": adapter.currentModel.FeatureManager.GetFeatureCount(True),
        "rebuild_status": adapter.currentModel.GetRebuildStatus(),
    }


def list_configurations(adapter: Any) -> list[str]:
    """List all configuration names on the active model.

    Args:
        adapter: ``PyWin32Adapter`` with an active model.

    Returns:
        list[str]: Configuration names, or empty list when unavailable.
    """
    raw_names = getattr(adapter.currentModel, "GetConfigurationNames", None)
    names = raw_names() if callable(raw_names) else raw_names
    if names is None:
        names = []
    if isinstance(names, str):
        return [names]

    normalized_names = [str(name) for name in names]
    if normalized_names:
        return normalized_names

    active_config = adapter._attempt(
        lambda: adapter.currentModel.GetActiveConfiguration(), default=None
    )
    active_name = adapter._attempt(lambda: active_config.GetName(), default=None)
    if active_name:
        return [str(active_name)]
    return []


def get_mass_properties(adapter: Any) -> MassProperties:
    """Get mass properties for the active model.

    Args:
        adapter: ``PyWin32Adapter`` with an active model.

    Returns:
        MassProperties: Computed mass, volume, area, COM, and inertia terms.

    Raises:
        Exception: If mass properties cannot be determined.
    """
    adapter._attempt(lambda: adapter.currentModel.ForceRebuild3(False), default=None)
    mass_props = adapter._attempt(
        lambda: adapter.currentModel.Extension.CreateMassProperty(), default=None
    )

    if mass_props:
        volume = mass_props.Volume * 1e9
        surface_area = mass_props.SurfaceArea * 1e6
        mass = mass_props.Mass

        center_of_mass = [0.0, 0.0, 0.0]
        com = adapter._attempt(lambda: mass_props.CenterOfMass, default=None)
        if isinstance(com, (list, tuple)) and len(com) >= 3:
            center_of_mass = [com[0] * 1000, com[1] * 1000, com[2] * 1000]

        moi = adapter._attempt(lambda: mass_props.GetMomentOfInertia(0), default=None)
        if not isinstance(moi, (list, tuple)) or len(moi) < 9:
            moi = [0.0] * 9
    else:
        raw = adapter._attempt(
            lambda: adapter.currentModel.GetMassProperties, default=None
        )
        if not isinstance(raw, (list, tuple)) or len(raw) < 6:
            raise Exception("Failed to get mass properties")

        center_of_mass = [raw[0] * 1000.0, raw[1] * 1000.0, raw[2] * 1000.0]
        volume = raw[3] * 1e9
        surface_area = raw[4] * 1e6
        mass = raw[5]

        moi = [0.0] * 9
        if len(raw) >= 12:
            moi[0] = raw[6]
            moi[4] = raw[7]
            moi[8] = raw[8]
            moi[1] = raw[9]
            moi[5] = raw[10]
            moi[2] = raw[11]

    return MassProperties(
        volume=volume,
        surface_area=surface_area,
        mass=mass,
        center_of_mass=center_of_mass,
        moments_of_inertia={
            "Ixx": moi[0],
            "Iyy": moi[4],
            "Izz": moi[8],
            "Ixy": moi[1],
            "Ixz": moi[2],
            "Iyz": moi[5],
        },
    )


def _is_success(value: Any) -> bool:
    """Interpret SolidWorks save API return values consistently.

    Args:
        value: Return value from ``Save*`` COM calls.

    Returns:
        bool: ``True`` when return value indicates success.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 0
    return bool(value)
