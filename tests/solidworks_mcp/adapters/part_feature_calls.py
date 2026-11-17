"""One call of each part-feature adapter method, shared by the layer tests."""

from __future__ import annotations

from typing import Any

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    (
        "pattern_linear",
        (["Hole1"], [0.0, -20.0, 20.0], 3, 10.0),
        {"direction2": "Axis1", "count2": 2, "spacing2": 5.0},
    ),
    ("create_shell", (2.0, [[0.0, 0.0, 20.0]]), {}),
    ("add_draft", (3.0, [[20.0, 0.0, 10.0]], [0.0, 0.0, 0.0]), {"reverse": True}),
    ("create_rib", ("Sketch3", 2.0), {}),
    (
        "create_hole",
        ([0.0, 0.0, 20.0], "counterbore", "iso", "M6"),
        {"fastener": "Cap (4762)"},
    ),
    ("list_hole_sizes", ("iso", "simple"), {"fastener": "Screw Clearances"}),
    ("add_cosmetic_thread", ([3.0, 0.0, 20.0], "#10-24", 4.8), {"depth": 5.0}),
    (
        "sketch_convert_entities",
        ([[0.0, 0.0, 20.0]], [0.0, 0.0, 20.0]),
        {"construction": True},
    ),
]

IDS = [call[0] for call in CALLS]
