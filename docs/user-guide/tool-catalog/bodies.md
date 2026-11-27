# Body Tools

See, combine, split, move, copy, delete and scale the solid bodies of a part.

> **Prerequisite:** an open part. A part gets several bodies from `create_extrusion` with `merge_result: false`, from a split or from a copy.

**Total tools in this category: 6**

`list_bodies` names the bodies; the other five tools take those names. Ignore case when typing them. A name that matches no body is refused with the list of bodies there are. SolidWorks renames a body a feature changes (a combine's result becomes `Combine1`, a split's pieces `Split1[1]` and `Split1[2]`), so every reply lists `bodies_after`.

Each operation is measured. Its reply gives the body names, their count and the volume before and after, and `volume_change_mm3`. An operation whose result its kind can't produce is undone and fails as `feature_not_built`, so it never passes silently:

- a subtract or common that leaves the main body no smaller;
- an add of bodies that don't touch;
- a split that makes no new body;
- a move that moves nothing.

---

### `list_bodies`

List the active part's solid bodies by name, with each one's volume and bounding box.

Each entry has `name`, `volume_mm3` and `bounding_box_mm` (`min`, `max` and `size`, each `[x, y, z]` mm). The reply also has `count` and `total_volume_mm3`. Bodies come in the order SolidWorks lists them, newest first.

**Prerequisite:** Active part.

**Parameters:** none.

**Sample call:**

```json
{}
```

---

### `combine_bodies`

Add bodies together, subtract tool bodies from a main body, or keep only the volume they share.

The tool bodies are consumed and the result is one body. The result is judged by its own volume, so a tool lying elsewhere, consumed without cutting, fails the call.

**Prerequisite:** Active part with the bodies.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation` | `str` | ✅ |  | 'add' joins the bodies, 'subtract' removes the tool bodies from the main body, 'common' keeps only the volume they share |
| `main_body` | `str` | ✅ |  | The body to keep, as list_bodies names it |
| `tool_bodies` | `list[str]` | ✅ |  | The bodies to add, subtract or intersect; they are consumed |

**Sample call:**

```json
{"operation": "subtract", "main_body": "Boss-Extrude1", "tool_bodies": ["Boss-Extrude2"]}
```

---

### `split_body`

Split the part's bodies with a plane or a sketch, keeping every piece in the part.

Every body the plane or sketch crosses all the way is split; `made` names the new bodies. To save a piece as its own part, use `save_body_as_part`.

**Prerequisite:** Active part with a body.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `tool` | `str` | ✅ |  | A plane (e.g. 'Right Plane') or a sketch that crosses the bodies all the way; every body it crosses is split |

**Sample call:**

```json
{"tool": "Right Plane"}
```

---

### `move_copy_body`

Move bodies by a translation or a rotation, or copy them up to 50 times.

Give `translate` (mm) or `rotate` (degrees about the model's x, y and z axes through `rotation_point`), not both: SolidWorks applies only the rotation when given both, so the tool refuses the pair. Move twice instead. With `as_copy`, copy n sits n translations away and the originals stay put.

**Prerequisite:** Active part with the bodies.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `bodies` | `list[str]` | ✅ |  | The bodies to move or copy, as list_bodies names them |
| `translate` | `list[float]` | — | `[0, 0, 0]` | Translation [x, y, z] in mm |
| `rotate` | `list[float]` | — | `[0, 0, 0]` | Rotation [x, y, z] in degrees about the model axes through rotation_point |
| `rotation_point` | `list[float]` | — | `[0, 0, 0]` | Centre of the rotation [x, y, z] in mm |
| `as_copy` | `bool` | — | `false` | Copy the bodies instead of moving them |
| `copies` | `int` | — | `1` | With as_copy, how many copies (1 to 50); copy n is moved n times the translation |

**Sample call:**

```json
{"bodies": ["Boss-Extrude1"], "translate": [30, 0, 0], "as_copy": true, "copies": 3}
```

---

### `delete_bodies`

Delete bodies, or with `keep: true` keep only the named ones.

The reply's `removed` names the bodies that went. Deleting every body is refused. The Body-Delete/Keep feature can be undone with `delete_feature`.

**Prerequisite:** Active part with the bodies.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `bodies` | `list[str]` | ✅ |  | The bodies, as list_bodies names them |
| `keep` | `bool` | — | `false` | false deletes these bodies; true keeps only these and deletes the rest |

**Sample call:**

```json
{"bodies": ["Split1[1]"], "keep": true}
```

---

### `scale_body`

Scale bodies uniformly or per axis, about each body's centroid or the part's origin.

Give `scale` (one factor) or `scale_xyz`. A body's volume is multiplied by the factors' product, so ×2 makes it 8 times larger. A scale of 1 on every axis is refused.

**Prerequisite:** Active part with a body.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `scale` | `float` | — |  | One factor for all three axes, e.g. 2 |
| `scale_xyz` | `list[float]` | — |  | Factors [x, y, z], each above 0; instead of scale |
| `about` | `str` | — | `"centroid"` | Scale about each body's centroid or the part's origin |
| `bodies` | `list[str]` | — |  | The bodies to scale; all when omitted |

**Sample call:**

```json
{"scale": 2, "bodies": ["Body-Move/Copy1[1]"]}
```
