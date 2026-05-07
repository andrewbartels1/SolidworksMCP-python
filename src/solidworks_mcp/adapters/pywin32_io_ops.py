"""I/O and document-query operations extracted from the PyWin32Adapter.

This module groups model load/save/export operations plus feature/configuration
query helpers so the main adapter class stays thinner and easier to test.

All public functions accept the adapter as their first argument and return
``AdapterResult`` values through the adapter's shared COM wrapper.
"""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

try:
    import pythoncom
    import win32com.client
except ImportError:  # pragma: no cover
    pythoncom = SimpleNamespace(VT_BYREF=0, VT_I4=0)
    win32com = SimpleNamespace(client=SimpleNamespace(VARIANT=lambda *_args: 0))

from .base import (
    AdapterResult,
    AdapterResultStatus,
    SolidWorksModel,
)


def _as_result(value: Any) -> AdapterResult[Any]:
    """Cast adapter wrapper output to a typed AdapterResult.

    The adapter exposes a dynamically-typed ``_handle_com_operation_call``
    helper; this utility keeps strict type checkers satisfied in this module.
    """
    return cast(AdapterResult[Any], value)


def _set_dimension_auto_approve(adapter: Any, enabled: bool) -> bool | None:
    """Set the global dimension-input preference toggle.

    Args:
        adapter: Active pywin32 adapter instance.
        enabled: Whether the interactive value-on-create dialog should remain
            enabled. ``False`` suppresses confirmation dialogs during
            automation-oriented dimension workflows.

    Returns:
        Previously configured toggle value if readable; otherwise ``None``.
    """
    pref_toggle = adapter.constants["swInputDimValOnCreate"]
    previous_value = adapter._attempt(
        lambda: bool(adapter.swApp.GetUserPreferenceToggle(pref_toggle)),
        default=None,
    )
    adapter._attempt(
        lambda: adapter.swApp.SetUserPreferenceToggle(pref_toggle, enabled),
        default=None,
    )
    return previous_value


def _restore_dimension_auto_approve(adapter: Any, previous_value: bool | None) -> None:
    """Restore the global dimension-input preference toggle.

    Args:
        adapter: Active pywin32 adapter instance.
        previous_value: Previous value returned by
            :func:`_set_dimension_auto_approve`. ``None`` means no restoration
            should be attempted.
    """
    if previous_value is None:
        return
    pref_toggle = adapter.constants["swInputDimValOnCreate"]
    adapter._attempt(
        lambda: adapter.swApp.SetUserPreferenceToggle(pref_toggle, previous_value),
        default=None,
    )


def _open_model_impl(adapter: Any, file_path: str) -> SolidWorksModel:
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

    errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

    app = adapter.swApp
    model = app.OpenDoc6(
        resolved_path,
        doc_type,
        1,
        "",
        errors,
        warnings,
    )
    if not model:
        raise Exception(f"Failed to open model: {resolved_path}")

    adapter.currentModel = model
    title = adapter._read_model_title(model)
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


def open_model(adapter: Any, file_path: str) -> AdapterResult[SolidWorksModel]:
    """Open a SolidWorks document and set it as the current model."""
    if not adapter.is_connected():
        return AdapterResult(
            status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
        )
    return cast(
        AdapterResult[SolidWorksModel],
        _as_result(
            adapter._handle_com_operation_call(
                "open_model", _open_model_impl, adapter, file_path
            )
        ),
    )


def _close_model_impl(adapter: Any, save: bool) -> None:
    model = adapter.currentModel
    app = adapter.swApp
    if model is None or app is None:
        raise Exception("SolidWorks application is not connected")

    if save:
        model.Save()

    app.CloseDoc(model.GetTitle())
    adapter.currentModel = None


def close_model(adapter: Any, save: bool = False) -> AdapterResult[None]:
    """Close the active model with optional save."""
    if not adapter.currentModel:
        return AdapterResult(
            status=AdapterResultStatus.WARNING, error="No active model to close"
        )
    return cast(
        AdapterResult[None],
        _as_result(
            adapter._handle_com_operation_call(
                "close_model", _close_model_impl, adapter, save
            )
        ),
    )


def _create_part_impl(
    adapter: Any, _name: str | None, _units: str | None
) -> SolidWorksModel:
    model = None
    app = adapter.swApp
    if app is None:
        raise Exception("SolidWorks application is not connected")

    new_part = getattr(app, "NewPart", None)
    if callable(new_part):
        model = adapter._attempt(new_part)

    if not model:
        part_template = adapter._resolve_template_path([8, 0, 1, 2, 3], ".prtdot")
        if not part_template:
            raise Exception("No part template configured in SolidWorks")
        model = app.NewDocument(part_template, 0, 0, 0)

    if not model:
        raise Exception("Failed to create new part")

    adapter.currentModel = model
    return SolidWorksModel(
        path="",
        name=adapter._read_model_title(model),
        type="Part",
        is_active=True,
        configuration="Default",
        properties={"created": datetime.now().isoformat()},
    )


