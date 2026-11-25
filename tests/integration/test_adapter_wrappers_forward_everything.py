"""Every adapter method a tool can call reaches SolidWorks through each wrapper.

The server wraps the PyWin32 adapter in ``CircuitBreakerAdapter`` (and can
pool it with ``ConnectionPoolAdapter``). A method the wrapper doesn't define
fails as ``AttributeError`` before SolidWorks is called (#267:
``pack_and_go_assembly``), so each wrapper and the base adapter must define
every public async method the PyWin32 adapter has.
"""

from __future__ import annotations

import inspect

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

#: Methods the base adapter has no stand-in for on purpose.
_BASE_EXCEPTIONS = {"execute_macro"}


def _async_methods(cls: type) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(cls)
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    }


@pytest.mark.parametrize("wrapper", [CircuitBreakerAdapter, ConnectionPoolAdapter])
def test_each_wrapper_forwards_every_adapter_method(wrapper: type) -> None:
    missing = _async_methods(PyWin32Adapter) - _async_methods(wrapper)
    assert not missing, f"{wrapper.__name__} doesn't forward {sorted(missing)}"


def test_the_base_adapter_has_every_method() -> None:
    missing = _async_methods(PyWin32Adapter) - _async_methods(SolidWorksAdapter)
    assert missing <= _BASE_EXCEPTIONS, sorted(missing - _BASE_EXCEPTIONS)
