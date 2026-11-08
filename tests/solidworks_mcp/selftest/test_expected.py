"""The selftest's hand calculations come out as the design says."""

from __future__ import annotations

import pytest

from solidworks_mcp.selftest import expected as ex


def test_block_hole_fillet_and_pin_volumes() -> None:
    assert ex.BLOCK_VOLUME_MM3 == 8000.0
    assert ex.HOLE_VOLUME_MM3 == pytest.approx(7214.60, abs=0.01)
    assert ex.FILLET_VOLUME_MM3 == pytest.approx(7180.26, abs=0.01)
    assert ex.PIN_VOLUME_MM3 == pytest.approx(1417.64, abs=0.01)


def test_boxes_are_in_model_axes() -> None:
    assert ex.BLOCK_BOX_MM == [40.0, 10.0, 20.0]
    assert ex.PIN_BOX_MM == [9.5, 20.0, 9.5]


def test_the_pin_clears_the_hole() -> None:
    assert ex.HOLE_RADIUS_MM - ex.PIN_RADIUS_MM == pytest.approx(0.25)
