"""Batch-convert STEP/STP files to native SolidWorks part files (.SLDPRT).

The SolidWorks "3D Interconnect" feature, enabled by default in modern
versions, makes ``OpenDoc6`` return a *linked reference* to the STEP file
instead of importing its geometry. That's unusable for assembly component
insertion (AddComponent5 needs a SLDPRT with real geometry). This script
temporarily disables 3D Interconnect (preference toggle ``691``), opens
each STEP, saves as SLDPRT, closes, and restores the toggle.

Usage
-----

Single file::

    .venv\\Scripts\\python.exe -m solidworks_mcp.utils.convert_step_to_sldprt \\
        "G:/path/to/part.step"

Whole directory (non-recursive)::

    .venv\\Scripts\\python.exe -m solidworks_mcp.utils.convert_step_to_sldprt \\
        "G:/path/to/folder"

Recursive directory::

    .venv\\Scripts\\python.exe -m solidworks_mcp.utils.convert_step_to_sldprt \\
        "G:/path/to/folder" --recursive

Options::

    --overwrite          Overwrite existing .SLDPRT files (default: skip)
    --recursive          Recurse into subdirectories
    --dry-run            Report what would be converted without doing it

Prerequisites
-------------

- Running SolidWorks (the script attaches to the active instance via
  ``GetActiveObject``). If SW isn't already open the script will launch it.
- No file with the same stem already open in SW (SW refuses to overwrite
  a file that's currently loaded).
- Write permission on the destination directory.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make the package importable when this script is invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time  # noqa: E402

import pythoncom  # noqa: E402
import win32api  # noqa: E402
import win32com.client  # noqa: E402
from win32com.client import dynamic  # noqa: E402

from solidworks_mcp.adapters import sw_type_info  # noqa: E402
from solidworks_mcp.adapters.com_executor import ComExecutor  # noqa: E402


# swUserPreferenceToggle_e constants (from swconst.tlb).
# Verified by introspection of the gen_py wrapper for SW 2025.
SW_PREF_MULTICAD_ENABLE_3D_INTERCONNECT = 691

# swDocumentTypes_e constants.
SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DOC_DRAWING = 3

# swOpenDocOptions_e.
SW_OPEN_SILENT = 1

# swSaveAsOptions_e.
SW_SAVE_SILENT = 1

# swFileLoadError_e bits worth decoding on the fly.
_LOAD_ERROR_BITS = {
    1: "GenericError",
    2: "FileNotFound",
    16: "ReadOnlyAccess",
    128: "AlreadyOpen",
    256: "RequiresReMigration",
    512: "SameTitleAlreadyOpen",
    4096: "InvalidInputError",
    65536: "CannotOpenInProduct",
    2097152: "TranslationFailed / ThreeDInterconnectIssue",
}


def _decode_errors(error_code: int) -> str:
    """Describe a ``swFileLoadError_e`` bitmask for log readability."""
    if error_code == 0:
        return "none"
    parts = [name for bit, name in _LOAD_ERROR_BITS.items() if error_code & bit]
    return ", ".join(parts) if parts else f"unknown(0x{error_code:X})"


def _find_step_files(target: Path, *, recursive: bool) -> list[Path]:
    """Return the STEP files implied by ``target``.

    If ``target`` is a file, returns it (if it's STEP) or empty.
    If a directory, walks it (optionally recursively) and returns
    every .step/.stp file.
    """
    if target.is_file():
        if target.suffix.lower() in {".step", ".stp"}:
            return [target]
        return []
    if not target.is_dir():
        return []
    pattern = "**/*" if recursive else "*"
    return sorted(
        p
        for p in target.glob(pattern)
        if p.suffix.lower() in {".step", ".stp"} and p.is_file()
    )


_EXT_BY_DOC_TYPE = {SW_DOC_PART: ".SLDPRT", SW_DOC_ASSEMBLY: ".SLDASM"}


def convert_one(
    sw: object,
    step_path: Path,
    *,
    overwrite: bool,
    dry_run: bool,
    poll_timeout_s: float = 60.0,
) -> tuple[bool, str]:
    """Convert a single STEP file to SLDPRT/SLDASM.

    Runs inside the ComExecutor thread — callers must not invoke this
    from elsewhere.

    Uses the **ShellExecute workaround** (not ``OpenDoc6``): on SW 2025
    the API's STEP translator returns ``swFileRequiresRepairError``
    (0x200000) for virtually all foreign-format imports even with
    3D Interconnect and Import Diagnostics disabled. The Windows shell
    handler path goes through a different SW code branch that imports
    cleanly. We detect the newly-opened document by polling
    ``GetDocumentCount`` and grabbing ``ActiveDoc`` once it increases.

    The output extension is chosen from the imported doc's actual type
    (STEP files can be parts OR assemblies; SW decides after translation).
    If an output file already exists and ``overwrite`` is False, the STEP
    is skipped without opening SW at all.

    Returns:
        (success, message) pair. ``success=False`` on skip or failure.
    """
    # Guess the target path based on input. We may correct the extension
    # after opening if it turns out to be an assembly.
    prospective_sldprt = step_path.with_suffix(".SLDPRT")
    prospective_sldasm = step_path.with_suffix(".SLDASM")

    # Pre-flight: if either output already exists, respect --overwrite.
    existing = [p for p in (prospective_sldprt, prospective_sldasm) if p.exists()]
    if existing and not overwrite:
        names = ", ".join(p.name for p in existing)
        return (False, f"output exists (use --overwrite): {names}")

    if dry_run:
        return (
            True,
            f"would convert -> {prospective_sldprt.name} (.SLDASM if assembly)",
        )

    # Snapshot current doc count so we can detect the new one.
    try:
        n_before = int(sw.GetDocumentCount())
    except Exception as e:
        return (False, f"GetDocumentCount failed: {e!r}")

    # Trigger the UI-path import via Windows shell. This is synchronous
    # from ShellExecute's POV but SW does the actual work asynchronously.
    try:
        win32api.ShellExecute(0, "open", str(step_path), None, None, 1)
    except Exception as e:
        return (False, f"ShellExecute failed: {e!r}")

    # Poll for the new document. Large STEP assemblies can take tens of
    # seconds to translate, so give ``poll_timeout_s`` before giving up.
    deadline = time.monotonic() + poll_timeout_s
    while time.monotonic() < deadline:
        time.sleep(0.5)
        try:
            if int(sw.GetDocumentCount()) > n_before:
                break
        except Exception:
            continue
    else:
        return (False, f"SW didn't open the file within {poll_timeout_s}s")

    # Small settle delay — SW reports the doc as active slightly before
    # translation finishes. Without this the first API call often sees
    # an uninitialized dispatch.
    time.sleep(0.5)

    doc = sw.ActiveDoc
    if doc is None:
        return (False, "ActiveDoc is None after import")
    # Python can reuse the memory address (id) of a previously-flagged
    # dispatch that was closed; the flag cache would then short-circuit
    # flagging on what is actually a fresh, un-flagged IDispatch. Drop
    # any stale cache entry before flagging.
    sw_type_info.invalidate_flag_cache(doc)
    sw_type_info.flag_methods(doc, "IModelDoc2", "IPartDoc", "IAssemblyDoc")

    try:
        doc_type = int(doc.GetType())
    except Exception as e:
        # If we can't even read GetType, something's deeply wrong.
        return (False, f"GetType failed after import: {e!r}")

    out_ext = _EXT_BY_DOC_TYPE.get(doc_type)
    if out_ext is None:
        # Unknown doc type (drawings don't come from STEP) — bail gracefully.
        try:
            sw.CloseDoc(doc.GetTitle())
        except Exception:
            pass
        return (False, f"unexpected doc type {doc_type} after STEP import")

    out_path = step_path.with_suffix(out_ext)

    # Use the single-arg SaveAs form — the Extension.SaveAs 6-arg variant
    # hits pywin32 VARIANT type issues with None/Missing for the export
    # data parameter.
    try:
        ok = bool(doc.SaveAs(str(out_path)))
    except Exception as e:
        # Best-effort close before returning the error.
        try:
            sw.CloseDoc(doc.GetTitle())
        except Exception:
            pass
        return (False, f"SaveAs raised: {type(e).__name__}: {e}")

    # Always close the imported doc so subsequent files in a batch don't
    # collide on "document already open".
    try:
        sw.CloseDoc(doc.GetTitle())
    except Exception:
        pass

    if not ok:
        return (False, "SaveAs returned False")
    if not out_path.exists():
        return (False, "SaveAs reported success but file not written")

    return (True, f"{out_path.name} ({out_path.stat().st_size:,} bytes)")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        description=(
            "Batch-convert STEP/STP files to SolidWorks native "
            ".SLDPRT via the pywin32 COM adapter."
        ),
    )
    parser.add_argument(
        "target",
        type=Path,
        help="STEP file or directory containing STEP files",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .SLDPRT files (default: skip)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories when target is a folder",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be converted, don't actually do it",
    )
    args = parser.parse_args(argv)

    target: Path = args.target.resolve()
    if not target.exists():
        print(f"ERROR: path not found: {target}")
        return 2

    step_files = _find_step_files(target, recursive=args.recursive)
    if not step_files:
        print(f"No STEP files found under: {target}")
        return 1

    print(f"Found {len(step_files)} STEP file(s).")

    # Sole owner of the COM apartment for the duration of the batch.
    com = ComExecutor(name="convert-step")
    com.start()
    try:

        def _setup() -> tuple[object, bool]:
            try:
                raw = win32com.client.GetActiveObject("SldWorks.Application")
                app = dynamic.Dispatch(raw._oleobj_)
            except Exception:
                app = dynamic.Dispatch("SldWorks.Application")
            sw_type_info.flag_methods(app, "ISldWorks")
            app.Visible = True

            # Capture current state so we restore it faithfully.
            was_on = bool(
                app.GetUserPreferenceToggle(SW_PREF_MULTICAD_ENABLE_3D_INTERCONNECT)
            )
            if was_on:
                app.SetUserPreferenceToggle(
                    SW_PREF_MULTICAD_ENABLE_3D_INTERCONNECT, False
                )
            return (app, was_on)

        sw, interconnect_was_on = com.run(_setup, timeout=30.0)
        if interconnect_was_on:
            print(
                "3D Interconnect was enabled — temporarily disabled for "
                "this batch (will restore on exit)."
            )

        ok_count = 0
        skip_count = 0
        fail_count = 0
        for step_path in step_files:
            print(f"[{step_path.name}] ", end="", flush=True)
            try:
                ok, msg = com.run(
                    lambda p=step_path: convert_one(
                        sw,
                        p,
                        overwrite=args.overwrite,
                        dry_run=args.dry_run,
                    ),
                    timeout=300.0,
                )
            except Exception as e:
                ok, msg = False, f"exception: {type(e).__name__}: {e}"

            if ok:
                print(f"OK: {msg}")
                ok_count += 1
            elif "exists" in msg or "would convert" in msg:
                print(msg)
                skip_count += 1
            else:
                print(f"FAIL: {msg}")
                fail_count += 1

        # Restore the 3D Interconnect preference.
        def _restore() -> None:
            if interconnect_was_on:
                sw.SetUserPreferenceToggle(
                    SW_PREF_MULTICAD_ENABLE_3D_INTERCONNECT, True
                )

        com.run(_restore, timeout=10.0)
    finally:
        com.stop()

    print(f"\nDone. {ok_count} converted, {skip_count} skipped, {fail_count} failed.")
    return 0 if fail_count == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
