"""Shared fixtures and gating for the live-SolidWorks test suite.

Every ``tests/live/test_live_sw_*.py`` module needs a real SolidWorks install
and is skipped everywhere else. Rather than repeat the same ``pytestmark`` /
adapter fixture / scratch-doc cleanup in each file, they live here:

* When ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION`` is unset (every normal, CI or
  mock run) the modules are not even collected - ``collect_ignore_glob``.
* When it *is* set, every collected item is marked ``solidworks_only`` /
  ``windows_only`` so ``-m solidworks_only`` still selects exactly this suite
  (that marker split is what ``dev-test-combined`` keys off).
* ``live_adapter`` connects a ``PyWin32Adapter`` per test.
* ``connected_adapter`` is a thin alias (the regression suite's name for it);
  ``scratch`` wraps the adapter in ``_ScratchSession``, which on teardown
  closes only the never-saved documents a test created and deletes only the
  files it wrote - safe against a SolidWorks session with real work open.
* ``_pace_live_tests`` (autouse) drains every open document and idles
  ``SW_TEST_PACE_SECONDS`` after each test (default 0 = off;
  ``dev-test-combined`` sets 4). This is the recovery the per-batch
  ``sw_close_all_and_settle`` drain provided - a long uninterrupted run
  degrades (open assemblies accumulate, then ``create_part`` / ``open_model``
  start throwing ``RPC_E_DISCONNECTED``); doing it in-process per test is the
  same effect without a pytest subprocess per batch.

**Headless (opt-in, off by default).** Set ``SOLIDWORKS_MCP_HEADLESS=1`` and
every ``connect()`` leaves the SolidWorks window hidden instead of showing
it. That is ~40% faster - but SolidWorks' sketch APIs
(``CreateCornerRectangle``, ``InsertSketch``) intermittently fail with
``RPC_E_DISCONNECTED`` when the window is hidden, so two of eight wave3 tests
flaked on every headless run while the visible suite is 8/8. Not worth
defaulting on. ``pytest_sessionfinish`` restores the window if it was set.

Turning off the render passes (RealView, shadows, ambient occlusion, edge AA)
plus ``VerifyOnRebuild`` was also tried and showed no measurable change - the
remaining time is ``create_part`` (default-template load, ~5 s) and the
geometry-kernel rebuilds, both SolidWorks-internal. A fresh SolidWorks
process still helps most: a long session (many connects, a crash/relaunch)
visibly slows every call.
"""

from __future__ import annotations

import os
import platform
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio

_REAL_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"
_REAL_ENABLED = os.getenv(_REAL_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}

# Headless is NOT enabled here. It is honoured only if the caller exports
# SOLIDWORKS_MCP_HEADLESS themselves - the adapter reads it directly. Default
# on made two wave3 tests flake every run and once brought the whole process
# down with `Windows fatal exception: 0x80010108` (RPC_E_DISCONNECTED) mid
# create_part: SolidWorks' sketch/doc COM surface is not reliable with the
# window hidden. The visible suite is 8/8.


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Un-hide the SolidWorks window the headless run left hidden (best effort)."""
    if os.getenv("SOLIDWORKS_MCP_HEADLESS", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    try:  # pragma: no cover - only meaningful with a live SolidWorks
        import pythoncom  # noqa: F401
        import win32com.client

        win32com.client.Dispatch("SldWorks.Application").Visible = True
    except Exception:  # noqa: BLE001 - restoring the window is not worth failing over
        pass


# Skip collection entirely off-Windows or without the opt-in flag - same effect
# the per-file skipif pytestmark used to have, minus the "skipped" noise.
if not _REAL_ENABLED or platform.system() != "Windows":
    collect_ignore_glob = ["test_live_sw_*.py"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test under tests/live/ as the real-SolidWorks suite."""
    for item in items:
        nodeid = item.nodeid.replace("\\", "/")
        if "/live/" in nodeid or nodeid.startswith("live/"):
            item.add_marker(pytest.mark.solidworks_only)
            item.add_marker(pytest.mark.windows_only)


