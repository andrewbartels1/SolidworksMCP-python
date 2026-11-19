## 1. Adapter (COM) in a new `adapters/solidworks/assembly.py`

- [ ] 1.1 A mixin `SolidWorksAssemblyMixin` on `PyWin32Adapter`, importing `_find_components`, `_component_names` and `_as_com` from `io.py`; a helper for the assembly's bounding box
- [ ] 1.2 `create_exploded_view` (auto, or steps: components mark 1, the plane normal to x/y/z mark 2, `AddExplodeStep2`; `CreateExplodedView` first when the configuration has none; `ShowExploded2`) and `set_exploded_view` (`ShowExploded2`, `IsExploded` read back)
- [ ] 1.3 `pattern_components`: `CreateDefinition` (local linear 108 / circular 109), seeds, axis, spacing or angle, count, `CreateFeature`; component counts before and after
- [ ] 1.4 `mirror_components`: `MirrorComponents3` about a plane, as instances; the new names
- [ ] 1.5 `replace_component`: the file checked first, `ReplaceComponents2` (one or all instances, mates re-attached); names and files read back
- [ ] 1.6 `set_component_state` gains `visible` (through `CompConfigProperties5`) and `transparent` (`SetComponentTransparent`), read back
- [ ] 1.7 `create_drawing_view` `exploded` (`IView.ShowExploded`) and `add_balloons` (`CreateAutoBalloonOptions`, layout, `IgnoreMultiple`, `AutoBalloon5`), beside the drawing code
- [ ] 1.8 Unit tests with fake COM objects for each: success, each failure, nothing changed on failure

## 2. Adapter wrappers and mock

- [ ] 2.1 `base.py`, `circuit_breaker.py`, `connection_pool.py`: the six new methods and the new arguments; tests beside each
- [ ] 2.2 `mock_adapter.py`: the six methods and arguments, with the same input errors; tests

## 3. Tools in a new `tools/assembly.py`

- [ ] 3.1 Inputs and the six tools, descriptions to the standard; registered with the other tool modules; toolset family
- [ ] 3.2 `set_component_state` and `create_drawing_view` inputs gain `visible`, `transparent` and `exploded`
- [ ] 3.3 `replace_` in the verb list (`docs/agents/tool-description-standard.md`); `tool_hints.py`, `support_levels.py` (beta until the live demo), error classifier rules, `test_all_endpoints_harness.py`; tests beside each module

## 4. Docs

- [ ] 4.1 Catalog: the six tools and the new options; tool counts to 157
- [ ] 4.2 Progress files, `llms.txt`, CHANGELOG
- [ ] 4.3 Unit suite at 100% coverage, ruff, mypy, mkdocs strict, link check

## 5. Live demo and sign-off

- [ ] 5.1 `tests/live/test_live_sw_assembly_depth.py`: a base plate, a 30 mm pin, a 45 mm pin and a foot made as parts; an assembly with the base fixed, one pin patterned to four along x, the foot mirrored about the Right Plane, the pins replaced by the long pin (all instances), the base hidden and shown and made transparent, the pins exploded 40 mm up; then a drawing with an exploded isometric view, a BOM and balloons. Each step checked: component counts, the bounding box, the balloon count against the BOM's rows; one refused call
- [ ] 5.2 The user runs the demo; fix what it finds; record the GIF (captions held long enough to read)
- [ ] 5.3 Promote the six tools to stable; commit; ask before pushing