def create_part(
    adapter: Any,
    name: str | None = None,
    units: str | None = None,
) -> AdapterResult[SolidWorksModel]:
    """Create a new part document."""
    if not adapter.is_connected():
        return AdapterResult(
            status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
        )
    return cast(
        AdapterResult[SolidWorksModel],
        _as_result(
            adapter._handle_com_operation_call(
                "create_part", _create_part_impl, adapter, name, units
            )
        ),
    )


def _create_assembly_impl(adapter: Any, _name: str | None) -> SolidWorksModel:
    model = None
    app = adapter.swApp
    if app is None:
        raise Exception("SolidWorks application is not connected")

    new_assembly = getattr(app, "NewAssembly", None)
    if callable(new_assembly):
        model = adapter._attempt(new_assembly)

    if not model:
        asm_template = adapter._resolve_template_path([9, 2, 3, 1, 0], ".asmdot")
        if not asm_template:
            raise Exception("No assembly template configured in SolidWorks")
        model = app.NewDocument(asm_template, 0, 0, 0)

    if not model:
        raise Exception("Failed to create new assembly")

    adapter.currentModel = model
    return SolidWorksModel(
        path="",
        name=adapter._read_model_title(model),
        type="Assembly",
        is_active=True,
        configuration="Default",
        properties={"created": datetime.now().isoformat()},
    )


def create_assembly(
    adapter: Any,
    name: str | None = None,
) -> AdapterResult[SolidWorksModel]:
    """Create a new assembly document."""
    if not adapter.is_connected():
        return AdapterResult(
            status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
        )
    return cast(
        AdapterResult[SolidWorksModel],
        _as_result(
            adapter._handle_com_operation_call(
                "create_assembly", _create_assembly_impl, adapter, name
            )
        ),
    )


def _create_drawing_impl(adapter: Any, _name: str | None) -> SolidWorksModel:
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
    return SolidWorksModel(
        path="",
        name=adapter._read_model_title(model),
        type="Drawing",
        is_active=True,
        configuration="Default",
        properties={"created": datetime.now().isoformat()},
    )


def create_drawing(
    adapter: Any,
    name: str | None = None,
) -> AdapterResult[SolidWorksModel]:
    """Create a new drawing document."""
    if not adapter.is_connected():
        return AdapterResult(
            status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
        )
    return cast(
        AdapterResult[SolidWorksModel],
        _as_result(
            adapter._handle_com_operation_call(
                "create_drawing", _create_drawing_impl, adapter, name
            )
        ),
    )


def _export_file_impl(adapter: Any, file_path: str, format_type: str) -> None:
    format_map = {
        "step": 0,
        "iges": 1,
        "stl": 2,
        "pdf": 3,
        "dwg": 4,
        "jpg": 5,
        "glb": 41,
        "gltf": 41,
    }

    format_lower = format_type.lower()
    if format_lower not in format_map:
        raise Exception(f"Unsupported export format: {format_type}")

    resolved_path = os.path.abspath(file_path)
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
    if os.path.exists(resolved_path):
        adapter._attempt(lambda: os.remove(resolved_path))

    target_doc = (
        getattr(adapter.swApp, "ActiveDoc", None) if adapter.swApp else None
    ) or adapter.currentModel

    if format_lower == "stl":
        adapter._attempt(lambda: target_doc.ResolveAllLightweightComponents(True))
        ext = getattr(target_doc, "Extension", None)
        if ext is None:
            raise RuntimeError("No Extension object available for STL export")

        stl_data = adapter._prepare_stl_export_data()
        if not adapter._save_stl_with_extension(ext, stl_data, resolved_path):
            adapter._save_stl_with_fallback(target_doc, resolved_path)
        return None

    success = target_doc.SaveAs3(resolved_path, 0, 2)
    if not success and not os.path.exists(resolved_path):
        raise Exception(f"SaveAs3 returned False and no file produced: {resolved_path}")


def export_file(
    adapter: Any,
    file_path: str,
    format_type: str,
) -> AdapterResult[None]:
    """Export the active model to a target format."""
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[None],
        _as_result(
            adapter._handle_com_operation_call(
                "export_file", _export_file_impl, adapter, file_path, format_type
            )
        ),
    )


