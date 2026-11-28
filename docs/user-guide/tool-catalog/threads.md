# Thread Tools

Modelled threads at standard sizes: external (a bolt or rod) and internal (a tapped hole).

> **Prerequisite:** SolidWorks running (the sizes are read from its thread profiles); for `create_thread`, an open part with the rod or hole.

**Total tools in this category: 2**

The sizes are the ones SolidWorks's own thread profiles hold (Tools > Options > File Locations > Thread Profiles): Metric Die and Metric Tap, Inch Die and Inch Tap. Every size `list_thread_sizes` gives works in `create_thread`.

For each size the tools give:

- **Coarse or fine.** Metric coarse pitches come from SolidWorks's Hole Wizard library (its plain `M6` rows); elsewhere the coarsest pitch listed at a diameter is coarse and the others fine, and a diameter with one size is `only`.
- **The basic thread depth**, ISO 68-1: 0.541266 × pitch (5/8 of the 60° profile's fundamental triangle). Inch threads share the profile.
- **The runout**, the incomplete thread to leave before a shoulder: ISO 3508's normal 2.5 × pitch and short 1.25 × pitch. For inch threads the same rule is applied to the inch pitch (25.4 / TPI), a reasoned default rather than a standard; `runout_basis` says which. The runout is reported, not modelled.

`add_cosmetic_thread` remains for a thread shown only in drawings; `create_hole` makes the tap drill for an internal thread.

---

### `list_thread_sizes`

List the standard thread sizes SolidWorks holds, metric or inch, with coarse or fine pitch, depth and runout.

Each entry has `size` (the name `create_thread` takes), `diameter_mm`, `pitch_mm` (and `tpi` for inch), `pitch_class`, `basic_depth_mm` and `runout_mm` (`normal`, `short`). Inch sizes named in decimals (`0.2500-20`) also give their fractional name as `also` (`1/4-20`).

**Prerequisite:** SolidWorks running.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `standard` | `str` | — | `"metric"` | 'metric' (ISO, e.g. M6x1.0) or 'inch' (UTS) |

**Sample call:**

```json
{"standard": "metric"}
```

---

### `create_thread`

Cut a modelled thread, external (a bolt) or internal (a tapped hole), at a standard size.

Pick the circular edge where the thread starts with `edge_point`: a rod's end, or a hole's opening. An external thread wants a rod of the nominal diameter (M6: 6 mm), an internal one a hole of about the tap drill (nominal minus one pitch, M6: 5 mm); a diameter more than one pitch off is refused before anything is built. Inch sizes may be given as fractions (`1/4-20`). A thread that cuts nothing is undone.

**Prerequisite:** Active part with the rod or hole.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `kind` | `str` | — | `"external"` | 'external' (a bolt or rod, male) or 'internal' (a tapped hole, female) |
| `standard` | `str` | — | `"metric"` | 'metric' or 'inch' |
| `size` | `str` | ✅ |  | A size as list_thread_sizes names it, e.g. 'M6x1.0'; inch also takes '1/4-20' |
| `edge_point` | `list[float]` | ✅ |  | [x, y, z] in mm on the circular edge where the thread starts: a rod's end edge, or a hole's edge at its opening |
| `length` | `float` | ✅ |  | Length of full thread in mm |
| `hand` | `str` | — | `"right"` | 'right' (the usual) or 'left' hand |

**Sample call:**

```json
{"size": "M6x1.0", "edge_point": [3, 25, 0], "length": 12}
```
