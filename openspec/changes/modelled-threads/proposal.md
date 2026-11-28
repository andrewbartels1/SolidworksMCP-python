## Why

The user's request (2026-11-26): modelled threads, external (male) and
internal (female), at the standard sizes with their coarse and fine pitches
and the right depths, read from tables rather than typed in, with a thread
runout. Today the server has only `add_cosmetic_thread`, a drawing
annotation with no geometry. M3 to M6 are the sizes most used. Queue item
43; research and the user's decisions: `openspec/research/modelled-threads.md`.

## What Changes

- **`list_thread_sizes`**: the sizes SolidWorks's own thread profiles hold
  (the Die and Tap profiles in the Thread Profiles folder, read from the
  installed SolidWorks), for `metric` or `inch`. Each size gives its
  nominal diameter and pitch in mm (and threads per inch for inch), whether
  its pitch is the coarse or a fine one for that diameter, the ISO 68-1
  basic thread depth, and the ISO 3508 runout (normal 2.5P, short 1.25P;
  for inch the same rule on 1/TPI, labelled as a reasoned default).
- **`create_thread`**: a modelled thread with SolidWorks's Thread feature:
  `kind` external (die) or internal (tap), `standard` metric or inch,
  `size` (as `list_thread_sizes` names it), started at the circular edge
  picked by `edge_point`, `length` mm long, right or left hand. The
  cylinder's diameter is checked against the size before anything is
  built. The thread is measured: a thread that removes no material is
  undone and fails. The reply gives the thread's depth and runout.
- **`create_hole`**: its description points to `create_thread` and
  `list_thread_sizes` for a modelled thread when fasteners are involved; it
  still models none by default (the user's decision 4).
- Two new tools, beta until the live demo.

## Capabilities

### New Capabilities

- `tools/threads`: `list_thread_sizes` and `create_thread`.

### Modified Capabilities

None (the `create_hole` change is a description only).

## Impact

- `adapters/thread_rules.py` (pure: size parsing, coarse or fine, depth,
  runout, the diameter check); `adapters/solidworks/threads.py` (COM);
  `adapters/mock_threads.py`; base, circuit breaker and connection pool
  wrappers.
- `tools/threads.py`, registered; core toolset; support levels (beta);
  hints; classifier rules.
- Docs: a tool-catalog page, counts, the skill's thread workflow.
- Tests mirroring src; a live test with an M6 bolt-like rod and an M6
  tapped hole, one refusal each.
