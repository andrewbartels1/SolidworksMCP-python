"""Contract and behaviour tests for the ``set_units`` capability.

``set_units`` must exist on the base adapter, the mock, the circuit breaker
and the connection pool - a method missing from a wrapper silently degrades
to the base "not implemented" default at runtime, which mock mode cannot
catch because the mock is not wrapped.
"""

import inspect

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.adapters.solidworks.io import (
    _apply_unit_system,
    _normalise_unit_system,
)

WRAPPERS = [
    SolidWorksAdapter,
    MockSolidWorksAdapter,
    CircuitBreakerAdapter,
    ConnectionPoolAdapter,
]


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_set_units_exists_on_every_layer(cls: type) -> None:
    """Every adapter layer defines ``set_units`` as an async method."""
    method = getattr(cls, "set_units", None)
    assert method is not None, f"{cls.__name__} is missing set_units"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.set_units must be async"
    )


def test_wrappers_do_not_silently_fall_through_to_base() -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert "set_units" in vars(cls), (
            f"{cls.__name__} inherits set_units from the base adapter, so calls "
            "to it return 'not implemented' instead of reaching the real adapter"
        )


def test_real_adapter_resolves_to_the_io_mixin() -> None:
    """PyWin32Adapter resolves ``set_units`` to the COM mixin, not the stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if "set_units" in vars(k)), None
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.set_units resolves to {owner}, not the COM mixin."
    )


@pytest.mark.asyncio
async def test_base_default_reports_missing_capability() -> None:
    """The base default returns an error naming the missing capability."""
    result = await SolidWorksAdapter.set_units(None, "mm")
    assert not result.is_success
    assert "set_units" in (result.error or "")


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("mm", "mm"),
        ("MM", "mm"),
        ("millimeters", "mm"),
        (" Inch ", "in"),
        ("inches", "in"),
        ("feet", "ft"),
        ("m", "m"),
        ("centimeter", "cm"),
    ],
)
def test_normalise_unit_system_accepts_aliases(token: str, expected: str) -> None:
    """Case, whitespace and long-form aliases all map to a canonical token."""
    assert _normalise_unit_system(token) == expected


@pytest.mark.parametrize("token", ["", "furlong", "mmgs", None])
def test_normalise_unit_system_rejects_unknown(token: str) -> None:
    """Empty, unknown and preset-name tokens return ``None``."""
    assert _normalise_unit_system(token) is None


class _FakeExt:
    """Minimal ``IModelDocExtension`` stand-in recording preference writes."""

    def __init__(self, readback: dict[int, int] | None = None) -> None:
        """Seed the readback map used by ``GetUserPreferenceInteger``.

        Args:
            readback: Optional starting ``{pref: value}`` map; writes update it.
        """
        self.writes: list[tuple[int, int, int]] = []
        self._readback = readback or {}

    def SetUserPreferenceInteger(self, pref: int, option: int, value: int) -> bool:
        """Record the write, update the readback map, and report success.

        Args:
            pref: ``swUserPreferenceIntegerValue_e`` slot.
            option: ``swUserPreferenceOption_e`` value.
            value: The integer to store.

        Returns:
            bool: Always ``True`` (tests override this to simulate rejection).
        """
        self.writes.append((pref, option, value))
        self._readback[pref] = value
        return True

    def GetUserPreferenceInteger(self, pref: int, option: int) -> int:
        """Return the stored value for ``pref``, or ``-1`` when unset.

        Args:
            pref: ``swUserPreferenceIntegerValue_e`` slot.
            option: ``swUserPreferenceOption_e`` value (ignored).

        Returns:
            int: The recorded value or ``-1``.
        """
        return self._readback.get(pref, -1)


class _FakeModel:
    """Stand-in for ``IModelDoc2`` with a fake ``Extension`` and rebuild count."""

    def __init__(self, ext: _FakeExt) -> None:
        """Attach the fake extension and zero the rebuild counter.

        Args:
            ext: The ``_FakeExt`` to expose as ``.Extension``.
        """
        self.Extension = ext
        self.rebuilt = 0

    def EditRebuild3(self) -> bool:
        """Count a rebuild request and report success."""
        self.rebuilt += 1
        return True

    def GraphicsRedraw2(self) -> None:
        """No-op stand-in for the graphics refresh call."""
        return None

    def SetSaveFlag(self) -> None:
        """No-op stand-in for marking the document dirty."""
        return None


class _FakeAdapter:
    """Just enough of the adapter surface for ``_apply_unit_system``."""

    @staticmethod
    def _attempt(fn, default=None):  # noqa: ANN001
        """Run ``fn`` and return ``default`` if it raises.

        Args:
            fn: Zero-argument callable to invoke.
            default: Value returned on any exception.

        Returns:
            The callable's result, or ``default``.
        """
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return default


def test_apply_unit_system_preset_sets_only_the_system_slot_and_verifies() -> None:
    """A preset writes only swUnitSystem and verifies against slot 263."""
    ext = _FakeExt()
    model = _FakeModel(ext)

    out = _apply_unit_system(_FakeAdapter(), model, "in")

    # A preset (IPS = 3) sets swUnitSystem (263) only; the preset drives the
    # linear unit, so the swUnitsLinear slot (47) is left alone.
    assert (263, 0, 3) in ext.writes
    assert not any(pref == 47 for pref, _opt, _val in ext.writes)
    assert model.rebuilt == 1
    assert out["verified"] is True
    assert out["observed_unit_system"] == 3
    assert out["set_call_ok"] is True


def test_apply_unit_system_custom_sets_both_slots_for_feet() -> None:
    """``ft`` has no preset, so it writes swUnitSystem=Custom plus swUnitsLinear."""
    ext = _FakeExt()
    out = _apply_unit_system(_FakeAdapter(), _FakeModel(ext), "ft")

    # ft has no preset: swUnitSystem (263) -> Custom (4),
    # swUnitsLinear (47) -> swFEET (4)
    assert (263, 0, 4) in ext.writes
    assert (47, 0, 4) in ext.writes
    assert out["verified"] is True
    assert out["observed_length_unit"] == 4


def test_apply_unit_system_raises_when_document_keeps_its_unit_system() -> None:
    """When the readback shows the doc did not move, the helper raises."""
    # The document reports swUnitSystem 5 (MMGS) no matter what is written.
    ext = _FakeExt(readback={263: 5, 47: 0})

    def _no_op_write(pref, option, value):  # noqa: ANN001
        """Record the write but leave the readback map unchanged (SW ignored it).

        Args:
            pref: Preference slot.
            option: Option value.
            value: Value that would have been written.

        Returns:
            bool: ``False`` - SW "accepted" the call but changed nothing.
        """
        ext.writes.append((pref, option, value))
        return False

    ext.SetUserPreferenceInteger = _no_op_write  # type: ignore[method-assign]

    with pytest.raises(Exception, match="was not adopted"):
        _apply_unit_system(_FakeAdapter(), _FakeModel(ext), "in")


def test_apply_unit_system_verified_none_when_readback_unavailable() -> None:
    """When the readback itself fails, ``verified`` is ``None`` (not ``False``)."""
    ext = _FakeExt()

    def _raise(pref, option):  # noqa: ANN001
        """Raise to simulate ``GetUserPreferenceInteger`` being unavailable.

        Args:
            pref: Preference slot (unused).
            option: Option value (unused).

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("no readback")

    ext.GetUserPreferenceInteger = _raise  # type: ignore[method-assign]

    out = _apply_unit_system(_FakeAdapter(), _FakeModel(ext), "cm")
    assert out["verified"] is None


@pytest.mark.asyncio
async def test_mock_set_units_records_on_current_model() -> None:
    """The mock stores the normalised token on the current model's properties."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.set_units("inch")
    assert result.is_success
    assert result.data["unit_system"] == "in"

    info = await adapter.get_model_info()
    assert (info.data or {}).get("units") == "in" or adapter._current_model.properties[
        "units"
    ] == "in"


@pytest.mark.asyncio
async def test_mock_set_units_rejects_unknown_token() -> None:
    """An unrecognised token is an error in the mock, as it is live."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.set_units("cubits")
    assert not result.is_success
    assert "Unrecognised" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_set_units_errors_without_active_model() -> None:
    """Calling set_units with no current model is an error."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.set_units("mm")
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_create_part_applies_and_validates_units() -> None:
    """create_part(units=...) normalises a valid token and rejects a bad one."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    ok = await adapter.create_part(units="Millimeters")
    assert ok.is_success
    assert ok.data.properties["units"] == "mm"

    bad = await adapter.create_part(units="smoots")
    assert not bad.is_success
