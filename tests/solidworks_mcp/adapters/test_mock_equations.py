"""The mock adapter's equations: values worked out, refusals as SolidWorks gives them.

Spec: tools/equations.
"""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.adapters.mock_equations import mock_value

pytestmark = pytest.mark.asyncio


async def _mock() -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    return adapter


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ("60mm", 60.0),
        ("2.5 in", 2.5),
        ("-(3 + 1) * 2 / 4", -2.0),
        ("+7", 7.0),
        ('"Width" / 2', 30.0),
        ('"Blank" + 1', None),
        ("sin(30)", None),
        ("1 / 0", None),
        ("2 ** 3", None),
        ("'text'", None),
        ("not (", None),
    ],
)
async def test_mock_value(expression: str, value: float | None) -> None:
    assert mock_value(expression, {"width": 60.0, "blank": None}) == value


async def test_a_quoted_name_with_no_equation_is_a_lookup_error() -> None:
    with pytest.raises(LookupError, match="Nope"):
        mock_value('"Nope" * 2', {})


async def test_a_global_variable_drives_a_dimension() -> None:
    adapter = await _mock()
    await adapter.set_equation("Width", "60mm")
    driven = await adapter.set_equation("D1@Sketch1", '"Width" / 2')
    changed = await adapter.set_equation("width", "80mm", ["Default"])

    assert driven.data["kind"] == "dimension"
    assert driven.data["value"] == 30.0
    assert changed.data["action"] == "changed"
    assert changed.data["configurations"] == ["Default"]
    assert adapter._dimensions["D1@Sketch1"] == 40.0
    listed = (await adapter.list_equations()).data
    assert [(r["index"], r["name"], r["value"]) for r in listed] == [
        (0, "width", 80.0),
        (1, "D1@Sketch1", 40.0),
    ]


async def test_refusals() -> None:
    adapter = await _mock()
    refused = await adapter.set_equation("X", '"Nope" * 2')
    no_dimension = await adapter.set_equation("D9@Nowhere", "1")
    no_config = await adapter.set_equation("X", "1", ["Short"])
    no_equation = await adapter.delete_equation("Ghost")

    assert refused.error == (
        'SolidWorks refused the equation "X" = "Nope" * 2; nothing was changed.'
    )
    assert no_dimension.error.startswith("No dimension named 'D9@Nowhere'")
    assert no_config.error.startswith("No configuration named 'Short'")
    assert no_equation.error == "No equation named 'Ghost'; the model has none."
    assert (await adapter.list_equations()).data == []


async def test_delete_keeps_the_dimension_value() -> None:
    adapter = await _mock()
    await adapter.set_equation("D1@Sketch1", "12")
    deleted = await adapter.delete_equation("D1@Sketch1")

    assert deleted.data == {"deleted": "D1@Sketch1", "equations": []}
    assert adapter._dimensions["D1@Sketch1"] == 12.0


async def test_no_model_is_an_error() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    for call in (
        adapter.list_equations(),
        adapter.set_equation("X", "1"),
        adapter.delete_equation("X"),
    ):
        assert (await call).error == "No active model"
