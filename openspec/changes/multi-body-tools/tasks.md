## 1. Probe (with the user's OK; one script, paced, no destructive calls)

- [ ] 1.1 Write `C:\...\scratchpad\probe_bodies.py` on `PyWin32Adapter`. It
      builds two blocks and a cylinder unmerged, then records for each
      operation: the selection mark it needs, what `PreSplitBody2` returns,
      what `PostSplitBody2` takes, whether "add" of non-touching bodies
      succeeds, the move/copy order, and the body names after each feature
- [ ] 1.2 Ask the user to run it; write the answers into design.md
      (Decision 1) and commit them as "spec: multi-body probe answers"

## 2. Adapter interface

- [ ] 2.1 `adapters/base.py`: the parameter models `CombineBodiesParameters`,
      `SplitBodyParameters`, `MoveCopyBodyParameters`,
      `DeleteBodiesParameters` and `ScaleBodyParameters`; non-abstract
      `list_bodies`, `combine_bodies`, `split_body`, `move_copy_body`,
      `delete_bodies` and `scale_body`, each returning "not implemented
      by this adapter"
- [ ] 2.2 `circuit_breaker.py` and `connection_pool.py`: the six wrappers;
      tests beside each (`tests/solidworks_mcp/adapters/test_*_bodies.py`)

## 3. SolidWorks adapter

- [ ] 3.1 `adapters/solidworks/bodies.py`: body lookup by name (count,
      volume, box per body) and `list_bodies`
- [ ] 3.2 `_body_measured` with one rule per operation; it deletes the
      feature when the rule fails
- [ ] 3.3 `combine_bodies` (`InsertCombineFeature`, bodies passed directly)
- [ ] 3.4 `split_body` (`PreSplitBody2` / `PostSplitBody2`, as the probe
      found)
- [ ] 3.5 `move_copy_body`, `delete_bodies` and `scale_body` (selection as
      the probe found)
- [ ] 3.6 Mix `SolidWorksBodiesMixin` into `pywin32_adapter.py` and
      `solidworks/__init__.py`; unit tests with fakes in
      `tests/solidworks_mcp/adapters/solidworks/test_bodies.py` at 100%

## 4. Mock adapter

- [ ] 4.1 `adapters/mock_bodies.py`: bodies as boxes, recorded by unmerged
      `create_extrusion`, and the six operations by the spec's rules and
      refusals
- [ ] 4.2 Mix it into `mock_adapter.py`; tests in
      `tests/solidworks_mcp/adapters/test_mock_bodies.py`

## 5. Tools

- [ ] 5.1 `tools/bodies.py`: strict inputs (names non-empty, factors above
      0, `copies` 1 to 50, `tool_bodies` without the main body) and the six
      tools through the tool boundary (`require_success`, no try/except);
      register in `tools/__init__.py`
- [ ] 5.2 `error_classifier.py`: rules for the unknown-body and
      nothing-to-do refusals (`invalid_input`) and the failed rules
      (`feature_not_built`)
- [ ] 5.3 `tool_hints.py`, `support_levels.py` (all six beta, "not yet
      checked live"), the toolsets table (a "bodies" family);
      `save_body_as_part`'s description points to `list_bodies`
- [ ] 5.4 Tests in `tests/solidworks_mcp/tools/test_bodies.py` on the mock:
      every scenario in both specs

## 6. Docs

- [ ] 6.1 A catalog page for the body tools; tool counts (README,
      `docs/index.md`, catalog index, tools overview)
- [ ] 6.2 The skill's `references/workflows.md`: a multi-body recipe (a
      mould core: block minus part); `SKILL.md` points to it
- [ ] 6.3 Progress files, `llms.txt`, CHANGELOG
- [ ] 6.4 Unit suite at 100% coverage, ruff, mypy, mkdocs strict, link check

## 7. Live demo and sign-off

- [ ] 7.1 `tests/live/test_live_sw_multi_body.py`, every value checked by
      hand calculation, one refusal in each test:
      - a mould core: a block minus a cylinder, `list_bodies` before and
        after;
      - a split and a delete: a block split at Right Plane, one half kept;
      - copies and a scale: a block copied three times, one copy scaled by
        2.
- [ ] 7.2 The user runs the demos; fix what they find; record the GIF
- [ ] 7.3 Promote the tools as the user decides; commit; ask before pushing
