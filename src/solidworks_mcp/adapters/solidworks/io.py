"""Model I/O mixin for PyWin32 SolidWorks operations."""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from .. import sw_type_info as _sw_type_info
from ..base import AdapterResult, AdapterResultStatus, MassProperties, SolidWorksModel

try:
    import pythoncom
    import win32com.client
except ImportError:  # pragma: no cover
    pythoncom = SimpleNamespace()
    win32com = SimpleNamespace(client=SimpleNamespace())

try:
    import comtypes
    import comtypes.client as _comtypes_client

    _COMTYPES_AVAILABLE = True
except ImportError:  # pragma: no cover
    _COMTYPES_AVAILABLE = False

# SolidWorks type library GUID (stable across SW versions)
_SW_TLB_GUID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
# Cached comtypes wrapper module (loaded once per process)
_sw_comtypes_lib: Any = None


def _get_sw_comtypes_lib() -> Any:
    """Return the comtypes wrapper for the SolidWorks type library.

    Tries SW version numbers 35..30 (newest to oldest). Returns ``None`` when
    comtypes is unavailable or the TLB cannot be found in the registry.
    """
    global _sw_comtypes_lib
    if _sw_comtypes_lib is not None:
        return _sw_comtypes_lib
    if not _COMTYPES_AVAILABLE:
        return None
    for major in (35, 34, 33, 32, 31, 30):  # pragma: no cover
        try:
            _sw_comtypes_lib = _comtypes_client.GetModule(
                (comtypes.GUID(_SW_TLB_GUID), major, 0)
            )
            return _sw_comtypes_lib
        except Exception:
            continue
    return None  # pragma: no cover


def _bridge_com_to_comtypes(pywin32_obj: Any, iface: Any) -> Any:  # pragma: no cover
    """Bridge a pywin32 CDispatch/COM object to a comtypes interface pointer.

    Extracts the raw IUnknown pointer from pywin32's repr string, then
    QueryInterface-es for *iface* via comtypes.  The AddRef keeps the object
    alive through the Python reference.
    """
    unk = pywin32_obj._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
    m = re.search(r"obj at (0x[0-9a-fA-F]+)", repr(unk))
    if not m:
        raise RuntimeError(f"Could not extract COM pointer from {repr(unk)!r}")
    ptr_int = int(m.group(1), 16)
    ct_unk = ctypes.cast(ptr_int, ctypes.POINTER(comtypes.IUnknown))
    ct_unk.AddRef()
    return ct_unk.QueryInterface(iface)


