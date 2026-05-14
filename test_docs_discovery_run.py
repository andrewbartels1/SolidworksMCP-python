"""Tests for test docs discovery run."""

import sys
from pathlib import Path

sys.path.insert(0, "src")

from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery

OUTPUT_DIR = Path(".generated/docs-index")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

d = SolidWorksDocsDiscovery(output_dir=OUTPUT_DIR)

try:
    d.connect_to_solidworks()
    print("Connected to SolidWorks OK")
except Exception as e:
    print("Connect failed:", e)

index = d.discover_all()

print("COM objects:")
for iface, data in index.get("com_objects", {}).items():
    mc = data.get("method_count", 0)
    pc = data.get("property_count", 0)
    methods_sample = data.get("methods", [])[:5]
    print(f"  {iface}: {mc} methods, {pc} properties | sample={methods_sample}")

print("VBA refs:")
for k, v in index.get("vba_references", {}).items():
    print(f"  {k}: {v.get('status')} - {v.get('description', '')}"[:120])

print("Total methods:", index.get("total_methods"))
print("Total properties:", index.get("total_properties"))

saved = d.save_index("solidworks_docs_index_2026.json")
print("Saved to:", saved)
