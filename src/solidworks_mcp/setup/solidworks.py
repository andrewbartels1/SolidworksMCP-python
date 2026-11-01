"""Which SolidWorks versions are installed, read from the Windows registry.

Each install leaves a key ``HKLM\\SOFTWARE\\SolidWorks\\SOLIDWORKS <year>``.
Setup only reports the years; the server finds the running SolidWorks itself.
"""

from __future__ import annotations

import re
from types import ModuleType
from typing import Any

_VERSION_KEY = re.compile(r"^SOLIDWORKS (\d{4})$", re.IGNORECASE)


def installed_versions(registry: ModuleType | None = None) -> list[int]:
    """List the installed SolidWorks years.

    Args:
        registry: A ``winreg``-like module; defaults to ``winreg`` (tests
            pass a fake).

    Returns:
        The years, newest first; empty off Windows or with no install.
    """
    if registry is None:
        try:
            import winreg
        except ImportError:  # not Windows
            return []
        registry = winreg
    reg: Any = registry  # winreg and the test fakes share this shape
    try:
        root = reg.OpenKey(reg.HKEY_LOCAL_MACHINE, r"SOFTWARE\SolidWorks")
    except OSError:  # no SolidWorks key at all
        return []
    years: set[int] = set()
    with root:
        index = 0
        while True:
            # EnumKey raises OSError past the last subkey; that ends the walk.
            try:
                name = reg.EnumKey(root, index)
            except OSError:
                break
            if match := _VERSION_KEY.match(name):
                years.add(int(match.group(1)))
            index += 1
    return sorted(years, reverse=True)
