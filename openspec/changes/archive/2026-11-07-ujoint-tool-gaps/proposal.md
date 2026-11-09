## Why

Building SolidWorks' U-Joint sample from a prompt (the README's top demo),
both agent sessions hit the same walls (#209). The pin can't be mated
concentric to its hole, because `add_mate` only takes named planes and axes.
The knob can't spin, because nothing fixes, floats or flexes a component.
There are no planes at an angle or on a sloped face. Every chamfer is 45°.
The bent bracket had to be drawn as a closed outline, because the agent
didn't know thin extrudes work. And the agent concluded `both_directions` was
ignored, because the reply echoed `direction: blind`. Scripts that call a
tool function with a plain dict still fail on most tools.

## What Changes

- **Face mates.** `add_mate` takes `face_a` / `face_b` in place of
  `entity_a` / `entity_b`: a point on the face in the component's own part
  coordinates (mm). The face is found among that component's faces only, so
  a pin and the hole it sits in can't be confused. Concentric, coincident,
  parallel, distance and angle mates all work on faces.
- **`set_component_state`, a new tool.** Fix or float a component, and make
  a sub-assembly rigid or flexible (so its own mates move in the parent).
  The reply reads the state back.
- **Angled and face-based reference planes.** `create_reference_plane` takes
  `angle` with an `axis` to rotate about (a named axis or a straight edge's
  point), and `face_point` to use a planar face, sloped or not, as the
  reference.
- **Angled chamfers.** `add_chamfer` takes `angle` (default 45°) and `flip`,
  using SolidWorks' angle-distance chamfer, which it already called with a
  fixed 45°.
- **Extrusion replies say what was built.** `create_extrusion` reports the
  end condition SolidWorks used (`MidPlane` for `both_directions`) and the
  thin wall, instead of echoing `direction`. Thin extrudes from an open
  profile are checked live and documented, with `thin_side` (one side, the
  other side, or mid-plane).
- **Plain-dict input for every tool.** The tool boundary validates a dict
  argument as the tool's input model, so a script can call any tool function
  with a dict. The export tools' own fix (6ae900f) is folded into it.
- The stale `check_interference` result in #209 was the router's cache,
  removed by #213; a live check confirms it.

## Capabilities

### New Capabilities
- `tools/assembly-mates`: face mates and component state (fixed, floating,
  rigid, flexible).
- `tools/reference-plane`: planes offset from, angled to, or on a face.
- `tools/extrusion`: what an extrusion reply reports; thin extrudes.

### Modified Capabilities
- `tools/edge-treatment`: chamfers at an angle.
- `tools/error-boundary`: a plain dict is validated as the tool's input.

## Impact

- Adapter: `add_mate`, `create_reference_plane` and `add_chamfer` gain
  parameters, and `set_component_state` is new. Each goes through base, mock,
  COM, circuit breaker and connection pool.
- Tools: `modeling.py` inputs and descriptions; `tool_boundary.py`; the
  support levels and hints for the new tool; the progress files regenerate.
- Live tests for every changed tool, recorded as GIFs on the Demos page.
- Closes #209.
