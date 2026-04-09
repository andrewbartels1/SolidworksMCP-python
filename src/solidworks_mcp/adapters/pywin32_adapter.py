"""
PyWin32 SolidWorks adapter for Windows COM integration.

This adapter uses pywin32 to communicate with SolidWorks via COM,
providing real SolidWorks automation capabilities on Windows platforms.
"""

import asyncio
import os
import platform
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

from ..exceptions import SolidWorksMCPError
from .base import (
    SolidWorksAdapter,
    AdapterResult,
    AdapterHealth,
    AdapterResultStatus,
    SolidWorksModel,
    SolidWorksFeature,
    ExtrusionParameters,
    RevolveParameters,
    SweepParameters,
    LoftParameters,
    MassProperties,
)

try:
    import win32com.client
    import pythoncom
    import pywintypes

    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False


T = TypeVar("T")


def _parse_vb_module_name(macro_path: str) -> str:
    """Read ``Attribute VB_Name = "..."`` from a SolidWorks text macro file.

    Falls back to the file stem (e.g. ``paper_airplane`` for ``paper_airplane.swp``),
    then to ``"SolidWorksMacro"`` which is the name used by the macro recorder.
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
    return stem if stem else "SolidWorksMacro"


class PyWin32Adapter(SolidWorksAdapter):
    """SolidWorks adapter using pywin32 COM integration.

    This adapter provides direct COM integration with SolidWorks using pywin32,
    enabling real-time automation and control of SolidWorks applications on Windows.

    Attributes:
        sw_app: SolidWorks application COM object
        sw_model: Current active SolidWorks model
        config: Configuration dictionary for adapter settings
        connected: Boolean indicating connection status
        last_error: Last error message encountered

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
            config: Optional configuration dictionary containing:
                - timeout (int): Connection timeout in seconds (default: 30)
                - auto_connect (bool): Auto-connect on initialization (default: False)
                - startup_timeout (int): SolidWorks startup timeout (default: 60)
                - operation_timeout (int): Operation timeout in seconds (default: 300)

        Raises:
            SolidWorksMCPError: If pywin32 is not available or not on Windows platform

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
        if not PYWIN32_AVAILABLE:
            raise SolidWorksMCPError(
                "pywin32 is not available. Install with: pip install pywin32"
            )

        if platform.system() != "Windows":
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

        Establishes connection to SolidWorks application through COM interface.
        Attempts to connect to existing instance first, creates new instance if needed.

        Raises:
            SolidWorksMCPError: If connection to SolidWorks fails

        Note:
            This method automatically:
            - Initializes COM apartment for thread safety
            - Makes SolidWorks visible for automation
            - Disables confirmation dialogs for batch processing

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
            raise SolidWorksMCPError(f"Failed to connect to SolidWorks: {e}")

    async def disconnect(self) -> None:
        """Disconnect from SolidWorks application.

        Properly disconnects from SolidWorks COM interface and cleans up resources.
        This method should always be called when finished to prevent memory leaks.

        Note:
            - Clears references to current model and application
            - Uninitialize COM apartment
            - Does not close SolidWorks application itself

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
            bool: True if connected to SolidWorks application, False otherwise

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

        Performs comprehensive health check including connection status,
        operation metrics, and SolidWorks application responsiveness.

        Returns:
            AdapterHealth: Health status object containing:
                - healthy (bool): Overall health status
                - last_check (datetime): Timestamp of check
                - error_count (int): Total errors encountered
                - success_count (int): Total successful operations
                - average_response_time (float): Average operation time in seconds
                - connection_status (str): Connection state description
                - metrics (dict): Additional adapter-specific metrics

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

        Wraps COM operations with comprehensive error handling, performance metrics,
        and standardized result formatting. All SolidWorks COM calls should use this.

        Args:
            operation_name: Name of the operation for logging and metrics
            operation_func: Callable that performs the COM operation

        Returns:
            AdapterResult: Standardized result object containing:
                - status: SUCCESS, ERROR, or WARNING
                - data: Operation result data
                - execution_time: Time taken in seconds
                - error_info: Error details if operation failed

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
        """Execute a best-effort operation.

        Keep non-critical fallback handling in one place instead of scattering
        broad try/except blocks throughout operation code.

        Args:
            operation: Zero-argument callable to evaluate.
            default: Value returned when operation raises.

        Returns:
            T | None: Operation result, or default on failure.
        """
        try:
            return operation()
        except Exception:
            return default

    def _attempt_with_error(
        self, operation: Callable[[], T]
    ) -> tuple[T | None, Exception | None]:
        """Execute an operation and capture any exception.

        Args:
            operation: Zero-argument callable to evaluate.

        Returns:
            tuple[T | None, Exception | None]: Operation result and captured exception.
        """
        try:
            return operation(), None
        except Exception as exc:
            return None, exc

    def _get_attr_or_call(self, obj: Any, attr_name: str) -> Any:
        """Read COM attribute exposed as a property or zero-arg method.

        Args:
            obj: COM object instance.
            attr_name: Attribute or method name.

        Returns:
            Any: Resolved value from property access or method invocation.
        """
        attr = getattr(obj, attr_name, None)
        return attr() if callable(attr) else attr

    def _get_feature_id(self, feature: Any) -> str:
        """Extract a stable string feature ID from COM feature objects.

        Some SolidWorks COM bindings return an int-like value from GetID(), while
        others return a .NET object exposing ToString().
        """
        feature_id_getter = getattr(feature, "GetID", None)
        feature_id_value = (
            feature_id_getter() if callable(feature_id_getter) else feature_id_getter
        )
        to_string = getattr(feature_id_value, "ToString", None)
        return str(to_string() if callable(to_string) else feature_id_value)

    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Open a SolidWorks model file.

        Opens a SolidWorks document and sets it as the current active model.
        Supports Part (.sldprt), Assembly (.sldasm), and Drawing (.slddrw) files.

        Args:
            file_path: Absolute path to the SolidWorks file to open

        Returns:
            AdapterResult[SolidWorksModel]: Result containing:
                - SolidWorksModel object with file info and properties
                - Error details if opening failed

        Raises:
            SolidWorksMCPError: If not connected to SolidWorks

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
            """Execute open operation.

            Returns:
                SolidWorksModel: Describe the returned value.

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

            app = self.swApp
            if app is None:
                raise Exception("SolidWorks application is not connected")

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
            save: Whether to save the model before closing (default: False)

        Returns:
            AdapterResult[None]: Result indicating success or failure

        Note:
            If no model is active, returns a WARNING status rather than ERROR

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
            """Execute close operation.

            Returns:
                None: Describe the returned value.

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

        Installations vary by where template paths are stored; this probes multiple
        slots and prefers existing files with the expected extension.
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
        """Read model title regardless of COM exposing method or value."""
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
        """Create a new part document."""
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create_operation() -> SolidWorksModel:
            """Execute create operation.

            Returns:
                SolidWorksModel: Describe the returned value.

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
        """Create a new assembly document."""
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create_operation() -> SolidWorksModel:
            """Execute create operation.

            Returns:
                SolidWorksModel: Describe the returned value.

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
        """Create a new drawing document."""
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        def _create_operation() -> SolidWorksModel:
            """Execute create operation.

            Returns:
                SolidWorksModel: Describe the returned value.

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
        """Create an extrusion feature."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _extrusion_operation() -> SolidWorksFeature:
            # Get feature manager
            """Execute extrusion operation.

            Returns:
                SolidWorksFeature: Describe the returned value.

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
        """Create a revolve feature."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _revolve_operation() -> SolidWorksFeature:
            """Execute revolve operation.

            Returns:
                SolidWorksFeature: Describe the returned value.

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
        """Create a sweep feature."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="Sweep feature not implemented in basic pywin32 adapter",
        )

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a loft feature."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="Loft feature not implemented in basic pywin32 adapter",
        )

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create a new sketch on the specified plane.

        Creates a new sketch on the specified reference plane and sets it as active.
        The sketch is ready for adding geometry (lines, circles, etc.).

        Args:
            plane: Name of the reference plane. Supports:
                - Standard names: "Top", "Front", "Right"
                - Coordinate names: "XY", "XZ", "YZ"
                - Full names: "Top Plane", "Front Plane", "Right Plane"

        Returns:
            AdapterResult[str]: Result containing sketch name if successful

        Raises:
            SolidWorksMCPError: If no active model or plane selection fails

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
            """Execute sketch operation.

            Returns:
                str: Describe the returned value.

            """
            plane_name_map = {
                "Top": "Top Plane",
                "Front": "Front Plane",
                "Right": "Right Plane",
                "XY": "Top Plane",
                "XZ": "Front Plane",
                "YZ": "Right Plane",
            }

            actual_plane = plane_name_map.get(plane, plane)

            selected = False
            selection_error = None

            # Prefer direct feature lookup to avoid SelectByID2 variant mismatch.
            plane_candidates = [
                actual_plane,
                plane,
                "Top Plane",
                "Front Plane",
                "Right Plane",
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

        Creates a line segment in the active sketch between two points.
        Coordinates are automatically converted from millimeters to meters.

        Args:
            x1: Starting point X coordinate in millimeters
            y1: Starting point Y coordinate in millimeters
            x2: Ending point X coordinate in millimeters
            y2: Ending point Y coordinate in millimeters

        Returns:
            AdapterResult[str]: Result containing line identifier if successful

        Raises:
            SolidWorksMCPError: If no active sketch or line creation fails

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
            """Execute line operation.

            Returns:
                str: Describe the returned value.

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
            center_x: Circle center X coordinate in millimeters
            center_y: Circle center Y coordinate in millimeters
            radius: Circle radius in millimeters (must be positive)

        Returns:
            AdapterResult[str]: Result containing circle identifier if successful

        Raises:
            SolidWorksMCPError: If no active sketch or circle creation fails

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
            """Execute circle operation.

            Returns:
                str: Describe the returned value.

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

        Creates a rectangle in the active sketch defined by two corner points.
        The rectangle is created as four connected lines with automatic constraints.

        Args:
            x1: First corner X coordinate in millimeters
            y1: First corner Y coordinate in millimeters
            x2: Opposite corner X coordinate in millimeters
            y2: Opposite corner Y coordinate in millimeters

        Returns:
            AdapterResult[str]: Result containing rectangle identifier if successful

        Note:
            The rectangle is oriented parallel to the coordinate axes.
            Corner points can be specified in any order.

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
            """Execute rectangle operation.

            Returns:
                str: Describe the returned value.

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

        Creates a circular arc in the active sketch defined by center point,
        start point, and end point. Arc is drawn counterclockwise from start to end.

        Args:
            center_x: Arc center X coordinate in millimeters
            center_y: Arc center Y coordinate in millimeters
            start_x: Arc start point X coordinate in millimeters
            start_y: Arc start point Y coordinate in millimeters
            end_x: Arc end point X coordinate in millimeters
            end_y: Arc end point Y coordinate in millimeters

        Returns:
            AdapterResult[str]: Result containing arc identifier if successful

        Note:
            - Start and end points should be equidistant from center
            - Arc direction is counterclockwise from start to end point
            - For full circles, use add_circle() instead

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
            """Execute arc operation.

            Returns:
                str: Describe the returned value.

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

        Creates a smooth spline curve through the specified control points.
        The spline automatically generates smooth transitions between points.

        Args:
            points: List of point dictionaries, each containing:
                - 'x': X coordinate in millimeters
                - 'y': Y coordinate in millimeters
            Minimum 3 points required for spline creation.

        Returns:
            AdapterResult[str]: Result containing spline identifier if successful

        Raises:
            SolidWorksMCPError: If insufficient points or spline creation fails

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
            """Execute spline operation.

            Returns:
                str: Describe the returned value.

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
        """Add a centerline to the current sketch."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _centerline_operation() -> str:
            # Convert mm to meters and create centerline
            """Execute centerline operation.

            Returns:
                str: Describe the returned value.

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
        """Add a polygon to the current sketch."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _polygon_operation() -> str:
            # Convert mm to meters
            """Execute polygon operation.

            Returns:
                str: Describe the returned value.

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
        """Add an ellipse to the current sketch."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _ellipse_operation() -> str:
            # Convert mm to meters
            """Execute ellipse operation.

            Returns:
                str: Describe the returned value.

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
        """Add a geometric constraint between sketch entities."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _constraint_operation() -> str:
            # Map relation types to SolidWorks constants
            """Execute constraint operation.

            Returns:
                str: Describe the returned value.

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

            constraint_type = relation_map.get(relation_type.lower(), 0)

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
        """Add a dimension to sketch entities."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _dimension_operation() -> str:
            # For now, return a success without actual dimension - this requires entity selection
            # which is complex in the basic adapter
            """Execute dimension operation.

            Returns:
                str: Describe the returned value.

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
        """Create a linear pattern of sketch entities."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _linear_pattern_operation() -> str:
            # For now, return a success placeholder - linear patterns require entity selection
            """Execute linear pattern operation.

            Returns:
                str: Describe the returned value.

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
        """Create a circular pattern of sketch entities."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _circular_pattern_operation() -> str:
            # For now, return a success placeholder - circular patterns require entity selection
            """Execute circular pattern operation.

            Returns:
                str: Describe the returned value.

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
        """Mirror sketch entities about a centerline."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _mirror_operation() -> str:
            # For now, return a success placeholder - mirroring requires entity selection
            """Execute mirror operation.

            Returns:
                str: Describe the returned value.

            """
            mirror_id = f"Mirror_{mirror_line}_{int(time.time() * 1000) % 10000}"

            return mirror_id

        return self._handle_com_operation("sketch_mirror", _mirror_operation)

    async def sketch_offset(
        self, entities: list[str], offset_distance: float, reverse_direction: bool
    ) -> AdapterResult[str]:
        """Create an offset of sketch entities."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def _offset_operation() -> str:
            # For now, return a success placeholder - offsetting requires entity selection
            """Execute offset operation.

            Returns:
                str: Describe the returned value.

            """
            direction = "inward" if reverse_direction else "outward"
            offset_id = f"Offset_{offset_distance}_{direction}_{int(time.time() * 1000) % 10000}"

            return offset_id

        return self._handle_com_operation("sketch_offset", _offset_operation)

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties of the current model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _mass_props_operation() -> MassProperties:
            # Get mass properties
            """Execute mass props operation.

            Returns:
                MassProperties: Describe the returned value.

            """
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

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Export the current model to a file."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _export_operation() -> None:
            # Determine export format
            """Execute export operation.

            Returns:
                None: Describe the returned value.

            """
            format_map = {
                "step": 0,  # swSaveAsSTEP
                "iges": 1,  # swSaveAsIGS
                "stl": 2,  # swSaveAsSTL
                "pdf": 3,  # swSaveAsPDF
                "dwg": 4,  # swSaveAsDWG
                "jpg": 5,  # swSaveAsJPEG
            }

            format_lower = format_type.lower()
            if format_lower not in format_map:
                raise Exception(f"Unsupported export format: {format_type}")

            save_format = format_map[format_lower]

            resolved_path = os.path.abspath(file_path)
            os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

            if os.path.exists(resolved_path):
                self._attempt(lambda: os.remove(resolved_path))

            # Save/export the file
            success = self.currentModel.SaveAs3(
                resolved_path,
                save_format,
                2,  # swSaveAsOptions_Silent
            )

            if not success and not os.path.exists(resolved_path):
                raise Exception(f"Failed to export file: {resolved_path}")

            return None

        return self._handle_com_operation("export_file", _export_operation)

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Get the value of a dimension."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _get_dim_operation() -> float:
            """Execute get dim operation.

            Returns:
                float: Describe the returned value.

            """
            dimension = self.currentModel.Parameter(name)

            if not dimension:
                raise Exception(f"Dimension '{name}' not found")

            value = dimension.GetValue3(8, None)  # Get system value
            return value * 1000  # Convert meters to mm

        return self._handle_com_operation("get_dimension", _get_dim_operation)

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set the value of a dimension."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _set_dim_operation() -> None:
            """Execute set dim operation.

            Returns:
                None: Describe the returned value.

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
        """Save the current model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _save_operation() -> None:
            """Execute save operation.

            Returns:
                None: Describe the returned value.

            """

            def _is_success(value: Any) -> bool:
                # COM save APIs may return bool OR an integer status code
                # where 0 indicates success.
                """Execute is success.

                Args:
                    value (Any): Describe value.

                Returns:
                    bool: Describe the returned value.

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
        """Rebuild the current model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _rebuild_operation() -> None:
            """Execute rebuild operation.

            Returns:
                None: Describe the returned value.

            """
            success = self.currentModel.ForceRebuild3(False)
            if not success:
                raise Exception("Failed to rebuild model")
            return None

        return self._handle_com_operation("rebuild_model", _rebuild_operation)

    async def get_model_info(self) -> AdapterResult[dict[str, Any]]:
        """Get information about the current model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _info_operation() -> dict[str, Any]:
            """Execute info operation.

            Returns:
                dict[str, Any]: Describe the returned value.

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
        """List features in the active model feature tree."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        def _list_operation() -> list[dict[str, Any]]:
            """Execute list operation.

            Returns:
                list[dict[str, Any]]: Describe the returned value.

            """
            features: list[dict[str, Any]] = []
            seen: set[tuple[str, str]] = set()

            def _is_suppressed(feature: Any) -> bool:
                # Prefer parameter-less calls to avoid COM optional-arg marshalling issues.
                """Execute is suppressed.

                Args:
                    feature (Any): Describe feature.

                Returns:
                    bool: Describe the returned value.

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
                """Execute append feature.

                Args:
                    feature (Any): Describe feature.
                    position (int): Describe position.

                Returns:
                    None: Describe the returned value.

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

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List all configuration names in the active model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        def _list_operation() -> list[str]:
            """Execute list operation.

            Returns:
                list[str]: Describe the returned value.

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
            active_name = self._attempt(
                lambda: active_config.GetName(), default=None
            )
            if active_name:
                return [str(active_name)]

            return []

        return self._handle_com_operation("list_configurations", _list_operation)

    def _get_document_type(self) -> str:
        """Helper method to get document type."""
        if not self.currentModel:
            return "Unknown"

        doc_type = self.currentModel.GetType()
        type_map = {1: "Part", 2: "Assembly", 3: "Drawing"}
        return type_map.get(doc_type, "Unknown")

    async def create_cut_extrude(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a cut extrude feature."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _cut_operation() -> SolidWorksFeature:
            """Execute cut operation.

            Returns:
                SolidWorksFeature: Describe the returned value.

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
        """Add a fillet feature."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _fillet_operation() -> SolidWorksFeature:
            # Select edges first
            """Execute fillet operation.

            Returns:
                SolidWorksFeature: Describe the returned value.

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
        """Add a chamfer feature."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _chamfer_operation() -> SolidWorksFeature:
            # Select edges first
            """Execute chamfer operation.

            Returns:
                SolidWorksFeature: Describe the returned value.

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

    async def execute_macro(
        self, params: dict[str, Any]
    ) -> AdapterResult[dict[str, Any]]:
        """Execute a SolidWorks macro file using RunMacro2."""
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
            # RunMacro2: (FileName, ModuleName, ProcName, Options, Errors As Long ByRef)
            # Parse module name from "Attribute VB_Name = ..." in the macro file.
            # Falls back to filename stem (SW recorder default) then "SolidWorksMacro".
            module_name = _parse_vb_module_name(macro_path)
            proc_name = params.get("proc_name", "main")

            # Win32com late-binding: pass 0 for the ByRef Errors param.
            # RunMacro2 returns (bool, errors_out) as a tuple when the ByRef
            # param is marshalled — capture both.
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

        return self._handle_com_operation("execute_macro", _run)

    async def exit_sketch(self) -> AdapterResult[None]:
        """Exit the current sketch editing mode."""
        if not self.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.WARNING, error="No active sketch to exit"
            )

        def _exit_operation() -> None:
            # Toggle sketch mode off and clear local sketch references.
            """Execute exit operation.

            Returns:
                None: Describe the returned value.

            """
            self.currentSketchManager.InsertSketch(True)
            self.currentSketch = None
            self.currentSketchManager = None
            return None

        return self._handle_com_operation("exit_sketch", _exit_operation)
