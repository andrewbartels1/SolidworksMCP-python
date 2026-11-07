## 1. Plain dicts at the boundary

- [x] 1.1 `tool_boundary.py`: validate a dict argument as its annotated model; tests beside it, and one calling every tool with a dict on the mock

## 2. Part features

- [x] 2.1 `create_extrusion`: reply reports the applied end condition, `both_directions`, thin thickness and `thin_side`; `thin_side` input mapped to `RevThinDir`; tests
- [x] 2.2 `add_chamfer`: `angle` and `flip` through every adapter layer; correct the chamfer-type comment; tests
- [x] 2.3 `create_reference_plane`: `axis` with `angle`, and `face_point`; every adapter layer; tests

## 3. Assemblies

- [ ] 3.1 Live read-only probe: in which space a component's faces report coordinates; record it in design.md
- [ ] 3.2 `add_mate`: `face_a` / `face_b` through every adapter layer; tests
- [ ] 3.3 `set_component_state` tool and adapter method (base, mock, COM, breaker, pool), hints, support level; tests

## 4. Docs and levels

- [ ] 4.1 Tool descriptions; skill's errors-and-limits (remove the `add_mate` and fixed-45° limits); support levels (`add_mate` stable once live); regenerate progress
- [ ] 4.2 CHANGELOG; queue

## 5. Live

- [ ] 5.1 `tests/live/test_live_sw_ujoint_tool_gaps.py`: one test per tool (thin bent plate, mid-plane extrusion, 60° chamfer, angled plane, face plane, pin-in-hole face mate, fix/float/flexible, a dict call, a repeated interference check)
- [ ] 5.2 Run them live (paced), record GIFs, add them to the Demos page
- [ ] 5.3 Full mock suite, ruff, 100 % coverage, `mkdocs build --strict`
