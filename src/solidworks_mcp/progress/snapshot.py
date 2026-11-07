"""Refresh the committed type-library snapshot (Windows, SolidWorks installed).

Run after a SolidWorks upgrade, then regenerate the progress files::

    python -m solidworks_mcp.progress.snapshot
    python -m solidworks_mcp.progress.generate

It reads the pywin32 gen_py wrapper of ``sldworks.tlb``; SolidWorks itself
doesn't need to be running.
"""

from __future__ import annotations

from pathlib import Path

from ..adapters import sw_type_info
from .com_coverage import Snapshot

#: Where the snapshot is committed, relative to the repository root.
SNAPSHOT_PATH = Path("docs/assets/progress/com_snapshot.json")


def take_snapshot() -> Snapshot:
    """Read the installed type library's interface and method names.

    Returns:
        Snapshot: The names, with the wrapper's module name as its source.

    Raises:
        RuntimeError: If the gen_py wrapper isn't available.
    """
    library = sw_type_info.type_library_name()
    if library is None:
        raise RuntimeError(
            "The SolidWorks type library isn't available: run this on Windows "
            "with SolidWorks and pywin32 installed."
        )
    # The module name carries the IID and version; keep the part after gen_py.
    return Snapshot(library.rsplit(".", 1)[-1], sw_type_info.all_interface_methods())


def main(root: Path | None = None) -> Path:
    """Write the snapshot under ``root``.

    Args:
        root: The repository root; the current directory when omitted.

    Returns:
        Path: The file written.
    """
    path = (root or Path.cwd()) / SNAPSHOT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(take_snapshot().to_json(), encoding="utf-8", newline="\n")
    return path


if __name__ == "__main__":
    print(main())
