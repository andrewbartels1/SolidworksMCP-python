# Equation Tools

Read, add, change and delete a part's or assembly's equations and global variables, so one value drives several dimensions and the model stays consistent when it changes.

> **Prerequisite:** an open part or assembly. A number with no unit is in the document's units; write `60mm` or `30deg` to be sure.

**Total tools in this category: 3**

A global variable is a named value (`"Width" = 60mm`). A dimension equation sets a dimension from an expression (`"D1@Sketch1" = "Width" / 2`), using the dimension's `full_name` from `list_model_dimensions`. Change `Width` and every dimension that uses it follows on the next rebuild, which `set_equation` does for you.

---

### `list_equations`

List the active part's or assembly's equations and global variables, with their values.

Each row has `index`, `name`, `expression`, `kind` (`global_variable`, `dimension` or `other`, such as a suppression equation) and `value` (solved, in the document's units; null when SolidWorks has none).

**Prerequisite:** Active part or assembly.

**Parameters:** none.

**Sample call:**

```json
{}
```

---

### `set_equation`

Add or change an equation or global variable, so one value drives others.

A `name` with `@` is a dimension of the active document; any other name is a global variable. If the model already has an equation for `name` (case doesn't matter), its expression is replaced; otherwise one is added. The model is solved and rebuilt, and the reply gives the equation, its `value`, `action` (`added` or `changed`) and the `configurations` it applies in. An expression SolidWorks can't use, such as one naming a variable that doesn't exist, fails as `equation_refused` and changes nothing.

It applies in every configuration by default, as SolidWorks' Equations dialog does; `set_dimension` defaults to the active one only.

**Prerequisite:** Active part or assembly; for a dimension, the dimension.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ |  | A global variable (e.g. 'Width'), or a dimension of the active document as list_model_dimensions names it (e.g. 'D1@Sketch1'); no quotes |
| `expression` | `str` | ✅ |  | The right-hand side, e.g. '60mm' or '"Width" / 2'; names in double quotes |
| `configurations` | `str \| list[str]` | — | `"all"` | 'all', 'this' (the active configuration), or configuration names from `list_configurations` |

**Sample call:**

```json
{"name": "D1@Sketch1", "expression": "\"Width\" / 2"}
```

---

### `delete_equation`

Delete an equation or global variable of the active part or assembly, by name.

A dimension the equation drove keeps its last value. An equation that used a deleted global variable stops solving, so check `list_equations` afterwards.

**Prerequisite:** Active part or assembly with that equation.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ |  | The equation's name as list_equations gives it, e.g. 'Width' |

**Sample call:**

```json
{"name": "Width"}
```
