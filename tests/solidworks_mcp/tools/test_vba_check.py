"""The restricted-mode VBA check (spec: tools/macro-execution)."""

from __future__ import annotations

import pytest

from solidworks_mcp.tools.vba_check import check_vba, declared_names, member_blocked

MEMBERS = {
    "ActiveDoc",
    "ClearSelection2",
    "Extension",
    "SelectByID2",
    "SketchManager",
    "InsertSketch",
    "CreatePoint",
    "SaveAs3",
    "RunMacro2",
    "Name",
    "Close",
}
CONSTANTS = {"swDocumentTypes_e", "swDocPART"}
INTERFACES = {"ISldWorks", "IModelDoc2"}


def _check(source: str) -> list[str]:
    return check_vba(source, MEMBERS, CONSTANTS, INTERFACES)


SKETCH = '''Option Explicit
Dim swApp As SldWorks.SldWorks
Dim Part As ModelDoc2
Private Type Pt
    X As Double
End Type
Sub main()
    Dim i As Integer, p As Pt
    Const STEP_MM = 10
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    ' Shell "calc.exe" is a comment
    Rem so is Kill "x"
    Part.Extension.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, _
        False, 0, Nothing, 0
    With Part.SketchManager
        .InsertSketch True
        For i = 1 To 3: .CreatePoint i * 0.001, 1.5E-3, p.X: Next i
        .InsertSketch True
    End With
    If MsgBox("Shell ""quoted""", vbOKCancel) = vbCancel Then GoTo Done
    Debug.Print Format$(Now, "hh:mm") & swDocPART & Part.Name & &HFF
Done:
    Err.Clear
End Sub

Private Function Twice(ByVal n As Long, Optional label As String = "") As Long
    Twice = n * 2
End Function

Property Get Size() As Long
    Size = 1
End Property
'''


def test_a_solidworks_only_macro_passes() -> None:
    assert _check(SKETCH) == []


def test_application_sldworks_at_the_start_of_a_line_passes() -> None:
    assert (
        _check(
            "Sub main()\n    Application.SldWorks.ActiveDoc.ClearSelection2 True\nEnd Sub"
        )
        == []
    )


@pytest.mark.parametrize(
    ("line", "refusal"),
    [
        ('Shell "cmd"', "Shell: reaches outside SolidWorks"),
        ('Set o = CreateObject("x")', "CreateObject: reaches outside SolidWorks"),
        ('Open "f" For Output As #1', "Open: reaches outside SolidWorks"),
        ('Print #1, "x"', "Print: reaches outside SolidWorks"),
        ('Kill "f"', "Kill: reaches outside SolidWorks"),
        ('Name "a" As "b"', "Name: reaches outside SolidWorks"),
        ("Get #1, , v", "Get: reaches outside SolidWorks"),
        ('Debug.Print Environ("USERNAME")', "Environ: reaches outside SolidWorks"),
        ("Application.Quit", "Application: only Application.SldWorks is allowed"),
        (
            'swApp.ActiveDoc.SaveAs3 "f", 0, 0',
            "SaveAs3: a SolidWorks call that reaches outside the open documents",
        ),
        (
            'swApp.RunMacro2 "m"',
            "RunMacro2: a SolidWorks call that reaches outside the open documents",
        ),
        ("swApp.NotAMember", "NotAMember: not a SolidWorks API member"),
        ("y = 1", "y: not declared"),
    ],
    ids=[
        "shell",
        "createobject",
        "open",
        "print#",
        "kill",
        "name-as",
        "get#",
        "environ",
        "application",
        "saveas",
        "runmacro",
        "unknown member",
        "undeclared",
    ],
)
def test_each_refusal_names_the_name_and_line(line: str, refusal: str) -> None:
    source = f"Sub main()\n    Dim swApp As Object, v As Variant\n    {line}\nEnd Sub"

    refused = _check(source)

    assert any(r.startswith(f"line 3: {refusal}") for r in refused), refused


def test_a_refusal_is_listed_once_per_line() -> None:
    source = 'Sub main()\n    Shell "a": Shell "b"\nEnd Sub'

    assert _check(source) == ["line 2: Shell: reaches outside SolidWorks"]


def test_a_declared_name_wins_over_a_risky_word() -> None:
    assert _check("Sub main()\n    Dim Name As String\n    Name = 1\nEnd Sub") == []


def test_an_unclosed_continuation_is_still_checked() -> None:
    assert _check('Shell "x" _') == ["line 1: Shell: reaches outside SolidWorks"]


def test_declared_names_reads_every_kind() -> None:
    names = declared_names(
        [
            (1, "Public Enum Shape"),
            (2, "    Square"),
            (3, "End Enum"),
            (4, "Static Function F(ByRef a, ParamArray rest())"),
            (5, "ReDim Preserve arr(1 To 3), other(2)"),
            (6, "For Each item In arr"),
            (7, "Retry:"),
            (8, "Sub G"),
        ]
    )

    assert names == {
        "shape",
        "square",
        "f",
        "a",
        "rest",
        "arr",
        "other",
        "item",
        "retry",
        "g",
    }


@pytest.mark.parametrize(
    ("name", "blocked"),
    [
        ("SaveAs3", True),
        ("ExportToDWG2", True),
        ("SetUserPreferenceToggle", True),
        ("CloseDoc", True),
        ("CreatePoint", False),
        ("Close", False),
    ],
)
def test_member_blocked(name: str, blocked: bool) -> None:
    assert member_blocked(name) is blocked


def test_the_installation_guide_lists_everything_refused() -> None:
    import re
    from pathlib import Path

    from solidworks_mcp.tools.vba_check import (
        BLOCKED_MEMBERS,
        BLOCKED_PREFIXES,
        OUTSIDE,
    )

    guide = Path(__file__).resolve().parents[3] / "docs/getting-started/installation.md"
    text = guide.read_text(encoding="utf-8")
    section = text.split("### What `restricted` refuses", 1)[1].split("###", 1)[0]
    listed = {name.lower().rstrip("…") for name in re.findall(r"`([^`]+)`", section)}

    assert set(BLOCKED_MEMBERS) | set(OUTSIDE) | set(BLOCKED_PREFIXES) <= listed
