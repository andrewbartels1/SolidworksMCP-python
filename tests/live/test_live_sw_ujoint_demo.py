"""The U-joint demo: the SolidWorks sample, a prompt, and an agent's build of it.

One live test, recorded for the top of the README and the Demos page
(``docs/demos.md#ujoint``). It opens on the original U-Joint assembly from
SolidWorks' own samples, then the prompt that describes it, then replays,
call by call and through an in-memory MCP client (the path Claude Code took),
what a Claude Code session with the agent skill installed did
for that prompt (``data/ujoint/with_skill_calls.json``, taken from the
session's transcript with the folder replaced by ``{out}``). Each call is a
captioned frame and must end as it did in the session: 291 succeeded and 3
failed, and the agent recovered from those. The last frame is the finished
assembly in an isometric view.

The session's three failures are replayed too: they are part of how it got
there. The demo is the evidence for the agent skill (#175): see
``docs/agents/agent-skill.md`` for the with/without comparison.

Record it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_ujoint_demo.py `
        -CaptureDir docs/assets/demos/ujoint -Record -PromptSeconds 12

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import json
import os
import shutil
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence, starting

_DATA = Path(__file__).resolve().parent / "data" / "ujoint"
#: SolidWorks' own sample: read from a copy, never opened in place.
_SAMPLES = Path(r"C:\Users\Public\Documents\SOLIDWORKS")
_PROMPT_MAX_LINES = 40
_PROMPT_WRAP_CHARS = 70
#: swStandardViews_e (swconst.tlb, SW 2026): the isometric view.
_ISO_VIEW = 7
#: Calls after which the camera turns to the isometric view.
_LOOK_AFTER = {
    "create_extrusion",
    "create_cut_extrude",
    "create_revolve",
    "insert_component",
    "add_mate",
}


def _calls() -> list[dict[str, Any]]:
    """The session's SolidWorks tool calls, in order, with how each ended."""
    return json.loads((_DATA / "with_skill_calls.json").read_text(encoding="utf-8"))


def _prompt_lines() -> list[str]:
    """The prompt, wrapped for the caption (markdown emphasis dropped)."""
    text = (_DATA / "prompt.md").read_text(encoding="utf-8").replace("**", "")
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines += textwrap.wrap(paragraph, _PROMPT_WRAP_CHARS) or [""]
    return lines


def _with_folder(value: Any, out: Path) -> Any:
    """Put the test's folder where the session's folder was (``{out}``)."""
    if isinstance(value, str):
        return (
            value.replace("{out}/", str(out) + os.sep).replace("/", os.sep)
            if "{out}" in value
            else value
        )
    if isinstance(value, dict):
        return {k: _with_folder(v, out) for k, v in value.items()}
    if isinstance(value, list):
        return [_with_folder(v, out) for v in value]
    return value


def _sample_copy(dest: Path) -> Path | None:
    """Copy the U-Joint sample folder into ``dest``; None when not installed."""
    found = sorted(_SAMPLES.glob("SOLIDWORKS 20*/samples/learn/U-Joint/UJoint.SLDASM"))
    if not found:
        return None
    shutil.copytree(found[-1].parent, dest)
    return dest / "UJoint.SLDASM"


def _look(adapter: Any, view: int) -> None:
    """Point the camera for the demo: a standard view, zoomed to fit.

    Staging for the recording, not a tool call: an agent does not need it.
    """
    model = adapter.currentModel
    if model is None:
        return
    adapter._attempt(lambda: model.ShowNamedView2("", view), default=None)
    adapter._zoom_to_fit(model)


def _brief(result: dict[str, Any]) -> dict[str, Any]:
    """The part of a reply worth a caption: its message and what it measured."""
    shown: dict[str, Any] = {
        "status": result.get("status"),
        "message": result.get("message"),
    }
    change = result.get("measured_change")
    if change:
        shown["volume_after_mm3"] = change.get("volume_after_mm3")
        shown["bounding_box_after_mm"] = change.get("bounding_box_after_mm")
    if "verdict" in result:
        shown["verdict"] = result["verdict"]
    if result.get("status") == "error":
        shown["error_type"] = result.get("error_type")
    return shown


async def _server(adapter: Any) -> Any:
    """The tools registered as the server registers them."""
    from fastmcp import FastMCP

    from solidworks_mcp.config import SolidWorksMCPConfig
    from solidworks_mcp.tools import register_tools

    mcp = FastMCP("ujoint-demo")
    await register_tools(mcp, adapter, SolidWorksMCPConfig())
    return mcp


def _reply(result: Any) -> dict[str, Any]:
    """A client's tool result as the payload dict the agent saw."""
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    if isinstance(data, dict):
        return data
    text = "".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)
    except ValueError:
        return {"status": "error" if result.is_error else "success", "message": text}


@pytest.mark.asyncio
@pytest.mark.timeout(5400)  # 294 calls, paced for a demo
async def test_ujoint_from_prompt_to_assembly(scratch: Any, tmp_path: Path) -> None:
    """The original sample, the prompt, then the agent's 294 calls replayed."""
    from fastmcp import Client

    adapter = scratch.adapter
    client = Client(await _server(adapter))
    await client.__aenter__()
    out = tmp_path / "build"
    out.mkdir()

    sample = _sample_copy(tmp_path / "sample")
    if sample is not None:
        opened = await adapter.open_model(str(sample))
        assert opened.is_success, opened.error
        _look(adapter, _ISO_VIEW)
        evidence(
            "the original: SolidWorks' U-Joint sample (8 parts, a crank sub-assembly)",
            {"file": "samples/learn/U-Joint/UJoint.SLDASM"},
        )
        await adapter.close_model(save=False)

    evidence("the prompt", _prompt_lines(), max_lines=_PROMPT_MAX_LINES)

    calls = _calls()
    differed: list[str] = []
    for number, recorded in enumerate(calls, start=1):
        name, args = recorded["tool"], _with_folder(recorded["args"], out)
        label = f"tool call {number} of {len(calls)}: {name}"
        shown_args = args.get("input_data", args)
        shown = f"{name}({json.dumps(shown_args, ensure_ascii=False)})".replace(
            json.dumps(str(out) + os.sep)[1:-1], ""
        )
        starting(label, shown)
        result = _reply(await client.call_tool(name, args, raise_on_error=False))
        if result.get("status") != recorded["status"]:
            differed.append(
                f"{number} {name}: {recorded['status']} -> {result.get('status')}: {result.get('message')}"
            )
        if name in _LOOK_AFTER and result.get("status") == "success":
            _look(adapter, _ISO_VIEW)
        brief = _brief(result)
        brief["message"] = str(brief["message"]).replace(str(out) + os.sep, "")
        evidence(label, brief, call=shown)

    await client.__aexit__(None, None, None)
    assert not differed, "calls that ended differently from the session:\n" + "\n".join(
        differed
    )
    saved = sorted(
        p.name
        for p in out.iterdir()
        if p.suffix.upper() in {".SLDPRT", ".SLDASM"} and not p.name.startswith("~$")
    )
    scratch.written_files += [str(out / name) for name in saved]
    assert "UJoint.SLDASM" in saved and len(saved) == 10, saved

    _look(adapter, _ISO_VIEW)
    evidence(
        f"the finished U-joint, isometric: {len(calls)} tool calls replayed",
        {"saved": saved},
    )
