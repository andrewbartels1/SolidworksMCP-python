"""The configuration methods on the base adapter: none is implemented there."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter

from .configuration_calls import CALLS, IDS

ALL = [*CALLS, ("delete_configuration", ("Long",), {})]


def _bare() -> SolidWorksAdapter:
    """A concrete adapter built from the base class alone."""
    abstract = getattr(SolidWorksAdapter, "__abstractmethods__", frozenset())

    async def _none(*_args: Any, **_kwargs: Any) -> None:
        return None

    body: dict[str, Any] = dict.fromkeys(abstract, _none)
    return type("_BareAdapter", (SolidWorksAdapter,), body)()


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args", "kwargs"), ALL, ids=[*IDS, "delete"])
async def test_each_configuration_method_names_itself_as_missing(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    result = await getattr(_bare(), name)(*args, **kwargs)

    assert result.error == f"{name} is not implemented by this adapter"
