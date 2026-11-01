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

**`Sd` comes from the end-condition form, never from the SW version.** The
blind form becomes `("", True, blind, blind)`. The Through All forms keep
#192's values: `True` for one way, and `False` with `T1=T2=ThroughAll`
first for both ways. `sw_major` is then read only to choose
`OptimizeGeometry`, and the comment above it says so.

*Rejected alternative:* keep `Sd=False` and fall back to `Sd=True` when the
first call returns nothing. It adds a second COM call to every internal
blind cut, keeps a meaning of `Sd` we know is wrong, and on a face sketch
the double-ended form could someday cut something on the far side.

**Order: after #192.** Changing the pre-#192 code on main would rewrite the
same lines #192 replaces and cause another conflict for the contributor.
Once #192 is merged, the implementation is a one-line change plus tests.

## Risks / Trade-offs

- [A face-sketch blind cut behaves differently with `Sd=True`] → No.
  Before 69d3dbd, every version used `Sd=True`, and the pre-2025 branch
  still does. The live `verify_model` hole test (142.5 mm³) checks this on
  SW 2026.
- [SW 2025 is not on hand to test] → The `Sd` meaning is the same in every
  API version since 2010. The live run is on SW 2026. The 2025 branch
  differs only in `OptimizeGeometry`, which this change does not touch.
