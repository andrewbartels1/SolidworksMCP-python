from prefab_ui import PrefabApp
from prefab_ui.components import (
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    DataTable,
    DataTableColumn,
)
from prefab_ui.rx import Rx

with PrefabApp(
    title="Smoke Table",
    state={
        "rows": [
            {
                "step": "1",
                "goal": "Example",
                "tools": "create_sketch",
                "status": "queued",
            }
        ]
    },
) as app:
    with Card():
        with CardHeader():
            CardTitle("Smoke Table")
        with CardContent():
            DataTable(
                columns=[
                    DataTableColumn(key="step", header="Step"),
                    DataTableColumn(key="goal", header="Goal"),
                    DataTableColumn(key="tools", header="Tools"),
                    DataTableColumn(key="status", header="Status"),
                ],
                rows=Rx("rows"),
                paginated=True,
            )
