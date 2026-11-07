## 1. Reproduce

- [x] 1.1 `tests/integration/test_circuit_breaker_stack.py`: the factory's real wrapping around a fake adapter; reproduce "success, then open" and "never half-opens"; record the cause in design.md

## 2. Fix and reset

- [x] 2.1 Fix the cause; the spec's first two requirements pass
- [x] 2.2 `CircuitBreakerAdapter.reset(operation=None)`, forwarded by the pool; tests beside each
- [x] 2.3 `reset_circuit_breaker` tool (description to the standard, Read-only towards SolidWorks); tests
- [x] 2.4 `circuit_open` hint with the wait and the tool name

## 3. Docs and ship

- [x] 3.1 `CLAUDE.md` runbook item 4, the agent skill's errors reference, CHANGELOG, queue
- [x] 3.2 Full mock suite, ruff, 100 % coverage; then a paced live check with the user's permission
