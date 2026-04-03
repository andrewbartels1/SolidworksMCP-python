# GUI Visualization Integration Plan

## Update (April 2026): Decision-Card Interaction Direction

In addition to the existing dashboard goals, the preferred interaction pattern is now explicit "pre-baked choice" cards so users can quickly branch design decisions without writing long prompts.

Priority card types:

1. Hinge selector card (ball-bearing, concealed, piano, living hinge)
2. Sourcing card (McMaster-Carr vs commodity online alternatives)
3. Printability card (orientation face, support burden, weak-axis risk)
4. Build-volume card (fits vs split strategy)

Each card should emit typed JSON that can be logged to SQLite and reused in follow-up prompts.

**Objective**: Create a unified interface that allows users to interact with LLM-driven SolidWorks automation without constant context-switching between the text prompt and SolidWorks CAD environment.

## Problem Statement

Current workflow requires users to:

1. Write prompts/commands in LLM interface
2. Switch to SolidWorks to see results
3. Return to LLM to adjust or continue
4. Repeat

This creates friction and breaks the flow of design iteration.

## Research Phase: Technology Options

### 1. **FastMCP + Web Dashboard** (Recommended for MVP)

- **Pros**:
  - FastMCP already in project roadmap
  - FastMCP provides automatic HTTP endpoints for MCP tools
  - Web UI can run in browser tab alongside VS Code
  - No additional window management needed
- **Cons**:
  - FastMCP is relatively new, limited ecosystem
  - Need to build custom UI components

   **Investigation needed**:

- Evaluate `fastmcp` package capabilities for auto-generating tool UIs
- Check if `fastmcp[web]` extra exists (newer versions)
- Estimate UI development effort for tool parameter forms
- Test WebSocket support for real-time feedback

### 2. **VS Code Extension with Webview**

- **Pros**:
  - Integrated directly in editor
  - Can use VS Code Copilot inline
  - No extra browser windows needed
    - Existing extension framework well-documented
- **Cons**:
  - Separate extension development
  - Cannot directly embed SolidWorks preview

   **Investigation needed**:

- Review VS Code Webview API for panel integration
- Plan how to display SolidWorks rendering/preview
- Could use screenshot streaming or viewport sharing

### 3. **Electron App + SolidWorks COM Bridge**

- **Pros**:
  - Desktop app with native look/feel
  - Can create custom visualization
  - Full control over UI/UX
- **Cons**:
  - Significant development effort
  - Cross-platform complexity
  - Duplicate COM bridge logic

   **Investigation needed**:
     - Evaluate Electron + Python subprocess model
     - Plan IPC communication layer

### 4. **Python GUI with Tkinter/PyQt + Rendering**

- **Pros**:
  - Single language (Python)
  - Can embed SolidWorks through COM
  - No build system complexity
- **Cons**:
  - Limited modern GUI capabilities
  - Cross-platform UI polish required

   **Investigation needed**:
     - Can PyQt6 embed SolidWorks HWND?
     - Performance impact of COM integration in GUI thread

## Recommended MVP Approach

### **Option A: FastMCP Web Dashboard (2-3 weeks)**

1. **Phase 1: Research & Prototype** (1 week)
   - Test FastMCP web capabilities
   - Build minimal proof-of-concept dashboard
   - Verify tool introspection works

2. **Phase 2: Core UI** (1 week)
   - Auto-generate tool parameter forms from Pydantic schemas
   - Create command queue/history panel
   - Implement real-time result display

3. **Phase 3: Visualization** (1 week)
   - Screenshot capture from SolidWorks
   - Display in dashboard with refresh timer
   - Add basic 3D preview (maybe pre-rendered models)

### **Option B: VS Code Webview + Copilot** (3-4 weeks)

1. Create side panel in VS Code
2. Embed live MCP tool browser
3. Show Copilot inline prompting
4. Stream SolidWorks screenshots for preview

## Implementation Details

### UI Components Needed

```
Dashboard Layout:
┌─────────────────────────┬──────────────────┐
│   LLM Output Panel      │  SolidWorks View │
│   (streaming text)      │  (screenshot)    │
├─────────────────────────┤                  │
│   Command Builder       │                  │
│   (form from schema)    │                  │
├─────────────────────────┴──────────────────┤
│   Command History & Results                │
│   (tree view of executed commands)         │
└─────────────────────────────────────────────┘
```

### Data Flow Architecture

```
LLM (Claude/GPT)
     ↓
VS Code Copilot / Chat UI
     ↓
MCP Tool Registry (FastMCP)
     ↓
SolidWorks MCP Server
     ↓
SolidWorks COM Adapter
     ↓
SolidWorks Application
     ↓ (screenshot/state)
Dashboard Rendering
```

### Real-time Feedback Loop

- MCP tool execution → result JSON
- Stream results to dashboard
- Poll SolidWorks state every 2-5 seconds
- Update preview image
- Display status/errors

## Visualization Enhancements

### Short-term (MVP)

- Live screenshot of SolidWorks viewport
- Command history tree
- Parameter form UI from Pydantic schema
- Status indicators (running/success/error)

### Medium-term (v2)

- 3D model preview (exported glTF/step from SolidWorks)
- Execution timeline with undo/redo
- Batch command queue with visual representation
- Performance profiling for long-running tasks

### Long-term (v3+)

- AI-assisted parameter suggestions
- Visual command builder (drag-drop feature components)
- Gesture recording and macro creation
- Multi-user collaboration view

## Tech Stack Recommendation

### FastMCP Dashboard Approach

```
Frontend:
- React 18 + TypeScript
- Tailwind CSS for styling
- Socket.io for real-time updates
- Three.js for 3D preview (future)

Backend:
- FastMCP (serves HTTP endpoints)
- Python async task runner for screenshots
- WebSocket bridge for streaming

Deployment:
- Bundled in project docs/web folder
- Served by FastMCP dev server on :8001
- Accessible at http://localhost:8001/dashboard
```

## Success Criteria

✅ **MVP Pass** (4 weeks)

- [ ] Dashboard loads and shows available tools
- [ ] Can execute one tool through UI and see result
- [ ] SolidWorks screenshot displays in dashboard
- [ ] Command history shows executed commands
- [ ] No context-switching required for basic workflow

✅ **V1 Ready** (8 weeks)

- [ ] All tools have auto-generated parameter forms
- [ ] Real-time feedback from executed commands
- [ ] Persistent history across sessions
- [ ] Error handling and user feedback
- [ ] Basic batch command queuing

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| FastMCP immaturity | High | Have VS Code extension backup plan |
| Screenshot latency | Medium | Cache strategy, async updates |
| SolidWorks COM blocking | High | Run COM in worker thread, async wrapper |
| User expectation mismatch | Medium | Clear UI indicators, tooltips |

## Next Steps

1. **Week 1**: Spike on FastMCP capabilities
   - Test `fastmcp` web features
   - Create hello-world dashboard
   - Measure screenshot latency

2. **Week 2**: Spike on VS Code Webview as alternative
   - Prototype panel layout
   - Test Copilot integration
   - Compare complexity

3. **Week 3**: Decision & start MVP based on spike results

4. **Week 4+**: Incremental development with user feedback
