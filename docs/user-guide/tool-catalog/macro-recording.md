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
| `macro_path` | `str?` | — | `null` | Path to a binary SolidWorks macro (.swp, or legacy .swb). VBA source (.vb, .bas, text) cannot be run directly. |
| `macro_file` | `str?` | — | `null` | Alternative to macro_path (.swp or .swb) |
| `proc_name` | `str` | — | `"main"` | The macro procedure to call; main by default |
| `repeat_count` | `int` | — | `1` | How many times to run the macro (1-100); it stops at the first failure |
| `pause_between_runs` | `float` | — | `0.0` | Seconds to wait between runs |

**Sample call:**

```json
{
  "parameters": {}
}
```

---

