"""A scripted stand-in for the selftest's ToolCaller."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from solidworks_mcp.selftest.results import ToolFailed

Reply = dict[str, Any] | Callable[[dict[str, Any] | None], dict[str, Any]]


class CallerStub:
    """Answer each tool from ``replies``; fail the tools named in ``failures``."""

    def __init__(
        self,
        replies: dict[str, Reply] | None = None,
        failures: dict[str, str] | None = None,
    ) -> None:
        self.replies = replies or {}
        self.failures = failures or {}
        self.calls: list[str] = []
        self.log: list[tuple[str, dict[str, Any] | None, bool]] = []

    async def __call__(
        self, name: str, args: dict[str, Any] | None = None, record: bool = True
    ) -> dict[str, Any]:
        if record:
            self.calls.append(name)
        self.log.append((name, args, record))
        if name in self.failures:
            raise ToolFailed(name, self.failures[name])
        reply = self.replies.get(name, {})
        reply = reply(args) if callable(reply) else reply
        return {"status": "success", **reply}
