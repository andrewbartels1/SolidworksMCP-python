"""Contract and behaviour tests for ``list_open_documents`` / ``activate_document``.

Both must exist on the base adapter, the mock, the circuit breaker and the
connection pool - a method missing from a wrapper silently degrades to the
base "not implemented" default at runtime, which mock mode cannot catch
because the mock is not wrapped.
"""

import inspect

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.adapters.solidworks.io import (
    _coerce_dispatch_sequence,
    _describe_open_document,
)

CAPABILITIES = ["list_open_documents", "activate_document"]

WRAPPERS = [
    SolidWorksAdapter,
    MockSolidWorksAdapter,
    CircuitBreakerAdapter,
    ConnectionPoolAdapter,
]


@pytest.mark.parametrize("capability", CAPABILITIES)
@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer(capability: str, cls: type) -> None:
    """Every adapter layer defines the capability as an async method."""
    method = getattr(cls, capability, None)
    assert method is not None, f"{cls.__name__} is missing {capability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{capability} must be async"
    )


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_wrappers_do_not_silently_fall_through_to_base(capability: str) -> None:
    """The breaker and pool define their own pass-through, not inherit the stub."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert capability in vars(cls), (
            f"{cls.__name__} inherits {capability} from the base adapter"
        )


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_real_adapter_resolves_to_the_io_mixin(capability: str) -> None:
    """PyWin32Adapter resolves the capability to the COM mixin, not the stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if capability in vars(k)), None
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.{capability} resolves to {owner}, not the COM mixin."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", CAPABILITIES)
async def test_base_defaults_report_missing_capability(capability: str) -> None:
    """The base default returns an error that names the missing capability."""
    method = getattr(SolidWorksAdapter, capability)
    result = await (
        method(None)
        if capability == "list_open_documents"
        else method(None, "whatever")
    )
    assert not result.is_success
    assert capability in (result.error or "")


# --- _coerce_dispatch_sequence ----------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected_len"),
    [
        (None, 0),
        ("single", 1),
        (["a", "b"], 2),
        (("a", None, "b"), 2),
        ([], 0),
    ],
)
def test_coerce_dispatch_sequence(raw: object, expected_len: int) -> None:
    """None, a bare dispatch and a tuple/list all normalise to a clean list."""
    assert len(_coerce_dispatch_sequence(raw)) == expected_len


# --- _describe_open_document ----------------------------------------------


class _FakeDoc:
    """Stand-in for ``IModelDoc2`` exposing the three accessors used."""

    def __init__(self, title: str, path: str, doc_type: int) -> None:
        """Store the values the fake's accessors return.

        Args:
            title: Value for ``GetTitle``.
            path: Value for ``GetPathName``.
            doc_type: Value for ``GetType`` (``swDocumentTypes_e``).
        """
        self._title = title
        self._path = path
        self._type = doc_type

    def GetTitle(self) -> str:
        """Return the document's window title."""
        return self._title

    def GetPathName(self) -> str:
        """Return the document's full path (empty when unsaved)."""
        return self._path

    def GetType(self) -> int:
        """Return the ``swDocumentTypes_e`` code for the document."""
        return self._type


class _FakeAdapter:
    """Minimal adapter surface: ``_attempt`` and ``_get_attr_or_call``."""

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

    @staticmethod
    def _get_attr_or_call(obj, name):  # noqa: ANN001
        """Return ``obj.name``, calling it when it resolves to a method.

        Args:
            obj: Object to read the attribute from.
            name: Attribute name.

        Returns:
            The attribute value, or its call result when callable.
        """
        attr = getattr(obj, name)
        return attr() if callable(attr) else attr


def test_describe_open_document_marks_active_by_title() -> None:
    """A title that matches the active title yields the full active summary."""
    doc = _FakeDoc("bracket.SLDPRT", r"C:\p\bracket.SLDPRT", 1)
    out = _describe_open_document(_FakeAdapter(), doc, "bracket.SLDPRT", None)
    assert out == {
        "title": "bracket.SLDPRT",
        "path": r"C:\p\bracket.SLDPRT",
        "type": "Part",
        "is_active": True,
    }


def test_describe_open_document_inactive_and_unknown_type() -> None:
    """A non-matching title is inactive; an unmapped type code is 'Unknown'."""
    doc = _FakeDoc("thing.SLDXXX", "", 99)
    out = _describe_open_document(_FakeAdapter(), doc, "other.SLDASM", None)
    assert out["is_active"] is False
    assert out["type"] == "Unknown"


def test_describe_open_document_falls_back_to_path_for_active_match() -> None:
    """With no active title, a case-insensitive path match marks the doc active."""
    doc = _FakeDoc("asm.SLDASM", r"C:\P\Asm.SLDASM", 2)
    out = _describe_open_document(_FakeAdapter(), doc, None, r"c:\p\asm.sldasm")
    assert out["is_active"] is True
    assert out["type"] == "Assembly"


# --- mock behaviour ----------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_list_open_documents_reports_active() -> None:
    """The mock marks only the most recently created model active."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    first = await adapter.create_part()
    second = await adapter.create_part()

    listed = await adapter.list_open_documents()
    assert listed.is_success
    by_title = {d["title"]: d for d in listed.data}
    assert by_title[first.data.name]["is_active"] is False
    assert by_title[second.data.name]["is_active"] is True


@pytest.mark.asyncio
async def test_mock_activate_document_switches_active() -> None:
    """activate_document makes the named model active in the mock."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    first = await adapter.create_part()
    await adapter.create_part()  # this one is active now

    result = await adapter.activate_document(first.data.name)
    assert result.is_success
    assert result.data["activated"] == first.data.name

    listed = await adapter.list_open_documents()
    active = [d["title"] for d in listed.data if d["is_active"]]
    assert active == [first.data.name]


@pytest.mark.asyncio
async def test_mock_activate_document_unknown_is_an_error() -> None:
    """Activating a model the mock never created is an error."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.activate_document("no-such-doc.SLDPRT")
    assert not result.is_success
    assert "No open document matches" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_activate_document_blank_is_an_error() -> None:
    """A blank target is rejected before any lookup."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.activate_document("   ")
    assert not result.is_success
