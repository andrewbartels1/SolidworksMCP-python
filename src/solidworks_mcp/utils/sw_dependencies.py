"""Read the file paths out of SolidWorks' ``GetDependencies2`` reply."""

from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
from typing import Any

_MODEL_SUFFIXES = (".sldprt", ".sldasm", ".slddrw")


def dependency_paths(raw_dependencies: Any) -> list[Path]:
    """The model files in a ``GetDependencies2`` reply, each once, in order.

    ``IModelDoc2.GetDependencies2`` returns a flat array that alternates a
    document's name and its full path. Only full paths to SolidWorks model
    files are kept; a repeated path (compared as Windows does, ignoring case)
    is kept once.

    Args:
        raw_dependencies: The reply; anything other than a list or tuple
            gives no paths.

    Returns:
        list[Path]: The absolute model-file paths.
    """
    if not isinstance(raw_dependencies, (list, tuple)):
        return []
    paths: list[Path] = []
    seen: set[str] = set()
    for item in raw_dependencies:
        if not isinstance(item, str) or not item.lower().endswith(_MODEL_SUFFIXES):
            continue
        path = Path(item)
        key = os.path.normcase(os.path.normpath(item))
        absolute = path.is_absolute() or PureWindowsPath(item).is_absolute()
        if absolute and key not in seen:
            seen.add(key)
            paths.append(path)
    return paths
