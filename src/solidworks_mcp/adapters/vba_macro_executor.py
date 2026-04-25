"""VBA macro execution lifecycle management for SolidWorks automation."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import AdapterResult, AdapterResultStatus


@dataclass(frozen=True)
class MacroExecutionRequest:
    """Request to execute a VBA macro.

    Attributes:
        macro_code (str): The macro code value.
        macro_name (str): The macro name value.
        subroutine (str): The subroutine value.
    """

    macro_code: str
    macro_name: str
    subroutine: str = "Main"


@dataclass(frozen=True)
class MacroExecutionResult:
    """Result of VBA macro execution.

    Attributes:
        duration_seconds (float): The duration seconds value.
        error (str | None): The error value.
        macro_name (str): The macro name value.
        output (str | dict[str, Any] | None): The output value.
        success (bool): The success value.
    """

    success: bool
    macro_name: str
    output: str | dict[str, Any] | None = None
    error: str | None = None
    duration_seconds: float = 0.0


class VbaMacroExecutor:
    """Manage VBA macro execution with save and tracking.

    This executor handles the full lifecycle: code generation, on-disk persistence,
    execution via the backing adapter, and result tracking.

    Args:
        temp_macro_dir (Path | None): The temp macro dir value. Defaults to None.

    Attributes:
        _temp_macro_dir (Any): The temp macro dir value.
    """

    def __init__(self, temp_macro_dir: Path | None = None) -> None:
        """Initialize macro executor.

        Args:
            temp_macro_dir (Path | None): The temp macro dir value. Defaults to None.

        Returns:
            None: None.
        """
        self._temp_macro_dir = temp_macro_dir or Path(tempfile.gettempdir())
        self._execution_history: dict[str, MacroExecutionResult] = {}

    async def execute_macro(
        self,
        request: MacroExecutionRequest,
        backing_adapter: Any,
    ) -> AdapterResult[MacroExecutionResult]:
        """Provide execute macro support for the vba macro executor.

        Args:
            request (MacroExecutionRequest): The request value.
            backing_adapter (Any): The backing adapter value.

        Returns:
            AdapterResult[MacroExecutionResult]: The result produced by the operation.
        """
        start_time = datetime.utcnow()
        macro_path = self._save_macro_to_disk(request.macro_code, request.macro_name)

        try:
            result = await self._execute_via_adapter(
                macro_path=macro_path,
                subroutine=request.subroutine,
                backing_adapter=backing_adapter,
            )

            duration = (datetime.utcnow() - start_time).total_seconds()
            execution_result = MacroExecutionResult(
                success=result.get("success", False),
                macro_name=request.macro_name,
                output=result.get("output"),
                error=result.get("error"),
                duration_seconds=duration,
            )

            self._execution_history[request.macro_name] = execution_result

            return AdapterResult(
                status=AdapterResultStatus.SUCCESS,
                data=execution_result,
                metadata={
                    "macro_path": str(macro_path),
                    "macro_name": request.macro_name,
                    "duration_seconds": duration,
                    "subroutine": request.subroutine,
                },
            )

        except Exception as exc:
            duration = (datetime.utcnow() - start_time).total_seconds()
            execution_result = MacroExecutionResult(
                success=False,
                macro_name=request.macro_name,
                error=str(exc),
                duration_seconds=duration,
            )

            self._execution_history[request.macro_name] = execution_result

            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"macro execution failed: {exc}",
            )

    def get_execution_history(
        self, macro_name: str | None = None
    ) -> dict[
        str,
        MacroExecutionResult,
    ]:
        """Retrieve macro execution history.

        Args:
            macro_name (str | None): The macro name value. Defaults to None.

        Returns:
            dict[
                str,
                MacroExecutionResult,
            ]: A dictionary containing the
                                                                    resulting values.
        """
        if macro_name is not None:
            return (
                {
                    macro_name: self._execution_history[macro_name],
                }
                if macro_name in self._execution_history
                else {}
            )
        return dict(self._execution_history)

    def _save_macro_to_disk(self, macro_code: str, macro_name: str) -> Path:
        """Save VBA macro code to a file.

        Args:
            macro_code (str): The macro code value.
            macro_name (str): The macro name value.

        Returns:
            Path: The result produced by the operation.
        """
        safe_name = "".join(
            c if c.isalnum() or c in ("_", "-") else "_" for c in macro_name
        )
        timestamp = datetime.utcnow().timestamp()
        macro_file = self._temp_macro_dir / f"{safe_name}_{timestamp}.swp"
        macro_file.write_text(macro_code, encoding="utf-8")
        return macro_file

    async def _execute_via_adapter(
        self,
        macro_path: Path,
        subroutine: str,
        backing_adapter: Any,
    ) -> dict[str, Any]:
        """Delegate macro execution to backing adapter.

        Args:
            macro_path (Path): The macro path value.
            subroutine (str): The subroutine value.
            backing_adapter (Any): The backing adapter value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
        if not hasattr(backing_adapter, "execute_macro"):
            return {
                "success": False,
                "error": "backing adapter does not support macro execution",
            }

        try:
            result = await backing_adapter.execute_macro(
                macro_path=str(macro_path),
                subroutine=subroutine,
            )
            if hasattr(result, "data"):
                return result.data or {}
            return result if isinstance(result, dict) else {"output": str(result)}
        except AttributeError:
            return {
                "success": False,
                "error": "adapter execute_macro failed",
            }
