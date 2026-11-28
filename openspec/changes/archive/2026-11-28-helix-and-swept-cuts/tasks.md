## 1. Live probe (before the build)

- [x] 1.1 With the user's OK, one short probe on new documents: `InsertHelix` on a closed, selected sketch; the start point at `start_angle` 0 and 90; `InsertCutSwept5` with marks 1 and 4; `CircularProfile` with only the path selected. Record the answers in this design

## 2. Adapter (COM) in a new `adapters/solidworks/swept.py`

- [x] 2.1 Move `create_sweep` from `features.py`, with its tests
- [x] 2.2 The profile helper (circle, named, closed last) and `SweepParameters.profile` / `circular_profile_diameter`
- [x] 2.3 `create_cut_sweep` (`InsertCutSwept5`); both sweeps measured (`_measured`), the right direction required
- [x] 2.4 `create_helix`: the base sketch checked (one circle), `InsertHelix`, the new feature found by name, height/pitch/revolutions, length and start point
- [x] 2.5 Unit tests with fake COM objects for each: success, each failure, nothing left behind on failure

## 3. Adapter wrappers and mock

- [x] 3.1 `base.py`, `circuit_breaker.py`, `connection_pool.py`: `create_helix` and `create_cut_sweep`; tests beside each
- [x] 3.2 `mock_adapter.py`: both, with the same input errors; the sweep's new options; tests

## 4. Tools in `tools/modeling.py`

- [x] 4.1 `CreateHelixInput` (the `defined_by` checks), `create_helix`; `CreateSweepInput` gains `profile` and `circular_profile_diameter`; `create_cut_sweep`; descriptions to the standard
- [x] 4.2 `tool_hints.py`, `support_levels.py` (beta until the live demo), error classifier rules, `test_all_endpoints_harness.py` (generic: it reads every registered tool, so nothing to add); tests beside each module

## 5. Docs

- [x] 5.1 Modeling catalog: the two tools and the sweep options; tool counts to 159
- [x] 5.2 Progress files, `llms.txt`, CHANGELOG
- [x] 5.3 Unit suite at 100% coverage, ruff, mypy, mkdocs strict, link check

## 6. Live demo and sign-off

- [x] 6.1 `tests/live/test_live_sw_helix_and_swept_cuts.py`: a compression spring (a 20 mm helix, pitch 6, height 48; a 2 mm wire by `circular_profile_diameter`; volume 1,586.2 mm³, the circle's area times the reported length) and a threaded rod (a rod, a helix on it, a triangular thread profile at the helix's start, `create_cut_sweep`; the volume removed against the hand calculation); one refused call each
- [x] 6.2 The user runs the demo; fix what it finds; record the GIF (captions held long enough to read). Both passed 2026-11-26 after one fix (the base sketch was read through an unflagged `IFeature`, so every sketch read as empty): the spring's wire 1,585.9 mm³ against 1,586.3, the thread cut -177.8 mm³ against -178.4. Refusals now read as `invalid_input` without a repeated prefix. GIF: the user's to record
- [x] 6.3 ~~Promote the two tools to stable~~ Kept at beta by the user's choice (2026-11-26), with the reason "checked live once"; commit; ask before pushing
