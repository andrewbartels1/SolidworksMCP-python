## Why

An agent can already make a multi-body part (`create_extrusion` with
`merge_result: false`) and save one body as a part (`save_body_as_part`),
but it can't do anything with the bodies in between. It can't see which
bodies exist, combine them (add, subtract, keep the common part), split one
at a plane, move or copy one, delete one, or scale one. These are the usual
steps of multi-body modelling: a mould core made by subtracting a part from
a block, a part cut in two for printing, a body arrayed by copying. Queue
item 35, the next of the COM-coverage packages.

## What Changes

- **`list_bodies`**: the active part's solid bodies, each with its name,
  volume and bounding box. Every other tool here names bodies by these
  names, and every refusal lists them.
- **`combine_bodies`**: add, subtract or keep the common volume of a main
  body and one or more tool bodies (`IFeatureManager.InsertCombineFeature`).
- **`split_body`**: splits the part's bodies with a plane or a sketch as the
  cutting tool (`PreSplitBody2`, then `PostSplitBody2`), and names the
  bodies that result.
- **`move_copy_body`**: moves bodies by a translation and a rotation, or
  copies them a number of times (`InsertMoveCopyBody2`).
- **`delete_bodies`**: deletes the named bodies, or with `keep: true` keeps
  only them (`InsertDeleteBody2`).
- **`scale_body`**: scales the part's bodies uniformly or per axis, about
  the centroid, the origin or a coordinate system (`InsertScale`).
- **Each operation is measured.** Its reply gives the body count and the
  volume before and after. An operation that leaves them in a state its
  kind can't produce fails, and the feature is removed. Examples: a
  subtract that removes nothing, a split that makes no new body, a copy
  that adds no volume.
- Six new tools, all beta until their live demo. The tool count rises by
  six; the starting figure depends on whether the helix change merges
  first.

## Capabilities

### New Capabilities

- `tools/body-listing`: `list_bodies` names each solid body with its
  volume and size.
- `tools/body-operations`: `combine_bodies`, `split_body`,
  `move_copy_body`, `delete_bodies` and `scale_body`. Each acts on bodies by
  name, is measured, and refuses unknown bodies by listing the real ones.

### Modified Capabilities

None. `multibody-part-export` (`save_body_as_part`) keeps its behaviour. Its
description will point to `list_bodies` for the names.

## Impact

- **COM and adapter code** (the extra risk per CLAUDE.md: late binding,
  method flagging, the connect thread):
  - a new `adapters/solidworks/bodies.py` holds the COM calls and is mixed
    into `pywin32_adapter.py`;
  - a new `adapters/mock_bodies.py` holds the mock;
  - new non-abstract methods go in `adapters/base.py`, with wrappers in
    `circuit_breaker.py` and `connection_pool.py`.
- **Tools:**
  - a new `tools/bodies.py` holds the inputs and the six tools;
  - `tool_hints.py`, `support_levels.py`, the toolsets table and
    `error_classifier.py` (rules for the new refusals) are updated.
- **Docs:**
  - a new catalog page for body tools;
  - the tool counts (README, index, catalog index, tools overview);
  - the progress files, `llms.txt`, the CHANGELOG;
  - the agent skill's workflow reference gets a multi-body recipe.
- **Live demo:** `tests/live/test_live_sw_multi_body.py`, recorded as a GIF,
  with one deliberate refusal in each test.
- No new dependency. No breaking change. No GitHub issue: this is queue
  item 35.
