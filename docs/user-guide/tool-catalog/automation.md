# Automation Tools

`generate_vba_code` writes a VBA macro skeleton for a step the other tools don't
cover. For variants of a part, use configurations (planned in queue item 13).

> **Prerequisite:** None for `generate_vba_code`; it only writes text.

**Total tools in this category: 1**

## Known limits

- `generate_vba_code` writes macro text; it does not run it. Run a saved `.swp`
  with `execute_macro`.
- Mock mode returns the same text as real mode, since nothing calls SolidWorks.

---

### `generate_vba_code`

Write a VBA macro skeleton for an operation you describe: the SolidWorks connection, the active document and optional error handling, with the operation itself left as a TODO.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation_description` | `str?` | — | `null` | Description of the operation to generate VBA for |
| `operation_type` | `str?` | — | `null` | Operation type alias |
| `target_document` | `str` | — | `"Part"` | The document type the macro runs on; it stops, printing why, on any other |
| `include_error_handling` | `bool` | — | `true` | Include error handling in generated code |

**Sample call:**

```json
{
  "parameters": {}
}
```
