## 1. Prerequisite

- [x] 1.1 Branch `fix/blind-cut-single-direction` from #192 (with #191 and main merged in); it rebases onto `main` once #192 merges.

## 2. Adapter fix

- [x] 2.1 In `src/solidworks_mcp/adapters/solidworks/features.py` (`create_cut_extrude`), change the blind form to `("", True, blind, blind)`. Rewrite its comment to say that `Sd` means single direction and why `False` failed for internal sketches (#193).
- [x] 2.2 Update the comment above the `sw_major` detection: it now picks only `OptimizeGeometry`.
- [x] 2.3 Correct the docstring wherever it describes `Sd` or the per-version blind behaviour.

## 3. Unit tests

- [x] 3.1 In `tests/solidworks_mcp/adapters/solidworks/test_features.py`, change the version and end-condition table's blind rows to expect `Sd=True`. Add a `34.1.0` Blind row and an undetected-version (`0`) Blind row.
- [x] 3.2 Add a test that a blind cut makes one `FeatureCut4` call with `Sd=True`, `T2=Blind` and `D2=0`, on both 33.x and 34.x.
- [x] 3.3 Run `pytest tests -m "not solidworks_only"` and the coverage report. `features.py` must stay at 100%.

## 4. Docs

- [x] 4.1 Add a `docs/agents/com-api-pitfalls.md` entry: "`Sd` on `FeatureCut3`/`FeatureCut4` means single direction". Cover its symptom (no feature, no error, internal sketch only) and its fix.
- [x] 4.2 Add a CHANGELOG entry under Fixed.

## 5. Live tests (ask the user first; they run them with `SW_TEST_PACE_SECONDS=4`)

- [x] 5.1 In `tests/live/test_live_sw_contributor_fixes.py`, remove the `xfail` from `test_blind_cut_still_cuts_one_way`, and add `test_through_all_cuts_one_way` (expect 62.83 mm³).
- [x] 5.1a First live run: internal-sketch blind cut passes; face-sketch blind cuts (`verify_model` hole, `cut_extrude_sketch_fix` hole) return no feature with `Sd=True`.
- [x] 5.1b Second run: the double-ended fallback did not help, and SolidWorks crashed in the next test (`check_interference`).
- [x] 5.1c Probe (`tests/live/probe_blind_cut_forms.py`, not committed): only single-ended with `Dir` reversed cuts the Top Plane hole; `Sd=False` with `D2=0` never builds; a failed attempt does not spoil the retry.
- [x] 5.1d Replace the fallback with a single-ended retry in the opposite direction, plus `direction_flipped` on the result and in the tool reply; unit tests.
- [x] 5.1e Document it where agents read it: the tool description and field descriptions, the no-feature error message, a `feature_not_built` classifier rule and hint, the catalog note and error table, pitfall #35, the CHANGELOG and these artifacts.
- [x] 5.1f Live tests assert `direction_flipped` (true for the Top Plane hole, false through the middle of the block).
- [ ] 5.2 Ask the user to run `tests/live/test_live_sw_contributor_fixes.py`, `tests/live/test_live_sw_verify_model.py` and `tests/live/test_live_sw_cut_extrude_sketch_fix.py`. Expect the internal blind cut to remove 37.70 mm³, the Top Plane hole 142.5 mm³ (flipped), Through All one way 62.83 mm³ and both ways 125.66 mm³.

## 6. Ship

- [ ] 6.1 Commit the fix together with `tests/live/test_live_sw_contributor_fixes.py`, then open a PR that closes #193 (no Claude attribution).
