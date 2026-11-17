"""The template methods on the base adapter: none is implemented there."""

from __future__ import annotations

from typing import Any

import pytest

from .template_calls import CALLS, IDS
from .test_base_part_features import _bare


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args", "kwargs"), CALLS, ids=IDS)
async def test_each_template_method_names_itself_as_missing(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    result = await getattr(_bare(), name)(*args, **kwargs)

    assert result.error == f"{name} is not implemented by this adapter"
