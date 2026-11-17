"""A macro that waits for the user fails cleanly instead of hanging (#97).

1. ``MsgBox "Done"``: after ``dialog_timeout`` (3 s) the box is answered OK
   and the run is an error, ``macro_waited_for_user``, naming the box;
2. an OK/Cancel prompt whose OK would add a sketch: the watch answers
   Cancel, so no sketch is added;
3. a macro with no dialog still succeeds.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_macro_dialog.py

Watch SolidWorks: each dialog appears, stays about 3 s, then closes by
itself. Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on
Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence, note
from tests.live.test_live_sw_beta_tools import _feature_names, _tools

pytestmark = pytest.mark.asyncio

_SKETCH = """    Part.ClearSelection2 True
    Part.Extension.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    Part.SketchManager.InsertSketch True
    Part.SketchManager.CreatePoint 0, 0, 0
    Part.SketchManager.InsertSketch True
"""

_HEAD = """Dim swApp As Object
Dim Part As Object
Sub main()
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
"""


def _macro(tmp_path: Path, name: str, body: str) -> str:
    """Write a legacy text macro (.swb) and return its path."""
    path = tmp_path / f"{name}.swb"
    path.write_text(_HEAD + body + "End Sub\n", encoding="ascii")
    return str(path)


async def test_a_waiting_macro_is_answered_and_fails(
    scratch: Any, tmp_path: Path
) -> None:
    """MsgBox answered OK; an OK/Cancel prompt answered Cancel; no dialog: success."""
    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "macro_dialog"}))["status"] == "success"
    note(
        "A macro that waits for the user",
        "Each dialog stays up 3 s, then the server answers it (OK, or Cancel "
        "when there is one) and reports the run as an error instead of hanging.",
        seconds=4.0,
    )

    done = await tools["execute_macro"](
        {
            "macro_path": _macro(tmp_path, "msgbox", '    MsgBox "Done"\n'),
            "dialog_timeout": 3,
        }
    )
    evidence(
        "MsgBox: answered OK after 3 s, the run an error",
        {k: done.get(k) for k in ("status", "error_type", "message")},
    )

    before = await _feature_names(scratch.adapter)
    prompt = (
        '    If MsgBox("Add a sketch?", vbOKCancel) = vbOK Then\n'
        + _SKETCH.replace("\n    ", "\n        ").replace("    Part", "        Part", 1)
        + "    End If\n"
    )
    asked = await tools["execute_macro"](
        {"macro_path": _macro(tmp_path, "prompt", prompt), "dialog_timeout": 3}
    )
    added = [n for n in await _feature_names(scratch.adapter) if n not in before]
    evidence(
        "OK/Cancel prompt: answered Cancel, so no sketch was added",
        {"message": asked.get("message"), "added": added},
    )

    quiet = await tools["execute_macro"](
        {"macro_path": _macro(tmp_path, "quiet", _SKETCH), "dialog_timeout": 3}
    )
    evidence("No dialog: the macro runs as before", quiet.get("message"))

    assert done["status"] == "error"
    assert done["error_type"] == "macro_waited_for_user"
    assert "'Done' (answered 'OK')" in done["message"]
    assert asked["error_type"] == "macro_waited_for_user"
    assert "(answered 'Cancel')" in asked["message"]
    assert added == []
    assert quiet["status"] == "success", quiet
