# SolidWorks MCP — Architecture Analysis

**Updated:** April 8, 2026  
**Scope:** Gap analysis between the documented 5-layer architecture ([../user-guide/architecture.md](../user-guide/architecture.md)) and the actual implementation.

---

## Background

The documented architecture describes intelligent runtime routing between COM and VBA execution paths, complexity-based adapter selection, response caching, and multi-layer security enforcement. The original codebase delivered a solid infrastructure foundation — adapters, pooling, circuit breaker, and 106 tools — but was missing the runtime intelligence layer entirely. This document tracks what was missing and what has since been implemented.

---

## Component Status

| Component | Original State | Current State | Notes |
|-----------|---------------|---------------|-------|
| MCP Protocol / JSON-RPC | ✅ Complete | ✅ Complete | FastMCP handles transport |
| Tool registry | ✅ Complete (90+) | ✅ Complete (106) | Exceeds documented count |
| Direct COM adapter | ✅ Complete | ✅ Complete | ~2200-line pywin32_adapter |
| Circuit breaker | ✅ Complete | ✅ Complete | CLOSED/OPEN/HALF_OPEN state machine |
| Connection pool | ✅ Complete | ✅ Complete | FIFO AsyncIO queue; not load-aware by design |
| Complexity analyzer | ❌ Missing | ✅ Implemented | 25+ operation profiles; param-count + history scoring |
| Intelligent router | ❌ Missing | ✅ Implemented | 45+ operations; automatic COM/VBA selection + cache lookup |
| Response cache | ❌ Missing | ✅ Implemented | TTL in-memory cache; 20+ read-only operations cached |
| VBA adapter | ⚠️ Tools only | ✅ Implemented | VbaGeneratorAdapter + VbaMacroExecutor; registered in factory |
| Security enforcement | ❌ Stubs | ⚠️ Partial | API key + rate-limit enforced in tool path; no OAuth2 yet |
| Multi-instance load balancing | ❌ Missing | 🔮 Planned | Out of current scope; pool remains FIFO |

---

## What Was Missing

The original gaps were all in the runtime intelligence layer, not the tooling itself:

- **No complexity analysis** — `create_extrusion(21 params)` always went directly to COM with no automatic VBA fallback.
- **No intelligent router** — adapter was selected once at startup; per-request routing didn't exist.
- **No response cache** — a cache directory was created on disk but no hit/miss logic existed anywhere in the codebase.
- **No VBA adapter** — VBA generation existed as standalone tools; users had to manually call `generate_vba_part_modeling` and then execute the output themselves.
- **Security stubs** — `require_auth()` was a passthrough decorator, `setup_authentication()` was empty, and rate limiting was implemented but never connected to the request path.

---

## What Changed

### Complexity Analyzer (`adapters/complexity_analyzer.py`)

Scores each operation using a weighted formula:

```
score = (param_ratio × 0.45) + (profile_complexity × 0.40) + (history_failure_rate × 0.15)
```

25+ operations have explicit complexity profiles. Operations with high parameter counts (>12), known-complex profiles (sweep, loft, spline), or poor COM history are flagged for VBA routing.

### Intelligent Router (`adapters/intelligent_router.py`)

Wraps the base adapter and intercepts calls to 45+ operations. On each call: check response cache → score complexity → route to COM or VBA path. Falls back automatically on failure, and updates performance history after each call.

### Response Cache (`cache/response_cache.py`)

In-memory TTL cache with LRU eviction and deterministic key generation from operation name + payload hash. 20+ read-heavy operations are cached (model info, mass properties, drawing analysis, feature listing, docs discovery). TTL and capacity are configurable via `config.py`.

### VBA Adapter (`adapters/vba_adapter.py`, `adapters/vba_macro_executor.py`)

`VbaGeneratorAdapter` wraps the COM adapter and generates operation-specific VBA code with metadata annotations. `VbaMacroExecutor` handles the macro lifecycle: write to temp file → call `RunMacro2` → track result + cleanup. Registered in the adapter factory under `AdapterType.VBA`.

### Security (`security/runtime.py`, `security/auth.py`)

API key validation and per-client rate limiting are now enforced in the tool invocation path via a `SecurityEnforcer` inserted before each tool call. Full OAuth2/JWT transport-level auth is a future item.

---

## Remaining Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| Multi-instance load balancing | FIFO pool only; multiple SW processes not distributed intelligently | Low — single-machine is standard |
| OAuth2 / JWT | Remote deployments rely on API key or IP allowlisting | Medium — needed for hosted deployments |
| Security level → tool access control | `security_level` config field unused; all tools always accessible | Medium |
| Persistent performance history | Complexity analyzer resets on restart; no SQLite backing yet | Low — degrades gracefully |

---

## Tool Registry

**106 tools across 12 modules** (exceeds documented 90+). All registered with FastMCP and backed by Pydantic input schemas.

```
analysis.py            5 tools
automation.py          8 tools
drawing.py            12 tools
drawing_analysis.py    8 tools
export.py              7 tools
file_management.py    14 tools
macro_recording.py     7 tools
modeling.py            9 tools
sketching.py          18 tools
template_management.py 6 tools
vba_generation.py     10 tools
docs_discovery.py      2 tools
──────────────────────────────
Total                106 tools
```
