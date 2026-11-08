"""The area lines, the Markdown summary and the issue link."""

from __future__ import annotations

from urllib.parse import unquote

from solidworks_mcp.selftest import report
from solidworks_mcp.selftest.results import AreaResult, Check, Outcome

_ENV = {
    "solidworks": {
        "revision": "34.4.0",
        "language": "english",
        "year": 2026,
        "templates": {
            "part": {"file_name": "Part.prtdot", "exists": True},
            "drawing": {"file_name": "Drawing.drwdot", "exists": False},
        },
    },
    "os": "Windows-11",
    "python": "3.13.13",
    "pywin32": "311",
    "solidworks_mcp": "1.5.0",
}

_PART = AreaResult(
    "part",
    Outcome.PASS,
    [
        Check("block: volume_mm3", 8000.0, 8000.004, 1e-4, "mm³", True),
        Check(
            "block: bounding_box_mm",
            [40.0, 10.0, 20.0],
            [40.0, 10.0, 20.0],
            0.01,
            "mm",
            True,
        ),
        Check("pin: solid", 0.5, None, None, "", None),
        Check("flag", True, False, None, "", False),
    ],
    ["create_part", "create_sketch", "create_part"],
)
_SKIPPED = AreaResult("assembly", Outcome.SKIP, note="needs the saved pin")


def test_area_lines() -> None:
    assert report.area_line(_PART) == "PASS  part       2/4 checks"
    assert report.area_line(_SKIPPED) == "SKIP  assembly   needs the saved pin"


def test_summary_shows_environment_checks_and_tools() -> None:
    summary = report.summary_markdown(_ENV, [_PART, _SKIPPED])

    assert summary.startswith("### Selftest: 1 of 2 areas passed")
    assert "| SolidWorks | 34.4.0 (year 2026), english |" in summary
    assert (
        "| Templates | part: Part.prtdot; assembly: not set (missing); "
        "drawing: Drawing.drwdot (missing) |"
    ) in summary
    assert "| block: volume_mm3 | 8,000.00 mm3 | 8,000.00 | 0.01 % | pass |" in summary
    assert (
        "| [40.00, 10.00, 20.00] mm | [40.00, 10.00, 20.00] | 0.01 mm | pass |"
        in summary
    )
    assert "| pin: solid | 0.5  | not measured | exact | FAIL |" in summary
    assert "| flag | yes  | no | exact | FAIL |" in summary
    assert "Tools: `create_part` x2, `create_sketch`" in summary
    assert "#### assembly: SKIP\n\nneeds the saved pin" in summary


def test_the_link_fills_the_form_until_it_is_too_long() -> None:
    link = report.issue_link("### Selftest")
    assert link == report.ISSUE_FORM_URL + "&summary=%23%23%23%20Selftest"
    assert report.issue_link("x" * report.MAX_LINK_LENGTH) is None


def test_render_prints_lines_problems_summary_and_link() -> None:
    text = report.render(_ENV, [_PART], ["could not close Part2: busy"])

    assert text.startswith("PASS  part")
    assert "Cleanup:\n  could not close Part2: busy" in text
    link = text.strip().splitlines()[-1]
    assert unquote(link.split("&summary=")[1]) == report.summary_markdown(_ENV, [_PART])


def test_render_falls_back_to_the_plain_form(monkeypatch) -> None:
    monkeypatch.setattr(report, "MAX_LINK_LENGTH", 10)

    text = report.render(_ENV, [_SKIPPED], [])

    assert "Cleanup" not in text
    assert text.rstrip().endswith("paste the summary above:\n" + report.ISSUE_FORM_URL)
