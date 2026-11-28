"""The rules for modelled threads (queue item 43). Spec: tools/threads."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters import thread_rules as rules
from solidworks_mcp.adapters.base import ThreadParameters
from solidworks_mcp.exceptions import InputRefused


@pytest.mark.parametrize(
    ("name", "diameter", "pitch", "tpi"),
    [
        ("M6x1.0", 6.0, 1.0, None),
        ("m1.2x0.25", 1.2, 0.25, None),
        ("#10-32", 4.826, 0.7937, 32.0),
        ("0.2500-20", 6.35, 1.27, 20.0),
        ("1/4-20", 6.35, 1.27, 20.0),
        ("1-1/2-6", 38.1, 4.2333, 6.0),
        ("2.0000-4.5", 50.8, 5.6444, 4.5),
    ],
)
def test_sizes_parse(name: str, diameter: float, pitch: float, tpi: Any) -> None:
    size = rules.parse_size(name)

    assert size is not None
    assert (size.diameter_mm, size.pitch_mm, size.tpi) == (diameter, pitch, tpi)


def test_a_name_in_another_form_is_none() -> None:
    assert rules.parse_size("SP400-L-5") is None


@pytest.mark.parametrize(
    ("diameter_in", "tpi", "label"),
    [(0.25, 20, "1/4-20"), (1.5, 6, "1-1/2-6"), (2.0, 4.5, "2-4.5"), (0.2, 20, None)],
)
def test_inch_labels(diameter_in: float, tpi: float, label: str | None) -> None:
    assert rules.inch_label(diameter_in, tpi) == label


def test_a_size_table_from_the_list_alone() -> None:
    table = rules.size_table(
        ["#0-80", "#1-64", "#1-72", "0.2500-20", "0.2500-28", "junk"]
    )

    assert [(e["size"], e["pitch_class"]) for e in table] == [
        ("#0-80", "only"),
        ("#1-64", "coarse"),
        ("#1-72", "fine"),
        ("0.2500-20", "coarse"),
        ("0.2500-28", "fine"),
    ]
    quarter = table[3]
    assert quarter["also"] == "1/4-20"
    assert quarter["tpi"] == 20.0
    assert "also" not in table[0]
    assert quarter["runout_mm"] == {"normal": 3.17, "short": 1.59}


def test_known_coarse_pitches_decide() -> None:
    table = rules.size_table(
        ["M6x1.0", "M8x1.25", "M8x1.0", "M7x1.0"], {6.0: 1.0, 8.0: 1.25}
    )

    classes = {e["size"]: e["pitch_class"] for e in table}

    assert classes == {
        "M6x1.0": "coarse",
        "M7x1.0": "only",
        "M8x1.25": "coarse",
        "M8x1.0": "fine",
    }
    assert table[0]["basic_depth_mm"] == pytest.approx(0.5413)


def test_coarse_pitches_from_hole_rows() -> None:
    rows = [
        {"size": "M6", "dimensions": {"pitch": 1.0}},
        {"size": "M8x1.0", "dimensions": {"pitch": 1.0}},
        {"size": "M10", "dimensions": {"pitch": "?"}},
        {"size": None, "dimensions": None},
    ]

    assert rules.coarse_from_hole_rows(rows) == {6.0: 1.0}


@pytest.mark.parametrize(
    ("wanted", "found"),
    [("m6X1.0", "M6x1.0"), ("1/4-20", "0.2500-20"), ("M6x1", "M6x1.0")],
)
def test_sizes_match(wanted: str, found: str) -> None:
    assert rules.match_size(["M6x1.0", "M8x1.25", "0.2500-20"], wanted).size == found


@pytest.mark.parametrize(
    ("wanted", "nearest"),
    [("M7x1.0", "nearest: M6x1.0, M8x1.25"), ("bolt", "nearest: M6x1.0")],
)
def test_an_unknown_size_names_the_nearest(wanted: str, nearest: str) -> None:
    with pytest.raises(InputRefused, match=nearest):
        rules.match_size(["M6x1.0", "M8x1.25"], wanted)


def test_no_sizes_at_all() -> None:
    with pytest.raises(InputRefused, match="nearest: none"):
        rules.match_size([], "M6x1.0")


def test_the_diameter_check() -> None:
    m6 = rules.ThreadSize("M6x1.0", 6.0, 1.0)

    rules.check_diameter(m6, "external", 6.0)
    rules.check_diameter(m6, "internal", 5.0)
    with pytest.raises(InputRefused, match="wants a rod of about 6 mm"):
        rules.check_diameter(m6, "external", 10.0)
    with pytest.raises(
        InputRefused, match=r"wants a hole \(about the tap drill\) of about 5"
    ):
        rules.check_diameter(m6, "internal", 8.0)


def _params(**change: Any) -> ThreadParameters:
    values: dict[str, Any] = {"size": "M6x1.0", "edge_point": [3, 25, 0], "length": 12}
    values.update(change)
    return ThreadParameters(**values)


def test_good_inputs_pass() -> None:
    rules.check_inputs(_params())


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"standard": "din"}, "standard must be"),
        ({"kind": "male"}, "kind must be"),
        ({"hand": "both"}, "hand must be"),
        ({"edge_point": [1, 2]}, "edge_point must be"),
        ({"length": 0}, "length must be greater than 0"),
    ],
)
def test_bad_inputs_are_refused(change: dict[str, Any], words: str) -> None:
    with pytest.raises(InputRefused, match=words):
        rules.check_inputs(_params(**change))