class SolidWorksIOMixin:
    """Expose model open/save/create/configuration methods through a mixin."""

    @staticmethod
    def _adapter(obj: Any) -> Any:
        """Return the runtime adapter object for dynamic attribute access."""
        return cast(Any, obj)

    @staticmethod
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

    def _resolve_template_path(
        self, preferred_indices: list[int], extension: str
    ) -> str | None:
        """Resolve a template path from SolidWorks user preference slots.

        Args:
            preferred_indices: Preference indices to probe in order.
            extension: Expected template extension such as ``.prtdot``.

        Returns:
            str | None: First existing template match, otherwise first non-empty
            path candidate, or ``None`` if nothing is configured.
        """
        adapter = self._adapter(self)
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
            if template.lower().endswith(extension.lower()) and os.path.exists(
                template
            ):
                existing_match = template
                break

        return existing_match or first_non_empty

    def _read_model_title(self, model: Any) -> str:
        """Read a model title regardless of COM exposing method or property.

        Args:
            model: SolidWorks model COM object.

        Returns:
            str: Best-effort model title, defaulting to ``"Untitled"``.
        """
        adapter = self._adapter(self)
        title = adapter._attempt(lambda: adapter._get_attr_or_call(model, "GetTitle"))
        if isinstance(title, str) and title:
            return title

        title_value = getattr(model, "Title", None)
        if isinstance(title_value, str) and title_value:
            return title_value

        return "Untitled"

    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Open a SolidWorks model file and set it as active on the adapter.

        Args:
            file_path: Path to a ``.sldprt``, ``.sldasm``, or ``.slddrw`` file.

        Returns:
            AdapterResult[SolidWorksModel]: Model metadata for the opened document.
        """
        adapter = self._adapter(self)
        if not adapter.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _open() -> SolidWorksModel:
            """Open the model document."""
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
            variant_ctor = getattr(getattr(win32com, "client", None), "VARIANT", None)
            vt_byref = int(getattr(pythoncom, "VT_BYREF", 0))
            vt_i4 = int(getattr(pythoncom, "VT_I4", 0))
            if callable(variant_ctor):
                errors = variant_ctor(vt_byref | vt_i4, 0)
                warnings = variant_ctor(vt_byref | vt_i4, 0)
            else:
                errors = 0
                warnings = 0
            model = app.OpenDoc6(resolved_path, doc_type, 1, "", errors, warnings)
            if not model:
                raise Exception(f"Failed to open model: {resolved_path}")

            adapter._attempt(
                lambda: _sw_type_info.flag_doc(model, int(doc_type)), default=0
            )

            adapter.currentModel = model
            title = self._read_model_title(model)
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

        return cast(
            AdapterResult[SolidWorksModel],
            adapter._handle_com_operation("open_model", _open),
        )

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close the current SolidWorks model and optionally save first.

        Args:
            save: When ``True``, calls ``Save`` before closing.

        Returns:
            AdapterResult[None]: Result of the close operation.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.WARNING, error="No active model to close"
            )
        model = adapter.currentModel
        app = adapter.swApp
        if model is None or app is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="SolidWorks application is not connected",
            )

        def _close() -> None:
            """Close the model document."""
            if save:
                model.Save()
            app.CloseDoc(model.GetTitle())
            adapter.currentModel = None

        return cast(
            AdapterResult[None],
            adapter._handle_com_operation("close_model", _close),
        )

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new part document and set it as active.

        Args:
            name: Reserved for future naming policy.
            units: Reserved for future units policy.

        Returns:
            AdapterResult[SolidWorksModel]: Metadata for the new part document.
        """
        adapter = self._adapter(self)
        if not adapter.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create() -> SolidWorksModel:
            """Create a new part."""
            _ = name, units
            model = None
            app = adapter.swApp
            if app is None:
                raise Exception("SolidWorks application is not connected")

            new_part = getattr(app, "NewPart", None)
            if callable(new_part):
                model = adapter._attempt(new_part)

            if not model:
                part_template = self._resolve_template_path([8, 0, 1, 2, 3], ".prtdot")
                if not part_template:
                    raise Exception("No part template configured in SolidWorks")
                model = app.NewDocument(part_template, 0, 0, 0)

            if not model:
                raise Exception("Failed to create new part")

            adapter._attempt(lambda: _sw_type_info.flag_doc(model, 1), default=0)
            adapter.currentModel = model
            title = self._read_model_title(model)
            return SolidWorksModel(
                path="",
                name=title,
                type="Part",
                is_active=True,
                configuration="Default",
                properties={"created": datetime.now().isoformat()},
            )

        return cast(
            AdapterResult[SolidWorksModel],
            adapter._handle_com_operation("create_part", _create),
        )

    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new assembly document and set it as active.

        Args:
            name: Reserved for future naming policy.

        Returns:
            AdapterResult[SolidWorksModel]: Metadata for the new assembly document.
        """
        adapter = self._adapter(self)
        if not adapter.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create() -> SolidWorksModel:
            """Create a new assembly."""
            _ = name
            model = None
            app = adapter.swApp
            if app is None:
                raise Exception("SolidWorks application is not connected")

            new_assembly = getattr(app, "NewAssembly", None)
            if callable(new_assembly):
                model = adapter._attempt(new_assembly)

            if not model:
                asm_template = self._resolve_template_path([9, 2, 3, 1, 0], ".asmdot")
                if not asm_template:
                    raise Exception("No assembly template configured in SolidWorks")
                model = app.NewDocument(asm_template, 0, 0, 0)

            if not model:
                raise Exception("Failed to create new assembly")

            adapter._attempt(lambda: _sw_type_info.flag_doc(model, 2), default=0)
            adapter.currentModel = model
            title = self._read_model_title(model)
            return SolidWorksModel(
                path="",
                name=title,
                type="Assembly",
                is_active=True,
                configuration="Default",
                properties={"created": datetime.now().isoformat()},
            )

        return cast(
            AdapterResult[SolidWorksModel],
            adapter._handle_com_operation("create_assembly", _create),
        )

    async def create_drawing(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new drawing document and set it as active.

        Args:
            name: Reserved for future naming policy.

        Returns:
            AdapterResult[SolidWorksModel]: Metadata for the new drawing document.
        """
        adapter = self._adapter(self)
        if not adapter.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create() -> SolidWorksModel:
            """Create a new drawing."""
            _ = name
            app = adapter.swApp
            if app is None:
                raise Exception("SolidWorks application is not connected")

            drw_template = app.GetUserPreferenceStringValue(1)
            if not drw_template:
                drw_template = app.GetUserPreferenceStringValue(0).replace(
                    "Part", "Drawing"
                )

            model = app.NewDocument(drw_template, 12, 0.2794, 0.2159)
            if not model:
                raise Exception("Failed to create new drawing")

            adapter._attempt(lambda: _sw_type_info.flag_doc(model, 3), default=0)
            adapter.currentModel = model
            title = self._read_model_title(model)
            return SolidWorksModel(
                path="",
                name=title,
                type="Drawing",
                is_active=True,
                configuration="Default",
                properties={"created": datetime.now().isoformat()},
            )

        return cast(
            AdapterResult[SolidWorksModel],
            adapter._handle_com_operation("create_drawing", _create),
        )

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Read a named model dimension in millimetres.

        Args:
            name: Fully-qualified dimension name.

        Returns:
            AdapterResult[float]: Dimension value in millimetres.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _get() -> float:
            """Get the dimension value."""
            dimension = adapter.currentModel.Parameter(name)
            if not dimension:
                raise Exception(f"Dimension '{name}' not found")
            # SystemValue is reliable on SW 2025 (in meters, convert to mm)
            value = adapter._attempt(lambda: dimension.SystemValue, default=None)
            if value is None:
                # Fall back to GetValue3 for older SW versions
                value = adapter._attempt(
                    lambda: dimension.GetValue3(0, 0), default=None
                )
            if value is None:
                raise Exception(f"Failed to read dimension '{name}'")
            return cast(float, float(value) * 1000)

        return cast(
            AdapterResult[float],
            adapter._handle_com_operation("get_dimension", _get),
        )

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set a named model dimension in millimetres and rebuild.

        Args:
            name: Fully-qualified dimension name.
            value: New value in millimetres.

        Returns:
            AdapterResult[None]: Result of the set operation.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _set() -> None:
            """Set the dimension value."""
            dimension = adapter.currentModel.Parameter(name)
            if not dimension:
                raise Exception(f"Dimension '{name}' not found")

            # SetValue3 has gen_py parameter mapping issues on SW 2025.
            # SystemValue (in meters) is reliable.
            value_m = value / 1000.0
            adapter._attempt(
                lambda: setattr(dimension, "SystemValue", value_m),
                default=None,
            )

            # Rebuild: try EditRebuild3 first, fall back to ForceRebuild3
            rebuilt = adapter._attempt(
                lambda: adapter.currentModel.EditRebuild3(), default=None
            )
            if rebuilt is None:
                rebuilt = adapter._attempt(
                    lambda: adapter.currentModel.ForceRebuild3(True), default=None
                )
            if rebuilt is None:
                raise Exception("Failed to set dimension")

        return cast(
            AdapterResult[None],
            adapter._handle_com_operation("set_dimension", _set),
        )

    async def save_file(self, file_path: str | None = None) -> AdapterResult[None]:
        """Save the active model to its current path or to a new file path.

        Args:
            file_path: Optional target path for Save As.

        Returns:
            AdapterResult[None]: Result of the save operation.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _save() -> None:
            """Save the model."""
            if file_path:
                resolved_path = os.path.abspath(file_path)
                os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

                if adapter.swApp:
                    adapter._attempt(lambda: adapter.swApp.CloseDoc(resolved_path))

                if os.path.exists(resolved_path):
                    adapter._attempt(lambda: os.remove(resolved_path))

                save_as3_result = adapter.currentModel.SaveAs3(resolved_path, 0, 0)
                if not self._is_success(save_as3_result):
                    save_as = getattr(adapter.currentModel, "SaveAs", None)
                    if callable(save_as):
                        fallback_result = save_as(resolved_path)
                        if not self._is_success(fallback_result):
                            raise Exception(f"Failed to save as: {resolved_path}")
                    else:
                        raise Exception(f"Failed to save as: {resolved_path}")

                if not os.path.exists(resolved_path):
                    raise Exception(f"File not written after save: {resolved_path}")
                return

            save_result = adapter._attempt(
                lambda: adapter.currentModel.Save3(1, None, None)
            )
            if save_result is None:
                save_fn = getattr(adapter.currentModel, "Save", None)
                if callable(save_fn):
                    save_result = save_fn()
                else:
                    raise Exception("Failed to save file")

            if self._is_success(save_result):
                return

            path_attr = getattr(adapter.currentModel, "GetPathName", "")
            model_path = path_attr() if callable(path_attr) else path_attr
            if model_path and os.path.exists(model_path):
                return
            raise Exception("Failed to save file")

        return cast(
            AdapterResult[None],
            adapter._handle_com_operation("save_file", _save),
        )

    async def rebuild_model(self) -> AdapterResult[None]:
        """Force a model rebuild.

        Returns:
            AdapterResult[None]: Result of the rebuild operation.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _rebuild() -> None:
            """Rebuild the model."""
            success = adapter.currentModel.ForceRebuild3(False)
            if not success:
                raise Exception("Failed to rebuild model")

        return cast(
            AdapterResult[None],
            adapter._handle_com_operation("rebuild_model", _rebuild),
        )

    async def get_model_info(self) -> AdapterResult[dict[str, Any]]:
        """Collect summary metadata about the active model.

        Returns:
            AdapterResult[dict[str, Any]]: Model information payload.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _get_info() -> dict[str, Any]:
            """Get model information."""
            active_config = adapter.currentModel.GetActiveConfiguration()
            # 'Name' on Configuration is a property, not a method.
            config_name = (
                getattr(active_config, "Name", "Default")
                if active_config
                else "Default"
            )
            # Try GetSaveFlag (method) first, fallback to property
            is_dirty_raw = adapter._attempt(
                lambda: adapter.currentModel.GetSaveFlag(), default=None
            )
            is_dirty = bool(is_dirty_raw) if is_dirty_raw is not None else None
            feature_count = adapter._attempt(
                lambda: int(
                    adapter.currentModel.FeatureManager.GetFeatureCount(True) or 0
                ),
                default=0,
            )
            rebuild_status_raw = adapter._attempt(
                lambda: adapter.currentModel.GetRebuildStatus(), default=None
            )
            # GetRebuildStatus returns 0=ok, 1=needs rebuild, or None=failed
            rebuild_status = (
                rebuild_status_raw if rebuild_status_raw is not None else None
            )
            return {
                "title": adapter.currentModel.GetTitle(),
                "path": adapter.currentModel.GetPathName(),
                "type": adapter._get_document_type(),
                "configuration": config_name,
                "is_dirty": is_dirty,
                "feature_count": feature_count,
                "rebuild_status": rebuild_status,
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("get_model_info", _get_info),
        )

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List all configuration names on the active model.

        Returns:
            AdapterResult[list[str]]: Configuration names, or empty list when unavailable.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        def _list() -> list[str]:
            """List configurations."""
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
            active_name = adapter._attempt(
                lambda: active_config.GetName(), default=None
            )
            if active_name:
                return [str(active_name)]
            return []

        return cast(
            AdapterResult[list[str]],
            adapter._handle_com_operation("list_configurations", _list),
        )

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties for the active model.

        Returns:
            AdapterResult[MassProperties]: Computed mass, volume, area, COM, and inertia.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _get() -> MassProperties:
            """Get mass properties."""
            adapter._attempt(
                lambda: adapter.currentModel.ForceRebuild3(False), default=None
            )

            # Primary: Extension.CreateMassProperty() object API (most detailed)
            mass_props = adapter._attempt(
                lambda: adapter.currentModel.Extension.CreateMassProperty(),
                default=None,
            )

            if mass_props:
                volume = mass_props.Volume * 1e9
                surface_area = mass_props.SurfaceArea * 1e6
                mass = mass_props.Mass

                center_of_mass = [0.0, 0.0, 0.0]
                com = adapter._attempt(lambda: mass_props.CenterOfMass, default=None)
                if isinstance(com, (list, tuple)) and len(com) >= 3:
                    center_of_mass = [com[0] * 1000, com[1] * 1000, com[2] * 1000]

                moi = adapter._attempt(
                    lambda: mass_props.GetMomentOfInertia(0), default=None
                )
                if not isinstance(moi, (list, tuple)) or len(moi) < 9:
                    moi = [0.0] * 9
            else:
                # Fallback: GetMassProperties as attribute (tuple) or callable (SW 2022)
                gmp = getattr(adapter.currentModel, "GetMassProperties", None)
                if callable(gmp):
                    raw = adapter._attempt(gmp, default=None)
                elif isinstance(gmp, (list, tuple)):
                    raw = gmp
                else:
                    raw = None

                if not isinstance(raw, (list, tuple)) or len(raw) < 6:
                    raise Exception("Failed to get mass properties")

                center_of_mass = [
                    raw[0] * 1000.0,
                    raw[1] * 1000.0,
                    raw[2] * 1000.0,
                ]
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

        return cast(
            AdapterResult[MassProperties],
            adapter._handle_com_operation("get_mass_properties", _get),
        )

    async def pack_and_go_assembly(
        self,
        source_path: str,
        target_dir: str,
    ) -> AdapterResult[dict[str, Any]]:
        """Copy an assembly and all its referenced components to a self-contained folder.

        Uses ``IModelDocExtension.GetPackAndGo()`` → ``IPackAndGo`` via the
        comtypes vtable interface (bypassing the broken IDispatch path present
        in SolidWorks 2026's late-binding layer), then calls
        ``IModelDocExtension.SavePackAndGo()`` to execute the copy.  All file
        paths inside the copied assembly are automatically updated by
        SolidWorks — this is the native Pack-and-Go mechanism.

        Args:
            source_path: Absolute path to the source ``.sldasm`` file.
            target_dir: Directory where the assembly and parts will be copied.
                        Created if it does not exist.

        Returns:
            AdapterResult[dict]: On success, ``data`` is a dict with keys:
            ``source_assembly``, ``target_dir``, ``copied_files``,
            ``source_files``, ``save_statuses``, and ``all_files_saved``.
        """
        adapter = self._adapter(self)
        source = Path(source_path)
        out_dir = Path(target_dir)

        def _do_pack_and_go() -> dict[str, Any]:  # pragma: no cover
            # Load comtypes TLB (cached after first call)
            sw_lib = _get_sw_comtypes_lib()
            if sw_lib is None:
                raise RuntimeError(
                    "comtypes SolidWorks type library not available. "
                    "Ensure comtypes is installed and SolidWorks is registered."
                )

            # Prepare a clean target directory. SW holds file locks on previously
            # opened assemblies so rmtree raises WinError 32. We rename the old
            # dir aside (Windows allows rename with open handles) and delete the
            # backup afterwards; if rename also fails we just proceed and let SW
            # overwrite existing files.
            if out_dir.exists():
                backup = out_dir.parent / f"{out_dir.name}_bak_{uuid.uuid4().hex[:8]}"
                try:
                    os.rename(out_dir, backup)
                    try:
                        shutil.rmtree(backup)
                    except Exception:
                        pass  # best-effort cleanup; stale backup is harmless
                except OSError:
                    pass  # rename also failed — proceed; SW will overwrite files
            out_dir.mkdir(parents=True, exist_ok=True)

            # Open the source assembly
            vt = pythoncom.VT_BYREF | pythoncom.VT_I4
            from win32com.client import VARIANT  # noqa: PLC0415

            err = VARIANT(vt, 0)
            warn = VARIANT(vt, 0)
            model = adapter.swApp.OpenDoc6(str(source), 2, 1, "", err, warn)
            if model is None and err.value == 65536:
                adapter.swApp.CloseAllDocuments(False)
                err = VARIANT(vt, 0)
                warn = VARIANT(vt, 0)
                model = adapter.swApp.OpenDoc6(str(source), 2, 1, "", err, warn)
            if model is None:
                raise RuntimeError(
                    f"OpenDoc6 failed err={err.value} warn={warn.value}"
                )
            _sw_type_info.flag_doc(model, 2)
            adapter.currentModel = model

            # Bridge model.Extension → IModelDocExtension via comtypes vtable
            ext_ct = _bridge_com_to_comtypes(model.Extension, sw_lib.IModelDocExtension)

            # GetPackAndGo() via vtable (IDispatch path broken in SW 2026)
            pg = ext_ct.GetPackAndGo()

            # Configure: flatten all files to root of target directory
            pg.FlattenToSingleFolder = True
            pg.SetSaveToName(True, str(out_dir) + "\\")

            # Record what files will be packed
            names_result = pg.GetDocumentNames()
            source_files: list[str] = list(names_result[0]) if names_result[0] else []

            # Execute Pack and Go — SavePackAndGo returns a tuple of per-file status codes
            ext_ct2 = _bridge_com_to_comtypes(model.Extension, sw_lib.IModelDocExtension)
            status_arr = ext_ct2.SavePackAndGo(pg)
            save_statuses: list[int] = list(status_arr) if status_arr else []

            copied_files = sorted(
                str(p)
                for p in out_dir.rglob("*")
                if p.is_file()
                and p.suffix.lower() in {".sldasm", ".sldprt", ".slddrw"}
            )
            return {
                "source_assembly": str(source),
                "target_dir": str(out_dir),
                "copied_files": copied_files,
                "source_files": source_files,
                "save_statuses": save_statuses,
                "all_files_saved": all(s == 0 for s in save_statuses),
            }

        result = adapter._handle_com_operation("pack_and_go_assembly", _do_pack_and_go)
        if not result.is_success:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Pack and Go failed: {result.error}",
            )
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=result.data,
            execution_time=result.execution_time,
        )
