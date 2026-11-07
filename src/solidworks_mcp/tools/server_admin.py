"""Tools that look after the server itself rather than a SolidWorks model.

Today one tool: ``reset_circuit_breaker``, which re-opens operations the
server's circuit breaker has paused after repeated failures (#208).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import normalize_input, require_success, with_tool_boundary


class ResetCircuitBreakerInput(CompatInput):
    """Input schema for resetting circuit breakers.

    Attributes:
        operation (str | None): The operation to reset, e.g. ``create_extrusion``.
    """

    operation: str | None = Field(
        default=None,
        description=(
            "The operation to reset, as named in the circuit_open error "
            "(e.g. create_extrusion); leave it out to reset every operation"
        ),
    )


async def register_server_admin_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register the server-administration tools with FastMCP.

    Args:
        mcp (FastMCP): The MCP server.
        adapter (SolidWorksAdapter): Adapter used by every tool.
        config (dict[str, Any]): Server configuration (unused).

    Returns:
        int: Number of tools registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def reset_circuit_breaker(
        input_data: ResetCircuitBreakerInput | None = None,
    ) -> dict[str, Any]:
        """Let calls through again to operations the server paused after repeated failures.

        Use it when a tool returns `error_type: circuit_open` and you have fixed what
        made the calls fail (a missing sketch, a wrong reference): without a reset, the
        operation stays paused until its timeout. Resetting does not fix the cause; a
        call that fails again counts towards a new pause. Changes: only the server's
        own state; no SolidWorks document is touched. Returns: `data` with `reset`, the
        operations that were paused (empty when none were).

        Args:
            input_data: Optional: `operation` resets only that operation; leave it out
                to reset every one.

        Returns:
            dict[str, Any]: The operations that were reset.
        """
        input_data = normalize_input(input_data, ResetCircuitBreakerInput)
        result = await adapter.reset_circuit_breakers(input_data.operation)
        require_success(result, context="Failed to reset the circuit breaker")
        names = list((result.data or {}).get("reset", []))
        message = f"Reset {', '.join(names)}" if names else "No operation was paused"
        return {"status": "success", "message": message, "data": {"reset": names}}

    return 1
