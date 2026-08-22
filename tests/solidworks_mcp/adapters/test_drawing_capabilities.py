"""Contract tests for the drawing capabilities added to the adapter surface.

``create_drawing_view``, ``add_drawing_view``, ``create_technical_drawing``,
``add_note``, ``auto_dimension_view`` and ``list_drawing_views`` each exist on
the base adapter, the mock, the circuit breaker and the connection pool. A
method missing from either wrapper silently degrades to the base "not
implemented" default at runtime, and mock mode cannot catch it — the mock is
not wrapped — so the wiring is asserted directly here.

The method names are deliberately the ones ``tools/drawing.py`` already gates
on with ``hasattr(adapter, ...)``. Renaming any of them re-breaks the tools
without failing a single existing test, so the names are pinned below.
"""

import inspect

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

#: Capabilities added on this branch. These names are a contract with the
#: gates in ``tools/drawing.py`` — see the module docstring.
CAPABILITIES = [
    "create_drawing_view",
    "add_drawing_view",
    "create_technical_drawing",
    "add_note",
    "list_drawing_views",
]

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
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    The mixin methods are only reachable if they are defined *inside*
    ``SolidWorksIOMixin``. Written at module scope in ``io.py`` they still
    import cleanly, still pass every mock test, and still satisfy the layer
    checks above — but ``PyWin32Adapter`` then resolves the name to
    ``SolidWorksAdapter``'s "not implemented" default and the real COM code is
    never called. That happened on the assembly branch and only showed up
    under runtime MRO inspection.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (klass.__name__ for klass in PyWin32Adapter.__mro__ if capability in vars(klass)),
        None,
    )
    assert owner == "SolidWorksIOMixin", (
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


#: Capabilities a tool on this branch already reaches. ``tools/drawing.py``
#: guards each tool with ``hasattr(adapter, "<name>")``, so a rename here
#: leaves the tool refusing forever with every adapter test still green.
GATED_ON_THIS_BRANCH = [
    "add_drawing_view",
    "create_technical_drawing",
]

#: Capabilities whose tool gates arrive with the refuse-instead-of-fabricate
#: change. The names are chosen to match those gates exactly so that neither
#: branch has to touch ``tools/drawing.py`` — the tools light up when both
#: land. Until then these adapter methods are reachable only by direct call.
GATED_ONCE_REFUSAL_PR_LANDS = [
    "create_drawing_view",
    "add_note",
]


@pytest.mark.parametrize("capability", GATED_ON_THIS_BRANCH)
def test_capability_names_match_the_tool_gates(capability: str) -> None:
    """A tool on this branch must reach the adapter by this exact name."""
    from pathlib import Path

    import solidworks_mcp.tools.drawing as drawing_tools

    source = Path(drawing_tools.__file__).read_text(encoding="utf-8")
    assert f'hasattr(adapter, "{capability}")' in source, (
        f"no tool in drawing.py gates on adapter.{capability}; either the tool "
        "gate was renamed or this capability is unreachable"
    )


def test_every_capability_is_accounted_for() -> None:
    """No capability may be added without deciding how a tool reaches it.

    An adapter method no tool can call is dead weight; this forces the choice
    to be explicit rather than forgotten.
    """
    classified = set(GATED_ON_THIS_BRANCH) | set(GATED_ONCE_REFUSAL_PR_LANDS)
    unclassified = set(CAPABILITIES) - classified - {"list_drawing_views"}
    assert not unclassified, (
        f"{sorted(unclassified)} reach no tool and are not recorded as "
        "pending; add the gate or say why it is deferred"
    )


@pytest.mark.asyncio
async def test_mock_view_placement_accumulates_and_lists() -> None:
    """Placing views records state that list_drawing_views reflects back."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    empty = await adapter.list_drawing_views()
    assert empty.is_success
    assert empty.data == []

    first = await adapter.create_drawing_view(
        {"model_path": "C:/parts/a.sldprt", "orientation": "front"}
    )
    assert first.is_success
    assert first.data["views_before"] == 0
    assert first.data["views_after"] == 1

    second = await adapter.add_drawing_view(
        {"model_file": "C:/parts/a.sldprt", "view_type": "top"}
    )
    assert second.is_success
    assert second.data["views_after"] == 2

    listed = await adapter.list_drawing_views()
    assert listed.is_success
    assert len(listed.data) == 2


@pytest.mark.asyncio
async def test_mock_technical_drawing_adds_three_views() -> None:
    """create_technical_drawing lays out front, top and side."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_technical_drawing(
        {"model_file": "C:/parts/a.sldprt"}
    )
    assert result.is_success
    assert len(result.data["views"]) == 3
    assert result.data["projection"] == "third_angle"

    listed = await adapter.list_drawing_views()
    assert len(listed.data) == 3


