# Drawing Analysis Tools

Compare two versions of a drawing file on disk. A check of a drawing's contents
(`check_drawing`) is planned in the drawing pack.

> **Prerequisite:** Both drawing files on disk.

**Total tools in this category: 1**

---

### `compare_drawing_versions`

Compare two drawing files on disk: whether they are byte-identical, and how their sizes differ.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `drawing_version_1` | `str` | ✅ |  | Full path to the first drawing file |
| `drawing_version_2` | `str` | ✅ |  | Full path to the second drawing file |

**Sample call:**

```json
{"drawing_version_1": "C:\\Temp\\mcp_demo\\plate_v1.SLDDRW", "drawing_version_2": "C:\\Temp\\mcp_demo\\plate_v2.SLDDRW"}
```

---

