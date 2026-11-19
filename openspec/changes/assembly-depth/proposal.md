## Why

An agent can insert components, mate them, list them and check them for
interference, but it can't take an assembly to the drawing a shop builds
from: an exploded view with numbered balloons beside the BOM. It also can't
repeat a component (four bolts in a row), mirror one to the other side,
swap a part for another version, or hide a part to see inside. Today each
of these needs a hand-written macro. This is queue item 33, the second of
the COM-coverage packages (the user's choice 2026-11-19).

## What Changes

- **`create_exploded_view`**: explodes the active assembly, either
  automatically or step by step (these components, this far, along x, y or
  z), and shows it.
- **`set_exploded_view`**: shows the assembly exploded or collapsed.
- **`pattern_components`**: repeats components in a row along an axis
  (count and spacing) or around an axis (count and angle).
- **`mirror_components`**: mirrors components about a plane, as new
  instances of the same parts.
- **`replace_component`**: swaps a component for another part file, one
  instance or every instance, keeping its mates where they still fit.
- **`add_balloons`**: numbers the components in a drawing view with
  balloons, one per part, laid out around the view.
- **`set_component_state`** gains `visible` (hide or show) and
  `transparent`.
- **`create_drawing_view`** gains `exploded`: the view shows the
  assembly's exploded view.
- **`replace_`** joins the tool-naming verb list: it swaps one thing for
  another.
- Six new tools: 151 to 157.

## Capabilities

### New Capabilities

- `tools/exploded-views`: `create_exploded_view` and `set_exploded_view`,
  and a drawing view that shows the exploded view.
- `tools/component-patterns`: `pattern_components` and
  `mirror_components`.
- `tools/component-replace`: `replace_component`.
- `tools/drawing-balloons`: `add_balloons`.

### Modified Capabilities

- `tools/assembly-mates`: `set_component_state` also hides, shows and makes
  components transparent.
- `tools/tool-naming`: the verb list gains `replace_` (and lists the
  `activate_` and `delete_` verbs the standard already allows).

## Impact

- New adapter module `adapters/solidworks/assembly.py` for the COM calls,
  reusing the component helpers in `io.py` (`_find_components`,
  `_component_names`); balloons and the exploded drawing view beside the
  drawing code. New code goes in its own module instead of growing `io.py`
  (4,000 lines), as queue item 40 recommends.
- New tool module `tools/assembly.py`; `base.py`, `circuit_breaker.py`,
  `connection_pool.py` and the mock gain the new methods.
- `tool_hints.py`, `support_levels.py`, the toolsets, the error classifier,
  `docs/agents/tool-description-standard.md` (the verb).
- Docs: a catalog page for the assembly tools, tool counts, progress files,
  `llms.txt`, CHANGELOG, the demos page.
- A live demo, `tests/live/test_live_sw_assembly_depth.py`: a pinned base
  assembly built with every new tool and drawn exploded with balloons and a
  BOM, recorded as a GIF.
- No new dependency; the two extended tools keep today's behaviour by
  default.