def _get_dimension_impl(adapter: Any, name: str) -> float:
    """Read a named model dimension from SolidWorks.

    Args:
        adapter: Active pywin32 adapter instance.
        name: Fully-qualified SolidWorks dimension name.

    Returns:
        Dimension value in millimetres.

    Raises:
        Exception: If the dimension name cannot be resolved.
    """
    previous_dim_dialog_pref = _set_dimension_auto_approve(adapter, False)
    try:
        dimension = adapter.currentModel.Parameter(name)
        if not dimension:
            raise Exception(f"Dimension '{name}' not found")
        value = dimension.GetValue3(8, None)
        return float(value) * 1000.0
    finally:
        _restore_dimension_auto_approve(adapter, previous_dim_dialog_pref)


def get_dimension(adapter: Any, name: str) -> AdapterResult[float]:
    """Read a model dimension in millimetres.

    Args:
        adapter: Active pywin32 adapter instance.
        name: Fully-qualified SolidWorks dimension name.

    Returns:
        AdapterResult[float]: Dimension value in millimetres when successful.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[float],
        _as_result(
            adapter._handle_com_operation_call(
                "get_dimension", _get_dimension_impl, adapter, name
            )
        ),
    )


def _set_dimension_impl(adapter: Any, name: str, value: float) -> None:
    """Set a named model dimension and force a rebuild.

    Args:
        adapter: Active pywin32 adapter instance.
        name: Fully-qualified SolidWorks dimension name.
        value: New value in millimetres.

    Raises:
        Exception: If the dimension name cannot be resolved or the write fails.
    """
    previous_dim_dialog_pref = _set_dimension_auto_approve(adapter, False)
    try:
        dimension = adapter.currentModel.Parameter(name)
        if not dimension:
            raise Exception(f"Dimension '{name}' not found")

        success = dimension.SetValue3(value / 1000.0, 8, None)
        if not success:
            raise Exception(f"Failed to set dimension '{name}'")

        adapter.currentModel.ForceRebuild3(False)
    finally:
        _restore_dimension_auto_approve(adapter, previous_dim_dialog_pref)


def set_dimension(adapter: Any, name: str, value: float) -> AdapterResult[None]:
    """Set a model dimension in millimetres and rebuild.

    Args:
        adapter: Active pywin32 adapter instance.
        name: Fully-qualified SolidWorks dimension name.
        value: New value in millimetres.

    Returns:
        AdapterResult[None]: Success/error status for the update operation.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[None],
        _as_result(
            adapter._handle_com_operation_call(
                "set_dimension", _set_dimension_impl, adapter, name, value
            )
        ),
    )


def _is_save_success(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 0
    return bool(value)


def _save_file_impl(adapter: Any, file_path: str | None = None) -> None:
    if file_path:
        resolved_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

        if adapter.swApp:
            adapter._attempt(lambda: adapter.swApp.CloseDoc(resolved_path))

        if os.path.exists(resolved_path):
            adapter._attempt(lambda: os.remove(resolved_path))

        save_as3_result = adapter.currentModel.SaveAs3(resolved_path, 0, 0)
        if not _is_save_success(save_as3_result):
            save_as = getattr(adapter.currentModel, "SaveAs", None)
            if callable(save_as):
                fallback_result = save_as(resolved_path)
                if not _is_save_success(fallback_result):
                    raise Exception(f"Failed to save as: {resolved_path}")
            else:
                raise Exception(f"Failed to save as: {resolved_path}")

        if not os.path.exists(resolved_path):
            raise Exception(f"File not written after save: {resolved_path}")
        return None

    save_result = adapter._attempt(lambda: adapter.currentModel.Save3(1, None, None))
    if save_result is None:
        save_fn = getattr(adapter.currentModel, "Save", None)
        if callable(save_fn):
            save_result = save_fn()
        else:
            raise Exception("Failed to save file")

    if _is_save_success(save_result):
        return None

    path_attr = getattr(adapter.currentModel, "GetPathName", "")
    model_path = path_attr() if callable(path_attr) else path_attr
    if model_path and os.path.exists(model_path):
        return None
    raise Exception("Failed to save file")


def save_file(adapter: Any, file_path: str | None = None) -> AdapterResult[None]:
    """Save the active model to current or provided path."""
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[None],
        _as_result(
            adapter._handle_com_operation_call(
                "save_file", _save_file_impl, adapter, file_path
            )
        ),
    )


def _rebuild_model_impl(adapter: Any) -> None:
    success = adapter.currentModel.ForceRebuild3(False)
    if not success:
        raise Exception("Failed to rebuild model")


def rebuild_model(adapter: Any) -> AdapterResult[None]:
    """Force a model rebuild."""
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[None],
        _as_result(
            adapter._handle_com_operation_call(
                "rebuild_model", _rebuild_model_impl, adapter
            )
        ),
    )


