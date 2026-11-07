## Context

`factory.create_adapter` wraps the COM adapter in `CircuitBreakerAdapter` (per-operation buckets, threshold 5, timeout 60 s from `SOLIDWORKS_MCP_CIRCUIT_BREAKER_TIMEOUT`), then in `ConnectionPoolAdapter`, whose `adapter_factory` returns that same wrapped instance, so every pool slot shares one breaker. On an exception the pool retries up to `max_retries`, disconnects the "failed" adapter and asks the factory for a replacement (the same object). No server log survived the failing session.

## Goals / Non-Goals

**Goals:** find and fix the lock-out with a test that reproduces it; a reset tool; clearer `circuit_open` errors.
**Non-Goals:** redesigning the pool (a later change may remove it, since one COM apartment can't use several connections).

## Decisions

- **Reproduce first.** Build the production stack around a fake adapter that fails in the ways `create_extrusion` can (exception, error result, slow call) and drive the session's sequence. Candidate causes to test: a pool retry recording several failures for one call; the pool disconnecting the shared adapter; a refused call resetting `last_failure_time`; `half_open_calls` never reset. The fix follows what the test shows; the spec's scenarios are the acceptance tests.
- **The reset tool lives beside the other server tools**, uses `require_capability(adapter, "reset_circuit_breakers")`, and is forwarded by the pool. The breaker gains `reset(operation=None) -> list[str]`.
- **Hint text** comes from the error classifier's `circuit_open` rule: it names `reset_circuit_breaker` and `SOLIDWORKS_MCP_CIRCUIT_BREAKER_TIMEOUT` (the seconds left aren't known to the classifier).

## Risks / Trade-offs

- [The reset tool lets an agent hammer a failing operation] → the result says what was open and the agent skill says to fix the cause first.

## Cause (found 2026-11-06)

The server log of the failing session shows one `create_extrusion` failure, then "Circuit breaker opened after 5 failures" in the same second, with a traceback cycling `server._routed_call` → `IntelligentRouter.execute` → `VbaGeneratorAdapter.create_extrusion` → `server._routed_call`. `_instrument_adapter_methods` replaces methods on the adapter instance, and the server's `VbaGeneratorAdapter` was built on that same instance, so the router's "VBA fallback" re-entered the routed method: each COM failure fell back, failed again and recursed, counting one failure many times. Every later attempt (the sketch was already used, so it really failed) did the same, which is why the breaker looked like it never recovered. Fix: the server no longer passes a VBA route (it only re-ran the same COM call). The pool is not involved, so the open question below is closed: no.

The same session's stale interference result (#209) was the router's 60-second cache of `check_interference`; it is removed from the cacheable set.

## Open Questions

- Whether the lock-out also needs the pool turned off by default; decided after the reproduction.
