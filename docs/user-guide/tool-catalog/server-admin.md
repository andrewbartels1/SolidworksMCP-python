# Server Admin Tools

The server's own state. These never touch SolidWorks.

**Total tools in this category: 1**

---

### `reset_circuit_breaker`

Let calls through again to operations the server paused after repeated failures.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation` | `str?` | — | `null` | The operation to reset, as named in the circuit_open error (e.g. create_extrusion); leave it out to reset every operation |

**Sample call:**

```json
{}
```
