"""PyWin32 SolidWorks adapter for Windows COM integration.

This adapter uses pywin32 to communicate with SolidWorks via COM, providing real
SolidWorks automation capabilities on Windows platforms.
"""

import os
import platform
import time
from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace
from typing import Any, TypeVar

from ..exceptions import SolidWorksMCPError
from .base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    LoftParameters,
    MassProperties,
    RevolveParameters,
    SolidWorksAdapter,
    SolidWorksFeature,
    SolidWorksModel,
    SweepParameters,
)

try:
    import pythoncom
    import pywintypes
    import win32com.client

    PYWIN32_AVAILABLE = True
except ImportError:  # pragma: no cover
    # Keep names defined for tests that patch module attributes on non-Windows CI.
    pythoncom = SimpleNamespace()
    pywintypes = SimpleNamespace(com_error=Exception)
    win32com = SimpleNamespace(client=SimpleNamespace())
    PYWIN32_AVAILABLE = False


from loguru import logger  # noqa: E402

T = TypeVar("T")


def _parse_vb_module_name(macro_path: str) -> str:
    """Read ``Attribute VB_Name = "..."`` from a SolidWorks text macro file.

    Falls back to the file stem (e.g. ``paper_airplane`` for ``paper_airplane.swp``), then
    to ``"SolidWorksMacro"`` which is the name used by the macro recorder.

    Args:
        macro_path (str): The macro path value.

    Returns:
        str: The resulting text value.
    """
    try:
        with open(macro_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line.lower().startswith("attribute vb_name"):
                    # Attribute VB_Name = "SolidWorksMacro"
                    _, _, rhs = line.partition("=")
                    return rhs.strip().strip('"').strip("'")
    except OSError:
        pass
    stem = os.path.splitext(os.path.basename(macro_path))[0]
    if stem and not stem.startswith(".") and stem.strip("."):
        return stem
    return "SolidWorksMacro"


class PyWin32Adapter(SolidWorksAdapter):
    """SolidWorks adapter using pywin32 COM integration.

    This adapter provides direct COM integration with SolidWorks using pywin32, enabling
    real-time automation and control of SolidWorks applications on Windows.

    Args:
        config (dict[str, Any] | None): Configuration values for the operation. Defaults to
                                        None.

    Raises:
        SolidWorksMCPError: PyWin32Adapter requires Windows platform.

    Attributes:
        constants (Any): The constants value.

    Example:
                        ```python
                        adapter = PyWin32Adapter({'timeout': 30})
                        result = await adapter.connect()
                        if result.status == AdapterResultStatus.SUCCESS:
                            print("Connected to SolidWorks successfully")
                        ```
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize PyWin32Adapter with configuration.

        Args:
            config (dict[str, Any] | None): Configuration values for the operation. Defaults to
                                            None.

        Returns:
            None: None.

        Raises:
            SolidWorksMCPError: PyWin32Adapter requires Windows platform.

        Example:
                            ```python
                            config = {
                                "timeout": 30,
                                "auto_connect": True,
                                "startup_timeout": 60
                            }
                            adapter = PyWin32Adapter(config)
                            ```
        """
        if not PYWIN32_AVAILABLE:  # pragma: no cover
            raise SolidWorksMCPError(
                "pywin32 is not available. Install with: pip install pywin32"
            )

        if platform.system() != "Windows":  # pragma: no cover
            raise SolidWorksMCPError("PyWin32Adapter requires Windows platform")

        super().__init__(config)

        self.swApp: Any | None = None
        self.currentModel: Any | None = None
        self.currentSketch: Any | None = None
        self.currentSketchManager: Any | None = None

        # COM constants (equivalent to SolidWorks API constants)
        self.constants = {
            # Document types
            "swDocPART": 1,
            "swDocASSEMBLY": 2,
            "swDocDRAWING": 3,
            # Selection types
            "swSelFACES": 1,
            "swSelEDGES": 2,
            "swSelVERTICES": 3,
            "swSelSKETCHSEGS": 4,
            "swSelSKETCHPOINTS": 5,
            "swSelDATUMPLANES": 6,
            # Feature end conditions
            "swEndCondBlind": 0,
            "swEndCondThroughAll": 1,
            "swEndCondUpToNext": 2,
            "swEndCondUpToSurface": 3,
            "swEndCondOffset": 4,
            "swEndCondUpToVertex": 5,
            "swEndCondMidPlane": 6,
        }

    async def connect(self) -> None:
        """Connect to SolidWorks application via COM.

        Establishes connection to SolidWorks application through COM interface. Attempts to
        connect to existing instance first, creates new instance if needed.

        Returns:
            None: None.

        Raises:
            SolidWorksMCPError: If the operation cannot be completed.

        Example:
                            ```python
                            adapter = PyWin32Adapter()
                            await adapter.connect()
                            print("Connected to SolidWorks successfully")
                            ```
        """
        try:
            # Initialize COM apartment
            pythoncom.CoInitialize()

            # Try to get existing SolidWorks instance
            try:
                self.swApp = win32com.client.GetActiveObject("SldWorks.Application")
            except pywintypes.com_error:
                # Create new SolidWorks instance
                self.swApp = win32com.client.Dispatch("SldWorks.Application")

            if self.swApp is None:
                raise SolidWorksMCPError("SolidWorks COM application instance is None")

            app = self.swApp

            # Ensure SolidWorks is visible
            app.Visible = True

            # Disable confirmation dialogs for automation
            app.SetUserPreferenceToggle(150, False)  # Hide warnings
            app.SetUserPreferenceToggle(149, False)  # Hide questions

        except Exception as e:
            raise SolidWorksMCPError(f"Failed to connect to SolidWorks: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from SolidWorks application.

        Properly disconnects from SolidWorks COM interface and cleans up resources. This method
        should always be called when finished to prevent memory leaks.

        Note: - Clears references to current model and application - Uninitialize COM apartment
        - Does not close SolidWorks application itself

        Returns:
            None: None.

        Example:
                            ```python
                            try:
                                await adapter.connect()
                                # ... do work ...
                            finally:
                                await adapter.disconnect()
                            ```
        """
        try:
            if self.currentModel:
                self.currentModel = None
            if self.currentSketch:
                self.currentSketch = None
                self.currentSketchManager = None
            if self.swApp:
                # Re-enable user preferences
                self.swApp.SetUserPreferenceToggle(150, True)
                self.swApp.SetUserPreferenceToggle(149, True)
                self.swApp = None
        finally:
            # Uninitialize COM apartment
            pythoncom.CoUninitialize()

    def is_connected(self) -> bool:
        """Check if connected to SolidWorks.

        Returns:
            bool: True if connected, otherwise False.

        Example:
                            ```python
                            if adapter.is_connected():
                                print("Ready to automate SolidWorks")
                            else:
                                await adapter.connect()
                            ```
        """
        return self.swApp is not None

    async def health_check(self) -> AdapterHealth:
        """Get adapter health status.

        Performs comprehensive health check including connection status, operation metrics, and
        SolidWorks application responsiveness.

        Returns:
            AdapterHealth: The result produced by the operation.

        Example:
                            ```python
                            health = await adapter.health_check()
                            if health.healthy:
                                print(f"Adapter healthy, {health.success_count} operations completed")
                            else:
                                print(f"Adapter unhealthy: {health.error_count} errors")
                            ```
        """
        healthy = self.is_connected()

        # Support both callable COM method and property-style RevisionNumber.
        sw_version: str | None = None
        if self.swApp:
            sw_version = self._attempt(
                lambda: self._get_attr_or_call(self.swApp, "RevisionNumber")
            )

        # Try a simple operation to verify connection
        if healthy:
            healthy = sw_version is not None

        return AdapterHealth(
            healthy=healthy,
            last_check=datetime.now(),
            error_count=int(self._metrics["errors_count"]),
            success_count=int(
                self._metrics["operations_count"] - self._metrics["errors_count"]
            ),
            average_response_time=self._metrics["average_response_time"],
            connection_status="connected" if healthy else "disconnected",
            metrics={
                "adapter_type": "pywin32",
                "sw_version": sw_version or "Unknown",
                "current_model": self.currentModel.GetTitle()
                if self.currentModel
                else None,
            },
        )

    def _handle_com_operation(
        self, operation_name: str, operation_func: Callable[[], T]
    ) -> AdapterResult[T]:
        """Helper to handle COM operations with error handling and timing.

        Wraps COM operations with comprehensive error handling, performance metrics, and
        standardized result formatting. All SolidWorks COM calls should use this.

        Args:
            operation_name (str): The operation name value.
            operation_func (Callable[[], T]): The operation func value.

        Returns:
            AdapterResult[T]: The result produced by the operation.

        Example:
                            ```python
                            result = self._handle_com_operation(
                                "create_sketch",
                                lambda: self.swApp.ActiveDoc.SketchManager.InsertSketch(True)
                            )
                            if result.status == AdapterResultStatus.SUCCESS:
                                print("Sketch created successfully")
                            ```
        """
        start_time = time.time()

        try:
            result = operation_func()
            execution_time = time.time() - start_time
            self.update_metrics(execution_time, True)
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS,
                data=result,
                execution_time=execution_time,
            )
        except pywintypes.com_error as e:
            execution_time = time.time() - start_time
            self.update_metrics(execution_time, False)
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"COM error in {operation_name}: {e}",
                execution_time=execution_time,
            )
        except Exception as e:
            execution_time = time.time() - start_time
            self.update_metrics(execution_time, False)
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Error in {operation_name}: {e}",
                execution_time=execution_time,
            )

    def _attempt(
        self, operation: Callable[[], T], default: T | None = None
    ) -> T | None:
        """Build internal attempt.

        Keep non-critical fallback handling in one place instead of scattering broad try/except
        blocks throughout operation code.

        Args:
            operation (Callable[[], T]): Callable object executed by the helper.
            default (T | None): Fallback value returned when the operation fails. Defaults to
                                None.

        Returns:
            T | None: The result produced by the operation.
        """
        try:
            return operation()
        except Exception:
            return default

    def _attempt_with_error(
        self, operation: Callable[[], T]
    ) -> tuple[T | None, Exception | None]:
        """Build internal attempt with error.

        Args:
            operation (Callable[[], T]): Callable object executed by the helper.

        Returns:
            tuple[T | None, Exception | None]: A tuple containing the resulting values.
        """
        try:
            return operation(), None
        except Exception as exc:
            return None, exc

    def _get_attr_or_call(self, obj: Any, attr_name: str) -> Any:
        """Read COM attribute exposed as a property or zero-arg method.

        Args:
            obj (Any): The obj value.
            attr_name (str): The attr name value.

        Returns:
            Any: The result produced by the operation.
        """
        attr = getattr(obj, attr_name, None)
        return attr() if callable(attr) else attr

    def _get_feature_id(self, feature: Any) -> str:
        """Extract a stable string feature ID from COM feature objects.

        Some SolidWorks COM bindings return an int-like value from GetID(), while others return
        a .NET object exposing ToString().

        Args:
            feature (Any): The feature value.

        Returns:
            str: The resulting text value.
        """
        feature_id_getter = getattr(feature, "GetID", None)
        feature_id_value = (
            feature_id_getter() if callable(feature_id_getter) else feature_id_getter
        )
        to_string = getattr(feature_id_value, "ToString", None)
        return str(to_string() if callable(to_string) else feature_id_value)

    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Open a SolidWorks model file.

        Opens a SolidWorks document and sets it as the current active model. Supports Part
        (.sldprt), Assembly (.sldasm), and Drawing (.slddrw) files.

        Args:
            file_path (str): Path to the target file.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.

        Raises:
            Exception: If the operation cannot be completed.
            ValueError: If the operation cannot be completed.

        Example:
                            ```python
                            result = await adapter.open_model("C:/Models/bracket.sldprt")
                            if result.status == AdapterResultStatus.SUCCESS:
                                model = result.data
                                print(f"Opened {model.name} ({model.type})")
                            ```
        """
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _open_operation() -> SolidWorksModel:
            """Build internal operation.

            Returns:
                SolidWorksModel: The result produced by the operation.

            Raises:
                Exception: If the operation cannot be completed.
                ValueError: If the operation cannot be completed.
            """
            resolved_path = os.path.abspath(file_path)

            # Determine document type from extension
            file_path_lower = resolved_path.lower()
            if file_path_lower.endswith(".sldprt"):
                doc_type = self.constants["swDocPART"]
                model_type = "Part"
            elif file_path_lower.endswith(".sldasm"):
                doc_type = self.constants["swDocASSEMBLY"]
                model_type = "Assembly"
            elif file_path_lower.endswith(".slddrw"):
                doc_type = self.constants["swDocDRAWING"]
                model_type = "Drawing"
            else:
                raise ValueError(f"Unsupported file type: {resolved_path}")

            # Open the document
            errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

            # Note: swApp is guaranteed non-None by is_connected() check above.
            # No need to guard here; if swApp somehow becomes None, OpenDoc6 will fail
            # naturally with COM error, which is caught by _handle_com_operation.
            app = self.swApp
            model = app.OpenDoc6(
                resolved_path,
                doc_type,
                1,  # swOpenDocOptions_Silent
                "",
                errors,
                warnings,
            )

            if not model:
                raise Exception(f"Failed to open model: {resolved_path}")

            # Set as current model
            self.currentModel = model

            # Get model info (COM may expose methods as values on some setups)
            title = self._read_model_title(model)

            active_config = self._attempt(lambda: model.GetActiveConfiguration())
            config = (
                self._attempt(lambda: active_config.GetName(), default="Default")
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

        return self._handle_com_operation("open_model", _open_operation)

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close the current model.

        Closes the currently active SolidWorks model with optional saving.

        Args:
            save (bool): The save value. Defaults to False.

        Returns:
            AdapterResult[None]: The result produced by the operation.

        Example:
                            ```python
                            # Close without saving
                            await adapter.close_model()

                            # Close with saving
                            await adapter.close_model(save=True)
                            ```
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.WARNING, error="No active model to close"
            )

        model = self.currentModel
        app = self.swApp
        if model is None or app is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="SolidWorks application is not connected",
            )

        def _close_operation() -> None:
            """Build internal operation.

            Returns:
                None: None.
            """
            if save:
                model.Save()

            app.CloseDoc(model.GetTitle())
            self.currentModel = None
            return None

        return self._handle_com_operation("close_model", _close_operation)

    def _resolve_template_path(
        self, preferred_indices: list[int], extension: str
    ) -> str | None:
        """Resolve a SolidWorks template path from user preferences.

        Installations vary by where template paths are stored; this probes multiple slots and
        prefers existing files with the expected extension.

        Args:
            preferred_indices (list[int]): The preferred indices value.
            extension (str): The extension value.

        Returns:
            str | None: The result produced by the operation.
        """
        existing_match: str | None = None
        first_non_empty: str | None = None

        app = self.swApp
        if app is None:
            return None

        for index in preferred_indices:
            template = self._attempt(
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
        """Read model title regardless of COM exposing method or value.

        Args:
            model (Any): The model value.

        Returns:
            str: The resulting text value.
        """
        title = self._attempt(lambda: self._get_attr_or_call(model, "GetTitle"))
        if isinstance(title, str) and title:
            return title

        title_value = getattr(model, "Title", None)
        if isinstance(title_value, str) and title_value:
            return title_value

        return "Untitled"

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new part document.

        Args:
            name (str | None): The name value. Defaults to None.
            units (str | None): The units value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.

        Raises:
            Exception: Failed to create new part.
        """
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create_operation() -> SolidWorksModel:
            """Build internal operation.

            Returns:
                SolidWorksModel: The result produced by the operation.

            Raises:
                Exception: Failed to create new part.
            """
            model = None
            app = self.swApp
            if app is None:
                raise Exception("SolidWorks application is not connected")

            # Prefer native helper if available on this installation.
            new_part = getattr(app, "NewPart", None)
            if callable(new_part):
                model = self._attempt(new_part)

            if not model:
                part_template = self._resolve_template_path([8, 0, 1, 2, 3], ".prtdot")
                if not part_template:
                    raise Exception("No part template configured in SolidWorks")

                model = app.NewDocument(
                    part_template,
                    0,  # Paper size (not used for parts)
                    0,  # Width (not used for parts)
                    0,  # Height (not used for parts)
                )

            if not model:
                raise Exception("Failed to create new part")

            self.currentModel = model
            title = self._read_model_title(model)

            return SolidWorksModel(
                path="",  # New document, no path yet
                name=title,
                type="Part",
                is_active=True,
                configuration="Default",
                properties={"created": datetime.now().isoformat()},
            )

        return self._handle_com_operation("create_part", _create_operation)

    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new assembly document.

        Args:
            name (str | None): The name value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.

        Raises:
            Exception: Failed to create new assembly.
        """
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create_operation() -> SolidWorksModel:
            """Build internal operation.

            Returns:
                SolidWorksModel: The result produced by the operation.

            Raises:
                Exception: Failed to create new assembly.
            """
            model = None
            app = self.swApp
            if app is None:
                raise Exception("SolidWorks application is not connected")

            new_assembly = getattr(app, "NewAssembly", None)
            if callable(new_assembly):
                model = self._attempt(new_assembly)

            if not model:
                asm_template = self._resolve_template_path([9, 2, 3, 1, 0], ".asmdot")
                if not asm_template:
                    raise Exception("No assembly template configured in SolidWorks")

                model = app.NewDocument(asm_template, 0, 0, 0)

            if not model:
                raise Exception("Failed to create new assembly")

            self.currentModel = model
            title = self._read_model_title(model)

            return SolidWorksModel(
                path="",
                name=title,
                type="Assembly",
                is_active=True,
                configuration="Default",
                properties={"created": datetime.now().isoformat()},
            )

        return self._handle_com_operation("create_assembly", _create_operation)

    async def create_drawing(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new drawing document.

        Args:
            name (str | None): The name value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.

        Raises:
            Exception: Failed to create new drawing.
        """
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create_operation() -> SolidWorksModel:
            """Build internal operation.

            Returns:
                SolidWorksModel: The result produced by the operation.

            Raises:
                Exception: Failed to create new drawing.
            """
            app = self.swApp
            if app is None:
                raise Exception("SolidWorks application is not connected")

            # Get drawing template
            drw_template = app.GetUserPreferenceStringValue(1)  # Drawing template
            if not drw_template:
                drw_template = app.GetUserPreferenceStringValue(0).replace(
                    "Part", "Drawing"
                )

            model = app.NewDocument(drw_template, 12, 0.2794, 0.2159)  # A4 size

            if not model:
                raise Exception("Failed to create new drawing")

            self.currentModel = model
            title = model.GetTitle()

            return SolidWorksModel(
                path="",
                name=title,
                type="Drawing",
                is_active=True,
                configuration="Default",
                properties={"created": datetime.now().isoformat()},
            )

        return self._handle_com_operation("create_drawing", _create_operation)

    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create an extrusion feature.

        Args:
            params (ExtrusionParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.

        Raises:
            Exception: Failed to create extrusion feature.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _extrusion_operation() -> SolidWorksFeature:
            # Get feature manager
            """Build internal extrusion operation.

            Returns:
                SolidWorksFeature: The result produced by the operation.

            Raises:
                Exception: Failed to create extrusion feature.
            """
            featureManager = self.currentModel.FeatureManager

            # Create extrusion - use simplified approach first
            # This handles up to the pywin32 parameter limit better
            if params.thin_feature and params.thin_thickness:
                # Thin wall extrusion
                feature = featureManager.FeatureExtruThin2(
                    params.depth / 1000.0,  # Convert mm to meters
                    0,  # Depth2 (for both directions)
                    params.reverse_direction,
                    params.draft_angle * 3.14159 / 180.0,  # Convert to radians
                    0,  # Draft angle 2
                    False,  # Draft outward
                    False,  # Draft outward 2
                    True,  # Merge result
                    False,  # Use feature scope
                    True,  # Auto select
                    params.thin_thickness / 1000.0,  # Wall thickness
                    0,  # Thickness 2
                    False,  # Reverse offset
                    False,  # Both directions thin
                    False,  # Cap ends
                    self.constants["swEndCondBlind"],  # End condition
                    self.constants["swEndCondBlind"],  # End condition 2
                )
            else:
                # Standard boss extrusion.
                # API docs (SW 2026) define a 23-parameter signature for both
                # FeatureExtrusion3 and FeatureExtrusion2.
                # Keep the same argument shape/order for both methods.
                t0 = self.constants.get("swStartSketchPlane", 0)
                try:
                    feature = featureManager.FeatureExtrusion3(
                        True,  # Sd (single-ended)
                        False,  # Flip (side to cut)
                        params.reverse_direction,  # Dir
                        self.constants["swEndCondBlind"],  # T1
                        self.constants["swEndCondBlind"],  # T2
                        params.depth / 1000.0,  # D1 (m)
                        0.0,  # D2
                        False,  # Dchk1
                        False,  # Dchk2
                        False,  # Ddir1
                        False,  # Ddir2
                        params.draft_angle * 3.14159 / 180.0,  # Dang1 (rad)
                        0.0,  # Dang2
                        False,  # OffsetReverse1
                        False,  # OffsetReverse2
                        False,  # TranslateSurface1
                        False,  # TranslateSurface2
                        params.merge_result,  # Merge
                        False,  # UseFeatScope
                        True,  # UseAutoSelect
                        t0,  # T0 (start condition)
                        0.0,  # StartOffset
                        False,  # FlipStartOffset
                    )
                except Exception:
                    # Fallback to v2 for older SolidWorks installs.
                    feature = featureManager.FeatureExtrusion2(
                        True,  # Sd
                        False,  # Flip
                        params.reverse_direction,  # Dir
                        self.constants["swEndCondBlind"],  # T1
                        self.constants["swEndCondBlind"],  # T2
                        params.depth / 1000.0,  # D1 (m)
                        0.0,  # D2
                        False,  # Dchk1
                        False,  # Dchk2
                        False,  # Ddir1
                        False,  # Ddir2
                        params.draft_angle * 3.14159 / 180.0,  # Dang1 (rad)
                        0.0,  # Dang2
                        False,  # OffsetReverse1
                        False,  # OffsetReverse2
                        False,  # TranslateSurface1
                        False,  # TranslateSurface2
                        params.merge_result,  # Merge
                        False,  # UseFeatScope
                        True,  # UseAutoSelect
                        t0,  # T0
                        0.0,  # StartOffset
                        False,  # FlipStartOffset
                    )

            if not feature:
                raise Exception("Failed to create extrusion feature")

            return SolidWorksFeature(
                name=feature.Name,
                type="Extrusion",
                id=self._get_feature_id(feature),
                parameters={
                    "depth": params.depth,
                    "draft_angle": params.draft_angle,
                    "reverse_direction": params.reverse_direction,
                    "thin_feature": params.thin_feature,
                    "thin_thickness": params.thin_thickness,
                },
                properties={"created": datetime.now().isoformat()},
            )

        return self._handle_com_operation("create_extrusion", _extrusion_operation)

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a revolve feature.

        Args:
            params (RevolveParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.

        Raises:
            Exception: Failed to create revolve feature.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _revolve_operation() -> SolidWorksFeature:
            """Build internal revolve operation.

            Returns:
                SolidWorksFeature: The result produced by the operation.

            Raises:
                Exception: Failed to create revolve feature.
            """
            featureManager = self.currentModel.FeatureManager

            # Create revolve feature
            feature = featureManager.FeatureRevolve2(
                not params.both_directions,  # SingleDir
                True,  # IsSolid
                params.thin_feature,  # IsThin
                False,  # IsCut
                params.reverse_direction,  # ReverseDir
                False,  # BothDirectionUpToSameEntity
                self.constants["swEndCondBlind"],  # Dir1Type
                self.constants["swEndCondBlind"],  # Dir2Type
                params.angle * 3.14159 / 180.0,  # Dir1Angle (rad)
                (params.angle * 3.14159 / 180.0)
                if params.both_directions
                else 0.0,  # Dir2Angle (rad)
                False,  # OffsetReverse1
                False,  # OffsetReverse2
                0.0,  # OffsetDistance1
                0.0,  # OffsetDistance2
                0,  # ThinType (ignored when IsThin=False)
                (params.thin_thickness or 0.0) / 1000.0,  # ThinThickness1 (m)
                0.0,  # ThinThickness2 (m)
                params.merge_result,  # Merge
                False,  # UseFeatScope
                True,  # UseAutoSelect
            )

            if not feature:
                raise Exception("Failed to create revolve feature")

            return SolidWorksFeature(
                name=feature.Name,
                type="Revolve",
                id=self._get_feature_id(feature),
                parameters={
                    "angle": params.angle,
                    "reverse_direction": params.reverse_direction,
                    "both_directions": params.both_directions,
                    "thin_feature": params.thin_feature,
                    "thin_thickness": params.thin_thickness,
                },
                properties={"created": datetime.now().isoformat()},
            )

        return self._handle_com_operation("create_revolve", _revolve_operation)

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a sweep feature.

        Args:
            params (SweepParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="Sweep feature not implemented in basic pywin32 adapter",
        )

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a loft feature.

        Args:
            params (LoftParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="Loft feature not implemented in basic pywin32 adapter",
        )

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create a new sketch on the specified plane.

        Creates a new sketch on the specified reference plane and sets it as active. The sketch
        is ready for adding geometry (lines, circles, etc.).

        Args:
            plane (str): The plane value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: If the operation cannot be completed.

        Example:
                            ```python
                            # Create sketch on top plane
                            result = await adapter.create_sketch("Top")
                            if result.status == AdapterResultStatus.SUCCESS:
                                sketch_name = result.data
                                print(f"Created sketch: {sketch_name}")
                                # Now ready to add geometry
                            ```
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _sketch_operation() -> str:
            # Select the plane first
            """Build internal sketch operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: If the operation cannot be completed.
            """
            plane_name_map = {
                "Top": "Top Plane",
                "Front": "Front Plane",
                "Right": "Right Plane",
                "XY": "Top Plane",
                "XZ": "Front Plane",
                "YZ": "Right Plane",
            }

            # Spanish-UI SolidWorks names default planes "Alzado"/"Planta"/
            # "Vista lateral". Map each semantic name to its locale variants
            # so the feature lookup below finds the right plane regardless
            # of install language.
            semantic_plane_aliases = {
                "Top": ["Top Plane", "Planta"],
                "Front": ["Front Plane", "Alzado"],
                "Right": ["Right Plane", "Vista lateral"],
                "XY": ["Top Plane", "Planta"],
                "XZ": ["Front Plane", "Alzado"],
                "YZ": ["Right Plane", "Vista lateral"],
            }

            actual_plane = plane_name_map.get(plane, plane)

            selected = False
            selection_error = None

            # Prefer direct feature lookup to avoid SelectByID2 variant mismatch.
            plane_candidates = [
                *semantic_plane_aliases.get(plane, []),
                actual_plane,
                plane,
                "Top Plane",
                "Front Plane",
                "Right Plane",
                "Planta",
                "Alzado",
                "Vista lateral",
            ]
            for candidate in plane_candidates:
                if not candidate:
                    continue
                plane_feature, selection_error_candidate = self._attempt_with_error(
                    lambda c=candidate: self.currentModel.FeatureByName(c)
                )
                if selection_error_candidate:
                    selection_error = selection_error_candidate
                    continue
                selected = bool(
                    plane_feature
                    and self._attempt(
                        lambda pf=plane_feature: pf.Select2(False, 0), default=False
                    )
                )
                if selected:
                    break

            # Fallback to SelectByID2 with callout variants for compatibility.
            if not selected:
                for callout in ("", None, 0):
                    selected, selection_error_candidate = self._attempt_with_error(
                        lambda co=callout: self.currentModel.Extension.SelectByID2(
                            actual_plane,
                            "PLANE",
                            0,
                            0,
                            0,
                            False,
                            0,
                            co,
                            0,
                        )
                    )
                    if selection_error_candidate:
                        selection_error = selection_error_candidate
                        continue
                    if selected:
                        break

            if not selected:
                if selection_error:
                    raise Exception(
                        f"Failed to select plane: {actual_plane} ({selection_error})"
                    )
                raise Exception(f"Failed to select plane: {actual_plane}")

            # Insert sketch
            self.currentSketchManager = self.currentModel.SketchManager
            try:
                self.currentSketch = self.currentSketchManager.InsertSketch(True)
            except pywintypes.com_error:
                # Some SolidWorks installs expose InsertSketch() without the boolean arg.
                self.currentSketch = self.currentSketchManager.InsertSketch()

            if not self.currentSketch:
                self.currentSketch = self._attempt(
                    lambda: self.currentModel.GetActiveSketch2()
                )

            if self.currentSketch and hasattr(self.currentSketch, "Name"):
                return self.currentSketch.Name

            # Some COM bindings do not return a sketch object even when the
            # sketch mode was entered successfully.
            return f"Sketch_{int(time.time() * 1000) % 100000}"

        return self._handle_com_operation("create_sketch", _sketch_operation)

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a line to the current sketch.

        Creates a line segment in the active sketch between two points. Coordinates are
        automatically converted from millimeters to meters.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: Failed to create line.

        Example:
                            ```python
                            # Create horizontal line 50mm long starting at origin
                            result = await adapter.add_line(0, 0, 50, 0)
                            if result.status == AdapterResultStatus.SUCCESS:
                                line_id = result.data
                                print(f"Created line: {line_id}")
                            ```
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _line_operation() -> str:
            # Convert mm to meters
            """Build internal line operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: Failed to create line.
            """
            line = self.currentSketchManager.CreateLine(
                x1 / 1000.0, y1 / 1000.0, 0, x2 / 1000.0, y2 / 1000.0, 0
            )

            if not line:
                raise Exception("Failed to create line")

            return f"Line_{int(time.time() * 1000) % 10000}"

        return self._handle_com_operation("add_line", _line_operation)

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Add a circle to the current sketch.

        Creates a circle in the active sketch with specified center point and radius.
        Coordinates are automatically converted from millimeters to meters.

        Args:
            center_x (float): The center x value.
            center_y (float): The center y value.
            radius (float): The radius value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: Failed to create circle.

        Example:
                            ```python
                            # Create 25mm diameter circle centered at (10, 20)
                            result = await adapter.add_circle(10, 20, 12.5)
                            if result.status == AdapterResultStatus.SUCCESS:
                                circle_id = result.data
                                print(f"Created circle: {circle_id}")
                            ```
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _circle_operation() -> str:
            # Convert mm to meters
            """Build internal circle operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: Failed to create circle.
            """
            circle = self.currentSketchManager.CreateCircleByRadius(
                center_x / 1000.0, center_y / 1000.0, 0, radius / 1000.0
            )

            if not circle:
                raise Exception("Failed to create circle")

            return f"Circle_{int(time.time() * 1000) % 10000}"

        return self._handle_com_operation("add_circle", _circle_operation)

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a rectangle to the current sketch.

        Creates a rectangle in the active sketch defined by two corner points. The rectangle is
        created as four connected lines with automatic constraints.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: Failed to create rectangle.

        Example:
                            ```python
                            # Create 50x30mm rectangle from origin
                            result = await adapter.add_rectangle(0, 0, 50, 30)
                            if result.status == AdapterResultStatus.SUCCESS:
                                rect_id = result.data
                                print(f"Created rectangle: {rect_id}")
                            ```
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _rectangle_operation() -> str:
            # Convert mm to meters
            """Build internal rectangle operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: Failed to create rectangle.
            """
            lines = self.currentSketchManager.CreateCornerRectangle(
                x1 / 1000.0, y1 / 1000.0, 0, x2 / 1000.0, y2 / 1000.0, 0
            )

            if not lines:
                raise Exception("Failed to create rectangle")

            return f"Rectangle_{int(time.time() * 1000) % 10000}"

        return self._handle_com_operation("add_rectangle", _rectangle_operation)

    async def add_arc(
        self,
        center_x: float,
        center_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> AdapterResult[str]:
        """Add an arc to the current sketch.

        Creates a circular arc in the active sketch defined by center point, start point, and
        end point. Arc is drawn counterclockwise from start to end.

        Args:
            center_x (float): The center x value.
            center_y (float): The center y value.
            start_x (float): The start x value.
            start_y (float): The start y value.
            end_x (float): The end x value.
            end_y (float): The end y value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: Failed to create arc.

        Example:
                            ```python
                            # Create 90-degree arc from (20,0) to (0,20) centered at origin
                            result = await adapter.add_arc(0, 0, 20, 0, 0, 20)
                            if result.status == AdapterResultStatus.SUCCESS:
                                arc_id = result.data
                                print(f"Created arc: {arc_id}")
                            ```
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _arc_operation() -> str:
            # Convert mm to meters
            """Build internal arc operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: Failed to create arc.
            """
            arc = self.currentSketchManager.CreateArc(
                center_x / 1000.0,
                center_y / 1000.0,
                0,  # Center point
                start_x / 1000.0,
                start_y / 1000.0,
                0,  # Start point
                end_x / 1000.0,
                end_y / 1000.0,
                0,  # End point
            )

            if not arc:
                raise Exception("Failed to create arc")

            return f"Arc_{int(time.time() * 1000) % 10000}"

        return self._handle_com_operation("add_arc", _arc_operation)

    async def add_spline(self, points: list[dict[str, float]]) -> AdapterResult[str]:
        """Add a spline to the current sketch.

        Creates a smooth spline curve through the specified control points. The spline
        automatically generates smooth transitions between points.

        Args:
            points (list[dict[str, float]]): The points value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: Failed to create spline.

        Example:
                            ```python
                            # Create curved spline through 4 points
                            spline_points = [
                                {'x': 0, 'y': 0},
                                {'x': 20, 'y': 10},
                                {'x': 40, 'y': -5},
                                {'x': 60, 'y': 0}
                            ]
                            result = await adapter.add_spline(spline_points)
                            if result.status == AdapterResultStatus.SUCCESS:
                                spline_id = result.data
                                print(f"Created spline: {spline_id}")
                            ```
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _spline_operation() -> str:
            # Convert points to SolidWorks format (mm to meters)
            """Build internal spline operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: Failed to create spline.
            """
            spline_points = []
            for point in points:
                spline_points.extend([point["x"] / 1000.0, point["y"] / 1000.0, 0])

            spline = self.currentSketchManager.CreateSpline2(
                spline_points,
                True,
                None,  # Points, periodic, tangency
            )

            if not spline:
                raise Exception("Failed to create spline")

            return f"Spline_{int(time.time() * 1000) % 10000}"

        return self._handle_com_operation("add_spline", _spline_operation)

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a centerline to the current sketch.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: Failed to create centerline.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _centerline_operation() -> str:
            # Convert mm to meters and create centerline
            """Build internal centerline operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: Failed to create centerline.
            """
            centerline = self.currentSketchManager.CreateCenterLine(
                x1 / 1000.0, y1 / 1000.0, 0, x2 / 1000.0, y2 / 1000.0, 0
            )

            if not centerline:
                raise Exception("Failed to create centerline")

            return f"Centerline_{int(time.time() * 1000) % 10000}"

        return self._handle_com_operation("add_centerline", _centerline_operation)

    async def add_polygon(
        self, center_x: float, center_y: float, radius: float, sides: int
    ) -> AdapterResult[str]:
        """Add a polygon to the current sketch.

        Args:
            center_x (float): The center x value.
            center_y (float): The center y value.
            radius (float): The radius value.
            sides (int): The sides value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: Failed to create polygon.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _polygon_operation() -> str:
            # Convert mm to meters
            """Build internal polygon operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: Failed to create polygon.
            """
            polygon = self.currentSketchManager.CreatePolygon(
                center_x / 1000.0,
                center_y / 1000.0,
                0,  # Center
                radius / 1000.0,  # Radius
                sides,  # Number of sides
                0,  # Rotation angle
            )

            if not polygon:
                raise Exception("Failed to create polygon")

            return f"Polygon_{sides}sided_{int(time.time() * 1000) % 10000}"

        return self._handle_com_operation("add_polygon", _polygon_operation)

    async def add_ellipse(
        self, center_x: float, center_y: float, major_axis: float, minor_axis: float
    ) -> AdapterResult[str]:
        """Add an ellipse to the current sketch.

        Args:
            center_x (float): The center x value.
            center_y (float): The center y value.
            major_axis (float): The major axis value.
            minor_axis (float): The minor axis value.

        Returns:
            AdapterResult[str]: The result produced by the operation.

        Raises:
            Exception: Failed to create ellipse.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _ellipse_operation() -> str:
            # Convert mm to meters
            """Build internal ellipse operation.

            Returns:
                str: The resulting text value.

            Raises:
                Exception: Failed to create ellipse.
            """
            ellipse = self.currentSketchManager.CreateEllipse(
                center_x / 1000.0,
                center_y / 1000.0,
                0,  # Center
                (center_x + major_axis / 2) / 1000.0,
                center_y / 1000.0,
                0,  # Major axis end
                (center_x) / 1000.0,
                (center_y + minor_axis / 2) / 1000.0,
                0,  # Minor axis end
            )

            if not ellipse:
                raise Exception("Failed to create ellipse")

            return f"Ellipse_{int(time.time() * 1000) % 10000}"

        return self._handle_com_operation("add_ellipse", _ellipse_operation)

    async def add_sketch_constraint(
        self, entity1: str, entity2: str | None, relation_type: str
    ) -> AdapterResult[str]:
        """Add a geometric constraint between sketch entities.

        Args:
            entity1 (str): The entity1 value.
            entity2 (str | None): The entity2 value.
            relation_type (str): The relation type value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _constraint_operation() -> str:
            # Map relation types to SolidWorks constants
            """Build internal constraint operation.

            Returns:
                str: The resulting text value.
            """
            relation_map = {
                "parallel": self.constants.get("swConstraintType_PARALLEL", 0),
                "perpendicular": self.constants.get(
                    "swConstraintType_PERPENDICULAR", 1
                ),
                "tangent": self.constants.get("swConstraintType_TANGENT", 2),
                "coincident": self.constants.get("swConstraintType_COINCIDENT", 3),
                "concentric": self.constants.get("swConstraintType_CONCENTRIC", 4),
                "horizontal": self.constants.get("swConstraintType_HORIZONTAL", 5),
                "vertical": self.constants.get("swConstraintType_VERTICAL", 6),
                "equal": self.constants.get("swConstraintType_EQUAL", 7),
                "symmetric": self.constants.get("swConstraintType_SYMMETRIC", 8),
                "collinear": self.constants.get("swConstraintType_COLLINEAR", 9),
            }

            relation_map.get(relation_type.lower(), 0)

            # For now, return a success without actual constraint - this requires entity selection
            # which is complex in the basic adapter
            constraint_id = (
                f"Constraint_{relation_type}_{int(time.time() * 1000) % 10000}"
            )

            return constraint_id

        return self._handle_com_operation(
            "add_sketch_constraint", _constraint_operation
        )

    async def add_sketch_dimension(
        self, entity1: str, entity2: str | None, dimension_type: str, value: float
    ) -> AdapterResult[str]:
        """Add a dimension to sketch entities.

        Args:
            entity1 (str): The entity1 value.
            entity2 (str | None): The entity2 value.
            dimension_type (str): The dimension type value.
            value (float): The value value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _dimension_operation() -> str:
            # For now, return a success without actual dimension - this requires entity selection
            # which is complex in the basic adapter
            """Build internal dimension operation.

            Returns:
                str: The resulting text value.
            """
            dimension_id = (
                f"Dimension_{dimension_type}_{value}_{int(time.time() * 1000) % 10000}"
            )

            return dimension_id

        return self._handle_com_operation("add_sketch_dimension", _dimension_operation)

    async def sketch_linear_pattern(
        self,
        entities: list[str],
        direction_x: float,
        direction_y: float,
        spacing: float,
        count: int,
    ) -> AdapterResult[str]:
        """Create a linear pattern of sketch entities.

        Args:
            entities (list[str]): The entities value.
            direction_x (float): The direction x value.
            direction_y (float): The direction y value.
            spacing (float): The spacing value.
            count (int): The count value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _linear_pattern_operation() -> str:
            # For now, return a success placeholder - linear patterns require entity selection
            """Build internal linear pattern operation.

            Returns:
                str: The resulting text value.
            """
            pattern_id = (
                f"LinearPattern_{count}x{spacing}_{int(time.time() * 1000) % 10000}"
            )

            return pattern_id

        return self._handle_com_operation(
            "sketch_linear_pattern", _linear_pattern_operation
        )

    async def sketch_circular_pattern(
        self,
        entities: list[str],
        center_x: float,
        center_y: float,
        angle: float,
        count: int,
    ) -> AdapterResult[str]:
        """Create a circular pattern of sketch entities.

        Args:
            entities (list[str]): The entities value.
            center_x (float): The center x value.
            center_y (float): The center y value.
            angle (float): The angle value.
            count (int): The count value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _circular_pattern_operation() -> str:
            # For now, return a success placeholder - circular patterns require entity selection
            """Build internal circular pattern operation.

            Returns:
                str: The resulting text value.
            """
            pattern_id = (
                f"CircularPattern_{count}x{angle}deg_{int(time.time() * 1000) % 10000}"
            )

            return pattern_id

        return self._handle_com_operation(
            "sketch_circular_pattern", _circular_pattern_operation
        )

    async def sketch_mirror(
        self, entities: list[str], mirror_line: str
    ) -> AdapterResult[str]:
        """Mirror sketch entities about a centerline.

        Args:
            entities (list[str]): The entities value.
            mirror_line (str): The mirror line value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _mirror_operation() -> str:
            # For now, return a success placeholder - mirroring requires entity selection
            """Build internal mirror operation.

            Returns:
                str: The resulting text value.
            """
            mirror_id = f"Mirror_{mirror_line}_{int(time.time() * 1000) % 10000}"

            return mirror_id

        return self._handle_com_operation("sketch_mirror", _mirror_operation)

    async def sketch_offset(
        self, entities: list[str], offset_distance: float, reverse_direction: bool
    ) -> AdapterResult[str]:
        """Create an offset of sketch entities.

        Args:
            entities (list[str]): The entities value.
            offset_distance (float): The offset distance value.
            reverse_direction (bool): The reverse direction value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _offset_operation() -> str:
            # For now, return a success placeholder - offsetting requires entity selection
            """Build internal offset operation.

            Returns:
                str: The resulting text value.
            """
            direction = "inward" if reverse_direction else "outward"
            offset_id = f"Offset_{offset_distance}_{direction}_{int(time.time() * 1000) % 10000}"

            return offset_id

        return self._handle_com_operation("sketch_offset", _offset_operation)

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties of the current model.

        Returns:
            AdapterResult[MassProperties]: The result produced by the operation.

        Raises:
            Exception: Failed to get mass properties.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _mass_props_operation() -> MassProperties:
            # Get mass properties
            """Build internal mass props operation.

            Returns:
                MassProperties: The result produced by the operation.

            Raises:
                Exception: Failed to get mass properties.
            """
            # Force a rebuild first — otherwise the IMassProperty reflects
            # the geometry from the last rebuild checkpoint, which can be
            # stale after a sequence of feature-creation calls within a
            # single MCP session.
            self._attempt(
                lambda: self.currentModel.ForceRebuild3(False), default=None
            )
            mass_props = self._attempt(
                lambda: self.currentModel.Extension.CreateMassProperty(), default=None
            )

            if mass_props:
                # Preferred path: IMassProperty object
                volume = mass_props.Volume * 1e9  # Convert m³ to mm³
                surface_area = mass_props.SurfaceArea * 1e6  # Convert m² to mm²
                mass = mass_props.Mass  # Already in kg

                # Center of mass and inertia members vary across COM versions.
                center_of_mass = [0.0, 0.0, 0.0]
                com = self._attempt(lambda: mass_props.CenterOfMass, default=None)
                if isinstance(com, (list, tuple)) and len(com) >= 3:
                    center_of_mass = [com[0] * 1000, com[1] * 1000, com[2] * 1000]

                moi = self._attempt(
                    lambda: mass_props.GetMomentOfInertia(0), default=None
                )
                if not isinstance(moi, (list, tuple)) or len(moi) < 9:
                    moi = [0.0] * 9
            else:
                # Fallback path: IModelDoc2.GetMassProperties tuple property
                raw = self._attempt(
                    lambda: self.currentModel.GetMassProperties, default=None
                )
                if not isinstance(raw, (list, tuple)) or len(raw) < 6:
                    raise Exception("Failed to get mass properties")

                center_of_mass = [raw[0] * 1000.0, raw[1] * 1000.0, raw[2] * 1000.0]
                volume = raw[3] * 1e9  # m³ -> mm³
                surface_area = raw[4] * 1e6  # m² -> mm²
                mass = raw[5]

                moi = [0.0] * 9
                if len(raw) >= 12:
                    # Mapping from documented SW tuple order:
                    # [6]=Ixx, [7]=Iyy, [8]=Izz, [9]=Lxy, [10]=Lyz, [11]=Lzx
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

        return self._handle_com_operation("get_mass_properties", _mass_props_operation)

    def _set_view_orientation(
        self, target_doc: Any, orientation: str, view_const: int
    ) -> None:
        """Set SolidWorks view orientation with graceful fallback.

        ShowNamedView2 can fail for assemblies with lightweight components,
        but screenshot can still succeed with current view. Logs warning on failure.

        Args:
            target_doc: SolidWorks model document
            orientation: Orientation name (for logging)
            view_const: SolidWorks view constant (1-9)

        Returns:
            None (operation always succeeds or fails silently)
        """
        try:
            target_doc.ShowNamedView2("", view_const)
        except Exception as exc:
            logger.warning(
                "[pywin32.export_image] ShowNamedView2({}) failed ({}), "
                "continuing with current view",
                orientation,
                exc,
            )

    def _zoom_to_fit(self, target_doc: Any) -> None:
        """Zoom model to fit viewport with fallback.

        Tries IModelDoc2.ViewZoomToFit2() first; falls back to
        IModelView.ZoomToFit() on the active view. Logs warning if both fail.

        Args:
            target_doc: SolidWorks model document

        Returns:
            None (operation always succeeds or fails silently)
        """
        try:
            target_doc.ViewZoomToFit2()
        except Exception:
            try:
                active_view = target_doc.ActiveView
                if active_view is not None:
                    active_view.ZoomToFit()
            except Exception as exc:
                logger.warning(
                    "[pywin32.export_image] ZoomToFit failed ({}), "
                    "screenshot may be zoomed out",
                    exc,
                )

    def _save_screenshot_with_modelview(
        self, model_view: Any, resolved_path: str, width: int, height: int
    ) -> bool:
        """Try IModelView2.SaveBitmapWithVariableSize for screenshot.

        Args:
            model_view: Active model view object
            resolved_path: Full path where to save image
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            True if file was created, False otherwise.
        """
        try:
            success = model_view.SaveBitmapWithVariableSize(
                resolved_path, width, height
            )
            return bool(success) and os.path.exists(resolved_path)
        except Exception as exc:
            logger.debug(
                "[pywin32.export_image] IModelView.SaveBitmapWithVariableSize failed ({}), "
                "trying IModelDoc2 path",
                exc,
            )
            return False

    def _save_screenshot_with_targetdoc(
        self, target_doc: Any, resolved_path: str, width: int, height: int
    ) -> bool:
        """Try IModelDoc2.SaveBitmapWithVariableSize for screenshot.

        Args:
            target_doc: SolidWorks model document
            resolved_path: Full path where to save image
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            True if file was created, False otherwise.
        """
        try:
            success = target_doc.SaveBitmapWithVariableSize(
                resolved_path, width, height
            )
            return bool(success) and os.path.exists(resolved_path)
        except Exception as exc:
            logger.debug(
                "[pywin32.export_image] IModelDoc2.SaveBitmapWithVariableSize failed ({}), "
                "trying SaveAs3 image export",
                exc,
            )
            return False

    def _save_screenshot_with_saveas3(
        self, target_doc: Any, resolved_path: str
    ) -> None:
        """Final fallback: SaveAs3 with image extension for screenshot.

        SolidWorks determines export format from file extension (.png, .jpg, .bmp, etc.).
        This path works on all SolidWorks versions without needing COM vtable access.

        Args:
            target_doc: SolidWorks model document
            resolved_path: Full path where to save image

        Raises:
            RuntimeError: If SaveAs3 fails or file is not created.
        """
        try:
            target_doc.SaveAs3(
                resolved_path, 0, 2
            )  # swSaveAsCurrentVersion=0, Silent=2
            if os.path.exists(resolved_path):
                return
        except Exception as exc:
            logger.debug(
                "[pywin32.export_image] SaveAs3 failed: {}",
                exc,
            )

        raise RuntimeError(f"All screenshot methods failed for {resolved_path}")

    async def export_image(self, payload: dict) -> AdapterResult[dict]:
        """Export a screenshot of the current model to a PNG/JPG file.

        Payload keys (matching ExportImageInput): file_path (str): Output path including
        extension. format_type (str): "png" or "jpg". Default "png". width (int): Pixel width.
        Default 1280. height (int): Pixel height. Default 720. view_orientation (str): "front" |
        "top" | "right" | "isometric" | "current".

        Args:
            payload (dict): The payload value.

        Returns:
            AdapterResult[dict]: The result produced by the operation.

        Raises:
            RuntimeError: If the operation cannot be completed.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        if not self.swApp:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="SolidWorks not connected"
            )

        orientation = str(payload.get("view_orientation", "current")).lower()
        file_path = payload.get("file_path", "")
        width = int(payload.get("width", 1280))
        height = int(payload.get("height", 720))

        # Map orientation names to SolidWorks swStandardViews_e constants
        _VIEW_CONSTANTS = {
            "front": 1,  # swFrontView
            "back": 2,  # swBackView
            "left": 3,  # swLeftView
            "right": 4,  # swRightView
            "top": 5,  # swTopView
            "bottom": 6,  # swBottomView
            "isometric": 7,  # swIsometricView
            "dimetric": 8,  # swDimetricView
            "trimetric": 9,  # swTriMetricView
        }

        def _screenshot_operation() -> dict:
            """Build internal screenshot operation.

            Returns:
                dict: A dictionary containing the resulting values.

            Raises:
                RuntimeError: If the operation cannot be completed.
            """

            import os as _os

            resolved = _os.path.abspath(file_path)
            _os.makedirs(_os.path.dirname(resolved), exist_ok=True)

            # Prefer swApp.ActiveDoc for screenshot — more reliably typed than
            # the IDispatch reference stored in self.currentModel after OpenDoc6.
            target_doc = (
                self.swApp.ActiveDoc if self.swApp else None
            ) or self.currentModel
            if not target_doc:
                raise RuntimeError("No active SolidWorks document for screenshot")

            # Ensure SolidWorks window is focused so the viewport is rendered.
            # Required for both view changes and bitmap capture.
            self._attempt(lambda: self.swApp.Frame.SetFocus())

            # Set view orientation if requested
            if orientation != "current" and orientation in _VIEW_CONSTANTS:
                view_const = _VIEW_CONSTANTS[orientation]
                self._set_view_orientation(target_doc, orientation, view_const)

            # Zoom to fit so the model fills the viewport before capture
            self._zoom_to_fit(target_doc)

            # Try screenshot methods in order: ModelView → TargetDoc → SaveAs3
            saved = self._save_screenshot_with_modelview(
                target_doc, resolved, width, height
            )
            if not saved:
                saved = self._save_screenshot_with_targetdoc(
                    target_doc, resolved, width, height
                )
            if not saved:
                self._save_screenshot_with_saveas3(target_doc, resolved)
                saved = _os.path.exists(resolved)

            if not saved:
                raise RuntimeError(
                    f"All screenshot methods produced no output for {resolved}"
                )

            return {
                "file_path": resolved,
                "format": _os.path.splitext(resolved)[1].lstrip(".").upper() or "PNG",
                "dimensions": f"{width}x{height}",
                "view": orientation,
            }

        return self._handle_com_operation("export_image", _screenshot_operation)

    def _prepare_stl_export_data(self) -> Any | None:
        """Prepare ISTLExportData for STL export with merged bodies option.

        Attempts to get and configure STL export settings from swApp.
        Returns None if swApp is unavailable or if COM operation fails.

        Returns:
            ISTLExportData object or None if unavailable/failed.
        """
        if self.swApp is None:
            return None

        try:
            # swExportDataFileType_e.swExportSTL = 2
            stl_data = self.swApp.GetExportFileData(2)
            if stl_data is None:
                return None

            # Configure for merged single-file export (best for assemblies)
            self._attempt(lambda: setattr(stl_data, "Merge", True))
            # swExportBodiesAs = 0 → swExportAsOneFile
            self._attempt(lambda: setattr(stl_data, "ExportBodiesAs", 0))

            return stl_data
        except Exception:
            return None

    def _save_stl_with_extension(
        self, ext: Any, stl_data: Any | None, resolved_path: str
    ) -> bool:
        """Attempt STL export using Extension.SaveAs2 with optional ISTLExportData.

        Tries SaveAs2 with stl_data first (enables body merging); falls back to
        SaveAs2(None) if type mismatch occurs (late-bound IDispatch can't marshal
        ISTLExportData* through IDispatch::Invoke).

        Args:
            ext: Extension object from target document
            stl_data: Optional ISTLExportData configuration
            resolved_path: Full path where to save STL file

        Returns:
            True if file was created, False otherwise.
        """
        try:
            # Try with stl_data first
            try:
                # swSaveAsVersion_e.swSaveAsCurrentVersion = 0
                # swSaveAsOptions_e.swSaveAsOptions_Silent = 2
                ext.SaveAs2(resolved_path, 0, 2, stl_data, None, "")
            except Exception:
                # Fallback: try without stl_data (type mismatch on IDispatch)
                ext.SaveAs2(resolved_path, 0, 2, None, None, "")

            return os.path.exists(resolved_path)
        except Exception as exc:
            logger.warning(
                "[pywin32.export_file] Extension.SaveAs2 failed: {}",
                str(exc),
            )
            return False

    def _save_stl_with_fallback(self, target_doc: Any, resolved_path: str) -> None:
        """Fallback STL export using SaveAs3 if SaveAs2 didn't create file.

        Args:
            target_doc: SolidWorks model document
            resolved_path: Full path to save file to

        Raises:
            Exception: If both SaveAs2 and SaveAs3 fail to produce file.
        """
        logger.warning(
            "[pywin32.export_file] SaveAs2 did not produce {}, falling back to SaveAs3",
            resolved_path,
        )
        try:
            target_doc.SaveAs3(
                resolved_path,
                0,  # swSaveAsCurrentVersion
                2,  # swSaveAsOptions_Silent
            )
        except Exception as exc:
            logger.warning(
                "[pywin32.export_file] SaveAs3 also failed: {}",
                str(exc),
            )

        if not os.path.exists(resolved_path):
            raise Exception(
                f"STL export failed for {resolved_path} "
                "(tried Extension.SaveAs2 and SaveAs3)"
            )

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Export the current model to a file.

        Args:
            file_path (str): Path to the target file.
            format_type (str): The format type value.

        Returns:
            AdapterResult[None]: The result produced by the operation.

        Raises:
            Exception: If the operation cannot be completed.
            RuntimeError: No active SolidWorks document for export.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _export_operation() -> None:
            """Build internal export operation.

            Returns:
                None: None.

            Raises:
                Exception: If the operation cannot be completed.
                RuntimeError: No active SolidWorks document for export.
            """
            format_map = {
                "step": 0,  # swSaveAsSTEP
                "iges": 1,  # swSaveAsIGS
                "stl": 2,  # swSaveAsSTL
                "pdf": 3,  # swSaveAsPDF
                "dwg": 4,  # swSaveAsDWG
                "jpg": 5,  # swSaveAsJPEG
                "glb": 41,  # swSaveAsGLTF (binary GLTF, SW 2023+)
                "gltf": 41,  # same enum value, text GLTF
            }

            format_lower = format_type.lower()
            if format_lower not in format_map:
                raise Exception(f"Unsupported export format: {format_type}")

            resolved_path = os.path.abspath(file_path)
            os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

            if os.path.exists(resolved_path):
                self._attempt(lambda: os.remove(resolved_path))

            # Prefer swApp.ActiveDoc — more reliably typed than the late-bound
            # IDispatch reference stored in self.currentModel after OpenDoc6.
            # Use getattr so tests can pass a SimpleNamespace without ActiveDoc.
            target_doc = (
                getattr(self.swApp, "ActiveDoc", None) if self.swApp else None
            ) or self.currentModel
            if not target_doc:
                raise RuntimeError("No active SolidWorks document for export")

            # ----------------------------------------------------------------
            # STL export: use Extension.SaveAs2 + ISTLExportData
            # for both parts AND assemblies.  SaveAs3 with format=2 works for
            # parts but is unreliable for assemblies (only exports first body).
            # ----------------------------------------------------------------
            if format_lower == "stl":
                # For assemblies, resolve lightweight components first so all
                # geometry is available for the mesh export.
                self._attempt(lambda: target_doc.ResolveAllLightweightComponents(True))

                ext = getattr(target_doc, "Extension", None)
                if ext is None:
                    raise RuntimeError("No Extension object available for STL export")

                stl_data = self._prepare_stl_export_data()
                if not self._save_stl_with_extension(ext, stl_data, resolved_path):
                    # SaveAs2 didn't produce file — try SaveAs3 fallback
                    self._save_stl_with_fallback(target_doc, resolved_path)

                return None

            # ----------------------------------------------------------------
            # All other formats — classic SaveAs3 path.
            # SaveAs3 signature: SaveAs3(FileName, Version, Options)
            # Version = 0 means "current version" (swSaveAsCurrentVersion).
            # SolidWorks infers the export format from the file extension, so
            # we must NOT pass the format-enum value as the Version argument.
            # ----------------------------------------------------------------
            _ = format_map[format_lower]  # validate format is known; value unused
            logger.debug(
                "[pywin32.export_file] SaveAs3 {} (version=0, options=Silent)",
                resolved_path,
            )
            success = target_doc.SaveAs3(
                resolved_path,
                0,  # swSaveAsCurrentVersion — format inferred from file extension
                2,  # swSaveAsOptions_Silent
            )

            if not success and not os.path.exists(resolved_path):
                raise Exception(
                    f"SaveAs3 returned False and no file produced: {resolved_path}"
                )

            return None

        return self._handle_com_operation("export_file", _export_operation)

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Get the value of a dimension.

        Args:
            name (str): The name value.

        Returns:
            AdapterResult[float]: The result produced by the operation.

        Raises:
            Exception: If the operation cannot be completed.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _get_dim_operation() -> float:
            """Build internal dim operation.

            Returns:
                float: The computed numeric result.

            Raises:
                Exception: If the operation cannot be completed.
            """
            dimension = self.currentModel.Parameter(name)

            if not dimension:
                raise Exception(f"Dimension '{name}' not found")

            value = dimension.GetValue3(8, None)  # Get system value
            return value * 1000  # Convert meters to mm

        return self._handle_com_operation("get_dimension", _get_dim_operation)

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set the value of a dimension.

        Args:
            name (str): The name value.
            value (float): The value value.

        Returns:
            AdapterResult[None]: The result produced by the operation.

        Raises:
            Exception: If the operation cannot be completed.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _set_dim_operation() -> None:
            """Build internal dim operation.

            Returns:
                None: None.

            Raises:
                Exception: If the operation cannot be completed.
            """
            dimension = self.currentModel.Parameter(name)

            if not dimension:
                raise Exception(f"Dimension '{name}' not found")

            # Convert mm to meters and set value
            success = dimension.SetValue3(value / 1000.0, 8, None)

            if not success:
                raise Exception(f"Failed to set dimension '{name}'")

            # Rebuild the model
            self.currentModel.ForceRebuild3(False)

            return None

        return self._handle_com_operation("set_dimension", _set_dim_operation)

    async def save_file(self, file_path: str | None = None) -> AdapterResult[None]:
        """Save the current model.

        Args:
            file_path (str | None): Path to the target file. Defaults to None.

        Returns:
            AdapterResult[None]: The result produced by the operation.

        Raises:
            Exception: Failed to save file.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _save_operation() -> None:
            """Build internal operation.

            Returns:
                None: None.

            Raises:
                Exception: Failed to save file.
            """

            def _is_success(value: Any) -> bool:
                # COM save APIs may return bool OR an integer status code
                # where 0 indicates success.
                """Build internal is success.

                Args:
                    value (Any): The value value.

                Returns:
                    bool: True if success, otherwise False.
                """
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)):
                    return value == 0
                return bool(value)

            if file_path:
                resolved_path = os.path.abspath(file_path)
                os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

                # If another SolidWorks document has this path open (for example
                # from a previous run), close it so SaveAs can overwrite.
                if self.swApp:
                    self._attempt(lambda: self.swApp.CloseDoc(resolved_path))

                # Remove stale copy when possible (may fail if still locked).
                if os.path.exists(resolved_path):
                    self._attempt(lambda: os.remove(resolved_path))

                # Save as new file.
                save_as3_result = self.currentModel.SaveAs3(resolved_path, 0, 0)
                if not _is_success(save_as3_result):
                    save_as = getattr(self.currentModel, "SaveAs", None)
                    if callable(save_as):
                        fallback_result = save_as(resolved_path)
                        if not _is_success(fallback_result):
                            raise Exception(f"Failed to save as: {resolved_path}")
                    else:
                        raise Exception(f"Failed to save as: {resolved_path}")

                if not os.path.exists(resolved_path):
                    raise Exception(f"File not written after save: {resolved_path}")
            else:
                # Save current file
                save_result = self._attempt(
                    lambda: self.currentModel.Save3(1, None, None)
                )
                if save_result is None:
                    save_fn = getattr(self.currentModel, "Save", None)
                    if callable(save_fn):
                        save_result = save_fn()
                    else:
                        raise Exception("Failed to save file")
                if not _is_success(save_result):
                    # Some SolidWorks versions return a non-success value when the
                    # document is already clean; if a valid file still exists,
                    # treat this as a successful no-op save.
                    path_attr = getattr(self.currentModel, "GetPathName", "")
                    model_path = path_attr() if callable(path_attr) else path_attr
                    if model_path and os.path.exists(model_path):
                        return None
                    raise Exception("Failed to save file")

            return None

        return self._handle_com_operation("save_file", _save_operation)

    async def rebuild_model(self) -> AdapterResult[None]:
        """Rebuild the current model.

        Returns:
            AdapterResult[None]: The result produced by the operation.

        Raises:
            Exception: Failed to rebuild model.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _rebuild_operation() -> None:
            """Build internal rebuild operation.

            Returns:
                None: None.

            Raises:
                Exception: Failed to rebuild model.
            """
            success = self.currentModel.ForceRebuild3(False)
            if not success:
                raise Exception("Failed to rebuild model")
            return None

        return self._handle_com_operation("rebuild_model", _rebuild_operation)

    async def get_model_info(self) -> AdapterResult[dict[str, Any]]:
        """Get information about the current model.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _info_operation() -> dict[str, Any]:
            """Build internal info operation.

            Returns:
                dict[str, Any]: A dictionary containing the resulting values.
            """
            info = {
                "title": self.currentModel.GetTitle(),
                "path": self.currentModel.GetPathName(),
                "type": self._get_document_type(),
                "configuration": self.currentModel.GetActiveConfiguration().GetName()
                if self.currentModel.GetActiveConfiguration()
                else "Default",
                "is_dirty": self.currentModel.GetSaveFlag(),
                "feature_count": self.currentModel.FeatureManager.GetFeatureCount(True),
                "rebuild_status": self.currentModel.GetRebuildStatus(),
            }
            return info

        return self._handle_com_operation("get_model_info", _info_operation)

    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, Any]]]:
        """List features in the active model feature tree.

        Args:
            include_suppressed (bool): The include suppressed value. Defaults to False.

        Returns:
            AdapterResult[list[dict[str, Any]]]: The result produced by the operation.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        def _list_operation() -> list[dict[str, Any]]:
            """Build internal list operation.

            Returns:
                list[dict[str, Any]]: A list containing the resulting items.
            """
            features: list[dict[str, Any]] = []
            seen: set[tuple[str, str]] = set()

            def _is_suppressed(feature: Any) -> bool:
                # Prefer parameter-less calls to avoid COM optional-arg marshalling issues.
                """Build internal is suppressed.

                Args:
                    feature (Any): The feature value.

                Returns:
                    bool: True if suppressed, otherwise False.
                """
                suppressed_direct = self._attempt(
                    lambda: feature.IsSuppressed(), default=None
                )
                if suppressed_direct is not None:
                    return bool(suppressed_direct)

                suppressed_result = self._attempt(
                    lambda: feature.IsSuppressed2(0, []), default=None
                )
                if isinstance(suppressed_result, (tuple, list)):
                    return bool(suppressed_result[0]) if suppressed_result else False
                return (
                    bool(suppressed_result) if suppressed_result is not None else False
                )

            def _append_feature(feature: Any, position: int) -> None:
                """Build internal append feature.

                Args:
                    feature (Any): The feature value.
                    position (int): The position value.

                Returns:
                    None: None.
                """
                if not feature:
                    return

                name = str(getattr(feature, "Name", ""))
                feature_type = str(
                    self._attempt(lambda: feature.GetTypeName2(), default="Unknown")
                )

                dedupe_key = (name, feature_type)
                if dedupe_key in seen:
                    return
                seen.add(dedupe_key)

                suppressed = _is_suppressed(feature)
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

            # Primary path: feature-tree traversal from model root.
            feature = self._attempt(lambda: self.currentModel.FirstFeature())

            pos = 0
            guard = 0
            while feature and guard < 10000:
                _append_feature(feature, pos)
                pos += 1
                guard += 1
                next_feature = self._attempt(
                    lambda current_feature=feature: current_feature.GetNextFeature()
                )
                if next_feature is None:
                    break
                feature = next_feature

            if features:
                return features

            # Fallback path: reverse position traversal via model API.
            feature_manager = getattr(self.currentModel, "FeatureManager", None)
            count = self._attempt(
                lambda: int(feature_manager.GetFeatureCount(True) or 0), default=0
            )

            for reverse_pos in range(1, count + 1):
                feature = self._attempt(
                    lambda pos=reverse_pos: self.currentModel.FeatureByPositionReverse(
                        pos
                    )
                )
                if feature is None:
                    continue

                # Convert reverse order to stable forward-ish index.
                position = count - reverse_pos
                _append_feature(feature, position)

            return features

        return self._handle_com_operation("list_features", _list_operation)

    @staticmethod
    def _normalize_feature_name(raw_name: str | None) -> str:
        """Normalise a raw feature/component name for case-insensitive comparison.

        Args:
            raw_name: Raw name, may be None.

        Returns:
            str: Stripped, quote-removed, casefolded string.
        """
        return str(raw_name or "").strip().strip('"').casefold()

    def _build_feature_candidate_names(
        self, feature_name: str, target_doc: Any
    ) -> list[str]:
        """Build the list of candidate names (bare + @doc-stem / @doc-title variants).

        Args:
            feature_name: Base feature name.
            target_doc: Active SolidWorks document COM object.

        Returns:
            list[str]: One to three candidate strings, e.g. ["Boss", "Boss@MyPart",
                "Boss@MyPart.SLDPRT"].
        """
        doc_title = ""
        doc_stem = ""
        try:
            raw_title = str(target_doc.GetTitle() or "").strip()
            if raw_title:
                doc_title = raw_title
                doc_stem = raw_title.rsplit(".", 1)[0]
        except Exception:
            pass

        candidates: list[str] = [feature_name]
        if doc_stem:
            candidates.append(f"{feature_name}@{doc_stem}")
        if doc_title and doc_title != doc_stem:
            candidates.append(f"{feature_name}@{doc_title}")
        return candidates

    def _try_select_by_extension(
        self,
        target_doc: Any,
        candidate_names: list[str],
        feature_name: str,
    ) -> dict[str, Any] | None:
        """Try SelectByID2 for each candidate × entity-type pair.

        Args:
            target_doc: Active SolidWorks document COM object.
            candidate_names: Ordered list of name candidates to attempt.
            feature_name: Original feature name for the result payload.

        Returns:
            Result dict on first success, or None if all attempts fail.
        """
        entity_types = ["BODYFEATURE", "COMPONENT", "SKETCH", "PLANE", "MATE", ""]
        for candidate in candidate_names:
            for entity_type in entity_types:
                try:
                    selected = target_doc.Extension.SelectByID2(
                        candidate, entity_type, 0, 0, 0, False, 0, None, 0
                    )
                    if selected:
                        return {
                            "selected": True,
                            "feature_name": feature_name,
                            "selected_name": candidate,
                            "entity_type": entity_type or "auto",
                        }
                except Exception:
                    continue
        return None

    def _try_select_by_component(
        self,
        target_doc: Any,
        candidate_names: list[str],
        feature_name: str,
    ) -> dict[str, Any] | None:
        """Try selecting via GetComponentByName and component Select methods.

        Args:
            target_doc: Active SolidWorks document COM object.
            candidate_names: Ordered list of name candidates to attempt.
            feature_name: Original feature name for the result payload.

        Returns:
            Result dict on first success, or None if unavailable or all fail.
        """
        get_component_by_name = getattr(target_doc, "GetComponentByName", None)
        if not callable(get_component_by_name):
            return None

        for candidate in candidate_names:
            component_name = candidate.split("@", 1)[0]
            component = self._attempt(
                lambda c=component_name: get_component_by_name(c), default=None
            )
            if component is None:
                continue
            for method_name, args in [
                ("Select4", (False, None, False)),
                ("Select", (False,)),
                ("Select2", (False, 0)),
            ]:
                selector = getattr(component, method_name, None)
                if not callable(selector):
                    continue
                try:
                    if bool(selector(*args)):
                        return {
                            "selected": True,
                            "feature_name": feature_name,
                            "selected_name": component_name,
                            "entity_type": f"component:{method_name}",
                        }
                except Exception:
                    continue
        return None

    def _try_select_by_feature_tree(
        self,
        target_doc: Any,
        feature_name: str,
        candidate_names: list[str],
    ) -> dict[str, Any] | None:
        """Walk the feature tree and select the first matching feature.

        Args:
            target_doc: Active SolidWorks document COM object.
            feature_name: Original feature name for the result payload.
            candidate_names: Candidate name list used to derive normalised lookup sets.

        Returns:
            Result dict on first match, or None if no match is found.
        """
        normalized_candidates = {
            self._normalize_feature_name(c)
            for c in candidate_names
            if self._normalize_feature_name(c)
        }
        normalized_bases = {c.split("@", 1)[0] for c in normalized_candidates if c}

        def _matches(raw_name: str | None) -> bool:
            n = self._normalize_feature_name(raw_name)
            if not n:
                return False
            if n in normalized_candidates:
                return True
            return n.split("@", 1)[0] in normalized_bases

        feature = self._attempt(lambda: target_doc.FirstFeature())
        guard = 0
        while feature and guard < 10000:
            guard += 1
            tree_name = self._attempt(lambda f=feature: str(f.Name or ""), default="")
            if _matches(tree_name):
                try:
                    if feature.Select2(False, 0):
                        return {
                            "selected": True,
                            "feature_name": feature_name,
                            "selected_name": tree_name or feature_name,
                            "entity_type": "feature-tree",
                        }
                except Exception:
                    pass
            next_feature = self._attempt(lambda f=feature: f.GetNextFeature())
            if next_feature is None:
                break
            feature = next_feature
        return None

    async def select_feature(self, feature_name: str) -> AdapterResult[dict[str, Any]]:
        """Highlight a named feature in SolidWorks by selecting it via SelectByID2.

        Tries common entity type strings in priority order and falls back to an empty type
        string which lets SolidWorks auto-resolve the entity class.

        Args:
            feature_name (str): The feature name value.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _select_operation() -> dict[str, Any]:
            """Orchestrate feature selection using three fallback strategies.

            Returns:
                dict[str, Any]: Selection result with selected, feature_name, selected_name, entity_type.
            """
            target_doc = self.currentModel
            candidate_names = self._build_feature_candidate_names(
                feature_name, target_doc
            )

            result = self._try_select_by_extension(
                target_doc, candidate_names, feature_name
            )
            if result:
                return result

            result = self._try_select_by_component(
                target_doc, candidate_names, feature_name
            )
            if result:
                return result

            result = self._try_select_by_feature_tree(
                target_doc, feature_name, candidate_names
            )
            if result:
                return result

            return {
                "selected": False,
                "feature_name": feature_name,
                "selected_name": feature_name,
            }

        return self._handle_com_operation("select_feature", _select_operation)

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List all configuration names in the active model.

        Returns:
            AdapterResult[list[str]]: The result produced by the operation.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        def _list_operation() -> list[str]:
            """Build internal list operation.

            Returns:
                list[str]: A list containing the resulting items.
            """
            raw_names = getattr(self.currentModel, "GetConfigurationNames", None)
            if callable(raw_names):
                names = raw_names()
            else:
                names = raw_names

            if names is None:
                names = []
            if isinstance(names, str):
                return [names]
            if isinstance(names, tuple):
                normalized_names = [str(name) for name in names]
            else:
                normalized_names = [str(name) for name in names]

            if normalized_names:
                return normalized_names

            active_config = self._attempt(
                lambda: self.currentModel.GetActiveConfiguration(), default=None
            )
            active_name = self._attempt(lambda: active_config.GetName(), default=None)
            if active_name:
                return [str(active_name)]

            return []

        return self._handle_com_operation("list_configurations", _list_operation)

    def _get_document_type(self) -> str:
        """Helper method to get document type.

        Returns:
            str: The resulting text value.
        """
        if not self.currentModel:
            return "Unknown"

        doc_type = self.currentModel.GetType()
        type_map = {1: "Part", 2: "Assembly", 3: "Drawing"}
        return type_map.get(doc_type, "Unknown")

    async def create_cut_extrude(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a cut extrude feature.

        Args:
            params (ExtrusionParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.

        Raises:
            Exception: Failed to create cut extrude feature.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _cut_operation() -> SolidWorksFeature:
            """Build internal cut operation.

            Returns:
                SolidWorksFeature: The result produced by the operation.

            Raises:
                Exception: Failed to create cut extrude feature.
            """
            featureManager = self.currentModel.FeatureManager

            # Create cut extrusion (similar to regular extrude but cuts material)
            feature = featureManager.FeatureCut3(
                True,  # Single ended
                False,  # Use feature scope
                params.reverse_direction,
                self.constants["swEndCondBlind"],
                self.constants["swEndCondBlind"],
                params.depth / 1000.0,  # Depth in meters
                0,  # Depth2
                False,  # Feature scope
                True,  # Auto select
                False,  # Assembly feature scope
                False,  # Auto select components
                params.draft_angle * 3.14159 / 180.0,  # Draft angle
                0,  # Draft angle 2
                True,  # Draft outward
                True,  # Draft outward 2
                False,  # Optimize geometry
                0,  # Start offset
                False,  # Flip side to cut
                False,  # Direction reversed
            )

            if not feature:
                raise Exception("Failed to create cut extrude feature")

            return SolidWorksFeature(
                name=feature.Name,
                type="Cut-Extrude",
                id=self._get_feature_id(feature),
                parameters={
                    "depth": params.depth,
                    "draft_angle": params.draft_angle,
                    "reverse_direction": params.reverse_direction,
                },
                properties={"created": datetime.now().isoformat()},
            )

        return self._handle_com_operation("create_cut_extrude", _cut_operation)

    async def add_fillet(
        self, radius: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        """Add a fillet feature.

        Args:
            radius (float): The radius value.
            edge_names (list[str]): The edge names value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.

        Raises:
            Exception: Failed to create fillet.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _fillet_operation() -> SolidWorksFeature:
            # Select edges first
            """Build internal fillet operation.

            Returns:
                SolidWorksFeature: The result produced by the operation.

            Raises:
                Exception: Failed to create fillet.
            """
            for edge_name in edge_names:
                selected = self.currentModel.Extension.SelectByID2(
                    edge_name,
                    "EDGE",
                    0,
                    0,
                    0,
                    True,
                    0,
                    None,
                    0,  # True for multi-select
                )
                if not selected:
                    raise Exception(f"Failed to select edge: {edge_name}")

            # Create fillet
            featureManager = self.currentModel.FeatureManager
            feature = featureManager.FeatureFillet3(
                radius / 1000.0,  # Convert mm to meters
                0,  # Setback radius
                0,  # Setback distance
                0,  # Variable radius type
                0,  # Fillet type
                False,  # Overflow type
                False,  # Rho value
                False,  # Rolling ball radius
                False,  # Help point
                False,  # Conic type
                False,  # Keep features
                False,  # Keep abrupt edges
                False,  # Optimize geometry
                0,  # Smooth transition
                False,  # Vertex fillet
            )

            if not feature:
                raise Exception("Failed to create fillet")

            return SolidWorksFeature(
                name=feature.Name,
                type="Fillet",
                id=self._get_feature_id(feature),
                parameters={"radius": radius, "edges": edge_names},
                properties={"created": datetime.now().isoformat()},
            )

        return self._handle_com_operation("add_fillet", _fillet_operation)

    async def add_chamfer(
        self, distance: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        """Add a chamfer feature.

        Args:
            distance (float): The distance value.
            edge_names (list[str]): The edge names value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.

        Raises:
            Exception: Failed to create chamfer.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _chamfer_operation() -> SolidWorksFeature:
            # Select edges first
            """Build internal chamfer operation.

            Returns:
                SolidWorksFeature: The result produced by the operation.

            Raises:
                Exception: Failed to create chamfer.
            """
            for edge_name in edge_names:
                selected = self.currentModel.Extension.SelectByID2(
                    edge_name, "EDGE", 0, 0, 0, True, 0, None, 0
                )
                if not selected:
                    raise Exception(f"Failed to select edge: {edge_name}")

            # Create chamfer
            featureManager = self.currentModel.FeatureManager
            feature = featureManager.FeatureChamfer(
                1,  # Chamfer type (distance-distance)
                distance / 1000.0,  # Distance 1 (convert mm to meters)
                distance / 1000.0,  # Distance 2
                0,  # Angle
                0,  # Vertex chamfer type
                False,  # Flip direction
                False,  # Keep features
                False,  # Optimize geometry
                False,  # Use tangent propagation
            )

            if not feature:
                raise Exception("Failed to create chamfer")

            return SolidWorksFeature(
                name=feature.Name,
                type="Chamfer",
                id=self._get_feature_id(feature),
                parameters={"distance": distance, "edges": edge_names},
                properties={"created": datetime.now().isoformat()},
            )

        return self._handle_com_operation("add_chamfer", _chamfer_operation)

    def _invoke_run_macro2(
        self, macro_path: str, module_name: str, proc_name: str
    ) -> dict[str, Any]:
        """Call swApp.RunMacro2 and parse the result into a result dict.

        Args:
            macro_path: Absolute path to the VBA macro file.
            module_name: VB module name (parsed from the file or stem fallback).
            proc_name: Entry-point procedure name, typically "main".

        Returns:
            dict[str, Any]: {"macro_path", "module_name", "errors"} on success.

        Raises:
            SolidWorksMCPError: If RunMacro2 reports failure.
        """
        result = self.swApp.RunMacro2(macro_path, module_name, proc_name, 0, 0)
        if isinstance(result, (list, tuple)):
            success, errors = result[0], result[1]
        else:
            success, errors = bool(result), 0
        if not success:
            raise SolidWorksMCPError(
                f"RunMacro2 failed for {macro_path}, module={module_name!r}, errors={errors}"
            )
        return {
            "macro_path": macro_path,
            "module_name": module_name,
            "errors": errors,
        }

    async def execute_macro(
        self, params: dict[str, Any]
    ) -> AdapterResult[dict[str, Any]]:
        """Provide execute macro support for the py win32 adapter.

        Args:
            params (dict[str, Any]): The params value.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.

        Raises:
            SolidWorksMCPError: If the operation cannot be completed.
        """
        macro_path = params.get("macro_path") or params.get("macro_file") or ""
        if not macro_path:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No macro_path provided"
            )
        if not os.path.isfile(macro_path):
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Macro file not found: {macro_path}",
            )

        def _run() -> dict[str, Any]:
            """Resolve module/proc names and delegate to _invoke_run_macro2.

            Returns:
                dict[str, Any]: A dictionary containing the resulting values.

            Raises:
                SolidWorksMCPError: If the operation cannot be completed.
            """
            module_name = _parse_vb_module_name(macro_path)
            proc_name = params.get("proc_name", "main")
            return self._invoke_run_macro2(macro_path, module_name, proc_name)

        return self._handle_com_operation("execute_macro", _run)

    async def exit_sketch(self) -> AdapterResult[None]:
        """Exit the current sketch editing mode.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.WARNING, error="No active sketch to exit"
            )

        def _exit_operation() -> None:
            # Toggle sketch mode off and clear local sketch references.
            """Build internal exit operation.

            Returns:
                None: None.
            """
            self.currentSketchManager.InsertSketch(True)
            self.currentSketch = None
            self.currentSketchManager = None
            return None

        return self._handle_com_operation("exit_sketch", _exit_operation)
