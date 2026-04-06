# Pydantic-AI Agent Integration Plan

## Current Baseline (April 2026)

The repository now includes a starter harness in `src/solidworks_mcp/agents/`:

- `harness.py` for model invocation + typed output validation
- `schemas.py` for reusable response schemas
- `history_db.py` for local SQLite run/error memory
- `smoke_test.py` for command-line prompt tests

This baseline supports fast iteration on custom `.agent.md` files while validating structured outputs and preserving error history.

## Immediate Usage Pattern

1. Select a workspace agent file from `.github/agents/`
2. Choose schema (`manufacturability` or `docs`)
3. Run `python -m solidworks_mcp.agents.smoke_test ...`
4. Review structured JSON output
5. Inspect `.solidworks_mcp/agent_memory.sqlite3` for failures and remediation guidance

**Objective**: Build an intelligent, context-aware SolidWorks agent using PydanticAI that understands design intent, coordinates multi-step operations, and learns from user patterns.

## Problem Statement

Current workflow:
- User must manually sequence MCP tool calls
- No design intent understanding
- Difficult error recovery without guidance
- No learning from past interactions
- Cannot auto-suggest better approaches

Desired workflow:
- User describes design goal in English
- Agent understands intent, suggests optimizations
- Agent coordinates multi-step operations autonomously
- Agent learns from success/failure patterns
- Agent integrates seamlessly with VS Code Copilot

## Architecture Overview

```
User (Design Intent)
     ↓
VS Code Copilot / Claude Code
     ↓
PydanticAI Agent
├─ Tool Registry (MCP tools)
├─ Context Memory (past commands, patterns)
├─ Design Knowledge (rules, best practices)
└─ Self-correction & Planning
     ↓
MCP Server (Tool Execution)
     ↓
SolidWorks COM Adapter
```

## Agent Design

### 1. Core Agent Components

#### Agent Definition (PydanticAI)
```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import ModelMessage
from solidworks_mcp.tools import MCPToolRegistry

class SolidWorksDesignAgent(Agent):
    """
    Multi-step SolidWorks design agent with design intent understanding,
    tool coordination, and learning capabilities.
    """
    
    def __init__(self, model: str = "claude-3-5-sonnet"):
        super().__init__(
            model=model,
            system_prompt=DESIGN_SYSTEM_PROMPT,
            tools=[...],  # Dynamically loaded from MCP registry
        )
```

#### System Prompt Pattern
```
You are an expert SolidWorks design engineer and MCP agent.

Your capabilities:
1. Understand high-level design intent
2. Decompose designs into sequential steps
3. Execute MCP tools with proper parameters
4. Validate intermediate results
5. Provide design guidance and optimization suggestions

When the user describes a design goal:
1. Ask clarifying questions if needed
2. Outline your step-by-step approach
3. Execute each step with explanations
4. Validate results and suggest improvements
5. Provide alternative approaches

Design guidelines:
- Always consider tolerances and material properties
- Optimize for manufacturability
- Suggest appropriate feature order
- Recommend standard sizes when applicable
- Flag potential issues early

On errors:
- Explain what went wrong
- Suggest recovery options
- Provide manual workaround if needed
- Learn from failure for future attempts
```

### 2. Tool Registration & Adaptation

#### Dynamic Tool Loading

```python
def load_mcp_tools(agent: Agent, mcp_server: MCP):
    """Load all available MCP tools into the agent"""
    
    for tool_def in mcp_server.list_tools():
        pydantic_agent_tool = PydanticAgentToolAdapter(
            name=tool_def.name,
            description=tool_def.description,
            input_schema=tool_def.input_schema,
            func=mcp_tool_executor(tool_def),
        )
        agent.add_tool(pydantic_agent_tool)
```

#### Tool Metadata Enrichment

```python
class MCPToolMetadata:
    """Enhanced metadata for agent reasoning"""
    
    primary_category: str  # "modeling | sketching | drawing | export | analysis"
    prerequisites: list[str]  # required preceding operations
    post_conditions: list[str]  # features created as result
    estimated_duration: float  # seconds
    reversibility: str  # "reversible | non-reversible | checkpoint_needed"
    common_errors: dict[str, str]  # error patterns & solutions
    design_best_practices: list[str]
    
    # Example for create_extrusion:
    prerequisites = ["create_sketch"]
    post_conditions = ["has_solid_body"]
    reversibility = "checkpoint_needed"
    common_errors = {
        "sketch_not_closed": "Ensure sketch geometry is fully defined...",
        "invalid_profile": "Sketch must form valid closed profile..."
    }
```

