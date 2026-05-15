"""Tests for test ui prefab modules."""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any


class _Expr:
    """Test expr."""

    def __init__(self, value: Any = None) -> None:
        """Test init."""

        self.value = value

    def __getattr__(self, name: str) -> _Expr:
        """Test getattr."""

        return _Expr(name)

    def __getitem__(self, key: Any) -> _Expr:
        """Test getitem."""

        return _Expr(key)

    def __call__(self, *args: Any, **kwargs: Any) -> _Expr:
        """Test call."""

        return _Expr((args, kwargs))

    def __mod__(self, other: Any) -> _Expr:
        """Test mod."""

        return _Expr(("%", other))

    def __mul__(self, other: Any) -> _Expr:
        """Test mul."""

        return _Expr(("*", other))

    def __add__(self, other: Any) -> _Expr:
        """Test add."""

        return _Expr(("+", other))

    def __gt__(self, other: Any) -> _Expr:
        """Test gt."""

        return _Expr((">", other))

    def __le__(self, other: Any) -> _Expr:
        """Test le."""

        return _Expr(("<=", other))

    def then(self, *_args: Any) -> _Expr:
        """Test then."""

        return _Expr("then")

    def default(self, fallback: Any) -> Any:
        """Test default."""

        return fallback


class _Ctx:
    """Test ctx."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Test init."""

        self.args = args
        self.kwargs = kwargs

    def __enter__(self) -> _Ctx:
        """Test enter."""

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Test exit."""

        return False


class _Fetch:
    """Test fetch."""

    @staticmethod
    def get(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """Test get."""

        return {"method": "GET", "args": args, "kwargs": kwargs}

    @staticmethod
    def post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """Test post."""

        return {"method": "POST", "args": args, "kwargs": kwargs}


class _OpenFilePicker:
    """Test open file picker."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Test init."""

        self.args = args
        self.kwargs = kwargs


class _SetState:
    """Test set state."""

    def __init__(self, key: str, value: Any) -> None:
        """Test init."""

        self.key = key
        self.value = value


class _SetInterval:
    """Test set interval."""

    def __init__(self, every_ms: int, on_tick: Any) -> None:
        """Test init."""

        self.every_ms = every_ms
        self.on_tick = on_tick


class _ShowToast:
    """Test show toast."""

    def __init__(self, message: Any, variant: str = "default") -> None:
        """Test init."""

        self.message = message
        self.variant = variant


class _DashboardUIState:
    """Test dashboard uistate."""

    def model_dump(self) -> dict[str, Any]:
        """Test model dump."""

        return {"session_id": "prefab-dashboard"}


def _make_component_module() -> types.ModuleType:
    """Test make component module."""

    module = types.ModuleType("prefab_ui.components")
    names = [
        "Accordion",
        "AccordionItem",
        "Badge",
        "Button",
        "Card",
        "CardContent",
        "CardDescription",
        "CardFooter",
        "CardHeader",
        "CardTitle",
        "Checkbox",
        "Column",
        "DataTable",
        "DataTableColumn",
        "Embed",
        "Else",
        "Grid",
        "GridItem",
        "Image",
        "If",
        "Muted",
        "Progress",
        "Row",
        "Text",
        "Textarea",
    ]
    for name in names:
        setattr(module, name, _Ctx)
    return module


def _install_prefab_stubs() -> None:
    """Test install prefab stubs."""

    prefab_ui = types.ModuleType("prefab_ui")
    prefab_ui.PrefabApp = _Ctx

    actions = types.ModuleType("prefab_ui.actions")
    actions.Fetch = _Fetch
    actions.OpenFilePicker = _OpenFilePicker
    actions.SetInterval = _SetInterval
    actions.SetState = _SetState
    actions.ShowToast = _ShowToast

    components = _make_component_module()

    control_flow = types.ModuleType("prefab_ui.components.control_flow")
    control_flow.If = _Ctx
    control_flow.Else = _Ctx

    rx = types.ModuleType("prefab_ui.rx")
    rx.ERROR = _Expr("ERROR")
    rx.EVENT = _Expr("EVENT")
    rx.RESULT = _Expr("RESULT")
    rx.STATE = _Expr("STATE")
    rx.Rx = _Expr

    ui_schemas = types.ModuleType("solidworks_mcp.ui.schemas")
    ui_schemas.DashboardUIState = _DashboardUIState

    sys.modules["prefab_ui"] = prefab_ui
    sys.modules["prefab_ui.actions"] = actions
    sys.modules["prefab_ui.components"] = components
    sys.modules["prefab_ui.components.control_flow"] = control_flow
    sys.modules["prefab_ui.rx"] = rx
    sys.modules["solidworks_mcp.ui.schemas"] = ui_schemas


def test_prefab_modules_import_with_stubbed_prefab_ui(monkeypatch) -> None:
    """Test prefab modules import with stubbed prefab ui."""

    _install_prefab_stubs()

    for name in [
        "src.solidworks_mcp.ui.prefab_smoke_minimal",
        "src.solidworks_mcp.ui.prefab_smoke_fetch",
        "src.solidworks_mcp.ui.prefab_smoke_table",
        "src.solidworks_mcp.ui.prefab_trace_probe",
        "src.solidworks_mcp.ui.prefab_dashboard",
    ]:
        sys.modules.pop(name, None)
        module = importlib.import_module(name)
        assert module is not None


def test_prefab_dashboard_helper_functions(monkeypatch) -> None:
    """Test prefab dashboard helper functions."""

    _install_prefab_stubs()
    sys.modules.pop("src.solidworks_mcp.ui.prefab_dashboard", None)
    module = importlib.import_module("src.solidworks_mcp.ui.prefab_dashboard")

    assert module._result_state("workflow_mode", "unselected") == "unselected"
    toast = module._error_toast()
    assert isinstance(toast, _ShowToast)
    assert toast.variant == "error"

    hydrated = module._hydrate_from_result()
    assert isinstance(hydrated, list)
    assert hydrated


def test_prefab_trace_probe_helpers(monkeypatch) -> None:
    """Test prefab trace probe helpers."""

    _install_prefab_stubs()
    sys.modules.pop("src.solidworks_mcp.ui.prefab_trace_probe", None)
    module = importlib.import_module("src.solidworks_mcp.ui.prefab_trace_probe")

    assert module._result_state("workflow_mode", "unselected") == "unselected"

    errors = module._trace_error("probe")
    assert len(errors) == 2
    assert isinstance(errors[0], _SetState)
    assert isinstance(errors[1], _ShowToast)

    hydrated = module._hydrate_trace()
    assert isinstance(hydrated, list)
    assert hydrated

    refresh = module._refresh_trace()
    assert refresh["method"] == "GET"

    checklist = module._run_checklist()
    assert checklist["method"] == "GET"
