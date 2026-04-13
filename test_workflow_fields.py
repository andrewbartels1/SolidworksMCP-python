#!/usr/bin/env python
"""Quick test to verify workflow text fields are in backend response."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from solidworks_mcp.ui.service import build_dashboard_state

state = build_dashboard_state()

print("=" * 60)
print("Backend response fields:")
print("=" * 60)
print(f"✓ workflow_label:          {state.get('workflow_label')!r}")
print(f"✓ flow_header_text:        {state.get('flow_header_text')!r}")
print(f"✓ workflow_guidance_text:  {state.get('workflow_guidance_text')!r}")
print()
print("Checking for template literal corruption:")
for key in ['workflow_label', 'flow_header_text', 'workflow_guidance_text']:
    val = state.get(key, "")
    if '{{' in val or '$result' in val:
        print(f"  ✗ {key} contains template literals!")
    else:
        print(f"  ✓ {key} is clean")