### 3. Context & Memory System

#### Execution Context

```python
class SolidWorksContext:
    """Maintains agent context during operation"""
    
    # Current model state
    active_model: str  # file path
    active_document_type: str  # "part | assembly | drawing"
    feature_tree: dict  # cached tree structure
    last_sketch_name: str | None
    last_feature_name: str | None
    
    # Session history
    operations_executed: list[dict]  # full history
    operations_successful: int
    operations_failed: int
    error_patterns: dict[str, int]  # frequency tracking
    
    # User preferences & patterns
    preferred_materials: list[str]
    preferred_tolerances: dict
    past_workflows: list[str]  # used workflow templates
    
    # Performance metrics
    total_execution_time: float
    average_tool_duration: dict[str, float]
```

#### Memory Store (SQLModel + SQLite)
```python
class AgentMemory(Base):
    """Persistent memory for agent learning"""
    
    interaction_id: UUID
    user_query: str
    agent_plan: str
    operations_executed: list[str]
    success: bool
    elapsed_time: float
    user_rating: int | None  # 1-5 star feedback
    lessons_learned: list[str]
    optimization_suggestions: list[str]
    created_at: datetime
    
    # Metadata for pattern learning
    design_category: str  # "bracket | assembly | drawing | etc"
    complexity_score: float  # 1-10
    reusable_as_template: bool
```

### 4. Agent Capabilities

#### A. Design Planning
```python
@agent.tool()
async def plan_design_approach(
    design_brief: str,
    constraints: dict,
    material: str = "Steel",
) -> dict:
    """
    Agent analyzes design goal and generates step-by-step plan.
    
    Returns:
    {
        "approach": "...",
        "estimated_steps": [
            {"step": 1, "action": "create_part", "rationale": "..."},
            {"step": 2, "action": "create_sketch", "rationale": "..."},
            ...
        ],
        "risks": [...],
        "alternatives": [...]
    }
    """
```

#### B. Error Recovery & Self-Correction
```python
async def handle_tool_error(
    tool_name: str,
    input_params: dict,
    error: Exception,
    context: SolidWorksContext
) -> dict:
    """
    Agent suggests recovery when a tool fails.
    
    Strategies:
    1. Check prerequisites (did previous step succeed?)
    2. Validate input parameters
    3. Suggest manual verification
    4. Offer alternative approaches
    5. Provide rollback/undo recommendations
    """
```

#### C. Design Optimization
```python
async def suggest_design_optimization(
    current_design: dict,  # feature tree, properties
    context: SolidWorksContext
) -> list[dict]:
    """
    Agent analyzes design and suggests improvements.
    
    Examples:
    - "Consider adding fillets to sharp edges for manufacturability"
    - "This geometry could use pattern to reduce redundancy"
    - "Tension analysis suggests reinforcement at stress points"
    - "Recommend moving to assembly-based design for complexity"
    """
```

#### D. Workflow Learning & Suggestions
```python
async def suggest_workflow_reuse(
    user_query: str,
    context: SolidWorksContext
) -> list[dict]:
    """
    Agent suggests applicable workflow templates from history.
    
    Returns:
    {
        "templates": [
            {
                "id": "template_123",
                "name": "Simple Bracket",
                "similarity_score": 0.87,
                "reason": "Similar geometry and constraints"
            }
        ]
    }
    """
```

## Integration Patterns

### 1. VS Code Copilot Integration

#### Approach 1: Copilot Extension with MCP
```typescript
// VS Code extension registers SolidWorks Copilot provider
vscode.commands.registerCommand(
    "solidworks.askCopilot",
    async (query: string) => {
        const response = await solidworksChatProvider.ask(query);
        // Copilot interprets and coordinates with agent
    }
);
```

#### Approach 2: Custom Chat Participant
```
@solidworks: Create a bracket with 80mm width and 3mm fillets
```
Copilot calls PydanticAI agent which:
1. Understands intent
2. Checks context (active document, preferences)
3. Plans steps
4. Executes via MCP
5. Reports results with visual feedback

### 2. LangChain Integration

#### Memory Chain for Multi-turn Conversations
```python
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory

def create_solidworks_chain():
    memory = ConversationBufferMemory(
        llm=claude,
        return_messages=True,
        memory_variables=["chat_history"]
    )
    
    chain = ConversationChain(
        llm=claude,
        memory=memory,
        prompt=SOLIDWORKS_PROMPT_TEMPLATE,
    )
    
    # Integrate PydanticAI agent as tool
    chain.add_tool(pydantic_agent.as_langchain_tool())
    
    return chain
```