class _ScratchSession:
    """A connected adapter plus cleanup of only the scratch docs a test made.

    A document is closed on teardown only when it is new since the baseline
    snapshot **and** either was never saved *or* was saved to one of this
    test's own ``written_files`` paths. A real file the user already had open
    is never touched, even if the baseline snapshot comes back empty.
    """

    def __init__(self, adapter) -> None:  # noqa: ANN001
        """Snapshot the currently open documents as the do-not-close baseline."""
        self.adapter = adapter
        self._baseline: set[str] = self._open_titles()
        self.written_files: list[str] = []

    def _open_docs(self) -> list:
        """Return the currently open ``IModelDoc2`` dispatches (never ``None``)."""
        raw = self.adapter._attempt(
            lambda: self.adapter.swApp.GetDocuments(), default=None
        )
        if isinstance(raw, (list, tuple)):
            return [d for d in raw if d is not None]
        return [raw] if raw else []

    def _open_titles(self) -> set[str]:
        """Return the window titles of every currently open document."""
        titles: set[str] = set()
        for d in self._open_docs():
            t = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetTitle"), default=None
            )
            if t:
                titles.add(str(t))
        return titles

    def cleanup(self) -> None:
        """Close every scratch document opened here, and delete any files written."""
        owned = {os.path.normcase(os.path.abspath(f)) for f in self.written_files}
        for d in self._open_docs():
            title = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetTitle"), default=None
            )
            path = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetPathName"),
                default=None,
            )
            if not title or str(title) in self._baseline:
                continue
            if path and os.path.normcase(os.path.abspath(str(path))) not in owned:
                continue
            self.adapter._attempt(lambda t=str(title): self.adapter.swApp.CloseDoc(t))
        for f in self.written_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass


@pytest.fixture(autouse=True)
def _pace_live_tests() -> Iterator[None]:
    """After each live test: drain every open document, then idle.

    Only active when ``SW_TEST_PACE_SECONDS`` is set (``dev-test-combined``
    sets 4); a bare ``pytest tests/live/`` stays fast. This is what the
    per-batch ``sw_close_all_and_settle`` drain used to do - the batching
    itself was subprocess churn, but closing leaked documents and giving
    SolidWorks a breather between real COM tests is what actually kept a long
    run from degrading (open assemblies pile up, then ``create_part`` /
    ``open_model`` start throwing ``RPC_E_DISCONNECTED``). Doing it in-process
    per test is the same effect without spawning a pytest per batch.
    """
    import time

    yield

    try:
        pace = float(os.getenv("SW_TEST_PACE_SECONDS", "0"))
    except ValueError:
        pace = 0.0
    if pace <= 0:
        return

    # Best-effort drain on a throwaway connection (app-global, cheap).
    try:  # pragma: no cover - only meaningful with a live SolidWorks
        import asyncio

        from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

        async def _drain() -> None:
            adapter = PyWin32Adapter({})
            await adapter.connect()
            try:
                adapter._attempt(lambda: adapter.swApp.CloseAllDocuments(True))
            finally:
                await adapter.disconnect()

        asyncio.run(_drain())
    except Exception:  # noqa: BLE001 - the drain is a courtesy, never a failure
        pass

    time.sleep(pace)


@pytest_asyncio.fixture
async def live_adapter() -> AsyncIterator[object]:
    """A connected ``PyWin32Adapter``; disconnected on teardown."""
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    adapter = PyWin32Adapter({})
    await adapter.connect()
    try:
        yield adapter
    finally:
        await adapter.disconnect()


@pytest_asyncio.fixture
async def connected_adapter(live_adapter: object) -> AsyncIterator[object]:
    """The regression suite's name for :func:`live_adapter`."""
    yield live_adapter


@pytest_asyncio.fixture
async def scratch(live_adapter: object) -> AsyncIterator[_ScratchSession]:
    """Yield a scratch session; on teardown close only its docs and files."""
    session = _ScratchSession(live_adapter)
    try:
        yield session
    finally:
        session.cleanup()
