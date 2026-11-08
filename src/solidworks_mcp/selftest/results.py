"""What a selftest run produces: checks, area results, and the tool caller."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    """An area's result."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class Check:
    """One value read back from SolidWorks against the hand calculation.

    ``passed`` is ``None`` when the value could not be measured, which
    counts as a failure.
    """

    name: str
    expected: Any
    measured: Any
    tolerance: Any = None
    unit: str = ""
    passed: bool | None = None


@dataclass
class AreaResult:
    """One area's outcome, its checks, the tools it called, and why if not PASS."""

    name: str
    outcome: Outcome
    checks: list[Check] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    note: str | None = None

    @property
    def passed_count(self) -> int:
        """The number of checks that passed."""
        return sum(1 for c in self.checks if c.passed is True)


class ToolFailed(Exception):
    """A tool call returned ``status: error``."""

    def __init__(self, tool: str, message: str) -> None:
        """Remember which tool failed and its message.

        Args:
            tool: The tool's name.
            message: The tool's error message.
        """
        super().__init__(f"{tool} failed: {message}")
        self.tool = tool
        self.message = message


def tool_reply(result: Any) -> dict[str, Any]:
    """A FastMCP client's tool result as the payload dict an agent sees.

    Args:
        result: The ``CallToolResult`` from ``Client.call_tool``.

    Returns:
        dict[str, Any]: The tool's reply.
    """
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    if isinstance(data, dict):
        return data
    text = "".join(getattr(c, "text", "") for c in result.content)
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    return {"status": "error" if result.is_error else "success", "message": text}


class ToolCaller:
    """Call MCP tools by name with dict input, as a client does; log each call."""

    def __init__(self, client: Any) -> None:
        """Wrap a connected ``fastmcp.Client``.

        Args:
            client: The client, already entered.
        """
        self._client = client
        self.calls: list[str] = []

    async def __call__(
        self, name: str, args: dict[str, Any] | None = None, record: bool = True
    ) -> dict[str, Any]:
        """Call ``name`` and return its reply; raise when it reports an error.

        Args:
            name: The tool's name.
            args: Its input, sent as ``input_data``; ``None`` for a tool
                without input.
            record: Whether the call is listed in the report.

        Returns:
            dict[str, Any]: The tool's reply.

        Raises:
            ToolFailed: The tool replied with ``status: error``.
        """
        if record:
            self.calls.append(name)
        result = await self._client.call_tool(
            name, {} if args is None else {"input_data": args}, raise_on_error=False
        )
        reply = tool_reply(result)
        if reply.get("status") != "success":
            raise ToolFailed(name, str(reply.get("message") or "no message"))
        return reply
