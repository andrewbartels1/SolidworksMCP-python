## Why

In a measured agent session (2026-11-06, the U-joint demo) `create_extrusion` succeeded once, was refused 12 seconds later with "Circuit breaker is open for create_extrusion", and stayed refused for more than 8 minutes, although the breaker's timeout is 60 seconds. The agent had to rebuild every later part by revolving and cutting, and asked for a reset tool that doesn't exist (#208).

## What Changes

- Fix the lock-out: the server's router fell back to a VBA adapter built on the same routed adapter, so one failure re-entered the router and was counted many times (design.md, Cause). The server no longer passes a VBA route.
- `check_interference` is no longer cached by the router (its stale result is part of #209).
- A new tool, `reset_circuit_breaker`: closes every breaker, or one operation's; reports what was open. Read-only towards SolidWorks.
- An open breaker's `hint` names the reset tool and the timeout setting.
- The runbook documents `SOLIDWORKS_MCP_CIRCUIT_BREAKER_TIMEOUT` and the reset tool.

## Capabilities

### New Capabilities
- `adapters/circuit-breaker`: when a breaker opens, how it recovers, and how it is reset.

### Modified Capabilities

## Impact

- `adapters/circuit_breaker.py`, `adapters/connection_pool.py`, possibly `adapters/factory.py` (wrapping order); a tool in `tools/analysis.py` or a new `tools/server_admin.py`; the agent skill's errors reference; `CLAUDE.md` runbook item 4.
- Touches adapter wrappers but no COM calls. Tests beside each module, plus a cross-module test of the production stack in `tests/integration/`.
