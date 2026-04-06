# SolidWorks MCP Roadmap 2026-2027

**Executive Summary**: Strategic evolution of SolidWorks MCP from tool library to intelligent AI-driven design platform with stateful workflows, real-time visualization, and autonomous agent capabilities.

## Timeline & Phases

### Q2 2026: Foundation & Bug Fixes (4 weeks) ✅ COMPLETE

- [x] Fixed Python 3.14 deprecation warnings
- [x] Unified server startup (run-mcp.ps1 → start_local_server.py)
- [x] Added vision extras (pillow, scikit-image, numpy)
- [x] Implemented year-aware API help search
- [x] Full test suite passing (323+ tests, 90%+ coverage)

### Q2 2026: Phase 1 - Research & Prototypes (6-8 weeks)

#### 1A. GUI Visualization Research & MVP (3-4 weeks)

- **Goal**: Proof-of-concept dashboard eliminating context-switch pain
- **Tech**: FastMCP web dashboard (primary), VS Code Webview (backup)
- **Deliverable**:
  - Minimal dashboard with tool browser
  - Live screenshot of SolidWorks
  - Command execution UI
  - Real-time feedback
- **Success Criteria**: User can execute 3-step workflow without switching to SolidWorks

#### 1B. Database System Design & Prototyping (3-4 weeks)

- **Goal**: Understand workflow persistence & recovery patterns
- **Spike**: Test SQLModel + SQLite performance
- **Deliverable**:
  - Schema definition
  - Basic operation logging
  - Checkpoint/recovery proof-of-concept
- **Decision Point**: Decide on snapshot vs. full state capture

#### 1C. PydanticAI Agent Proof-of-Concept (2-3 weeks)

- **Goal**: Verify agent can coordinate MCP tools
- **Spike**: Basic agent framework
- **Deliverable**:
  - Agent loads MCP tools dynamically
  - Executes simple 3-step workflow autonomously
  - Error handling proof-of-concept
- **Decision Point**: FastMCP vs. Claude API direct

### Q3 2026: Phase 2 - MVP Development (12 weeks)

#### 2A. GUI Dashboard (4 weeks)

- [ ] Auto-generate tool parameter forms from Pydantic schemas
- [ ] Real-time SolidWorks viewport streaming
- [ ] Command history with execution timeline
- [ ] Result display & error messages
- [ ] WebSocket bridge for live feedback

#### 2B. Workflow Database (4 weeks)

- [ ] SQLModel schema with all entities
- [ ] Operation logging middleware
- [ ] Basic replay & recovery
- [ ] Checkpoint creation & restoration
- [ ] Auto-save on server shutdown

#### 2C. PydanticAI Core Agent (4 weeks)

- [ ] Context tracking system
- [ ] Tool wrapper with error handling
- [ ] Basic planning capability
- [ ] Session memory storage
- [ ] Integration with MCP server

**Milestone**: End of Q3 - Fully functional standalone system (no Copilot)

### Q4 2026: Phase 3 - Integration & Polish (12 weeks)

#### 3A. VS Code Copilot Integration (4 weeks)

- [ ] Chat participant: `@solidworks`
- [ ] Copilot → Agent bridge
- [ ] Execution progress streaming
- [ ] Design review inline

#### 3B. Workflow Templating (3 weeks)

- [ ] Template creation from workflows
- [ ] Parameter mapping (Jinja2)
- [ ] Template library UI
- [ ] Execute template with parameters

#### 3C. Advanced Agent Features (3 weeks)

- [ ] Design optimization recommendations
- [ ] Error recovery with suggestions
- [ ] Workflow learning & reuse suggestions
- [ ] Performance metrics & analytics

#### 3D. Export & Scripting (2 weeks)

- [ ] Export to Python script
- [ ] Export to VBA macro
- [ ] YAML workflow format
- [ ] Git-friendly workflow files

**Milestone**: End of Q4 - Production-ready v1.0

### Q1 2027: Enhanced Features (12 weeks)

