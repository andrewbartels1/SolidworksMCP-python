"""Start the server the way a client will and confirm it lists its tools.

This is the MCP stdio handshake a client performs: ``initialize``, the
``initialized`` notification, then ``tools/list``. Setup runs it before
writing any config, so a broken launcher is caught here rather than as a
silent failure inside the client.
"""

from __future__ import annotations

import json
import queue
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import IO, Any

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "solidworks-mcp-setup", "version": "1"},
    },
}
_INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
_LIST_TOOLS = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

# stdout lines read by the pump thread; None marks the end of the stream.
_Lines = queue.Queue[bytes | None]


@dataclass(frozen=True)
class HandshakeResult:
    """The outcome of the start-up check.

    Attributes:
        ok: Whether the server answered and listed at least one tool.
        tools: How many tools it listed.
        message: One line for the user.
    """

    ok: bool
    tools: int
    message: str


def check_server(
    command: str, args: list[str], timeout: float = 90.0
) -> HandshakeResult:
    """Start ``command args`` and run the MCP handshake over its stdio.

    The process is always killed afterwards. Its stderr goes to a temporary
    file: an unread pipe can fill up and stall the server.

    Args:
        command: The launcher to start.
        args: Its arguments (setup passes ``--mock``).
        timeout: Seconds to wait for both replies, in total.

    Returns:
        Whether it worked, the tool count and a message.
    """
    with tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                [command, *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
            )
        except OSError as exc:
            return HandshakeResult(
                False, 0, f"Could not start {command}: {exc.strerror or exc}."
            )
        try:
            return _converse(process, time.monotonic() + timeout)
        finally:
            process.kill()
            process.wait()


def _converse(process: subprocess.Popen[bytes], deadline: float) -> HandshakeResult:
    """Send the handshake and read the two replies.

    Args:
        process: The started server, with piped stdin and stdout.
        deadline: ``time.monotonic()`` value to give up at.

    Returns:
        The check's outcome.
    """
    lines = _line_reader(process.stdout)
    _send(process, _INITIALIZE)
    if _response(lines, 1, deadline) is None:
        return _failed(process, "did not answer the MCP initialize request")
    _send(process, _INITIALIZED)
    _send(process, _LIST_TOOLS)
    reply = _response(lines, 2, deadline)
    if reply is None:
        return _failed(process, "did not answer the tools/list request")
    tools = reply.get("result", {}).get("tools")
    if not isinstance(tools, list) or not tools:
        return HandshakeResult(False, 0, "The server answered but listed no tools.")
    return HandshakeResult(
        True, len(tools), f"The server started and listed {len(tools)} tools."
    )


def _failed(process: subprocess.Popen[bytes], what: str) -> HandshakeResult:
    """Describe a missing reply, with the exit code if the server has exited.

    Args:
        process: The server process.
        what: What it failed to do.

    Returns:
        A failed result.
    """
    # stdout can close a moment before the process has finished exiting, so
    # give it a second to report its exit code.
    try:
        code: int | None = process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        code = None
    exited = f" (it exited with code {code})" if code is not None else ""
    return HandshakeResult(False, 0, f"The server {what}{exited}.")


def _send(process: subprocess.Popen[bytes], message: dict[str, Any]) -> None:
    """Write one JSON-RPC message as a line on the server's stdin.

    Args:
        process: The server process.
        message: The JSON-RPC message.
    """
    assert process.stdin is not None
    try:
        process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()
    except OSError:
        # The server has exited; the missing reply reports it.
        pass


def _line_reader(stream: IO[bytes] | None) -> _Lines:
    """Read ``stream`` line by line on a daemon thread.

    A thread lets the reader wait with a timeout: ``readline`` on a pipe
    blocks with no timeout of its own on Windows.

    Args:
        stream: The server's stdout.

    Returns:
        A queue of lines, ending with ``None`` when the stream closes.
    """
    lines: _Lines = queue.Queue()

    def pump() -> None:
        """Move each line into the queue, then the end marker."""
        assert stream is not None
        for line in iter(stream.readline, b""):
            lines.put(line)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    return lines


def _response(lines: _Lines, request_id: int, deadline: float) -> dict[str, Any] | None:
    """Wait for the JSON-RPC reply to ``request_id``.

    Lines that aren't JSON (a stray banner) and other messages (log
    notifications) are skipped.

    Args:
        lines: The server's stdout lines.
        request_id: The ``id`` of the request being answered.
        deadline: ``time.monotonic()`` value to give up at.

    Returns:
        The reply, or ``None`` on timeout or when the stream ends.
    """
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            return None
        if line is None:
            return None
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            return message
    return None
