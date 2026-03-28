# Macro Recording Tools

Record, replay, analyse, and optimise SolidWorks VBA macros. Create macro libraries for reuse, batch-execute recorded macros, and profile performance hot-spots. Ideal for capturing manual workflows and converting them to automated, repeatable sequences.

> **Prerequisite:** SolidWorks running. Macro execution requires a valid .swp file path.

**Total tools in this category: 7**

---

### `start_macro_recording`

Start recording a SolidWorks macro.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `macro_name` | `str?` | — | `None` | Name for the recorded macro |
| `recording_name` | `str?` | — | `None` | Alternative recording name |
| `description` | `str` | — | `` | Description of macro functionality |
| `output_file` | `str` | ✅ | `` | Output file for the recorded macro |
| `recording_mode` | `str` | — | `User actions` | Recording mode |
| `capture_mouse` | `bool` | — | `True` | Capture mouse actions |
| `capture_keyboard` | `bool` | — | `True` | Capture keyboard actions |
| `recording_quality` | `str` | — | `High` | Recording quality level |
| `auto_cleanup` | `bool` | — | `False` | Cleanup temporary files |
| `auto_stop` | `bool` | — | `False` | Auto-stop recording after timeout |
| `timeout_seconds` | `int` | — | `300` | Timeout for auto-stop in seconds |

**Sample call:**

```json
{
  "output_file": "example"
}
```

---

### `stop_macro_recording`

Stop macro recording and save the recorded macro.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `execute_macro`

Execute a saved SolidWorks macro.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `macro_path` | `str?` | — | `None` | Path to macro file (.swp or .vb) |
| `macro_file` | `str?` | — | `None` | Alternative macro file path |
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

### `analyze_macro`

Analyze a macro for complexity, dependencies, and optimization opportunities.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `macro_path` | `str?` | — | `None` | Path to macro file to analyze |
| `macro_file` | `str?` | — | `None` | Alternative macro file path |
| `analysis_type` | `str` | — | `full` | Analysis type (full, dependencies, performance) |
| `analysis_depth` | `str` | — | `Basic` | Analysis depth alias |
| `suggest_optimizations` | `bool` | — | `False` | Suggest optimizations |

**Sample call:**

```json
{}
```

---

### `batch_execute_macros`

Execute multiple macros in batch mode.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `macro_list` | `List[str]` | ✅ | `` | List of macro file paths |
| `target_directory` | `str?` | — | `None` | Target directory alias |
| `source_directory` | `str?` | — | `None` | Source directory alias |
| `file_pattern` | `str?` | — | `None` | File pattern alias |
| `execution_order` | `str` | — | `sequential` | Execution order (sequential, parallel) |
| `stop_on_error` | `bool` | — | `True` | Stop batch if error occurs |

**Sample call:**

```json
{
  "macro_list": []
}
```

---

### `optimize_macro`

Optimize an existing macro for better performance and reliability.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `create_macro_library`

Create a library of organized macros for team sharing and reuse.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---
