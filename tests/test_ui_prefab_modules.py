from __future__ import annotations

import importlib
import sys
import types
from typing import Any


class _Expr:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def __getattr__(self, name: str) -> "_Expr":
        return _Expr(name)

    def __call__(self, *args: Any, **kwargs: Any) -> "_Expr":
        return _Expr((args, kwargs))

    def __mod__(self, other: Any) -> "_Expr":
        return _Expr(("%", other))

    def __mul__(self, other: Any) -> "_Expr":
        return _Expr(("*", other))

    def __add__(self, other: Any) -> "_Expr":
        return _Expr(("+", other))

    def __gt__(self, other: Any) -> "_Expr":
        return _Expr((">", other))

    def __le__(self, other: Any) -> "_Expr":
        return _Expr(("<=", other))

    def then(self, *_args: Any) -> "_Expr":
        return _Expr("then")

    def default(self, fallback: Any) -> Any:
        return fallback


class _Ctx:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def __enter__(self) -> "_Ctx":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _Fetch:
    @staticmethod
    def get(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"method": "GET", "args": args, "kwargs": kwargs}

    @staticmethod
    def post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"method": "POST", "args": args, "kwargs": kwargs}


class _OpenFilePicker:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs


class _SetState:
    def __init__(self, key: str, value: Any) -> None:
        self.key = key
        self.value = value


class _SetInterval:
    def __init__(self, every_ms: int, on_tick: Any) -> None:
        self.every_ms = every_ms
        self.on_tick = on_tick


class _ShowToast:
    def __init__(self, message: Any, variant: str = "default") -> None:
        self.message = message
        self.variant = variant


class _DashboardUIState:
    def model_dump(self) -> dict[str, Any]:
        return {"session_id": "prefab-dashboard"}


def _make_component_module() -> types.ModuleType:
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
