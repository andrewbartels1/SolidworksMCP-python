"""One call of each configuration adapter method, shared by the layer tests."""

from __future__ import annotations

from typing import Any

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("create_configuration", ("Long",), {"parent": "Default", "activate": True}),
    ("activate_configuration", ("Default",), {}),
    ("active_configuration", (), {}),
]

IDS = [call[0] for call in CALLS]
