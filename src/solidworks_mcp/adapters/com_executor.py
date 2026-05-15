"""
Single-threaded executor for SolidWorks COM calls.

Background: SolidWorks COM is STA (single-threaded apartment). An
``IDispatch`` proxy obtained on thread A cannot be invoked from thread B —
pywin32's late-binding surfaces this as
``AttributeError: SldWorks.Application.<method>``. FastMCP dispatches async
tool handlers on worker threads that are *not* the thread where
``connect()`` ran, so any cached ``swApp`` reference breaks.

This module provides a single dedicated STA worker thread (``ComExecutor``).
All COM work is submitted to it as callables and awaited via ``Future``.
Because exactly one thread ever touches COM:

1. ``CoInitialize()`` is called once at thread startup.
2. ``self.swApp`` and ``self.currentModel`` can be shared instance attributes
   without marshalling — no thread-local trickery.
3. STA constraints are satisfied (SW is happy).
4. ``_FlagAsMethod`` results accumulate on the same object lifetime.

Usage:

    executor = ComExecutor()
    executor.start()
    try:
        result = executor.submit(lambda: sw.ActiveDoc.GetTitle())
    finally:
        executor.stop()

or with the synchronous helper:

    with ComExecutor() as ex:
        title = ex.run(lambda: sw.ActiveDoc.GetTitle())
"""

from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from typing import Any, Callable, TypeVar

from loguru import logger

try:
    import pythoncom

    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False


T = TypeVar("T")


# Sentinel object used to signal the worker thread to exit.
_SHUTDOWN = object()


class ComExecutor:
    """Single-threaded STA executor for SolidWorks COM calls.

    Thread-safe: ``submit()`` / ``run()`` may be called from any thread.

    Lifecycle:
        - Construct: creates the executor (no thread yet).
        - ``start()``: launches the worker thread and waits for it to
          CoInitialize.
        - ``submit(fn)``: schedules ``fn`` on the worker; returns a Future.
        - ``run(fn)``: convenience wrapper around submit+result.
        - ``stop()``: signals the worker to exit, joins the thread, then
          CoUninitializes.
    """

    def __init__(self, name: str = "SolidWorks-COM") -> None:
        """Create the executor (thread not yet running).

        Args:
            name: Thread name for debugging / logs.
        """
        self._name = name
        self._queue: queue.Queue[Any] = queue.Queue()
        self._thread: threading.Thread | None = None
        # Set by worker thread once CoInitialize succeeds, allowing submit()
        # to block until the executor is truly ready.
        self._ready = threading.Event()
        self._stopped = threading.Event()

    # ---- Public API ----

    def start(self, timeout: float = 10.0) -> None:
        """Launch the worker thread and wait until it has CoInitialized.

        Idempotent: calling ``start()`` on a running executor is a no-op.

        Args:
            timeout: Seconds to wait for CoInitialize to complete. If it
                doesn't fire in time, raises RuntimeError.

        Raises:
            RuntimeError: Worker didn't become ready in time.
        """
        if self._thread is not None and self._thread.is_alive():
            return

        if not PYWIN32_AVAILABLE:
            raise RuntimeError(
                "pywin32 is required for ComExecutor; not available"
            )

        self._ready.clear()
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._worker, name=self._name, daemon=True
        )
        self._thread.start()

        if not self._ready.wait(timeout):
            raise RuntimeError(
                f"ComExecutor worker '{self._name}' did not "
                f"initialize within {timeout}s"
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the worker to exit and wait for it to join.

        After ``stop()`` returns, no further ``submit()`` calls will be
        serviced. Idempotent.

        Args:
            timeout: Seconds to wait for the worker to exit cleanly before
                abandoning the join.
        """
        if self._thread is None or not self._thread.is_alive():
            return

        self._queue.put(_SHUTDOWN)
        self._thread.join(timeout)
        if self._thread.is_alive():
            logger.warning(
                f"ComExecutor worker '{self._name}' did not exit "
                f"within {timeout}s; abandoning"
            )
        self._thread = None
        self._stopped.set()

    def submit(self, fn: Callable[[], T]) -> Future[T]:
        """Schedule ``fn`` to run on the worker thread.

        The callable receives no arguments — close over any state needed
        via the enclosing scope. The return value (or exception) is
        propagated through the returned ``Future``.

        Args:
            fn: Zero-argument callable to run on the COM thread.

        Returns:
            Future that will hold the result or exception.

        Raises:
            RuntimeError: Executor isn't running.
        """
        if self._thread is None or not self._thread.is_alive():
            raise RuntimeError(
                f"ComExecutor '{self._name}' is not running; "
                "call start() first"
            )

        fut: Future[T] = Future()
        self._queue.put((fn, fut))
        return fut

    def run(self, fn: Callable[[], T], timeout: float | None = None) -> T:
        """Run ``fn`` on the worker and block until the result is ready.

        Convenience wrapper around ``submit()`` + ``Future.result()``.

        Args:
            fn: Zero-argument callable to run on the COM thread.
            timeout: Seconds to wait before raising TimeoutError.

        Returns:
            Whatever ``fn`` returned.

        Raises:
            Any exception raised by ``fn``, re-raised in the caller.
            TimeoutError: if ``timeout`` elapses before ``fn`` finishes.
        """
        return self.submit(fn).result(timeout=timeout)

    # ---- Context manager ----

    def __enter__(self) -> "ComExecutor":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()

    # ---- Worker ----

    def _worker(self) -> None:
        """Run on the dedicated thread; initialize COM, process work, cleanup.

        Loop exits when ``_SHUTDOWN`` appears in the queue. Each work item
        is a ``(callable, Future)`` tuple; the callable runs, and the
        Future is set with either the result or the raised exception.
        """
        try:
            pythoncom.CoInitialize()
        except Exception as e:
            logger.error(
                f"CoInitialize failed in ComExecutor worker "
                f"'{self._name}': {e!r}"
            )
            # Ready anyway so start() doesn't hang; submit() will fail fast
            # because COM isn't actually initialized.
            self._ready.set()
            return

        self._ready.set()
        logger.info(f"ComExecutor '{self._name}' ready")

        try:
            while True:
                item = self._queue.get()
                if item is _SHUTDOWN:
                    break

                fn, fut = item
                if not fut.set_running_or_notify_cancel():
                    continue

                try:
                    result = fn()
                except BaseException as e:  # noqa: BLE001 — propagate everything
                    fut.set_exception(e)
                else:
                    fut.set_result(result)
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            logger.info(f"ComExecutor '{self._name}' stopped")
