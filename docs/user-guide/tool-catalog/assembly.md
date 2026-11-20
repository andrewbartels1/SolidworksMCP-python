# Assembly Tools

Explode an assembly, repeat and mirror its components, and swap one for another file, the edits between inserting parts and drawing the assembly.

> **Prerequisite:** an open assembly. Components are named by their instance name (`pin-1`), as `list_components` reports it. Inserting, mating and fixing components are [modeling tools](modeling.md); balloons on the drawing are a [drawing tool](drawing.md).

**Total tools in this category: 5**

An assembly drawing a shop builds from is an exploded view with numbered balloons beside the BOM: `create_exploded_view`, then a drawing view with `exploded` (`create_drawing_view`), `insert_bom_table` and `add_balloons`.

---

### `create_exploded_view`

Explode the active assembly, automatically or step by step, and show it.

**Prerequisite:** An open assembly

**SolidWorks automation note:** With no `steps`, `IAssemblyDoc.AutoExplode`. Each step selects its components (mark 1) and the default plane normal to the direction (the Right Plane for x, Top for y, Front for z; mark 2) and calls `IConfiguration.AddExplodeStep2`; the configuration's exploded view is made first when it has none (`CreateExplodedView`). The view is then shown (`ShowExploded2`). The reply gives the assembly's bounding box before and after, so the explode is measured, not assumed.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `steps` | `list[ExplodeStep]` | — | `[]` | Steps in order, each `components`, `direction` (`x`, `y`, `z`), `distance` (mm) and `reverse`; empty explodes it automatically |

**Sample call:**

```json
{"steps": [{"components": ["pin-1", "pin-2", "pin-3", "pin-4"], "direction": "y", "distance": 40}]}
```

---

### `set_exploded_view`

Show the active assembly exploded, or collapse it.

**Prerequisite:** An open assembly with an exploded view

**SolidWorks automation note:** `IAssemblyDoc.ShowExploded2` on the active configuration's first exploded view, read back with `IModelDoc2.IsExploded`. No exploded view fails as `not_found`.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `exploded` | `bool` | ✅ | | `true` shows it exploded, `false` collapsed |

**Sample call:**

```json
{"exploded": false}
```

---

### `pattern_components`

Repeat assembly components in a row along an axis, or around one.

**Prerequisite:** An open assembly with the seed components and a reference axis (`create_axis`)

**SolidWorks automation note:** A component pattern feature from a definition (`IFeatureManager.CreateDefinition`, `swFmLocalLPattern` or `swFmLocalCirPattern`): the seeds (`SeedComponentArray`), the axis, the count and the spacing or angle, then `CreateFeature`. The component count is checked to grow by (count - 1) per seed.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `components` | `list[str]` | ✅ | | The seed components' instance names |
| `axis` | `str` | ✅ | | A reference axis's name, the pattern's direction or centre |
| `count` | `int` | ✅ | | Instances, the seeds included (2 or more) |
| `kind` | `str` | — | `linear` | `linear` (along the axis) or `circular` (around it) |
| `spacing` | `float?` | — | `None` | Linear: the distance between instances, mm |
| `angle` | `float?` | — | `None` | Circular: the total angle in degrees; 360 spaces them equally |

**Sample call:**

```json
{"components": ["pin-1"], "axis": "Axis1", "count": 4, "spacing": 25}
```

---

### `mirror_components`

Mirror assembly components about a plane, as instances of the same parts.

**Prerequisite:** An open assembly with the components and the plane

**SolidWorks automation note:** `IAssemblyDoc.MirrorComponents3` with the components as `ComponentsToInstance` (mirrored instances, no new part files). The new instances are read back as the components after minus before.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `components` | `list[str]` | ✅ | | Instance names to mirror |
| `plane` | `str` | ✅ | | `Front Plane`, `Top Plane`, `Right Plane` or a plane's name |

**Sample call:**

```json
{"components": ["foot-1"], "plane": "Right Plane"}
```

---

### `replace_component`

Swap an assembly component for another part or assembly file.

**Prerequisite:** An open assembly and the new file

**SolidWorks automation note:** Selects the component and calls `IAssemblyDoc.ReplaceComponents2` (the file's active configuration, mates re-attached). Each instance's file is read back afterwards; a file that doesn't exist fails as `invalid_input` before anything changes.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `component` | `str` | ✅ | | The instance name, e.g. `pin-1` |
| `file_path` | `str` | ✅ | | The `.sldprt` or `.sldasm` to put in its place |
| `all_instances` | `bool` | — | `False` | Replace every instance of the same file |

**Sample call:**

```json
{"component": "pin-1", "file_path": "C:/parts/pin-45.sldprt", "all_instances": true}
```
