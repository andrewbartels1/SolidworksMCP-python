"""The equation methods on the base adapter: none is implemented there."""

from __future__ import annotations

from typing import Any

import pytest

from .test_base_configurations import _bare


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("list_equations", ()),
        ("set_equation", ("Width", "60mm")),
        ("delete_equation", ("Width",)),
    ],
)
async def test_each_equation_method_names_itself_as_missing(
    name: str, args: tuple[Any, ...]
) -> None:
    result = await getattr(_bare(), name)(*args)

    assert result.error == f"{name} is not implemented by this adapter"
