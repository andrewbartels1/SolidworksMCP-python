# Runtime Operations and Observability Plan

## Why This Page Exists

The architecture docs should describe what is implemented today.
This page tracks runtime features that are desirable but not yet fully shipped.

## Current Baseline (April 2026)

Implemented today:

- async MCP tool handlers across the server and tool modules
- fixed-size connection pooling via `ConnectionPoolAdapter`
- circuit breaker protection via `CircuitBreakerAdapter`
- adapter health checks and basic pool metrics
- batch-oriented tools for export, file operations, template application, macro execution, and automation
- agent-side SQLite logging for prompt runs, tool events, and error history

Not fully implemented today:

- multi-level runtime caches for results, feature trees, properties, or queries
- TTL/event/manual cache invalidation workflow
- explicit cancellation of long-running MCP operations
- generic progress streaming for long-running operations
- alerting or notification hooks for failures and degraded service
- autoscaling or distributed runtime orchestration

## Planned Areas

### 1. Runtime Caching

Potential scope:

- result cache for expensive read operations
- feature-tree cache keyed by active file + change fingerprint
- property cache for repeated metadata/mass-property reads
- query cache for expensive docs/search analysis

Open design questions:

- what events should invalidate cache entries?
- should cache be per-session, per-file, or shared across sessions?
- should the server expose explicit cache-clear tools?

### 2. Progress and Cancellation

Potential scope:

- progress callbacks or structured progress events for long-running batch tools
- cancellation tokens for long-running operations
- checkpoint support for multi-step workflows
- resumable batch execution for partial failures

Candidate first targets:

- `batch_export`
- `batch_process_files`
- `batch_file_operations`
- `batch_apply_template`
- `batch_execute_macros`

### 3. Observability and Alerting

Potential scope:

- runtime metrics sink for health and latency
- adapter pool dashboards
- warning/error thresholds with notification hooks
- structured aggregation of retry and circuit-breaker trips
- per-tool latency percentiles and failure rates

Candidate first metrics:

- adapter acquisition latency
- per-tool execution time
- retry counts
- circuit breaker open/half-open durations
- pool utilization
- batch success/failure counts

### 4. Deployment and Scaling

Potential scope:

- multiple runtime instances with external coordination
- distributed state/caching if remote deployments become common
- queue-backed worker model for background operations
- deployment-specific configuration profiles

## Documentation Rule

If a feature is described as implemented in the architecture guide, it should have a concrete code path in `src/`.
If it is only an intended capability, it belongs in planning docs like this page.

## Candidate Milestones

### Milestone A

- document per-tool runtime support matrix
- add explicit progress fields to selected batch tools
- add a cache strategy proposal with invalidation rules

### Milestone B

- implement one real cache for repeated read-only model queries
- add manual cache clear command/tool
- add runtime metric aggregation for adapter pool health

### Milestone C

- add cancellation for long-running batch operations where feasible
- add notification hooks or external alert adapters
- validate the model with real SolidWorks multi-file workflows