@pytest.mark.asyncio
async def test_mock_first_angle_projection_is_honoured() -> None:
    """A first-angle request must not silently produce third-angle."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_technical_drawing(
        {"model_file": "C:/parts/a.sldprt", "projection": "first_angle"}
    )
    assert result.is_success
    assert result.data["projection"] == "first_angle"


@pytest.mark.asyncio
async def test_mock_does_not_claim_the_note_was_positioned() -> None:
    """The mock must not answer a placement check it cannot perform.

    ``positioned`` comes from ``IAnnotation::SetPosition`` on the real
    adapter. The mock has no sheet, so the only honest answer is "not
    determinable".
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_note({"text": "MATERIAL: AISI 1018"})
    assert result.is_success
    assert result.data["positioned"] is None, (
        "the mock reported a placement check it cannot perform"
    )


@pytest.mark.asyncio
async def test_mock_rejects_a_note_with_no_text() -> None:
    """An empty note is a validation error, not a fabricated success."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_note({"text": ""})
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_rejects_an_unknown_orientation() -> None:
    """An unknown orientation must fail rather than default to front."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_drawing_view(
        {"model_path": "C:/parts/a.sldprt", "orientation": "sideways"}
    )
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_view_placement_requires_a_model_path() -> None:
    """A view of nothing is an error, not an empty success."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_drawing_view({})
    assert not result.is_success


def test_dimension_import_is_not_claimed_as_a_capability() -> None:
    """``auto_dimension_view`` is deliberately absent, and must stay absent.

    ``IDrawingDoc::InsertModelAnnotations3`` could not be made to insert
    anything on SW 2025: it returns ``None`` with the view selected and
    activated, for both ``swInsertDimensions`` and
    ``swInsertDimensionsMarkedForDrawing``, with ``AllViews`` either way, on
    front and top views, against a part carrying a real sketch dimension, and
    after a ``ForceRebuild3``. ``IView::GetDisplayDimensionCount`` stayed 0
    throughout.

    Shipping it anyway would mean shipping a capability never observed to
    work — the exact failure this branch exists to correct. This test fails
    if someone adds it back without live proof.
    """
    from solidworks_mcp.adapters.base import SolidWorksAdapter as _Base

    assert not hasattr(_Base, "auto_dimension_view"), (
        "auto_dimension_view is back on the adapter surface; it must not "
        "ship until InsertModelAnnotations3 is shown to insert a dimension "
        "against real SolidWorks"
    )


def test_mock_orientations_match_the_com_layer() -> None:
    """The mock's accepted orientations must match the COM implementation.

    The two lists are maintained separately, so an orientation added to the
    COM layer alone would be rejected in mock mode and accepted live — and the
    whole test suite runs against the mock.
    """
    from solidworks_mcp.adapters.mock_adapter import _MOCK_NAMED_VIEWS
    from solidworks_mcp.adapters.solidworks.io import _NAMED_VIEWS

    assert set(_NAMED_VIEWS) == set(_MOCK_NAMED_VIEWS), (
        "orientation lists have drifted between io.py and mock_adapter.py"
    )


def test_payload_helper_accepts_dicts_models_and_none() -> None:
    """Tools hand the adapter dicts; direct callers may hand it a model."""
    from solidworks_mcp.adapters.solidworks.io import _first, _payload

    class _Model:
        def __init__(self) -> None:
            self.model_path = "C:/parts/a.sldprt"

        def model_dump(self) -> dict[str, str]:
            return {"model_path": self.model_path}

    assert _payload(None) == {}
    assert _payload({"a": 1}) == {"a": 1}
    assert _payload(_Model())["model_path"] == "C:/parts/a.sldprt"

    # model_file and model_path are the same thing on different schemas.
    assert _first({"model_file": "x"}, "model_path", "model_file") == "x"
    assert _first({}, "model_path", default="fallback") == "fallback"


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", CAPABILITIES)
async def test_base_defaults_report_missing_capability(capability: str) -> None:
    """The base defaults name the missing capability, not a fabrication.

    Called unbound: these defaults never touch ``self``, so this avoids
    standing up a concrete subclass just to reach them.
    """
    method = getattr(SolidWorksAdapter, capability)
    result = await (
        method(None) if capability == "list_drawing_views" else method(None, {})
    )

    assert not result.is_success
    assert capability in (result.error or ""), (
        f"the default for {capability} does not name the missing capability"
    )
