"""How much of the SolidWorks COM API the adapters call, counted by text.

The method names come from a committed snapshot of the type library, so
counting needs no SolidWorks. A name counts as called when the adapter
source uses it as an attribute (``model.ForceRebuild3``) or passes it as a
string (``flag_members(obj, "EditDelete")``). A name scan can't tell
``IFeature.Name`` from ``IComponent2.Name``, so the figures are approximate.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

#: The interfaces most modelling, assembly and drawing work goes through.
CORE_INTERFACES = (
    "ISldWorks",
    "IModelDoc2",
    "IModelDocExtension",
    "IPartDoc",
    "IAssemblyDoc",
    "IDrawingDoc",
    "IFeatureManager",
    "ISketchManager",
    "ISelectionMgr",
    "IComponent2",
    "IFeature",
    "ISketch",
)

_ATTRIBUTE = re.compile(r"\.([A-Z]\w*)\b")
_QUOTED = re.compile(r"[\"']([A-Z]\w+)[\"']")


@dataclass(frozen=True)
class InterfaceCoverage:
    """The methods of one interface that the adapters call.

    Attributes:
        name: The interface, e.g. ``IModelDoc2``.
        covered: The called method names, sorted.
        total: How many methods the interface has.
    """

    name: str
    covered: tuple[str, ...]
    total: int


@dataclass(frozen=True)
class ComCoverage:
    """Coverage of the core interfaces and of the whole API.

    Attributes:
        interfaces: One entry per core interface, in ``CORE_INTERFACES`` order.
        api_covered: Distinct method names called, across the whole API.
        api_total: Distinct method names in the whole API.
        type_library: The snapshot's source, which carries its version.
    """

    interfaces: tuple[InterfaceCoverage, ...]
    api_covered: int
    api_total: int
    type_library: str

    @property
    def core_covered(self) -> int:
        """Called methods summed over the core interfaces."""
        return sum(len(i.covered) for i in self.interfaces)

    @property
    def core_total(self) -> int:
        """Methods summed over the core interfaces."""
        return sum(i.total for i in self.interfaces)


@dataclass(frozen=True)
class Snapshot:
    """The type library's interface and method names.

    Attributes:
        type_library: Where it came from (the gen_py wrapper's name).
        interfaces: Interface name to its method names.
    """

    type_library: str
    interfaces: Mapping[str, frozenset[str]]

    def to_json(self) -> str:
        """The snapshot as committed: sorted, one interface per line.

        Returns:
            str: JSON text ending in a newline.
        """
        lines = [
            f"  {json.dumps(name)}: {json.dumps(sorted(methods))}"
            for name, methods in sorted(self.interfaces.items())
        ]
        body = ",\n".join(lines)
        return (
            f'{{\n "type_library": {json.dumps(self.type_library)},\n'
            f' "interfaces": {{\n{body}\n }}\n}}\n'
        )

    @classmethod
    def from_json(cls, text: str) -> Snapshot:
        """Read a snapshot written by :meth:`to_json`.

        Args:
            text: The JSON text.

        Returns:
            Snapshot: The parsed snapshot.
        """
        raw = json.loads(text)
        return cls(
            raw["type_library"],
            {name: frozenset(methods) for name, methods in raw["interfaces"].items()},
        )

    @classmethod
    def load(cls, path: Path) -> Snapshot:
        """Read the committed snapshot file.

        Args:
            path: The snapshot's path.

        Returns:
            Snapshot: The parsed snapshot.
        """
        return cls.from_json(path.read_text(encoding="utf-8"))


def called_names(sources: Iterable[str]) -> set[str]:
    """Capitalised names the source uses as attributes or string literals.

    Args:
        sources: The text of each source file.

    Returns:
        set[str]: Candidate COM member names (not yet matched to the API).
    """
    found: set[str] = set()
    for text in sources:
        found.update(_ATTRIBUTE.findall(text))
        found.update(_QUOTED.findall(text))
    return found


def adapter_sources(adapters_dir: Path) -> list[str]:
    """The text of every Python file under the adapters package.

    Args:
        adapters_dir: ``src/solidworks_mcp/adapters``.

    Returns:
        list[str]: One string per file, in path order.
    """
    return [p.read_text(encoding="utf-8") for p in sorted(adapters_dir.rglob("*.py"))]


def measure(snapshot: Snapshot, called: set[str]) -> ComCoverage:
    """Coverage of the core interfaces and the whole API.

    Args:
        snapshot: The type library's names.
        called: Names found in the adapter source.

    Returns:
        ComCoverage: The counts.
    """
    every = set().union(*snapshot.interfaces.values())
    interfaces = tuple(
        InterfaceCoverage(
            name,
            tuple(sorted(snapshot.interfaces.get(name, frozenset()) & called)),
            len(snapshot.interfaces.get(name, frozenset())),
        )
        for name in CORE_INTERFACES
    )
    return ComCoverage(
        interfaces, len(every & called), len(every), snapshot.type_library
    )
