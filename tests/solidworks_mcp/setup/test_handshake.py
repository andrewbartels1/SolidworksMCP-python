"""Tests for the stdio start-up check, against small fake servers."""

from __future__ import annotations

import io
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from solidworks_mcp.setup import handshake
from solidworks_mcp.setup.handshake import check_server


def _fake_server(tmp_path: Path, body: str) -> list[str]:
    """Write a fake server script; return the args to run it with Python."""
    script = tmp_path / "fake_server.py"
    script.write_text(
        textwrap.dedent(
            """
            import json, sys
            def reply(i, result):
                print(json.dumps({"jsonrpc": "2.0", "id": i, "result": result}), flush=True)
            """
        )
        + textwrap.dedent(body)
    )
    return [str(script)]


def test_a_working_server(tmp_path: Path) -> None:
    args = _fake_server(
        tmp_path,
        """
        print("a banner line, not JSON", flush=True)
        for line in sys.stdin:
            msg = json.loads(line)
            if msg.get("id") == 1:
                print(json.dumps({"jsonrpc": "2.0", "method": "notifications/message"}), flush=True)
                reply(1, {})
            elif msg.get("id") == 2:
                reply(2, {"tools": [{"name": "a"}, {"name": "b"}]})
        """,
    )

    result = check_server(sys.executable, args, timeout=30)

    assert result.ok and result.tools == 2
    assert result.message == "The server started and listed 2 tools."


def test_a_server_that_exits_at_once(tmp_path: Path) -> None:
    args = _fake_server(tmp_path, "sys.exit(3)")

    result = check_server(sys.executable, args, timeout=30)

    assert not result.ok
    assert result.message == (
        "The server did not answer the MCP initialize request (it exited with code 3)."
    )


def test_a_server_that_lists_no_tools(tmp_path: Path) -> None:
    args = _fake_server(
        tmp_path,
        """
        for line in sys.stdin:
            msg = json.loads(line)
            if "id" in msg:
                reply(msg["id"], {"tools": []})
        """,
    )

    result = check_server(sys.executable, args, timeout=30)

    assert not result.ok
    assert result.message == "The server answered but listed no tools."


def test_a_server_that_never_lists_tools(tmp_path: Path) -> None:
    args = _fake_server(
        tmp_path,
        """
        for line in sys.stdin:
            if json.loads(line).get("id") == 1:
                reply(1, {})
                sys.exit(0)
        """,
    )

    result = check_server(sys.executable, args, timeout=30)

    assert not result.ok
    assert result.message.startswith("The server did not answer the tools/list request")


def test_a_silent_server_times_out(tmp_path: Path) -> None:
    args = _fake_server(tmp_path, "import time; time.sleep(30)")

    result = check_server(sys.executable, args, timeout=0.5)

    assert result.message == "The server did not answer the MCP initialize request."


def test_a_launcher_that_does_not_exist(tmp_path: Path) -> None:
    result = check_server(str(tmp_path / "missing.exe"), [])

    assert not result.ok
    assert result.message.startswith(f"Could not start {tmp_path / 'missing.exe'}:")


def test_send_to_an_exited_server_is_quiet() -> None:
    class ClosedPipe(io.BytesIO):
        def write(self, data: object) -> int:
            raise BrokenPipeError

    process: Any = SimpleNamespace(stdin=ClosedPipe())

    handshake._send(process, {"id": 1})  # no exception escapes


def test_response_after_the_deadline_is_none() -> None:
    lines = handshake._Lines()
    lines.put(b'{"id": 1}')

    assert handshake._response(lines, 1, time.monotonic() - 1) is None
