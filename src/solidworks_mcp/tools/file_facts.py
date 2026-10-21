"""Honest filesystem facts for tools that compare files without opening them.

``compare_drawing_versions`` and ``compare_templates`` cannot parse SolidWorks
file internals, so they report only what the filesystem can say: existence,
size, modification time and a content hash.
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Any


def file_fact_snapshot(path_str: str) -> dict[str, Any] | None:
    """Read basic filesystem facts about a file: size, mtime, SHA-256.

    Args:
        path_str: Path to the file.

    Returns:
        dict[str, Any] | None: ``path``, ``size_bytes``, ``modified_time`` and
        ``sha256``; ``None`` when the path is empty or not an existing file.
    """
    if not path_str:
        return None
    path = pathlib.Path(path_str)
    if not path.is_file():
        return None
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_time": stat.st_mtime,
        "sha256": digest.hexdigest(),
    }
