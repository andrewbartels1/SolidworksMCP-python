"""VBA adapter path for complex operations with generated macro metadata."""

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

    This adapter currently uses the wrapped COM adapter for final execution,
    but annotates responses as VBA-routed and can be extended to execute
    generated macros directly in future iterations.
    """

    def __init__(
        self,
        backing_adapter: Any,
        macro_executor: VbaMacroExecutor | None = None,
    ) -> None:
        """Initialize this object.

        Args:
            backing_adapter: Primary adapter used for connection and execution.
            macro_executor: Optional macro executor for VBA lifecycle management.
        """
        self._backing_adapter = backing_adapter
        self._macro_executor = macro_executor or VbaMacroExecutor()
        self.config = getattr(backing_adapter, "config", None)

    def __getattr__(self, item: str) -> Any:
        """Delegate unknown members to backing adapter."""
        return getattr(self._backing_adapter, item)

    async def connect(self) -> None:
        """Connect to SolidWorks using wrapped adapter."""
        await self._backing_adapter.connect()

    async def disconnect(self) -> None:
        """Disconnect wrapped adapter."""
        await self._backing_adapter.disconnect()

    def is_connected(self) -> bool:
        """Return wrapped adapter connection state."""
        return self._backing_adapter.is_connected()

    async def health_check(self) -> Any:
        """Return wrapped adapter health with VBA route marker."""
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
        """Execute extrusion through VBA-routed path.

        Args:
            params: Extrusion parameters.

        Returns:
            Adapter operation result with VBA metadata.
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
        """Execute revolve through VBA-routed path."""
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
        """Execute sweep through VBA-routed path."""
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
        """Execute loft through VBA-routed path."""
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
        """Execute wrapped operation and annotate metadata as VBA-routed.

        Args:
            operation: Operation name.
            payload: Operation payload.
            com_call: Backing adapter callable.
            vba_code: Generated VBA source string.

        Returns:
            Adapter result with metadata.
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
        """Generate simple VBA snippet for extrusion operation."""
        return (
            "Sub CreateExtrusion()\n"
            "    ' Auto-generated VBA fallback snippet\n"
            f"    ' Depth: {params.depth}\n"
            "End Sub"
        )

    def _generate_revolve_vba(self, params: RevolveParameters) -> str:
        """Generate simple VBA snippet for revolve operation."""
        return (
            "Sub CreateRevolve()\n"
            "    ' Auto-generated VBA fallback snippet\n"
            f"    ' Angle: {params.angle}\n"
            "End Sub"
        )

    def _generate_sweep_vba(self, params: SweepParameters) -> str:
        """Generate simple VBA snippet for sweep operation."""
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
        """Execute generated VBA macro code.

        Args:
            macro_code: Full VBA source code.
            macro_name: Descriptive name for this macro.
            subroutine: Entry point subroutine name.

        Returns:
            Adapter result wrapping macro execution outcome.
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
            macro_name: Optional specific macro to query.

        Returns:
            Dictionary of execution results.
        """
        history = self._macro_executor.get_execution_history(macro_name)
        return {key: value.__dict__ for key, value in history.items()}

    def _generate_loft_vba(self, params: LoftParameters) -> str:
        """Generate simple VBA snippet for loft operation."""
        return (
            "Sub CreateLoft()\n"
            "    ' Auto-generated VBA fallback snippet\n"
            f"    ' Profiles: {len(params.profiles)}\n"
            "End Sub"
        )
