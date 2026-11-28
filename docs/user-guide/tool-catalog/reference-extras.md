# Reference and Analysis Extras

A coordinate system at a point, the centre-of-mass point, the bounding box, and a face's section properties.

> **Prerequisite:** an open part; all but the coordinate system need a solid body.

**Total tools in this category: 4**

Each reply is read back from SolidWorks: the coordinate system's transform, the centre of mass, the bodies' box and the face's section. For the numbers alone, without adding a feature, `get_mass_properties` gives the centre of mass and `verify_model` the box size.

---

### `create_coordinate_system`

Add a coordinate system with its origin at a point, axes along the model's.

The origin is a point in a 3D sketch the tool draws for it. The axes lie along the model's; they can't yet be turned or reversed. Use the coordinate system as a frame for measurements, mass properties or exports.

**Prerequisite:** Active part.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `origin` | `list[float]` | ✅ |  | The origin [x, y, z] in mm |

**Sample call:**

```json
{"origin": [20, 10, 20]}
```

---

### `create_center_of_mass_point`

Add SolidWorks's Center of Mass point to the active part, at its centre of mass.

The point moves with the geometry. A part has one at most; a second call, or a part with no solid body, is refused.

**Prerequisite:** Active part with a body.

**Parameters:** none.

**Sample call:**

```json
{}
```

---

### `create_bounding_box`

Add SolidWorks's Bounding Box feature around the active part's bodies and give the stock size.

The box is SolidWorks's best fit and updates with the part. The reply's `size_mm`, `min_mm` and `max_mm` are the bodies' box in model axes. A part has one at most.

**Prerequisite:** Active part with a body.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_hidden` | `bool` | — | `false` | Include hidden bodies in the box |

**Sample call:**

```json
{}
```

---

### `get_section_properties`

Read the area, centroid and second moments of area of a planar face, picked by a point on it.

Moments are about the face's centroid in model axes (`ixx` ... `iyz`, mm⁴), with the polar moment and the two principal moments. A 40 mm square face gives 1,600 mm² and 40⁴/12 = 213,333 mm⁴ about each in-plane axis. Changes nothing.

**Prerequisite:** Active part.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `face_point` | `list[float]` | ✅ |  | [x, y, z] in mm, a point on a planar face |

**Sample call:**

```json
{"face_point": [0, 10, 0]}
```
