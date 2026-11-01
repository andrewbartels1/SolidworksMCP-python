## 1. Standard and check

- [ ] 1.1 `docs/agents/tool-description-standard.md`: the description shape,
      the `input_data` line, the hints, two worked examples; linked from
      CONTRIBUTING.md and the mkdocs nav
- [ ] 1.2 `tests/integration/test_tool_descriptions.py`: the check across
      every registered tool, reporting all offenders at once; starts as
      expected-to-fail per module and is switched on as each module is done

## 2. Behaviour hints

- [ ] 2.1 `tools/tool_hints.py`: title and read-only / destructive /
      idempotent for all 154 tools, from each tool's adapter calls
- [ ] 2.2 `ToolRegistrar.tool()` passes the hints as MCP annotations;
      unit tests in `test_tool_boundary.py` (hints applied, an unknown tool
      is an error at registration)
- [ ] 2.3 `test_tool_hints.py`: the table matches the registered tools
      exactly; spot checks (`list_features` read-only, `delete_feature`
      destructive)

## 3. Descriptions, worst first

- [ ] 3.1 `drawing_analysis.py` (8 tools)
- [ ] 3.2 `vba_generation.py` (10)
- [ ] 3.3 `automation.py` (8) and `macro_recording.py` (7)
- [ ] 3.4 `template_management.py` (6) and `docs_discovery.py` (5)
- [ ] 3.5 `drawing.py` (14) and `drawing_automation.py` (7)
- [ ] 3.6 `file_management.py` (19) and `export.py` (7)
- [ ] 3.7 `analysis.py` (6) and `engineering_data.py` (8)
- [ ] 3.8 `modeling.py` (30)
- [ ] 3.9 `sketching.py` (19)

## 4. Ship

- [ ] 4.1 The check passes for every module; full mock suite and lint pass;
      100 % coverage kept
- [ ] 4.2 Regenerate the tool catalog docs if they quote descriptions;
      `mkdocs build --strict`
- [ ] 4.3 After the release: ask Glama for a rescan and record the new
      score in the internal assessment
