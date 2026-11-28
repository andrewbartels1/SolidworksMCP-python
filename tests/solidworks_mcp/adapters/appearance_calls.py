"""One call of each adapter method queue items 36 and 39 add, shared by the layer tests."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import (
    AppearanceParameters,
    AppearanceTarget,
    BoundingBoxParameters,
    CoordinateSystemParameters,
    SectionPropertiesParameters,
)

from .body_calls import recorder_for

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("set_appearance", (AppearanceParameters(color="#1f77b4"),), {}),
    ("get_appearance", (AppearanceTarget(feature="Boss-Extrude1"),), {}),
    (
        "create_coordinate_system",
        (CoordinateSystemParameters(origin=[20, 10, 20]),),
        {},
    ),
    ("create_center_of_mass_point", (), {}),
    ("create_bounding_box", (BoundingBoxParameters(),), {}),
    (
        "get_section_properties",
        (SectionPropertiesParameters(face_point=[0, 10, 0]),),
        {},
    ),
]

IDS = [call[0] for call in CALLS]


def recorder() -> Any:
    """A mock adapter whose appearance and reference methods record their arguments."""
    return recorder_for(IDS)
