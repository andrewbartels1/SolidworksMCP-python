"""Tests for the small COM helpers shared by the selection and rebuild code."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.solidworks.com_utils import as_list, strip_op_prefix


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, []), ((1, 2), [1, 2]), ([3], [3]), ("scalar", ["scalar"])],
)
def test_as_list_normalises_com_returns(value: object, expected: list) -> None:
    assert as_list(value) == expected


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, None),
        ("", ""),
        ("Error in select_feature: Feature not found", "Feature not found"),
        ("Feature not found", "Feature not found"),
    ],
)
def test_strip_op_prefix(error: str | None, expected: str | None) -> None:
    assert strip_op_prefix(error, "select_feature") == expected