def _get_model_info_impl(adapter: Any) -> dict[str, Any]:
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


def get_model_info(adapter: Any) -> AdapterResult[dict[str, Any]]:
    """Return summary metadata for the active model."""
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[dict[str, Any]],
        _as_result(
            adapter._handle_com_operation_call(
                "get_model_info", _get_model_info_impl, adapter
            )
        ),
    )


def _is_feature_suppressed(adapter: Any, feature: Any) -> bool:
    suppressed_direct = adapter._attempt(lambda: feature.IsSuppressed(), default=None)
    if suppressed_direct is not None:
        return bool(suppressed_direct)

    suppressed_result = adapter._attempt(
        lambda: feature.IsSuppressed2(0, []), default=None
    )
    if isinstance(suppressed_result, (tuple, list)):
        return bool(suppressed_result[0]) if suppressed_result else False
    return bool(suppressed_result) if suppressed_result is not None else False


def _append_feature_entry(
    adapter: Any,
    feature: Any,
    position: int,
    include_suppressed: bool,
    features: list[dict[str, Any]],
    seen: set[tuple[str, str]],
) -> None:
    name = str(getattr(feature, "Name", ""))
    feature_type = str(
        adapter._attempt(lambda: feature.GetTypeName2(), default="Unknown")
    )
    dedupe_key = (name, feature_type)
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)

    suppressed = _is_feature_suppressed(adapter, feature)
    if not include_suppressed and suppressed:
        return

    features.append(
        {
            "name": name,
            "type": feature_type,
            "suppressed": suppressed,
            "position": position,
        }
    )


def _list_features_impl(adapter: Any, include_suppressed: bool) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    feature = adapter._attempt(lambda: adapter.currentModel.FirstFeature())
    pos = 0
    guard = 0
    while feature and guard < 10000:
        _append_feature_entry(
            adapter,
            feature,
            pos,
            include_suppressed,
            features,
            seen,
        )
        pos += 1
        guard += 1
        next_feature = adapter._attempt(
            lambda current_feature=feature: current_feature.GetNextFeature()
        )
        if next_feature is None:
            break
        feature = next_feature

    if features:
        return features

    feature_manager = getattr(adapter.currentModel, "FeatureManager", None)
    count = (
        adapter._attempt(
            lambda: int(feature_manager.GetFeatureCount(True) or 0), default=0
        )
        if feature_manager is not None
        else 0
    )

    for reverse_pos in range(1, count + 1):
        feature = adapter._attempt(
            lambda pos=reverse_pos: adapter.currentModel.FeatureByPositionReverse(pos)
        )
        if feature is None:
            continue
        position = count - reverse_pos
        _append_feature_entry(
            adapter,
            feature,
            position,
            include_suppressed,
            features,
            seen,
        )

    return features


def list_features(
    adapter: Any,
    include_suppressed: bool = False,
) -> AdapterResult[list[dict[str, Any]]]:
    """List feature-tree entries on the active model."""
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[list[dict[str, Any]]],
        _as_result(
            adapter._handle_com_operation_call(
                "list_features", _list_features_impl, adapter, include_suppressed
            )
        ),
    )


def _select_feature_impl(adapter: Any, feature_name: str) -> dict[str, Any]:
    target_doc = adapter.currentModel
    candidate_names = adapter._build_feature_candidate_names(feature_name, target_doc)

    result = adapter._try_select_by_extension(target_doc, candidate_names, feature_name)
    if result:
        return cast(dict[str, Any], result)

    result = adapter._try_select_by_component(target_doc, candidate_names, feature_name)
    if result:
        return cast(dict[str, Any], result)

    result = adapter._try_select_by_feature_tree(
        target_doc, feature_name, candidate_names
    )
    if result:
        return cast(dict[str, Any], result)

    return {
        "selected": False,
        "feature_name": feature_name,
        "selected_name": feature_name,
    }


def select_feature(adapter: Any, feature_name: str) -> AdapterResult[dict[str, Any]]:
    """Select a named feature through extension/component/tree strategies."""
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[dict[str, Any]],
        _as_result(
            adapter._handle_com_operation_call(
                "select_feature", _select_feature_impl, adapter, feature_name
            )
        ),
    )


def _list_configurations_impl(adapter: Any) -> list[str]:
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


def list_configurations(adapter: Any) -> AdapterResult[list[str]]:
    """Return all active model configuration names."""
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")
    return cast(
        AdapterResult[list[str]],
        _as_result(
            adapter._handle_com_operation_call(
                "list_configurations", _list_configurations_impl, adapter
            )
        ),
    )