#### Tool Use with LangChain
```python
from langchain.tools import StructuredTool

solidworks_toolkit = [
    StructuredTool.from_function(
        func=pydantic_agent.run_design_task,
        name="execute_design_step",
        description="Execute a design step with agent coordination"
    ),
    # ... more tools
]
```

### 3. Multi-Agent Collaboration

#### Specialized Sub-Agents (Future)
```
PydanticAI Architecture:
┌─ Main SolidWorks Agent (orchestrator)
├─ Modeling Sub-Agent (part/feature knowledge)
├─ Sketching Sub-Agent (2D geometry expertise)
├─ Drawing Sub-Agent (technical drawing rules)
├─ Assembly Sub-Agent (component coordination)
└─ Analysis Sub-Agent (simulation, inspection)
```

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-3)

**Goal**: Basic agent with MCP tool integration

**Tasks**:
1. Define `SolidWorksDesignAgent` class with PydanticAI
2. Load MCP tools dynamically into agent
3. Implement tool exec with error handling
4. Create session context tracking
5. Write integration tests

**Deliverable**:
```python
agent = SolidWorksDesignAgent()
result = await agent.run_async(
    "Create a simple bracket: 80mm width, 60mm height, 3mm fillets"
)
```

### Phase 2: Context & Memory (Weeks 4-5)

**Goal**: Agent learns and maintains state

**Tasks**:
1. Implement `SolidWorksContext` tracking
2. Create interaction memory persistent store
3. Add context awareness to system prompt
4. Implement pattern detection
5. Build memory UI (display learned patterns)

**Deliverable**:
- Agent remembers preferred materials, tolerances
- Agent suggests workflows based on past choices
- Query results include "why this approach" explanation

### Phase 3: Error Recovery & Planning (Weeks 6-7)

**Goal**: Agent can recover from failures and plan complex workflows

**Tasks**:
1. Implement error classification system
2. Add recovery strategy recommendation
3. Create design planning tool (outline steps)
4. Add validation between steps
5. Implement rollback suggestions

**Deliverable**:
- When tool fails, agent explains why
- Agent suggests fixes (check prerequisites, validate inputs)
- Agent can plan complex 5+ step designs autonomously

### Phase 4: Copilot Integration (Weeks 8-9)

**Goal**: Seamless VS Code Copilot integration

**Tasks**:
1. Create VS Code chat participant for `@solidworks`
2. Bridge Copilot → PydanticAI agent
3. Display execution progress in chat
4. Show design preview/results in panel
5. Enable feedback collection (👍/👎 on suggestions)

**Deliverable**:
- User can chat directly with Copilot about designs
- Agent executes within MCP server
- Results flow back to Copilot

### Phase 5: Advanced Features (Weeks 10-12)

**Goal**: Optimization, learning, collaboration

**Tasks**:
1. Add design optimization suggestions
2. Implement workflow template learning
3. Create agent performance dashboard
4. Add multi-language support
5. Implement collaborative features

**Deliverable**:
- Agent suggests design improvements
- Agent auto-creates templates from successful designs
- Share workflows with team

## System Prompt Template

```python
DESIGN_SYSTEM_PROMPT = """
You are an expert SolidWorks design engineer and MCP automation agent.

CAPABILITIES:
- Execute SolidWorks operations via MCP tools
- Understand design intent and specifications
- Plan complex multi-step workflows
- Validate designs and suggest improvements
- Learn from past interactions

BEST PRACTICES:
1. Always ask for clarification on ambiguous requirements
2. Prefer standard sizes and materials when not specified
3. Consider manufacturability and cost
4. Suggest appropriate feature sequencing
5. Validate sketches before extrusion
6. Add safety margins to tolerances

ERROR HANDLING:
- When tool fails: Explain the error, suggest fixes
- Validate prerequisites before running tools
- Offer alternative approaches when stuck
- Save checkpoints before risky operations

TOOL USAGE:
- Provide clear parameters
- Explain rationale for each step
- Show intermediate results
- Confirm success before proceeding

LEARNING:
- Remember user preferences (materials, tolerances, style)
- Track successful workflows for reuse
- Suggest improvements based on past successes
- Ask for feedback on suggestions

Current Context:
- Active document: {context.active_document_type}
- Active model: {context.active_model}
- Recent operations: {context.last_5_operations}
- User preferences: {context.user_preferences}
"""
```

## Key Integrations

