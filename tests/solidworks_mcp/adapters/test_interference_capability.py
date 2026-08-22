"""Contract tests for interference detection on the adapter surface.

``check_interference`` exists on the base adapter, the mock, the circuit
breaker and the connection pool. A method missing from either wrapper silently
degrades to the base "not implemented" default at runtime, and mock mode cannot
catch it — the mock is not wrapped — so the wiring is asserted directly here.

The name is the one ``tools/analysis.py`` already gates on with
``hasattr(adapter, "check_interference")``, so renaming it leaves that tool
unreachable with every adapter test still green.
"""

import inspect

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

CAPABILITY = "check_interference"

WRAPPERS = [
    SolidWorksAdapter,
    MockSolidWorksAdapter,
    CircuitBreakerAdapter,
    ConnectionPoolAdapter,
]


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer(cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, CAPABILITY, None)
    assert method is not None, f"{cls.__name__} is missing {CAPABILITY}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{CAPABILITY} must be async"
    )


def test_real_adapter_resolves_to_the_com_mixin() -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if CAPABILITY in vars(k)), None
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.{CAPABILITY} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


def test_wrappers_do_not_silently_fall_through_to_base() -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert CAPABILITY in vars(cls), (
            f"{cls.__name__} inherits {CAPABILITY} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


def test_capability_name_matches_the_tool_gate() -> None:
    """``analysis.py`` reaches the adapter only by this exact name."""
    from pathlib import Path

    import solidworks_mcp.tools.analysis as analysis_tools

    source = Path(analysis_tools.__file__).read_text(encoding="utf-8")
    assert f'hasattr(adapter, "{CAPABILITY}")' in source, (
        f"no tool in analysis.py gates on adapter.{CAPABILITY}; either the "
        "gate was renamed or this capability is unreachable"
    )


def test_the_obsolete_com_call_is_not_used() -> None:
    """``ToolsCheckInterference2`` must not come back.

    It is declared ``Sub`` with two ``ByRef`` out-parameters and on SW 2025
    could not be made to report anything through pywin32 late binding:
    ``pythoncom.Missing`` raises, a plain ``None`` or a typed array VARIANT
    raises ``Type mismatch``, a component array throws server-side, and a
    byref ``VT_VARIANT`` pair is accepted but leaves both out-parameters
    ``None`` on an assembly that demonstrably interferes.

    A reference implementation read its non-existent return value as a count
    (``int(raw[0])``), which would report "no interference" on an assembly
    that has some.
    """
    from pathlib import Path

    import solidworks_mcp.adapters.solidworks.io as io_module

    source = Path(io_module.__file__).read_text(encoding="utf-8")
    # Match the call syntax rather than the name, so the docstring explaining
    # why it is avoided does not trip its own guard.
    call_sites = [
        line.strip()
        for line in source.splitlines()
        if ".ToolsCheckInterference" in line and "(" in line
    ]
    assert not call_sites, (
        "ToolsCheckInterference2 is being called again; it cannot report a "
        f"result on SW 2025. Offending lines: {call_sites}"
    )


@pytest.mark.asyncio
async def test_mock_does_not_claim_a_clean_assembly() -> None:
    """The mock must not answer a question it cannot answer.

    ``interference_found: False`` from a mock would read as "checked and
    clean". The mock has no geometry, so the only honest answer is "not
    determinable".
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.insert_component("C:/parts/a.sldprt")
    await adapter.insert_component("C:/parts/b.sldprt")

    result = await adapter.check_interference({})
    assert result.is_success
    assert result.data["interference_found"] is None, (
        "the mock reported an interference verdict it never computed"
    )
    assert result.data["interference_count"] is None


@pytest.mark.asyncio
async def test_mock_refuses_with_fewer_than_two_components() -> None:
    """One component cannot interfere with anything."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.insert_component("C:/parts/a.sldprt")

    result = await adapter.check_interference({})
    assert not result.is_success


@pytest.mark.asyncio
async def test_base_default_reports_the_missing_capability() -> None:
    """The base default names the missing capability, not a fabrication.

    Called unbound: the default never touches ``self``.
    """
    result = await SolidWorksAdapter.check_interference(None, {})

    assert not result.is_success
    assert CAPABILITY in (result.error or "")


def test_tolerance_is_reported_as_unapplied() -> None:
    """The tool schema accepts a tolerance SolidWorks has no setting for.

    Dropping it silently would let a caller believe a tolerance was honoured,
    so the payload carries ``tolerance_applied`` explicitly.
    """
    from pathlib import Path

    import solidworks_mcp.adapters.solidworks.io as io_module

    source = Path(io_module.__file__).read_text(encoding="utf-8")
    assert '"tolerance_applied": None' in source
