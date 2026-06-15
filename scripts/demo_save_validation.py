r"""Live end-to-end validation of issue #7 save-target safeguards.

Exercises every acceptance criterion from issue #7 against a running
SolidWorks instance so the validation is confirmed through the real tool
layer, not just unit-test mocks.

Criteria tested
---------------
AC1 — Saving to a nonexistent directory returns ``"status": "error"``
       with a clear message instead of an opaque COM exception.
AC2 — Saving to a non-writable directory returns ``"status": "error"``.
       (Windows ACL semantics make this unreliable without elevated
        privileges; tested via mock in unit tests, noted here.)
AC3 — Saving to an existing file with ``overwrite=False`` returns
       ``"status": "error"`` naming the conflicting file.
AC4 — Saving to an existing file with ``overwrite=True`` succeeds.
AC5 — Happy path (new file in writable directory) is unaffected.
AC6 — ``save_assembly`` applies the same guards as ``save_part``.

Run with the project virtualenv on a Windows box that already has SolidWorks
open (no specific file needs to be loaded — the script creates its own part)::

    .\.venv\Scripts\python.exe scripts\demo_save_validation.py
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
import traceback
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from fastmcp import FastMCP  # noqa: E402

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402
from solidworks_mcp.tools.file_management import register_file_management_tools  # noqa: E402

OUT_DIR = REPO_ROOT / "out" / "save_validation"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIP"

_results: list[tuple[str, str, str]] = []  # (criterion, status, detail)


def _record(criterion: str, status: str, detail: str = "") -> None:
    _results.append((criterion, status, detail))
    icon = "OK" if status == _PASS else ("--" if status == _SKIP else "NG")
    print(f"  {icon}  [{status}] {criterion}")
    if detail:
        print(f"        {detail}")


def _expect_error(criterion: str, result: dict[str, Any], fragment: str) -> None:
    """Assert the tool returned an error containing *fragment*."""
    if result.get("status") != "error":
        _record(criterion, _FAIL, f"expected error, got: {result}")
        return
    msg = result.get("message", "")
    if fragment.lower() not in msg.lower():
        _record(criterion, _FAIL, f"message missing '{fragment}': {msg!r}")
        return
    _record(criterion, _PASS, f"message: {msg!r}")


def _expect_success(criterion: str, result: dict[str, Any]) -> None:
    if result.get("status") == "success":
        _record(criterion, _PASS)
    else:
        _record(criterion, _FAIL, f"got: {result}")


async def _get_tool(server: FastMCP, name: str):
    for tool in await server.list_tools():
        if tool.name == name:
            return tool.fn
    raise RuntimeError(f"Tool '{name}' not found on server")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_validation() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    adapter = PyWin32Adapter({})
    print("Connecting to SolidWorks …")
    await adapter.connect()
    print(f"  Connected: {type(adapter.swApp).__name__}")

    try:
        # Create a throwaway part so the adapter has an active model
        part_result = await adapter.create_part()
        if not part_result.is_success:
            print(f"  ERROR: create_part failed: {part_result.error}")
            return 1
        print(f"  Created part: {part_result.data.name}")

        # Register tools with a local FastMCP server so we exercise the real
        # tool layer (including _prepare_save_target) and not just the adapter.
        server = FastMCP("save-validation-test")
        await register_file_management_tools(server, adapter, {})

        save_part_tool = await _get_tool(server, "save_part")
        save_assembly_tool = await _get_tool(server, "save_assembly")

        writable = OUT_DIR / "writable"
        writable.mkdir(parents=True, exist_ok=True)

        print("\n-- AC1: nonexistent directory ----------------------------------")
        ghost = OUT_DIR / "does_not_exist" / "part.sldprt"
        r = await save_part_tool(input_data={"file_path": str(ghost), "overwrite": True})
        _expect_error("AC1 save_part – missing dir", r, "Target directory does not exist")

        ghost_asm = OUT_DIR / "does_not_exist" / "asm.sldasm"
        r = await save_assembly_tool(input_data={"file_path": str(ghost_asm), "overwrite": True})
        _expect_error("AC1 save_assembly – missing dir", r, "Target directory does not exist")

        print("\n-- AC2: non-writable directory ---------------------------------")
        no_write = OUT_DIR / "readonly_dir"
        no_write.mkdir(parents=True, exist_ok=True)
        original_mode = no_write.stat().st_mode
        made_readonly = False
        try:
            # Remove write bits; on Windows this sets the read-only attribute.
            no_write.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            if not os.access(no_write, os.W_OK):
                made_readonly = True
                r = await save_part_tool(
                    input_data={"file_path": str(no_write / "part.sldprt"), "overwrite": True}
                )
                _expect_error("AC2 save_part – not writable", r, "not writable")
            else:
                _record(
                    "AC2 save_part – not writable",
                    _SKIP,
                    "os.access still returns W_OK after chmod on this Windows user; "
                    "covered by mock in unit tests",
                )
        finally:
            no_write.chmod(original_mode)

        print("\n-- AC3: overwrite=False with existing file ---------------------")
        existing_part = writable / "existing_part.sldprt"
        existing_part.write_bytes(b"placeholder")
        r = await save_part_tool(
            input_data={"file_path": str(existing_part), "overwrite": False}
        )
        _expect_error("AC3 save_part – overwrite=False", r, "already exists and overwrite=False")

        existing_asm = writable / "existing_asm.sldasm"
        existing_asm.write_bytes(b"placeholder")
        r = await save_assembly_tool(
            input_data={"file_path": str(existing_asm), "overwrite": False}
        )
        _expect_error("AC3 save_assembly – overwrite=False", r, "already exists and overwrite=False")

        # Default overwrite is False — same guard must fire without explicit flag.
        r = await save_part_tool(input_data={"file_path": str(existing_part)})
        _expect_error("AC3 save_part – default overwrite=False", r, "already exists and overwrite=False")

        print("\n-- AC4: overwrite=True with existing file ----------------------")
        r = await save_part_tool(
            input_data={"file_path": str(existing_part), "overwrite": True}
        )
        _expect_success("AC4 save_part – overwrite=True", r)

        print("\n-- AC5: happy path (new file, writable dir) --------------------")
        import time as _time
        new_part = writable / f"brand_new_part_{int(_time.time())}.sldprt"
        r = await save_part_tool(input_data={"file_path": str(new_part), "overwrite": False})
        _expect_success("AC5 save_part – happy path", r)
        if new_part.exists():
            print(f"        file written: {new_part} ({new_part.stat().st_size} bytes)")
        else:
            _record("AC5 save_part – file on disk", _FAIL, "file not found after save")

        # Extension normalisation: .step input → .sldprt on disk (overwrite=True
        # in case SW holds the file from a previous run of this script).
        step_path = writable / "normalised.step"
        r = await save_part_tool(input_data={"file_path": str(step_path), "overwrite": True})
        _expect_success("AC5 save_part – extension normalised to .sldprt", r)
        expected_ext = r.get("file_path", "")
        if expected_ext.endswith(".sldprt"):
            _record("AC5 extension check", _PASS, f"reported path: {expected_ext}")
        else:
            _record("AC5 extension check", _FAIL, f"reported path: {expected_ext}")

        print("\n-- AC6: save_assembly applies same guards ----------------------")
        # Need an active assembly for the happy-path save; create one now.
        asm_result = await adapter.create_assembly()
        if not asm_result.is_success:
            _record("AC6 save_assembly – create assembly", _FAIL, str(asm_result.error))
        else:
            new_asm = writable / f"brand_new_asm_{int(_time.time())}.sldasm"
            r = await save_assembly_tool(
                input_data={"file_path": str(new_asm), "overwrite": False}
            )
            _expect_success("AC6 save_assembly – happy path", r)
            if new_asm.exists():
                print(f"        file written: {new_asm} ({new_asm.stat().st_size} bytes)")

    finally:
        try:
            await adapter.disconnect()
            print("\nDisconnected.")
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN disconnect: {exc}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, s, _ in _results if s == _PASS)
    failed = sum(1 for _, s, _ in _results if s == _FAIL)
    skipped = sum(1 for _, s, _ in _results if s == _SKIP)
    for criterion, status, detail in _results:
        icon = "OK" if status == _PASS else ("--" if status == _SKIP else "NG")
        line = f"  {icon}  {criterion}"
        if detail:
            short = detail[:80] + "…" if len(detail) > 80 else detail
            line += f"\n       {short}"
        print(line)
    print(f"\n  {passed} passed  {failed} failed  {skipped} skipped")
    return 0 if failed == 0 else 1


def main() -> int:
    try:
        return asyncio.run(run_validation())
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
