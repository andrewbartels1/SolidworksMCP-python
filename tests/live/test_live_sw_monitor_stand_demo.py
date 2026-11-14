"""The monitor stand demo: a prompt, the tool calls that answer it, the part.

One live test, recorded for the Demos page (``docs/demos.md#monitor-stand``).
It opens on the user's real prompts, then runs every tool call of
``scripts/demo_monitor_stand.py``'s ``build()`` (the same function, so the
demo and the script cannot drift apart) through the registered MCP tools,
each call a captioned frame. The stand is built at the script's defaults,
the part as the user finished it: 66 mm tall, a 26 mm top, R25 arches and an
11.46 mm pocket. ``build()`` checks it with ``verify_model`` against a hand
calculation before saving and exporting an STL. The camera turns to the
isometric view after the extrusion, each cut and the fillet, and the last
frame is the finished part.

A second test (not recorded) builds the stand again, raises its height in
the extrusion's dimension, and checks the pocket followed the top face.

Record it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_monitor_stand_demo.py::test_monitor_stand_from_prompt_to_part `
        -CaptureDir docs/assets/demos/monitor-stand -Record -PromptSeconds 12

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence, starting

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo_monitor_stand.py"

#: The user's words, unedited: the request, then the follow-up after the build.
PROMPT = (
    "Ok, so this is fairly simple, so please make sure to reason through all the "
    "pieces and steps to make sure the tool calls make sense. I'm looking to make a "
    "simple square(ish) monitor stand with 4 legs, and large fillets on all corners "
    "where the legs meet the base where the monitor stand will rest on, think "
    "mini-table with an arch on 3 sides, front, left and right, but not the back. "
    'The monitor base itself is 170mm "deep" in the y direction if the positive '
    "X-axis is on your left and running left and right of you, and 173.71mm "
    '"wide" in the x-axis, and we\'ll want to add 1 cm to each side, extrude that '
    "some amount that makes sense for PETG, let's say 1.5 cm? I want it to look "
    "proportional, now the legs should be around 4 cm square on each corner, and I "
    "want the height to be roughly 50-55mm in total height from the bottom of the "
    "legs to the top of the monitor base"
)
FOLLOW_UP = (
    "can you make a shallow cut lip 1-2 mm wider than the actual x and y dimentions "
    'of the top where the display monitor would be so it sits "in" the monitor '
    "stand 3-4 mm."
)
FINISHED_BY_HAND = (
    "Then finished by hand: 66 mm tall (a 26 mm top) and an 11.46 mm pocket. "
    "This replays the build at those sizes."
)
#: The prompt caption is shown in full, however narrow the window: lines fit
#: the narrowest frame (1280 px, 76 characters, less the list's quotes).
_PROMPT_MAX_LINES = 26
_PROMPT_WRAP_CHARS = 70

#: The stand's volume at the script's defaults, measured on SolidWorks 2026
#: in the session that built it (issue #206). The script's hand calculation
#: leaves out a small blend and reads about 0.3 % low.
_MEASURED_VOLUME_MM3 = 901_769.0
#: How much the height is raised in the follow-the-height test, in mm.
_RAISE_MM = 4.0


def _load_script() -> Any:
    """Import ``scripts/demo_monitor_stand.py``, which is not a package."""
    spec = importlib.util.spec_from_file_location("demo_monitor_stand", _SCRIPT)
    assert spec is not None and spec.loader is not None, _SCRIPT
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("demo_monitor_stand", module)
    spec.loader.exec_module(module)
    return module


def _prompt_lines() -> list[str]:
    """The prompt, the follow-up and the hand edits, wrapped for the caption."""
    lines = textwrap.wrap(PROMPT, _PROMPT_WRAP_CHARS)
    lines += [""] + textwrap.wrap("Then: " + FOLLOW_UP, _PROMPT_WRAP_CHARS)
    lines += [""] + textwrap.wrap(FINISHED_BY_HAND, _PROMPT_WRAP_CHARS)
    return lines


def _brief(result: dict[str, Any]) -> dict[str, Any]:
    """The part of a reply worth a caption: its message and what it measured."""
    shown: dict[str, Any] = {"message": result.get("message")}
    change = result.get("measured_change")
    if change:
        shown["volume_delta_mm3"] = change.get("volume_delta_mm3")
        shown["volume_after_mm3"] = change.get("volume_after_mm3")
        shown["bounding_box_after_mm"] = change.get("bounding_box_after_mm")
    if "verdict" in result:
        shown["verdict"] = result["verdict"]
        shown["checks"] = [
            {k: c[k] for k in ("name", "expected", "actual", "passed") if k in c}
            for c in result.get("checks", [])
        ]
    return shown


class _Session:
    """Calls the registered MCP tools; each call is a captioned frame.

    Takes the place of the script's ``Session`` in ``build()``. Paths under
    the test's folder are shown relative to it, so no local path is
    published in a caption.
    """

    def __init__(self, tools: dict[str, Any], adapter: Any, folder: Path) -> None:
        self.tools = tools
        self.adapter = adapter
        self.prefix = str(folder) + os.sep
        self.calls: list[dict[str, Any]] = []
        self.results: dict[str, dict[str, Any]] = {}

    async def __call__(
        self, name: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call one tool, caption it, and require success."""
        label = f"tool call {len(self.calls) + 1}: {name}"
        shown = f"{name}({json.dumps(args or {}, ensure_ascii=False)})"
        shown = shown.replace(json.dumps(self.prefix)[1:-1], "")
        starting(label, shown)
        tool = self.tools[name]
        result: dict[str, Any] = await (tool() if args is None else tool(args))
        self.calls.append({"tool": name, "args": args or {}})
        self.results[name] = result
        assert result.get("status") == "success", f"{name}: {result.get('message')}"
        brief = _brief(result)
        brief["message"] = str(brief["message"]).replace(self.prefix, "")
        evidence(label, brief, call=shown)
        return result


