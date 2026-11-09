"""Check, AreaResult, tool_reply and ToolCaller."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidworks_mcp.selftest.results import (
    AreaResult,
    Check,
    Outcome,
    ToolCaller,
    ToolFailed,
    tool_reply,
)


def _result(structured=None, text="", is_error=False):
    return SimpleNamespace(
        structured_content=structured,
        content=[SimpleNamespace(text=text)],
        is_error=is_error,
    )


def test_passed_count_counts_only_true() -> None:
    result = AreaResult(
        "part",
        Outcome.FAIL,
        [
            Check("a", 1, 1, passed=True),
            Check("b", 1, None),
            Check("c", 1, 2, passed=False),
        ],
    )
    assert result.passed_count == 1


def test_tool_failed_carries_tool_and_message() -> None:
    exc = ToolFailed("add_mate", "no face there")
    assert (exc.tool, exc.message, str(exc)) == (
        "add_mate",
        "no face there",
        "add_mate failed: no face there",
    )


@pytest.mark.parametrize(
    ("result", "reply"),
    [
        (_result({"result": {"status": "success"}}), {"status": "success"}),
        (_result({"status": "error"}), {"status": "error"}),
        (_result(text='{"status": "success", "n": 1}'), {"status": "success", "n": 1}),
        (_result(text="boom", is_error=True), {"status": "error", "message": "boom"}),
        (_result(text="[1, 2]"), {"status": "success", "message": "[1, 2]"}),
    ],
)
def test_tool_reply_reads_every_shape(result, reply) -> None:
    assert tool_reply(result) == reply


class _Client:
    def __init__(self, reply: dict) -> None:
        self.reply = reply
        self.sent: list[tuple] = []

    async def call_tool(self, name, arguments, raise_on_error):
        self.sent.append((name, arguments, raise_on_error))
        return _result(self.reply)


@pytest.mark.asyncio
async def test_caller_sends_input_data_and_records_the_call() -> None:
    client = _Client({"status": "success", "ok": True})
    call = ToolCaller(client)

    reply = await call("create_part", {"name": "p"})
    await call("list_open_documents", record=False)

    assert reply == {"status": "success", "ok": True}
    assert client.sent == [
        ("create_part", {"input_data": {"name": "p"}}, False),
        ("list_open_documents", {}, False),
    ]
    assert call.calls == ["create_part"]


@pytest.mark.asyncio
async def test_caller_raises_on_an_error_reply() -> None:
    call = ToolCaller(_Client({"status": "error"}))

    with pytest.raises(ToolFailed, match="add_fillet failed: no message"):
        await call("add_fillet", {"radius": 2})
