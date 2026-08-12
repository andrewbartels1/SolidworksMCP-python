#!/usr/bin/env python
r"""Demo: assembly-aware ``list_features`` (GitHub issue #21).

Connects to a running SolidWorks instance and calls ``list_features`` on
both a Part and an Assembly from the built-in U-Joint sample set, showing
the behavior added by the ``assembly-aware-list-features`` OpenSpec change
(see ``openspec/changes/assembly-aware-list-features/``):

- A Part's own features are unchanged from before this change.
- An Assembly's response flattens in every resolved component's features
  alongside the assembly's own, each descriptor tagged with ``component``/
  ``component_path``/``component_parent`` (``None`` for the document's own
  features). The adapter contract stays a flat list on purpose - see
  design.md for why - but ``component_parent`` carries enough information
  to reconstruct the real nested tree, which
  ``build_component_tree`` (``solidworks_mcp.utils.feature_tree_classifier``)
  does for callers who want to look at the assembly structure rather than
  scan a flat, tagged list.
- Sub-assemblies are recursed into up to ``max_assembly_depth`` (default 2):
  ``UJoint.SLDASM`` contains a sub-assembly, ``crank sub.SLDASM``, whose own
  three part components (crank-arm, crank-knob, crank-shaft) show up
  correctly nested *under* ``crank sub-1`` in the tree view, not flattened
  alongside its top-level siblings.

Read-only: does not save or modify any document. Requires Windows +
SolidWorks running with the U-Joint sample installed (ships with SolidWorks
under ``…\samples\learn\U-Joint\``).

API surface used here (``GetType``, ``GetComponents``, ``IComponent2.
GetModelDoc2``) was cross-checked against the live SolidWorks installation
via this repo's own ``discover_solidworks_docs``/``SolidWorksDocsDiscovery``
tooling (``src/solidworks_mcp/tools/docs_discovery.py``). See
``docs/agents/com-api-pitfalls.md`` items #11 and #12 for the two
late-binding bugs found and fixed while first running this demo against a
live SolidWorks session (2026-08-11) — the traversal logic passed every
mock-adapter unit test but still failed on real COM until those fixes
landed.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.config import load_config
from solidworks_mcp.utils.feature_tree_classifier import build_component_tree

U_JOINT_DIR = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint"
)
UJOINT_ASSEMBLY = U_JOINT_DIR / "UJoint.SLDASM"
YOKE_MALE_PART = U_JOINT_DIR / "Yoke_male.sldprt"


def unwrap_adapter(adapter: Any) -> Any | None:
    """Walk the adapter chain to find the raw PyWin32Adapter (has swApp)."""
    current: Any | None = adapter
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if hasattr(current, "swApp") and hasattr(current, "currentModel"):
            return current
        current = getattr(current, "adapter", None)
    return None


def print_tree(node: dict[str, Any], indent: int = 0) -> None:
    """Print a build_component_tree() result as an indented outline."""
    pad = "  " * indent
    print(f"{pad}({len(node['features'])} own features)")
    for name, child in sorted(node["components"].items()):
        print(f"{pad}{name}  [{child['path']}]")
        print_tree(child, indent + 1)


def print_features(label: str, rows: list[dict[str, Any]], limit: int = 8) -> None:
    """Print a compact summary of a list_features result."""
    print(f"\n--- {label} ---")
    print(f"total descriptors: {len(rows)}")
    own = [r for r in rows if r["component"] is None]
    by_component: dict[str, int] = {}
    for row in rows:
        comp = row["component"]
        if comp:
            by_component[comp] = by_component.get(comp, 0) + 1
    print(f"document's own features (component=None): {len(own)}")
    if by_component:
        print("features per component:")
        for name, count in sorted(by_component.items()):
            print(f"  {name}: {count}")
    print(f"first {min(limit, len(rows))} descriptors:")
    for row in rows[:limit]:
        print(f"  {row}")


async def main() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    raw = unwrap_adapter(adapter)

    def close_all() -> None:
        # Close everything between steps so ActiveDoc is unambiguous - a
        # part already loaded as an assembly component doesn't reliably
        # become the active document otherwise.
        if raw is not None and raw.swApp is not None:
            raw.swApp.CloseAllDocuments(True)

    try:
        close_all()

        print("=" * 72)
        print("PART — Yoke_male.sldprt")
        print("Unchanged behavior: every feature has component=None,")
        print("exactly like list_features returned before this change.")
        print("=" * 72)
        result = await adapter.open_model(str(YOKE_MALE_PART))
        if not result.is_success:
            print(f"open_model failed: {result.error}")
            return
        feat_result = await adapter.list_features(include_suppressed=False)
        if not feat_result.is_success:
            print(f"list_features failed: {feat_result.error}")
            return
        print_features("Yoke_male.sldprt", feat_result.data)

        close_all()

        print("\n" + "=" * 72)
        print("ASSEMBLY — UJoint.SLDASM (contains a nested sub-assembly)")
        print("Every top-level component's features are flattened in,")
        print("tagged by component name/path. The sub-assembly 'crank sub-1'")
        print("is recursed into (max_assembly_depth=2 default), surfacing")
        print("its own three part components too.")
        print("=" * 72)
        result = await adapter.open_model(str(UJOINT_ASSEMBLY))
        if not result.is_success:
            print(f"open_model failed: {result.error}")
            return
        feat_result = await adapter.list_features(
            include_suppressed=False, max_assembly_depth=2
        )
        if not feat_result.is_success:
            print(f"list_features failed: {feat_result.error}")
            return
        print_features("UJoint.SLDASM", feat_result.data, limit=5)

        unresolved = [
            r for r in feat_result.data if r["type"] == "UnresolvedComponent"
        ]
        print(f"\nUnresolvedComponent rows: {len(unresolved)} (expect 0)")

        print("\n--- nested component tree (build_component_tree) ---")
        print("Same data as above, reshaped so 'crank sub-1's three parts")
        print("nest under it instead of sitting flat alongside its siblings:")
        tree = build_component_tree(feat_result.data)
        print_tree(tree)

    finally:
        close_all()
        await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
