## Why

An agent can sweep a profile along a path to add material, but it can't
make the path most sweeps in mechanical parts follow, a helix, and it can't
sweep to remove material. So it can't model a spring, a modelled thread, a
coil or a groove that winds around a shaft without a hand-written macro.
This is queue item 34, the third of the COM-coverage packages (the user's
choice 2026-11-19).

## What Changes

- **`create_helix`**: a helix or a flat spiral from a sketch holding one
  circle (the base): defined by height and pitch, height and revolutions,
  or pitch and revolutions; clockwise or not, reversed, a start angle, and
  an optional taper. The reply gives all three of height, pitch and
  revolutions, the helix's length and where it starts, so the agent can put
  a profile there.
- **`create_cut_sweep`**: sweeps a closed profile along a path and removes
  material, as `create_cut_extrude` is to `create_extrusion`.
- **`create_sweep`** gains `profile` (name the profile sketch instead of
  relying on "the sketch closed last") and `circular_profile_diameter`
  (sweep a circle of that size, no profile sketch). `create_cut_sweep` takes
  the same options.
- Both sweeps report the part's volume before and after, as the newer
  feature tools do, and a sweep that builds nothing is removed and
  reported.
- Two new tools: 157 to 159.

Not in this change: **thicken**. It turns a surface into a solid, and no
tool makes surfaces yet; it belongs with a surfaces package.

## Capabilities

### New Capabilities

- `tools/helix`: `create_helix`.
- `tools/swept-features`: `create_sweep` and `create_cut_sweep`, their
  profile choices and their measured result.

### Modified Capabilities

None.

## Impact

- New adapter module `adapters/solidworks/swept.py` for the helix and the
  cut sweep; the existing sweep moves there beside them from `features.py`
  (3,800 lines), as queue item 40 recommends.
- `tools/modeling.py` gains the two tools and the new sweep inputs;
  `base.py`, `circuit_breaker.py`, `connection_pool.py` and the mock gain
  the two methods.
- `tool_hints.py`, `support_levels.py` (beta until the live demo), the
  toolsets, error classifier rules.
- Docs: the modeling catalog, tool counts, progress files, `llms.txt`,
  CHANGELOG, the demos page.
- A live demo, `tests/live/test_live_sw_helix_and_swept_cuts.py`: a
  compression spring (a helix and a swept circle) and a threaded rod (a
  helix and a cut sweep of a thread profile), each checked by volume against
  the hand calculation, recorded as a GIF.
- No new dependency; `create_sweep` keeps today's behaviour by default.
