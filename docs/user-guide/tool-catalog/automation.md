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
| `operation_description` | `str?` | — | `None` | Description of the operation to generate VBA for |
| `operation_type` | `str?` | — | `None` | Operation type alias |
| `parameters` | `Dict[str, Any]` | ✅ | `` | Operation parameters |
| `target_document` | `str` | — | `Part` | Target document type (Part, Assembly, Drawing) |
| `include_error_handling` | `bool` | — | `True` | Include error handling in generated code |
| `code_style` | `str` | — | `professional` | Code style (simple, professional, advanced) |

**Sample call:**

```json
{
  "parameters": {}
}
```