#### 4A. Undo/Redo System (3 weeks)

- [ ] Operation reversibility analysis
- [ ] Full undo tree visualization
- [ ] Rollback & branch support
- [ ] Crash recovery improvements

#### 4B. LangChain & Advanced Integration (4 weeks)

- [ ] LangChain tool wrapper
- [ ] Multi-turn conversation chains
- [ ] Structured memory management
- [ ] Agent composition patterns

#### 4C. Collaboration & Sharing (3 weeks)

- [ ] Workflow marketplace
- [ ] Team workflow library
- [ ] Real-time collaborative editing
- [ ] Version control integration

#### 4D. Performance & Optimization (2 weeks)

- [ ] Database query optimization
- [ ] Screenshot caching
- [ ] Async execution prioritization
- [ ] Resource profiling

**Milestone**: End of Q1 2027 - v2.0 with full feature set

---

### Q2 2027: Automated Reverse-Engineering Loop

> **Background**: The AI-assisted design workflow described in
> [AI-Assisted Design Workflow](../agents/ai-assisted-design-workflow.md)
> currently relies on the user describing geometry by eye or from memory.
> This phase closes the loop: open any existing SolidWorks part,
> read its structure programmatically, and reconstruct it on a fresh document
> using agent-generated tool calls — with pass/fail validation at the end.

**Problem it solves**: Today, if you hand an engineer a legacy `.SLDPRT` file and say
"recreate this for a different material or tolerance," they open it, memorise the feature tree,
close it, and start over manually. This phase automates that loop entirely.

#### 5A. Feature Tree Reader

- [ ] New MCP tool: `read_feature_tree_structured` — returns typed feature data
  (feature type, sketch plane, dimension names and values, mate types for assemblies)
- [ ] New MCP tool: `read_sketch_geometry` — returns all entities from a named sketch
  (lines, arcs, circles, splines with coordinates)
- [ ] Integration with `list_features`, `get_dimension`, `get_mass_properties`
  into a single `capture_part_state` workflow call

#### 5B. Reconstruction Agent Integration

- [ ] `solidworks-part-reconstructor` agent accepts structured feature-tree JSON
  (not just text descriptions) and emits a typed `ReconstructionPlan`
- [ ] `ReconstructionPlan` schema includes VBA-boundary flags so the executor
  knows which steps need `generate_vba_part_modeling`
- [ ] Agent CLI flag: `--from-part <path>` — automatically runs `capture_part_state`,
  feeds it to the reconstructor, and saves the plan to `.solidworks_mcp/plans/`

#### 5C. Validation Pipeline

- [ ] After reconstruction, run `get_mass_properties()` on both parts and compare:
  volume within 1%, mass within 1%, centre-of-mass within 5 mm
- [ ] `screenshot-equivalence` pixel-diff at matching camera orientations:
  < 5% difference = pass
- [ ] Feature tree structural comparison: same feature count, same types, same order
- [ ] Automated test fixture in `tests/test_reverse_engineering_pipeline.py`
  using the SolidWorks 2026 sample parts as ground truth

