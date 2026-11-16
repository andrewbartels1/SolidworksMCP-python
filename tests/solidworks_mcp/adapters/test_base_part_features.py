"""The part-feature methods on the base adapter: none is implemented there."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter

from .part_feature_calls import CALLS, IDS


def _bare() -> SolidWorksAdapter:
    """A concrete adapter built from the base class alone."""
    abstract = getattr(SolidWorksAdapter, "__abstractmethods__", frozenset())

    async def _none(*_args: Any, **_kwargs: Any) -> None:
        return None

    def _false(*_args: Any, **_kwargs: Any) -> bool:
        return False

    body: dict[str, Any] = {
        name: (_false if name == "is_connected" else _none) for name in abstract
    }
    return type("_BareAdapter", (SolidWorksAdapter,), body)()


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args", "kwargs"), CALLS, ids=IDS)
async def test_each_part_feature_names_itself_as_missing(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    result = await getattr(_bare(), name)(*args, **kwargs)

    assert not result.is_success
    assert result.error == f"{name} is not implemented by this adapter"
