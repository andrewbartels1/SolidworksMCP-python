"""Utilities for prefab smoke fetch.
"""

import os

from prefab_ui import PrefabApp
from prefab_ui.actions import Fetch, SetState, ShowToast
from prefab_ui.components import Card, CardContent, CardHeader, CardTitle, Muted

API_ORIGIN = os.getenv("SOLIDWORKS_UI_API_ORIGIN", "http://127.0.0.1:8766")

with PrefabApp(
    title="Smoke Fetch",
    state={"session_id": "prefab-dashboard", "latest_message": "loading..."},
    connect_domains=[API_ORIGIN],
    on_mount=[
        Fetch.get(
            f"{API_ORIGIN}/api/ui/state?session_id={{ session_id }}",
            on_success=SetState(
                "latest_message", "{{ $result.latest_message || 'ok' }}"
            ),
            on_error=ShowToast("{{ $error }}", variant="error"),
        )
    ],
) as app:
    with Card():
        with CardHeader():
            CardTitle("Smoke Fetch")
        with CardContent():
            Muted("{{ latest_message }}")
