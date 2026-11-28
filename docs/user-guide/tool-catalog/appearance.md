# Appearance Tools

Colour the part, a feature, a body or one face, and read a colour back.

> **Prerequisite:** an open part.

**Total tools in this category: 2**

A colour shows from the nearest level that has one: a face's colour over its feature's, a feature's over its body's, a body's over the part's. Every part has a colour; a feature, body or face has one only once it is given one. `set_appearance` reads the colour back from SolidWorks after setting it, and `get_appearance` says which level the visible colour comes from.

A target is one of `feature` (its name in the tree), `body` (as `list_bodies` names it) or `face_point` (`[x, y, z]` mm, a point on the face); none means the whole part. Giving two targets is refused.

---

### `set_appearance`

Colour the active part, one feature, one body or the face at a point, or remove a colour.

`color` is `[r, g, b]`, each 0-255, or `#rrggbb`. `reset: true` removes a feature's, body's or face's own colour so the colour above it shows again; the reply's `showing` gives that colour and its level. The part's colour can't be reset, only changed. The geometry is never changed.

**Prerequisite:** Active part.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `feature` | `str` | — |  | A feature by its name in the tree, e.g. 'Boss-Extrude1' |
| `body` | `str` | — |  | A solid body, as list_bodies names it |
| `face_point` | `list[float]` | — |  | [x, y, z] in mm, a point on the face; give one target, or none for the whole part |
| `color` | `list[int] \| str` | — |  | [r, g, b], each 0-255, or '#rrggbb', e.g. [31, 119, 180] or '#1f77b4' |
| `transparency` | `float` | — | `0.0` | 0 opaque (default) to 1 clear |
| `reset` | `bool` | — | `false` | Remove the feature's, body's or face's own colour so the one above it shows; give no color |

**Sample call:**

```json
{"color": "#1f77b4", "face_point": [0, 10, 0]}
```

---

### `get_appearance`

Read the colour the active part, a feature, a body or the face at a point shows, and where it comes from.

The reply's `level` is `face`, `feature`, `body` or `part`: the nearest level with a colour of its own.

**Prerequisite:** Active part.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `feature` | `str` | — |  | A feature by its name in the tree, e.g. 'Boss-Extrude1' |
| `body` | `str` | — |  | A solid body, as list_bodies names it |
| `face_point` | `list[float]` | — |  | [x, y, z] in mm, a point on the face; give one target, or none for the whole part |

**Sample call:**

```json
{"face_point": [20, 5, 0]}
```
