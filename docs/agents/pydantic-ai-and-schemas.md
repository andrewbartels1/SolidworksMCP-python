# PydanticAI and Pydantic in This Project

This section explains where schema-driven validation belongs and how it relates to the MCP server.

## Scope Boundaries

- MCP server docs cover tool APIs, adapters, configuration, and runtime behavior in `src/solidworks_mcp/server.py` and `src/solidworks_mcp/tools/`.
- Agent docs cover prompt workflows, specialist agents, and schema-validated outputs in `src/solidworks_mcp/agents/`.
- Planning docs cover future ideas and roadmap items in `docs/planning/`.

## Where Pydantic Is Used

- Tool input models: request validation for MCP tools (strict and typed inputs).
- Output contracts: predictable response payloads (`status`, `message`, execution metadata).
- Config models: runtime config and environment parsing.

## Where PydanticAI Is Used

- Agent harness execution and model routing.
- Structured result schemas for agent responses.
- Recoverable failure handling with retry limits.
- Smoke tests for schema-conformant outputs.

## Practical Rule

Use MCP docs when implementing or troubleshooting server tools.
Use agent docs when designing prompt workflows, schemas, and logging/replay behavior.
Use planning docs for proposals that are not shipped yet.

## Related Pages

- [Agents and Prompt Testing](agents-and-testing.md)
- [Agent Memory and Recovery](agent-memory-and-recovery.md)
- [Logging and Agent Invocation](logging-and-agent-invocation.md)
- [Pydantic AI Integration Plan](../planning/PLAN_PYDANTIC_AI_INTEGRATION.md)
