## Context

`FeatureCut4` and `FeatureCut3` take `Sd` as their first argument. In the
SolidWorks API, `Sd` means "single direction": `True` cuts Direction 1 only,
and `False` also cuts Direction 2 using `T2` and `D2`.

Commit 69d3dbd added separate SW 2025 (major 33) and SW 2026+ (major 34)
branches, and both passed `is_through` as `Sd`. For a blind cut, that sends
`Sd=False`, `T2=Blind` and `D2=0`, a double-ended cut whose second side has
zero depth. From a sketch inside the body, SolidWorks rejects it: no
feature, no COM error. From a face sketch it works, because Direction 2 is
in empty space.

PR #192 replaces the three copies of the call with one builder,
`_cut_args(sd, t1, t2)`, and a list of `(label, Sd, T1, T2)` forms to try.
Its blind-cut branch keeps the bug on purpose:

```python
forms = [("", sw_major < 33, blind, blind)]
```

## Goals / Non-Goals

**Goals:**
- Blind cuts work from internal sketches on SW 2025 and 2026.
- One rule for `Sd`, with no version check: `True` unless the cut is meant to
  go both ways.

**Non-Goals:**
- New end conditions (Up To Surface, Offset From Surface, Mid Plane blind).
- Changing `OptimizeGeometry`. It stays `True` on 33.x and `False`
  otherwise, as #192 verified live.
- Exposing `both_directions` on the `create_cut_extrude` MCP tool. The #192
  review already raised this separately.

## Decisions

**Blind cuts try two forms: single-ended first, then double-ended.** The
first live run (SW 2026, 2026-11-01) showed that neither `Sd` value works
everywhere:

| Sketch | `Sd=True` | `Sd=False`, `T2=Blind`, `D2=0` |
|---|---|---|
| Inside the body | cuts (37.70 mm³) | no feature |
| On a face | no feature | cuts the full depth (142.5 mm³) |

With `Sd=True`, Direction 1 follows the sketch normal, which points out of
the part from a face sketch. The blind forms are therefore
`[("", True, blind, blind), (" [Sd=False, D2=0]", False, blind, blind)]`,
and #192's loop reselects the sketch between attempts. Single-ended goes
first because it is the documented meaning of a one-way cut. The
double-ended form has worked from face sketches on SW 2025+ since 69d3dbd.
`parameters.single_direction` records which one built the feature.

*Rejected alternative:* flip `Dir` on a single-ended retry. It would
probably work from face sketches too, but it hasn't been seen live. It
would also change what `reverse_direction=True` means when a caller sets it
on purpose. The double-ended fallback has been proven live, many times.

**Order: after #192.** Changing the pre-#192 code on main would rewrite the
same lines #192 replaces and cause another conflict for the contributor.

## Risks / Trade-offs

- [A face-sketch blind cut now costs one extra COM call] → Two calls
  (FeatureCut4, FeatureCut3) that build nothing, plus a reselect, at the
  0.25 s settle pause each. Acceptable for correctness; an internal sketch
  costs nothing extra.
- [SW 2025 is not on hand to test] → The 2025 branch differs only in
  `OptimizeGeometry`. Both forms were already used on 2025: double-ended
  since 69d3dbd, single-ended before it.