### 1. With MCP Tools
```python
# Tool execution wrapper
async def execute_mcp_tool(
    tool_name: str,
    tool_params: dict,
    context: RunContext
) -> dict:
    """
    Execute MCP tool with context awareness and error handling
    """
    # 1. Validate prerequisites from metadata
    # 2. Enrich input with context
    # 3. Execute via MCP server
    # 4. Validate output
    # 5. Update context
    # 6. Handle errors gracefully
```

### 2. With Workflow Database (Plan_Database_Workflows.md)
- Agent records successful workflows
- Agent suggests workflow templates
- Agent creates new templates from designs
- Agent learns success patterns from history

### 3. With GUI Dashboard (Plan_GUI_Visualization.md)
- Chat interface for agent prompting
- Real-time visualization of execution
- Feedback collection on agent suggestions
- One-click save of workflows

## Documentation Updates

### New User Guide Sections
```
docs/user-guide/
├── agent-basics.md
│   └── "Getting Started with SolidWorks AI Agent"
├── agent-workflows.md
│   └── "Common Design Patterns & Workflows"
├── agent-best-practices.md
│   └── "Tips for Better AI-Assisted Design"
├── agent-integration.md
│   └── "Integrate Agent with Your Tools"
├── agent-learning.md
│   └── "How the Agent Learns from Your Designs"
└── agent-examples/
    ├── example_1_simple_bracket.md
    ├── example_2_assembly.md
    ├── example_3_drawing_package.md
    └── example_4_batch_export.md
```

### Examples in Code

**Example 1: Simple Design Request**
```python
# User: "Create a steel bracket, 80mm wide, with mounting holes"
agent = SolidWorksDesignAgent()
result = await agent.run_async(
    "Create a steel bracket, 80mm wide, with mounting holes"
)
# Agent will:
# 1. Ask about hole sizes and positions
# 2. Create part with sketch
# 3. Extrude to 15mm depth
# 4. Create mounting hole pattern
# 5. Add fillets
# 6. Export to STEP
```

**Example 2: Complex Assembly**
```python
# User: "Create a hinge assembly with pin and two leaf parts"
result = await agent.run_async(
    "Create a hinge assembly: 2 leaf parts 40x10mm, "
    "with 5mm pin, should rotate freely"
)
# Agent orchestrates:
# 1. Plan assembly structure
# 2. Create each part
# 3. Add mates for assembly
# 4. Verify rotation works
# 5. Generate technical drawings
```

**Example 3: Batch Processing**
```python
# User: "Export all recent bracket designs to STEP format"
result = await agent.run_async(
    "Export my recent bracket designs to STEP format, "
    "organized by material type"
)
# Agent will:
# 1. Identify relevant designs
# 2. Filter by material (if applicable)
# 3. Batch export with naming convention
# 4. Generate report with file paths
```

## Success Metrics

✅ **MVP** (3 weeks)
- [ ] Agent loads MCP tools successfully
- [ ] Can execute 5+ step workflows autonomously
- [ ] Error messages are helpful and actionable
- [ ] Context is preserved across multiple queries

✅ **V1** (7 weeks)
- [ ] Copilot integration works
- [ ] Agent learns from past interactions
- [ ] Optimization suggestions are generated
- [ ] 80%+ success rate on standard workflows

✅ **V2** (12 weeks)
- [ ] Multi-agent collaboration works
- [ ] LangChain integration complete
- [ ] Advanced features (batch, collaborative) work

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Agent hallucination on tool calls | High | Strict input validation, tool metadata |
| Context bloat (too much memory) | Medium | Implement memory pruning, summarization |
| Copilot integration complexity | Medium | Start simple, iterate with feedback |
| Tool execution latency kills UX | Medium | Async background execution, progress UI |

## Tech Stack

```
Backend:
- pydantic-ai (agent framework)
- langchain (optional, for multi-turn)
- sqlmodel (memory persistence)
- fastapi (for API endpoints)

Frontend:
- VS Code Chat API (Copilot integration)
- Custom webview (dashboard, progress)
- React 18 (future: advanced UI)

LLM:
- Claude 3.5 Sonnet (default)
- Fallback to local LLama via Ollama (optional)
- Locally hosted smaller models with context
```

## Timeline

```
Week 1-3:   Agent foundation + MCP integration
Week 4-5:   Context & memory system
Week 6-7:   Error recovery & planning
Week 8-9:   Copilot integration
Week 10-12: Advanced features & polish
```

Estimated effort: **12 developer-weeks**
