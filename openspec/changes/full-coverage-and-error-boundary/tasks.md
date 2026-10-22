## 1. Error boundary core

- [x] 1.1 `ErrorClassifier` with an ordered rule table:
  - HRESULT from `com_error` args and from `"COM error in …: (<hresult>,"` text
  - circuit open, no active document, not found
  - fallbacks: `operation_failed` / `internal`
  - unit tests: one per rule, plus the fallbacks
- [x] 1.2 `ToolOperationError` + `require_success(result)`; the boundary wrapper builds the spec payload (`status`, `message`, `error_type`, `hint`, `execution_time`) from `ToolOperationError`, invalid input (`ValueError` / pydantic `ValidationError`) and any other exception. Tests for each path, including "adapter not called on invalid input"
- [x] 1.3 `ToolRegistrar` proxy whose `.tool()` applies the boundary. Wire it in `tools/__init__.register_tools`. Test that the tool schema is unchanged and that `call_tool` goes through the boundary
- [x] 1.4 Snapshot test: success payloads of a sample of tools are byte-identical before and after (spec "Success payload shape is unchanged")

## 2. Migrate tool modules (one commit per module, unit suite after each)

For each module:
- remove per-tool `try/except` and hand-built error dicts
- use `require_success`
- read every removed `except` body first, and keep any logic that does more than log-and-return
- update tests that pin `"Unexpected error"` wording

- [x] 2.1 `tools/modeling.py`
- [x] 2.2 `tools/sketching.py`
- [x] 2.3 `tools/drawing.py` and `tools/drawing_analysis.py`
- [x] 2.4 `tools/file_management.py`
- [x] 2.5 `tools/export.py`, `tools/analysis.py`, `tools/automation.py`
- [x] 2.6 `tools/docs_discovery.py`, `tools/vba_generation.py`, `tools/macro_recording.py`, `tools/template_management.py`
- [ ] 2.7 `ui/services/llm_service.py` catalog text and `docs/user-guide/tool-catalog/`: document `error_type` / `hint`

## 3. Coverage to 100% (honest config)

- [x] 3.1 Import-fallback tests (subprocess with the dependency blocked):
  - `pywin32_adapter`, `solidworks/io.py`, `sketch.py`
  - `com_executor`, `docs_discovery`, `agents/harness`
  - `ui/local_llm`, `agents/vector_rag` (`_FallbackSentenceTransformer`)
- [x] 3.2 Pack-and-go (unit tests done; the live check moved to dead-code item 13, run in the feature review):
  - unit tests for `_get_attr_or_call`, `_extract_dependency_paths`, `_copy_with_collision_handling`
  - a new live test that packs a generated assembly
- [x] 3.3 Fake-COM unit tests for the remaining branches:
  - `features.py`, `sketch.py`, `io.py`
  - `pywin32_adapter` geometry helpers
  - `face_selection`, `selection`, `rebuild_inspector`, `com_utils`, `sw_type_info`, `com_executor._worker`
- [x] 3.4 Audit every remaining `except Exception` in `adapters/`: keep (best-effort, documented), fold into `_attempt` / `_handle_com_operation`, or delete as redundant. Record the decisions in `dead-code.md`
- [x] 3.5 Dead-code ledger `dead-code.md` (`file:line`, guard, why unreachable); delete those lines. Any adapter behaviour change gets its own `mock_adapter.py` update and test step
- [x] 3.6 Remaining `ui/`, `agents/history_db`, `server`, `circuit_breaker`, `mock_adapter` lines
- [x] 3.7 Delete every `# pragma: no cover` in `src/` and drop the pragma exclusion from `pyproject.toml`; full run shows 100% with `honest.coveragerc`

## 4. Test layout mirrors src

- [x] 4.1 Record the baseline collected-test count (unit + live collect)
- [x] 4.2 Split coverage-bucket files by the module they exercise:
  - `test_coverage_push_final.py`, `test_coverage_gaps.py`, `test_solidworks_mixins_coverage.py`
  - `tools/test_additional_coverage.py`, `tools/test_exception_coverage.py`
  - `adapters/test_coverage.py`, the `*_coverage*.py` / `*_push*.py` files
  - the files at the `tests/` root
- [x] 4.3 `git mv` every remaining test to `tests/solidworks_mcp/<pkg>/test_<module>[_topic].py`; integration tests to `tests/integration/`
- [x] 4.4 Collected-test count equals the baseline; the full unit suite passes
  (2800 collected before = 2781 after + 19 deleted skip-only placeholders; `tests/integration/test_test_layout.py` now enforces the layout)

## 5. Verify and document

- [ ] 5.1 Full run (unit + smoke + all live files, warm-up gate on); honest coverage 100%; no new live failures
- [ ] 5.2 CLAUDE.md: tool contract (`error_type`, `hint`); fix the stale COM-threading section; test-layout rule
- [ ] 5.3 `openspec validate full-coverage-and-error-boundary --strict`
