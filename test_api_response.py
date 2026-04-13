#!/usr/bin/env python
"""Test the /api/ui/state endpoint to see what it actually returns."""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from solidworks_mcp.ui.service import build_dashboard_state


def test_state_response():
    """Check the actual state response."""
    state = build_dashboard_state()

    print("=" * 70)
    print("API /api/ui/state Response Keys:")
    print("=" * 70)

    # Check the three problematic fields
    problem_fields = ["workflow_label", "flow_header_text", "workflow_guidance_text"]

    print("\nProblem Fields Check:")
    for field in problem_fields:
        value = state.get(field)
        is_template = isinstance(value, str) and ("{{" in value or "$result" in value)
        status = "❌ TEMPLATE LITERAL" if is_template else "✓ OK"
        print(f"  {field:30s} {status}")
        print(f"    Value: {value!r}")

    # Check if all expected keys are present
    print("\nAll Response Keys:")
    all_keys = sorted(state.keys())
    for key in all_keys:
        print(f"  - {key}")

    # Save full response to file for inspection
    with open("api_state_response.json", "w") as f:
        json.dump(state, f, indent=2)
    print("\nFull response saved to api_state_response.json")


if __name__ == "__main__":
    test_state_response()
