# Macro Recording Tools

Run a binary SolidWorks macro (`.swp`). Record macros in SolidWorks itself
(Tools > Macro > Record); to write one from a description, use `generate_vba_code`.

> **Prerequisite:** SolidWorks running. Macro execution requires a valid .swp file path.

**Total tools in this category: 1**

---

### `execute_macro`

Run a binary SolidWorks macro (.swp, or legacy .swb) in the running SolidWorks, calling its `main` procedure once.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `macro_path` | `str?` | — | `None` | Path to a binary macro (.swp or .swb) |
| `macro_file` | `str?` | — | `None` | Alternative to macro_path (.swp or .swb) |
| `parameters` | `Dict[str, Any]` | ✅ | `` | Macro parameters |
| `target_file` | `str?` | — | `None` | Target file |
| `execution_mode` | `str?` | — | `None` | Execution mode |
| `pause_on_error` | `bool` | — | `False` | Pause on error |
| `log_execution` | `bool` | — | `False` | Log execution |
| `execution_parameters` | `Dict[str, Any]?` | — | `None` | Execution parameters |
| `repeat_count` | `int` | — | `1` | Number of times to execute |
| `pause_between_runs` | `float` | — | `0.0` | Pause between executions in seconds |

**Sample call:**

```json
{
  "parameters": {}
}
```

---