@pytest.mark.asyncio
@pytest.mark.timeout(1200)  # paced for a demo: a hold on every frame
async def test_monitor_stand_from_prompt_to_part(scratch: Any, tmp_path: Path) -> None:
    """The arched monitor stand from the user's prompt, checked, saved and exported."""
    script = _load_script()
    stand = script.Stand()
    adapter = scratch.adapter
    call = _Session(await script._tools(adapter), adapter, tmp_path)
    out = tmp_path / "MonitorStand.SLDPRT"
    scratch.written_files += [str(out), str(out.with_suffix(".stl"))]

    evidence("the prompt", _prompt_lines(), max_lines=_PROMPT_MAX_LINES)

    await script.build(
        stand,
        out,
        replace=False,
        stl=True,
        call=call,
        look=lambda: script.look_isometric(adapter),
    )

    assert out.is_file(), out
    assert out.with_suffix(".stl").is_file()
    check = call.results["verify_model"]
    assert check["verdict"] == "pass", check
    assert check["measured"]["volume_mm3"] == pytest.approx(
        _MEASURED_VOLUME_MM3, rel=1e-3
    )
    assert "create_reference_plane" not in [c["tool"] for c in call.calls]

    script.look_isometric(adapter)
    evidence(
        f"the finished stand, isometric: {len(call.calls)} tool calls, all successful",
        {
            "size_mm": check["measured"]["bounding_box_mm"]["size"],
            "volume_mm3": round(check["measured"]["volume_mm3"], 1),
            "saved": [out.name, out.with_suffix(".stl").name],
        },
    )


@pytest.mark.asyncio
@pytest.mark.timeout(900)
async def test_the_pocket_follows_a_raised_height(scratch: Any, tmp_path: Path) -> None:
    """Raise the stand by editing its extrusion; the pocket moves with the top.

    The pocket is sketched on the top face, so after the block's depth goes
    from 66 to 70 mm the part grows by exactly the plate's footprint times
    4 mm, and the pocket is still 11.46 mm deep from the new top. A pocket on
    a plane fixed at 66 mm would leave the volume short by the pocket's
    footprint times 4 mm.
    """
    script = _load_script()
    stand = script.Stand()
    adapter = scratch.adapter
    call = script.Session(await script._tools(adapter))
    out = tmp_path / "MonitorStandRaised.SLDPRT"
    scratch.written_files.append(str(out))

    # build() ends with verify_model, so the stand is right before the edit.
    await script.build(stand, out, replace=False, stl=False, call=call)

    raised = stand.height + _RAISE_MM
    await call("set_dimension", {"name": "D1@Boss-Extrude1", "value": raised})
    await call("rebuild_model")
    check = await call(
        "verify_model",
        {
            "bounding_box_mm": [
                round(stand.width, 4),
                round(raised, 4),
                round(stand.depth, 4),
            ],
            "volume_mm3": round(
                _MEASURED_VOLUME_MM3 + stand.width * stand.depth * _RAISE_MM, 1
            ),
            "solid_body_count": 1,
            "relative_tolerance": 0.002,
        },
    )

    evidence(
        "the pocket followed the top face",
        {
            "height_mm": raised,
            "volume_after_mm3": round(check["measured"]["volume_mm3"], 1),
            "verdict": check["verdict"],
        },
    )
    assert check["verdict"] == "pass", check
