# Heat-Insert Coupon Recording Prompt

The prompt below reproduces [`demo_recording_heat_insert.py`](demo_recording_heat_insert.py) —
a recording-friendly script that pauses between every build step so each
feature is visible on screen, for screen-recording an MCP-driven modeling
session end to end.

```
Write a standalone Python script (not a one-off tool call) that connects to
SolidWorks via the pywin32 adapter and, using the REAL registered MCP tools
(not raw COM calls), builds an M4 heat-set-insert mounting coupon:

- A 30x30x15mm rectangular block, sketched on the Top plane and extruded
  downward 15mm.
- A centered Ø5.5mm x 6mm deep hole for the insert.
- A 0.5mm chamfer on the top face (the face the block was sketched on) --
  select the whole face, not individual edges, so the hole rim and outer
  edges are chamfered together in one feature.
- A 1mm fillet on the *other* largest face -- the bottom, which does not
  touch the Top plane -- again by selecting the whole face.

Make the script recording-friendly:
- At the very start, print the natural-language prompt that produced the
  script, then print the script's own source code.
- Wait on input() before connecting, so I have time to switch to the
  SolidWorks window.
- Print a short step header before each build step, then pause a couple of
  seconds after each one completes, so the part visibly grows on screen one
  feature at a time instead of finishing instantly.
- At the end, print the final feature tree.

Verify each step's response status before moving on, and fail loudly with
the tool's error message if any step doesn't return success.
```

Verified working end to end (all 7 modeling steps + feature-tree check) on
2026-09-18 against SW2026 (major version 34).
