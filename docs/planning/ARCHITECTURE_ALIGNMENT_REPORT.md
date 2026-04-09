# SolidWorks MCP — Architecture Alignment Report

**Updated:** April 8, 2026

This report tracks alignment between the documented 5-layer architecture and the actual implementation. It supersedes the initial gap analysis from April 6 and reflects the current state after implementing the missing runtime intelligence layer.

This is a dated planning snapshot, not a source-of-truth spec. Update it when major routing, security, or adapter behavior changes.

---

## Summary

| Component | Documented | Status | Notes |
|-----------|-----------|--------|-------|
| Core infrastructure | 5 layers | ✅ Complete | Transport, adapters, circuit breaker, pool |
| Tool registry | 90+ tools | ✅ 106 tools | Exceeds spec; server-verified count |
| Circuit breaker | State machine | ✅ Complete | CLOSED/OPEN/HALF_OPEN with auto-recovery |
| Connection pool | Multi-instance | ✅ Complete | FIFO AsyncIO queue; not load-aware by design |
| Complexity analyzer | Decision tree | ✅ Implemented | 25+ ops profiled; param-count + history weighted |
| Intelligent router | Runtime routing | ✅ Implemented | 45+ ops; COM/VBA selection with cache lookup |
| Response cache | Hit/miss cache | ✅ Implemented | TTL in-memory; 20+ read-heavy ops cached |
| VBA adapter | Registered adapter | ✅ Implemented | VbaGeneratorAdapter + VbaMacroExecutor |
| Security enforcement | Multi-level | ⚠️ Partial | API key + rate-limit in tool path; no OAuth2 |
| Load balancing | Intelligent dist. | 🔮 Planned | FIFO pool remains; multi-instance out of scope |

---

## Layer-by-Layer Detail

### Layer 1: Client

MCP protocol layer handles all documented client types (Claude Desktop, custom apps, direct MCP). Web interface is not yet implemented.

---

### Layer 2: MCP Protocol

**Transport:** FastMCP handles JSON-RPC serialization, async request dispatch, and tool registration. Fully implemented.

**Authentication:** API key validation and per-client rate limiting are enforced in the tool invocation path (see `security/runtime.py`). OAuth2 / JWT transport-level auth is a future item.

**CORS:** Configurable via `security/cors.py`. Permissive by default; restrict `allowed_origins` in config for remote deployments.

---

### Layer 3: Application

#### Intelligent Router

`IntelligentRouter` wraps the base adapter and routes 45+ operations. Call path:

1. Check response cache → return cached result if valid
2. Score operation with `ComplexityAnalyzer`
3. Route to COM path (fast, direct) or VBA path (complex/high-param ops)
4. Fall back to alternate path on failure
5. Update performance history

Configuration flags: `enable_intelligent_routing`, `complexity_parameter_threshold` (default 12), `complexity_score_threshold` (default 0.6).

#### Tool Registry

106 tools across 12 modules, all registered with FastMCP and backed by Pydantic schemas.

```
analysis.py             5 tools
automation.py           8 tools
drawing.py             12 tools
drawing_analysis.py     8 tools
export.py               7 tools
file_management.py     14 tools
macro_recording.py      7 tools
modeling.py             9 tools
sketching.py           18 tools
template_management.py  6 tools
vba_generation.py      10 tools
docs_discovery.py       2 tools
────────────────────────────────
Total                 106 tools
```

#### Response Cache

`ResponseCache` (`cache/response_cache.py`) provides:

- Deterministic key generation from operation name + payload hash
- Per-operation TTL policies (configurable; default 60 s)
- LRU eviction bounded by `response_cache_max_entries` (default 512)
- Thread-safe via `RLock`

Cached operations include: `get_model_info`, `list_features`, `list_configurations`, `get_mass_properties`, `get_material_properties`, `analyze_geometry`, all drawing-analysis tools, and `discover_solidworks_docs`.

---

### Layer 4: Adapter

#### Complexity Analyzer (`adapters/complexity_analyzer.py`)

Scores each operation:

```
score = (param_ratio × 0.45) + (profile_complexity × 0.40) + (history_failure_rate × 0.15)
```

25+ operations have explicit profiles. VBA path is preferred when:

- Parameter count exceeds threshold (default 12), OR
- Operation profile flags it as VBA-preferred (sweep, loft, spline, multi-body), OR
- Composite score ≥ 0.6

Performance history resets on server restart (in-memory only; SQLite backing is a future item).

#### VBA Adapter (`adapters/vba_adapter.py`, `adapters/vba_macro_executor.py`)

`VbaGeneratorAdapter` wraps the COM adapter and annotates results with VBA metadata. `VbaMacroExecutor` manages the macro lifecycle: write to temp file → `RunMacro2` → track result → cleanup. Registered in the factory under `AdapterType.VBA`.

#### Direct COM Adapter (`adapters/pywin32_adapter.py`)

~2200-line Windows COM adapter covering document management, part modeling, assembly operations, sketching, analysis, drawing, and export. The primary execution path for all production work.

#### Circuit Breaker (`adapters/circuit_breaker.py`)

Full CLOSED/OPEN/HALF_OPEN state machine. Trips after 5 consecutive failures (configurable), waits 60 s, then allows test calls in HALF_OPEN before closing. Enabled by default; wraps the COM adapter in production.

#### Connection Pool (`adapters/connection_pool.py`)

FIFO AsyncIO queue with configurable pool size (default 3). Provides basic parallel access to the same adapter type. Not a load-aware scheduler — that is by design for single-machine deployments.

---

### Layer 5: SolidWorks

All adapter methods map directly to the SolidWorks COM API via pywin32. No gaps at this layer.

---

## Remaining Gaps

| Gap | Impact | Path forward |
|-----|--------|-------------|
| OAuth2 / JWT auth | Remote deployments rely on API key or IP allowlisting | Medium priority; implement transport middleware hook |
| Security level → tool gating | `security_level` config field exists but is not checked; all tools always accessible | Medium; add per-tool level check in `tools/__init__.py` |
| Persistent performance history | Complexity analyzer resets on restart; cold-start routing is less precise | Low; add SQLite backing to `ComplexityAnalyzer` |
| Multi-instance load balancing | Multiple SW processes not distributed intelligently; pool is FIFO | Low; single-machine is the standard deployment |

---

## References

- Documented architecture: [../user-guide/architecture.md](../user-guide/architecture.md)
- Gap analysis detail: [ARCHITECTURE_ANALYSIS.md](ARCHITECTURE_ANALYSIS.md)
- Config reference: [src/solidworks_mcp/config.py](src/solidworks_mcp/config.py)
