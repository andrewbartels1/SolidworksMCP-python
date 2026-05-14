"""VBA adapter path for complex operations with generated macro metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import (
    AdapterResult,
    ExtrusionParameters,
    LoftParameters,
    RevolveParameters,
    SweepParameters,
)
from .vba_macro_executor import MacroExecutionRequest, VbaMacroExecutor


class VbaGeneratorAdapter:
    """Adapter that executes complex operations through VBA-oriented flow.
    
    This adapter currently uses the wrapped COM adapter for final execution, but annotates
    responses as VBA-routed and can be extended to execute generated macros directly in
    future iterations.
    
    Args:
        backing_adapter (Any): The backing adapter value.
        macro_executor (VbaMacroExecutor | None): The macro executor value. Defaults to
                                                  None.
    
    Attributes:
        _backing_adapter (Any): The backing adapter value.
        _macro_executor (Any): The macro executor value.
        config (Any): The config value.
    """

    def __init__(
        self,
        backing_adapter: Any,
        macro_executor: VbaMacroExecutor | None = None,
    ) -> None:
        """Initialize the vba generator adapter.
        
        Args:
            backing_adapter (Any): The backing adapter value.
            macro_executor (VbaMacroExecutor | None): The macro executor value. Defaults to
                                                      None.
        
        Returns:
            None: None.
        """
        self._backing_adapter = backing_adapter
        self._macro_executor = macro_executor or VbaMacroExecutor()
        self.config = getattr(backing_adapter, "config", None)

    def __getattr__(self, item: str) -> Any:
        """Delegate unknown members to backing adapter.
        
        Args:
            item (str): The item value.
        
        Returns:
            Any: The result produced by the operation.
        """
        return getattr(self._backing_adapter, item)

    async def connect(self) -> None:
        """Connect to SolidWorks using wrapped adapter.
        
        Returns:
            None: None.
        """
        await self._backing_adapter.connect()

    async def disconnect(self) -> None:
        """Disconnect wrapped adapter.
        
        Returns:
            None: None.
        """
        await self._backing_adapter.disconnect()

    def is_connected(self) -> bool:
        """Return wrapped adapter connection state.
        
        Returns:
            bool: True if connected, otherwise False.
        """
        return self._backing_adapter.is_connected()

    async def health_check(self) -> Any:
        """Return wrapped adapter health with VBA route marker.
        
        Returns:
            Any: The result produced by the operation.
        """
        health = await self._backing_adapter.health_check()
        if hasattr(health, "metrics"):
            metrics = dict(health.metrics or {})
            metrics["route"] = "vba"
            health.metrics = metrics
        return health

    async def create_extrusion(
        self,
        params: ExtrusionParameters,
    ) -> AdapterResult[Any]:
        """Create the extrusion.
        
        Args:
            params (ExtrusionParameters): The params value.
        
        Returns:
            AdapterResult[Any]: The result produced by the operation.
        """
        return await self._run_with_vba_metadata(
            operation="create_extrusion",
            payload=params,
            com_call=self._backing_adapter.create_extrusion,
            vba_code=self._generate_extrusion_vba(params),
        )

    async def create_revolve(
        self,
        params: RevolveParameters,
    ) -> AdapterResult[Any]:
        """Create the revolve.
        
        Args:
            params (RevolveParameters): The params value.
        
        Returns:
            AdapterResult[Any]: The result produced by the operation.
        """
        return await self._run_with_vba_metadata(
            operation="create_revolve",
            payload=params,
            com_call=self._backing_adapter.create_revolve,
            vba_code=self._generate_revolve_vba(params),
        )

    async def create_sweep(
        self,
        params: SweepParameters,
    ) -> AdapterResult[Any]:
        """Create the sweep.
        
        Args:
            params (SweepParameters): The params value.
        
        Returns:
            AdapterResult[Any]: The result produced by the operation.
        """
        return await self._run_with_vba_metadata(
            operation="create_sweep",
            payload=params,
            com_call=self._backing_adapter.create_sweep,
            vba_code=self._generate_sweep_vba(params),
        )

    async def create_loft(
        self,
        params: LoftParameters,
    ) -> AdapterResult[Any]:
        """Create the loft.
        
        Args:
            params (LoftParameters): The params value.
        
        Returns:
            AdapterResult[Any]: The result produced by the operation.
        """
        return await self._run_with_vba_metadata(
            operation="create_loft",
            payload=params,
            com_call=self._backing_adapter.create_loft,
            vba_code=self._generate_loft_vba(params),
        )

    async def _run_with_vba_metadata(
        self,
        operation: str,
        payload: Any,
        com_call: Any,
        vba_code: str,
    ) -> AdapterResult[Any]:
        """Build internal run with vba metadata.
        
        Args:
            operation (str): Callable object executed by the helper.
            payload (Any): The payload value.
            com_call (Any): The com call value.
            vba_code (str): The vba code value.
        
        Returns:
            AdapterResult[Any]: The result produced by the operation.
        """
        result: AdapterResult[Any] = await com_call(payload)
        metadata = dict(result.metadata or {})
        metadata.update(
            {
                "route": "vba",
                "operation": operation,
                "vba_code": vba_code,
                "generated_at": datetime.utcnow().isoformat(),
            }
        )
        result.metadata = metadata
        return result

    def _generate_extrusion_vba(self, params: ExtrusionParameters) -> str:
        """Generate simple VBA snippet for extrusion operation.
        
        Args:
            params (ExtrusionParameters): The params value.
        
        Returns:
            str: The resulting text value.
        """
        return (
            "Sub CreateExtrusion()\n"
            "    ' Auto-generated VBA fallback snippet\n"
            f"    ' Depth: {params.depth}\n"
            "End Sub"
        )

    def _generate_revolve_vba(self, params: RevolveParameters) -> str:
        """Generate simple VBA snippet for revolve operation.
        
        Args:
            params (RevolveParameters): The params value.
        
        Returns:
            str: The resulting text value.
        """
        return (
            "Sub CreateRevolve()\n"
            "    ' Auto-generated VBA fallback snippet\n"
            f"    ' Angle: {params.angle}\n"
            "End Sub"
        )

    def _generate_sweep_vba(self, params: SweepParameters) -> str:
        """Generate simple VBA snippet for sweep operation.
        
        Args:
            params (SweepParameters): The params value.
        
        Returns:
            str: The resulting text value.
        """
        return (
            "Sub CreateSweep()\n"
            "    ' Auto-generated VBA fallback snippet\n"
            f"    ' Path: {params.path}\n"
            "End Sub"
        )

    async def execute_macro(
        self,
        macro_code: str,
        macro_name: str = "GeneratedMacro",
        subroutine: str = "Main",
    ) -> AdapterResult[Any]:
        """Provide execute macro support for the vba generator adapter.
        
        Args:
            macro_code (str): The macro code value.
            macro_name (str): The macro name value. Defaults to "GeneratedMacro".
            subroutine (str): The subroutine value. Defaults to "Main".
        
        Returns:
            AdapterResult[Any]: The result produced by the operation.
        """
        request = MacroExecutionRequest(
            macro_code=macro_code,
            macro_name=macro_name,
            subroutine=subroutine,
        )
        return await self._macro_executor.execute_macro(
            request=request,
            backing_adapter=self._backing_adapter,
        )

    def get_macro_execution_history(
        self, macro_name: str | None = None
    ) -> dict[
        str,
        Any,
    ]:
        """Retrieve VBA macro execution history.
        
        Args:
            macro_name (str | None): The macro name value. Defaults to None.
        
        Returns:
            dict[
                str,
                Any,
            ]: A dictionary containing the resulting values.
        """
        history = self._macro_executor.get_execution_history(macro_name)
        return {key: value.__dict__ for key, value in history.items()}

    def _generate_loft_vba(self, params: LoftParameters) -> str:
        """Generate simple VBA snippet for loft operation.
        
        Args:
            params (LoftParameters): The params value.
        
        Returns:
            str: The resulting text value.
        """
        return (
            "Sub CreateLoft()\n"
            "    ' Auto-generated VBA fallback snippet\n"
            f"    ' Profiles: {len(params.profiles)}\n"
            "End Sub"
        )