**Milestone**: End of Q2 2027 — any sample part in
`C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\`
can be fully reconstructed from its own data with ≥ 90% validation pass rate.

**Why sample parts first**: Because the finished `.SLDPRT` exists alongside the reconstruction
target, they are a labelled dataset — we know the correct answer.
Once the pipeline passes on all tier-1 and tier-2 samples,
it can be applied to proprietary legacy parts with the same confidence.

---

## Detailed Phase Dependencies

Note: All timelines and estimates are guesses as this is research, and
it's hard to know what will work and what will require more engineering
time, most importantly this is a side project of mine.


```
┌─────────────────────────────────────────────────────────────┐
│ Q2 2026: Foundation & Bug Fixes (4 weeks)                  │
│ • Python 3.14 compatibility ✅                              │
│ • Unified startup ✅                                        │
│ • API help search ✅                                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
   │ GUI Research│    │ DB Research  │    │ AI Research  │
   │   (3-4 wks) │    │   (3-4 wks)  │    │  (2-3 wks)   │
   └─────────────┘    └──────────────┘    └──────────────┘
        ↓                     ↓                     ↓
   ┌─────────────────────────────────────────────────────┐
   │ Q3 2026: MVP Development (12 weeks)                │
   │ • Dashboard (4w)                                    │
   │ • Database (4w)                                     │
   │ • Agent Core (4w)                                   │
   └─────────────────────────────────────────────────────┘
        ↓
   ┌─────────────────────────────────────────────────────┐
   │ Q4 2026: Integration & Polish (12 weeks)           │
   │ • Copilot Integration (4w)                          │
   │ • Templating (3w)                                   │
   │ • Agent Features (3w)                               │
   │ • Export/Scripting (2w)                             │
   └─────────────────────────────────────────────────────┘
        ↓
   ┌─────────────────────────────────────────────────────┐
   │ Q1 2027: Enhanced Features (12 weeks)              │
   │ • Undo/Redo (3w)                                    │
   │ • LangChain (4w)                                    │
   │ • Collaboration (3w)                                │
   │ • Optimization (2w)                                 │
   └─────────────────────────────────────────────────────┘
```

## Cross-Plan Integration Points

### GUI Dashboard ↔ Database System

- Display workflow history from database
- One-click save workflow as template
- Show execution timeline from operation log

### Database System ↔ Agent

- Agent uses workflow templates for multi-step planning
- Agent auto-creates templates from successful sequences
- Agent learns from operation success rates

### Agent ↔ Copilot

- Copilot commands → Agent planning → MCP execution
- Agent suggestions → Copilot inline display
- User feedback → Agent learning

### All ↔ Export/Scripting

- Dashboard can export to Python/VBA
- Templates generate executable scripts
- Agent reasoning becomes code documentation

## Key Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| GUI Framework | FastMCP Web (primary) | Modern, built on MCP ecosystem |
| Database | SQLModel + SQLite | Simple, portable, async-friendly |
| Agent Framework | PydanticAI | Type-safe, composable, Claude-native |
| LLM Integration | Claude 3.5 Sonnet | Best for complex reasoning, code |
| Export Target | Python + VBA | Covers CLI and in-SolidWorks scripting |
| Visualization | WebSocket streaming | Real-time, low-latency feedback |

## Resource Allocation

### Team Composition (Estimated for full delivery)

- **Backend Engineer**: 2.5 FTE (API, MCP integration, database)
- **Frontend Engineer**: 1.5 FTE (Dashboard, Copilot extension)
- **AI/ML Engineer**: 1 FTE (Agent, optimization, learning)
- **DevOps/Infrastructure**: 0.5 FTE (Testing, deployment, monitoring)

**Total**: ~5.5 FTE over 12 months

### Effort Estimate by Phase

| Phase | Weeks | Effort | Notes |
|-------|-------|--------|-------|
| Research & Spikes | 6-8 | 2.5 FTE | Parallel work possible |
| MVP Development | 12 | 3 FTE | Dashboard + DB + Agent |
| Integration & Polish | 12 | 3 FTE | Copilot + Templates + Export |
| Enhanced Features | 12 | 2.5 FTE | Advanced features + optimization |

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|-----------|
| FastMCP immaturity | High | Medium | Have VS Code Webview backup plan ready |
| COM blocking in async | High | Low | Worker thread strategy documented |
| Copilot API changes | Medium | Medium | Abstract API layer, flexibility in design |
| Agent hallucination | High | Medium | Strict validation, tool metadata guardrails |
| DB performance degradation | Medium | Low | Partitioning, archival strategy from start |
| User adoption | Medium | Low | Strong UX, good documentation, examples |

## Success Metrics

### MVP (End of Q3)

- ✅ Dashboard loads without context-switch
- ✅ Can replay 3-step workflow
- ✅ Agent plans and executes 5-step workflow autonomously
- ✅ Database captures all operations
- ✅ Crash recovery works for last checkpoint

### V1 (End of Q4)

- ✅ Copilot integration working
- ✅ Template creation & reuse working
- ✅ Python/VBA export generates correct code
- ✅ Agent success rate > 85% on standard workflows
- ✅ User satisfaction > 4/5 stars

### V2 (End of Q1 2027)

- ✅ Full undo/redo tree operational
- ✅ LangChain multi-agent patterns work
- ✅ Team collaboration features operational
- ✅ Performance metrics show <200ms tool execution
- ✅ Workflow marketplace has 50+ templates

## Documentation Plan

### New Files to Create

```
docs/
├── PLAN_GUI_VISUALIZATION.md          (research & MVP plan)
├── PLAN_DATABASE_WORKFLOWS.md         (data model & recovery)
├── PLAN_PYDANTIC_AI_INTEGRATION.md    (agent architecture)
├── ROADMAP_2026_2027.md              (this file)
├── user-guide/
│   ├── agent-basics.md
│   ├── agent-workflows.md
│   ├── agent-best-practices.md
│   ├── dashboard-guide.md
│   ├── workflow-templates.md
│   └── examples/
│       ├── simple-bracket.md
│       ├── assembly.md
│       ├── drawing-package.md
│       └── batch-export.md
├── developer-guide/
│   ├── agent-architecture.md
│   ├── tool-integration.md
│   ├── database-schema.md
│   └── copilot-integration.md
└── architecture/
    ├── agent-design.md
    ├── dashboard-architecture.md
    └── data-flow.md
