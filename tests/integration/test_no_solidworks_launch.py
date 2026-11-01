"""Guard against code outside the adapter starting SolidWorks.

Creating ``SldWorks.Application`` (``Dispatch``, ``EnsureDispatch``,
``DispatchEx``, ``CoCreateInstance``) from a process outside the desktop
session, such as an SSH shell or a test run, starts a hidden SLDWORKS.exe that
nobody can see or close. The adapter is the one place allowed to start
SolidWorks; everything else attaches with ``GetActiveObject`` or goes through
the adapter.

These tests pin two things:

1. No module outside ``adapters/`` creates a COM object.
2. The ``tests/conftest.py`` guard refuses to create SolidWorks in a non-live
   run, so a regression fails the test that triggered it rather than leaving a
   stray SLDWORKS.exe behind.
"""

import ast
import os
import pathlib

import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "solidworks_mcp"
ADAPTERS_DIR = SRC_DIR / "adapters"

#: Calls that create (and so may launch) a COM server. Attaching to a running
#: one, ``GetActiveObject``, is not on the list.
COM_CREATE_CALLS = {
    "Dispatch",
    "DispatchEx",
    "EnsureDispatch",
    "CoCreateInstance",
    "CoCreateInstanceEx",
}

REAL_INTEGRATION = os.getenv(
    "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION", ""
).strip().lower() in {"1", "true", "yes", "on"}


def _com_create_calls(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in COM_CREATE_CALLS:
            found.append(f"{path.relative_to(SRC_DIR)}:{node.lineno} {name}()")
    return found


def test_only_the_adapter_creates_com_objects() -> None:
    offenders = [
        call
        for path in sorted(SRC_DIR.rglob("*.py"))
        if ADAPTERS_DIR not in path.parents
        for call in _com_create_calls(path)
    ]
    assert offenders == [], (
        "COM object creation outside adapters/ can launch a hidden SolidWorks; "
        f"attach with GetActiveObject or go through the adapter: {offenders}"
    )


@pytest.mark.skipif(REAL_INTEGRATION, reason="the guard is off in live runs")
def test_conftest_guard_refuses_to_create_solidworks(
    solidworks_launch_attempts: list[str],
) -> None:
    pythoncom = pytest.importorskip("pythoncom")
    win32com_client = pytest.importorskip("win32com.client")

    # If the guard were not installed the calls below would start SolidWorks.
    assert getattr(pythoncom.CoCreateInstance, "solidworks_launch_guard", False)
    assert getattr(pythoncom.CoCreateInstanceEx, "solidworks_launch_guard", False)

    try:
        with pytest.raises(pythoncom.com_error):
            pythoncom.CoCreateInstance(
                "SldWorks.Application",
                None,
                pythoncom.CLSCTX_SERVER,
                pythoncom.IID_IDispatch,
            )
        with pytest.raises(pythoncom.com_error):
            win32com_client.DispatchEx("SldWorks.Application")
        assert len(solidworks_launch_attempts) == 2
    finally:
        solidworks_launch_attempts.clear()


@pytest.mark.skipif(REAL_INTEGRATION, reason="the guard is off in live runs")
def test_conftest_guard_lets_other_com_servers_through() -> None:
    pythoncom = pytest.importorskip("pythoncom")
    win32com_client = pytest.importorskip("win32com.client")

    assert getattr(pythoncom.CoCreateInstance, "solidworks_launch_guard", False)

    dictionary = win32com_client.Dispatch("Scripting.Dictionary")
    dictionary.Add("key", "value")
    assert dictionary.Count == 1
