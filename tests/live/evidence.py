"""Print a live test's proof, and hold SolidWorks on it during a demo.

``evidence(label, payload)`` prints ``[evidence] <label>: <payload>`` (what
``tests/scripts/live_demo.ps1`` shows). When ``SW_DEMO_HOLD_SECONDS`` is set
it then pauses, so a person watching SolidWorks sees the state the line
proves before the test moves on or closes its documents. Normal live runs
leave it unset and are not slowed.
"""

from __future__ import annotations

import os
import time
from typing import Any


def evidence(label: str, payload: Any) -> None:
    """Print one proof line, then hold for ``SW_DEMO_HOLD_SECONDS`` if set."""
    print(f"\n[evidence] {label}: {payload}", flush=True)
    try:
        hold = float(os.getenv("SW_DEMO_HOLD_SECONDS", "0"))
    except ValueError:
        hold = 0.0
    if hold > 0:
        time.sleep(hold)
