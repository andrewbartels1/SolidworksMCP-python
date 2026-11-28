## 1. Probe (with the user's OK; one script, paced, no destructive calls)

- [x] 1.1 Write `C:\...\scratchpad\probe_bodies.py` on `PyWin32Adapter`. It
      builds two blocks and a cylinder unmerged, then records for each
      operation: the selection mark it needs, what `PreSplitBody2` returns,
      what `PostSplitBody2` takes, whether "add" of non-touching bodies
      succeeds, the move/copy order, and the body names after each feature
- [x] 1.2 Run it (the user OK'd live iteration 2026-11-26; four probes, scratch parts only); write the answers into design.md
      (Decision 1) and commit them as "spec: multi-body probe answers"

## 2. Adapter interface

- [x] 2.1 `adapters/base.py`: the parameter models `CombineBodiesParameters`,
      `SplitBodyParameters`, `MoveCopyBodyParameters`,
      `DeleteBodiesParameters` and `ScaleBodyParameters`; non-abstract
      `list_bodies`, `combine_bodies`, `split_body`, `move_copy_body`,
      `delete_bodies` and `scale_body`, each returning "not implemented
      by this adapter"
- [x] 2.2 `circuit_breaker.py` and `connection_pool.py`: the six wrappers;
      tests beside each (`tests/solidworks_mcp/adapters/test_*_bodies.py`)

## 3. SolidWorks adapter

- [x] 3.1 `adapters/solidworks/bodies.py`: body lookup by name (count,
      volume, box per body) and `list_bodies`
- [x] 3.2 `_body_measured` with one rule per operation; it deletes the
      feature when the rule fails
- [x] 3.3 `combine_bodies` (`InsertCombineFeature`, bodies passed directly)
- [x] 3.4 `split_body` (`PreSplitBody2` / `PostSplitBody2`, as the probe
      found)
- [x] 3.5 `move_copy_body`, `delete_bodies` and `scale_body` (selection as
      the probe found)
- [x] 3.6 (Also: the rules shared by both adapters live in
      `adapters/body_rules.py`: name lookup, input checks, the rule per
      operation and the reply fields. `split_body` takes no `bodies`: a
      SolidWorks split acts on every body its tool crosses. A combine is
      judged by its result body, not the part's total, after a subtract of a
      tool lying elsewhere passed a total-volume rule on the mock.)
      Mix `SolidWorksBodiesMixin` into `pywin32_adapter.py` and
      `solidworks/__init__.py`; unit tests with fakes in
      `tests/solidworks_mcp/adapters/solidworks/test_bodies.py` at 100%

## 4. Mock adapter

- [x] 4.1 `adapters/mock_bodies.py`: bodies as boxes, recorded by unmerged
      `create_extrusion`, and the six operations by the spec's rules and
      refusals
- [x] 4.2 Mix it into `mock_adapter.py`; tests in
      `tests/solidworks_mcp/adapters/test_mock_bodies.py`

## 5. Tools

- [x] 5.1 `tools/bodies.py`: strict inputs (names non-empty, factors above
      0, `copies` 1 to 50, `tool_bodies` without the main body) and the six
      tools through the tool boundary (`require_success`, no try/except);
      register in `tools/__init__.py`
- [x] 5.2 `error_classifier.py`: rules for the unknown-body and
      nothing-to-do refusals (`invalid_input`) and the failed rules
      (`feature_not_built`)
- [x] 5.3 `tool_hints.py`, `support_levels.py` (all six beta, "not yet
      checked live"), the toolsets table (a "bodies" family);
      `save_body_as_part`'s description points to `list_bodies`
- [x] 5.4 Tests in `tests/solidworks_mcp/tools/test_bodies.py` on the mock:
      every scenario in both specs

## 6. Docs

- [x] 6.1 A catalog page for the body tools; tool counts (README,
      `docs/index.md`, catalog index, tools overview)
- [x] 6.2 The skill's `references/workflows.md`: a multi-body recipe (a
      mould core: block minus part); `SKILL.md` points to it
- [x] 6.3 Progress files, `llms.txt`, CHANGELOG
- [x] 6.4 Unit suite at 100% coverage, ruff, mypy, mkdocs strict, link check

## 7. Live demo and sign-off

- [x] 7.1 `tests/live/test_live_sw_multi_body.py`, every value checked by
      hand calculation, one refusal in each test:
      - a mould core: a block minus a cylinder, `list_bodies` before and
        after;
      - a split and a delete: a block split at Right Plane, one half kept;
      - copies and a scale: a block copied three times, one copy scaled by
        2.
- [x] 7.2 The user ran the demos 2026-11-27. The mould core was replaced,
      at the user's request, by boolean logic on a cube and a sphere (union
      89,132.7, both subtracts 55,622.4 and 25,132.7, intersection 8,377.6,
      exclusive or 80,755.2 mm³). Two fixes from the runs: list_features and
      get_selected_entities adopted ActiveDoc unflagged, so list_bodies after
      delete_feature took the part for no part; the exclusive or now cuts
      each pair within itself. Split and keep, copies and scale passed. The
      boolean GIF is in docs/demos.md.
- [x] 7.3 The user kept the six tools in beta; push approved.
