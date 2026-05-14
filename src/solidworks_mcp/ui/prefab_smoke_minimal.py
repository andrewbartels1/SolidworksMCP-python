"""Utilities for prefab smoke minimal.
"""

from prefab_ui import PrefabApp
from prefab_ui.components import Card, CardContent, CardHeader, CardTitle, Text

with PrefabApp(title="Smoke Minimal", state={"msg": "minimal ok"}) as app:
    with Card():
        with CardHeader():
            CardTitle("Smoke Minimal")
        with CardContent():
            Text("{{ msg }}")
