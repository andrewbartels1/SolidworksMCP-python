"""Close every open SolidWorks document, verify the process still answers,
then pause so it can settle.

Used by ``dev-test-combined`` between real-SolidWorks test batches. Running
the whole ``solidworks_only`` suite in one uninterrupted pytest session has
repeatedly driven SolidWorks into a degraded RPC state (or an outright
crash): documents pile up, and hundreds of rapid COM modelling calls with no
idle time exhaust it. Draining documents and idling a few seconds between
small batches keeps it stable.

Exit codes:

* ``0`` -- SolidWorks answered and no documents remain open.
* ``1`` -- SolidWorks answered but documents are still open (degraded).
* ``2`` -- SolidWorks is unreachable (not running / crashed / RPC dead).

Usage::

    python tests/scripts/sw_close_all_and_settle.py --settle 8
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time


def _solidworks_running() -> bool:
    """True if an ``SLDWORKS.exe`` process is alive.

    Checked before any COM call: ``win32com`` activation would otherwise
    *launch* SolidWorks (a 30-90s cold start) when it is not running, so a
    fast "is the process there" probe is what lets the preflight fail
    quickly with a clear message instead of silently booting SolidWorks.
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:  # noqa: BLE001 - if tasklist itself fails, assume running and let COM decide
        return True
    return "SLDWORKS.EXE" in out.stdout.upper()


async def _run(settle: float) -> int:
    if not _solidworks_running():
        print("[sw-reset] no SLDWORKS.exe process - SolidWorks is not running")
        return 2

    try:
        from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
    except Exception as exc:  # noqa: BLE001 - import error means we cannot proceed
        print(f"[sw-reset] cannot import adapter: {exc!r}")
        return 2

    adapter = PyWin32Adapter({})

    try:
        await adapter.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"[sw-reset] connect() failed - SolidWorks unreachable: {exc!r}")
        return 2

    try:
        health = await adapter.health_check()
        if not getattr(health, "healthy", False):
            print("[sw-reset] health_check reported unhealthy - SolidWorks unreachable")
            return 2

        listing = await adapter.list_open_documents()
        open_docs = list(listing.data or []) if listing.is_success else []
        titles = [d.get("title", "<untitled>") for d in open_docs]
        print(f"[sw-reset] open before: {titles or '[]'}")

        if open_docs:
            # Forceful drain first.
            adapter._attempt(
                lambda: adapter.swApp.CloseAllDocuments(True), default=None
            )
            # Then mop up anything CloseAllDocuments left (a doc mid-rebuild can
            # survive it); close_model acts on the active doc, so re-activate.
            for _ in range(len(open_docs) + 2):
                again = await adapter.list_open_documents()
                remaining = list(again.data or []) if again.is_success else []
                if not remaining:
                    break
                target = remaining[0].get("title") or remaining[0].get("path")
                if target:
                    await adapter.activate_document(target)
                closed = await adapter.close_model(save=False)
                if not closed.is_success:
                    break

        final = await adapter.list_open_documents()
        still_open = list(final.data or []) if final.is_success else []
        final_titles = [d.get("title", "<untitled>") for d in still_open]
        print(f"[sw-reset] open after:  {final_titles or '[]'}")

        rev = adapter._attempt(
            lambda: adapter._get_attr_or_call(adapter.swApp, "RevisionNumber"),
            default=None,
        )
        print(f"[sw-reset] SolidWorks RevisionNumber: {rev}")

        if settle > 0:
            print(f"[sw-reset] settling {settle:g}s ...")
            time.sleep(settle)

        if still_open:
            print("[sw-reset] WARNING: documents still open after drain")
            return 1
        print("[sw-reset] OK - SolidWorks healthy, no documents open")
        return 0
    finally:
        try:
            await adapter.disconnect()
        except Exception:  # noqa: BLE001 - disconnect is best-effort
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--settle",
        type=float,
        default=8.0,
        help="seconds to idle after closing docs (default: 8)",
    )
    args = parser.parse_args()
    return asyncio.run(_run(max(0.0, args.settle)))


if __name__ == "__main__":
    sys.exit(main())
