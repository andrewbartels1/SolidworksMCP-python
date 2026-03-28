"""Cleanup utility for generated SolidWorks integration artifacts."""

from __future__ import annotations

import platform
import shutil
import time
from pathlib import Path


def _read_com_value(obj: object, attr_name: str) -> str:
    """Read COM member that may be exposed as a method or property."""
    attr = getattr(obj, attr_name, "")
    try:
        value = attr() if callable(attr) else attr
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def _close_open_solidworks_docs_in_dir(target_dir: Path) -> None:
    """Attempt to close SolidWorks docs that point into the target directory."""
    if platform.system() != "Windows":
        return

    try:
        import win32com.client  # type: ignore
    except Exception:
        return

    try:
        sw_app = win32com.client.GetActiveObject("SldWorks.Application")
    except Exception:
        return

    target_prefix = str(target_dir.resolve()).lower()

    # pywin32 typically exposes this as a SAFEARRAY property (not callable).
    docs = getattr(sw_app, "GetDocuments", None)
    if not docs:
        return

    for doc in docs:
        path = _read_com_value(doc, "GetPathName")
        if not path:
            continue

        try:
            resolved = str(Path(path).resolve()).lower()
        except Exception:
            resolved = path.lower()

        if not resolved.startswith(target_prefix):
            continue

        # Prefer closing by full path; fallback to title.
        try:
            sw_app.CloseDoc(path)
        except Exception:
            title = _read_com_value(doc, "GetTitle")
            if title:
                try:
                    sw_app.CloseDoc(title)
                except Exception:
                    pass


def _remove_tree_with_retries(
    path: Path, attempts: int = 10, delay: float = 0.75
) -> None:
    """Remove a directory tree with retries for transient Windows file locks."""
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(path)
            return
        except PermissionError as exc:
            last_error = exc
            # Try to release common lock source (open SolidWorks documents)
            _close_open_solidworks_docs_in_dir(path)
            if attempt == attempts:
                break
            wait_s = delay * attempt
            print(
                f"Cleanup attempt {attempt}/{attempts} failed due to file lock; "
                f"retrying in {wait_s:.2f}s..."
            )
            time.sleep(wait_s)

    if last_error is not None:
        raise last_error


def _cleanup_children_best_effort(path: Path) -> list[str]:
    """Best-effort cleanup of directory contents; returns leftover entry names."""
    leftovers: list[str] = []

    for child in list(path.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except Exception:
            leftovers.append(child.name)

    for child in list(path.iterdir()):
        leftovers.append(child.name)

    return sorted(set(leftovers))


def main() -> int:
    """Test helper for main."""
    generated_dir = Path("tests") / ".generated" / "solidworks_integration"

    if not generated_dir.exists():
        print(f"No generated artifacts found at {generated_dir}")
        return 0

    try:
        _remove_tree_with_retries(generated_dir)
        print(f"Removed generated integration artifacts: {generated_dir}")
        return 0
    except PermissionError as exc:
        leftovers = _cleanup_children_best_effort(generated_dir)
        if leftovers:
            print(
                "Cleanup warning: some locked artifacts could not be removed yet: "
                + ", ".join(leftovers)
            )
        else:
            print(
                "Cleanup warning: directory handle is still locked; "
                "contents were removed successfully"
            )
        print(f"Original cleanup error: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