```

### Example Creation

- [ ] Simple bracket workflow (basic agent test)
- [ ] Assembly with mates (intermediate)
- [ ] Drawing package with batch export (advanced)
- [ ] Template creation & reuse (workflow management)
- [ ] Multi-step design with optimization (agent learning)

## Go/No-Go Decision Points

### After Phase 1 (End of 8 weeks)

**Question**: Can we build a viable MVP with this architecture?

- GUI prototype performing well? → Go
- Database design sound? → Go
- Agent proof-of-concept successful? → Go
- Any showstoppers? → No-go reevaluate

### After MVP (End of Q3)

**Question**: Is user experience compelling?

- Dashboard eliminates context-switching pain? → Go to integration
- Replay/recovery works reliably? → Go
- Agent success rate > 80%? → Go
- Otherwise: → Pivot or extend Q3

### Before v2 (End of Q4)

**Question**: Is Copilot integration stable?

- Chat commands work reliably? → Go to advanced
- No conflicting updates from VS Code? → Go
- User feedback positive? → Go
- Otherwise: → Extend Q4 or adjust roadmap

## Contingency Plans

### If FastMCP not suitable

→ Pivot to VS Code Webview approach
→ Same feature set, different UI framework
→ Timeline impact: +2-3 weeks

### If Agent complexity too high

→ Start with simpler command-coordination approach
→ Add learning/optimization in Phase 2
→ Timeline impact: -2 weeks Phase 1, +2 weeks Phase 2

### If Copilot integration blocked

→ Focus on standalone dashboard
→ Defer integration to Phase 3+
→ Timeline impact: -1 week Phase 2, same overall impact

## Next Immediate Steps

1. **Week 1**: Assign research spikes
   - Frontend engineer: FastMCP capabilities
   - Backend engineer: SQLModel + SQLite testing
   - AI engineer: PydanticAI + MCP tool integration

2. **Week 2-3**: Spike results & decisions
   - Technology choice confirmations
   - Proof-of-concept code reviews
   - Risk assessment updates

3. **Week 4**: Kick off MVP sprints
   - Detailed backlog creation
   - Team onboarding
   - Development environment setup

4. **Weekly**: Progress tracking
   - Standup meetings
   - Risk register updates
   - Stakeholder communication

---

**Document Version**: 1.0
**Last Updated**: 2026-03-27
**Status**: Planning Phase Complete, Ready for Research Spikes
