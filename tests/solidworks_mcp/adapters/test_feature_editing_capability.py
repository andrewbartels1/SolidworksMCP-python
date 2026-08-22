"""Contract tests for the feature-editing capabilities.

``delete_feature``, ``suppress_feature`` and ``undo`` each exist on the base
adapter, the mock, the circuit breaker and the connection pool. A method
missing from either wrapper silently degrades to the base "not implemented"
default at runtime, and mock mode cannot catch it — the mock is not wrapped —
so the wiring is asserted directly here.
"""

import inspect

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

CAPABILITIES = ["delete_feature", "suppress_feature", "undo"]

WRAPPERS = [
    SolidWorksAdapter,
    MockSolidWorksAdapter,
    CircuitBreakerAdapter,
    ConnectionPoolAdapter,
]


@pytest.mark.parametrize("capability", CAPABILITIES)
@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer(capability: str, cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, capability, None)
    assert method is not None, f"{cls.__name__} is missing {capability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{capability} must be async"
    )


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_real_adapter_resolves_to_the_com_mixin(capability: str) -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if capability in vars(k)), None
    )
    assert owner == "SolidWorksFeaturesMixin", (
        f"PyWin32Adapter.{capability} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_wrappers_do_not_silently_fall_through_to_base(capability: str) -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert capability in vars(cls), (
            f"{cls.__name__} inherits {capability} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


def test_zero_arg_edit_members_are_not_called_with_parentheses() -> None:
    """``EditSuppress2`` and friends must go through ``_get_attr_or_call``.

    Late binding resolves these zero-argument members as properties on some
    dispatches. Calling them with ``()`` performs the edit and *then* raises
    ``'bool' object is not callable``, so the operation succeeds while the
    caller is told it failed — measured on SW 2025 before this was fixed.
    """
    from pathlib import Path

    import solidworks_mcp.adapters.solidworks.features as features_module

    source = Path(features_module.__file__).read_text(encoding="utf-8")
    for member in ("EditSuppress2", "EditUnsuppress2", "EditDelete", "IsSuppressed"):
        assert f".{member}()" not in source, (
            f"{member} is called with parentheses; late binding may resolve it "
            "as a property, which raises after the edit has already happened. "
            "Use adapter._get_attr_or_call(obj, name)."
        )


@pytest.mark.asyncio
async def test_mock_delete_removes_the_feature() -> None:
    """delete_feature removes the named feature and reports the change."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    created = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    assert created.is_success
    name = created.data.name

    result = await adapter.delete_feature(name)
    assert result.is_success
    assert result.data["features_after"] < result.data["features_before"]

    listed = await adapter.list_features()
    remaining = [
        (f.get("name") if isinstance(f, dict) else getattr(f, "name", None))
        for f in listed.data or []
    ]
    assert name not in remaining


@pytest.mark.asyncio
async def test_mock_delete_of_a_missing_feature_is_an_error() -> None:
    """Deleting something absent must fail, not report a silent success."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.delete_feature("NoSuchFeature")
    assert not result.is_success
    assert "NoSuchFeature" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_suppress_round_trips() -> None:
    """suppress then unsuppress reports the state each way."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    created = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    name = created.data.name

    on = await adapter.suppress_feature(name, True)
    assert on.is_success
    assert on.data["suppressed"] is True
    assert on.data["was_suppressed"] is False

    off = await adapter.suppress_feature(name, False)
    assert off.is_success
    assert off.data["suppressed"] is False
    assert off.data["was_suppressed"] is True


@pytest.mark.asyncio
async def test_mock_suppress_of_a_missing_feature_is_an_error() -> None:
    """Suppressing something absent must fail."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.suppress_feature("NoSuchFeature", True)
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_undo_with_nothing_to_undo_reports_no_change() -> None:
    """An undo that changed nothing must say so.

    SolidWorks accepts an undo on an empty stack without complaining, so
    ``tree_changed`` is the only way a caller can tell. A mock that always
    reported ``True`` would make that check worthless.
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.undo(1)
    assert result.is_success
    assert result.data["tree_changed"] is False, result.data


@pytest.mark.asyncio
async def test_mock_undo_removes_the_last_feature() -> None:
    """An undo with something to undo reports the change."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    await adapter.create_extrusion(ExtrusionParameters(depth=5.0))

    result = await adapter.undo(1)
    assert result.is_success
    assert result.data["tree_changed"] is True
    assert result.data["features_after"] < result.data["features_before"]


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", CAPABILITIES)
async def test_base_defaults_report_missing_capability(capability: str) -> None:
    """The base defaults name the missing capability, not a fabrication."""
    method = getattr(SolidWorksAdapter, capability)
    result = await (
        method(None, 1) if capability == "undo" else method(None, "Feature1")
    )

    assert not result.is_success
    assert capability in (result.error or "")
