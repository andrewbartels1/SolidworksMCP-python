"""Manual smoke run for `SolidWorksDocsDiscovery` against a live SolidWorks session.

Relocated from repo root (`test_docs_discovery_run.py`) per issue #81 — it is
not a pytest suite (no assertions, prints a summary), so it doesn't belong in
`tests/` proper and was never collected by `dev-test` (`testpaths = ["tests"]`
would have picked it up if it were named without the `test_` prefix, which is
exactly why it moved here and got renamed off that prefix). Kept, rather than
deleted, because it's still useful for eyeballing the discovered COM
interface/method counts against a real SolidWorks install; the deterministic,
assertion-based coverage lives in `tests/test_tools_docs_discovery.py`.

Usage:
    .\\.venv\\Scripts\\python.exe tests\\scripts\\docs_discovery_smoke.py
"""

from __future__ import annotations

from pathlib import Path

from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery

OUTPUT_DIR = Path(".generated") / "docs-index"


def main() -> int:
    """Run docs discovery against a live SolidWorks session and print a summary."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    discovery = SolidWorksDocsDiscovery(output_dir=OUTPUT_DIR)

    try:
        discovery.connect_to_solidworks()
        print("Connected to SolidWorks OK")
    except Exception as exc:
        print("Connect failed:", exc)

    index = discovery.discover_all()

    print("COM objects:")
    for iface, data in index.get("com_objects", {}).items():
        method_count = data.get("method_count", 0)
        property_count = data.get("property_count", 0)
        methods_sample = data.get("methods", [])[:5]
        print(
            f"  {iface}: {method_count} methods, {property_count} properties "
            f"| sample={methods_sample}"
        )

    print("VBA refs:")
    for name, ref in index.get("vba_references", {}).items():
        summary = f"  {name}: {ref.get('status')} - {ref.get('description', '')}"
        print(summary[:120])

    print("Total methods:", index.get("total_methods"))
    print("Total properties:", index.get("total_properties"))

    saved = discovery.save_index("solidworks_docs_index_smoke.json")
    print("Saved to:", saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
