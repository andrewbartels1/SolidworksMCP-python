# Macro Recording Tools

Run a SolidWorks macro file (`.swp` or `.swb`), or VBA source when the server allows it. Record macros in SolidWorks itself
(Tools > Macro > Record); to write one from a description, use `generate_vba_code`.

> **Prerequisite:** SolidWorks running. Macro execution requires a valid .swp file path.

**Total tools in this category: 1**

---

### `execute_macro`

Run a SolidWorks macro (.swp, or legacy .swb), or VBA source text, in the running SolidWorks, calling its `main` procedure.

VBA source runs only when the server was started with `SOLIDWORKS_MCP_ALLOW_VBA_SOURCE=1` ([why it's off by default](../../getting-started/installation.md#5-let-execute_macro-run-vba-source-off-by-default)); otherwise it is refused as `vba_source_off`. The source is saved as a `.swb` file, and the reply gives `source_file` and the `vba_source` that ran.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `macro_path` | `str?` | — | `null` | Path to a SolidWorks macro file (.swp, or legacy .swb). For VBA source text, use vba_source. |
| `macro_file` | `str?` | — | `null` | Alternative to macro_path (.swp or .swb) |
| `vba_source` | `str?` | — | `null` | The macro's VBA text, instead of a file: written to a .swb and run. Only when the server allows it (SOLIDWORKS_MCP_ALLOW_VBA_SOURCE) |
| `proc_name` | `str` | — | `"main"` | The macro procedure to call; main by default |
| `repeat_count` | `int` | — | `1` | How many times to run the macro (1-100); it stops at the first failure |
| `pause_between_runs` | `float` | — | `0.0` | Seconds to wait between runs |
| `dialog_timeout` | `float` | — | `30.0` | Seconds a dialog the macro opens (MsgBox, form, prompt) may wait before it is answered with Cancel (or its only button) and the run fails as `macro_waited_for_user` |

**Sample call:**

```json
{
  "parameters": {}
}
```

---

