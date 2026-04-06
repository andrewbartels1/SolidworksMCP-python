# Agent UI Workflows (Planning)

This page outlines practical UI options for visually guiding users through agent decisions like hinge selection, sourcing, and printability checks.

## Problem to Solve

Prompt-only interaction is powerful but slows down design iteration when users need fast branching choices such as:

- Hinge family: ball-bearing, concealed, piano, living hinge
- Sourcing strategy: McMaster-Carr, local stock, commodity online
- Print strategy: orientation, split/no-split, support policy

## Recommended Interaction Patterns

## 1) FastMCP Choice Cards (MVP)

Use a local web UI that renders pre-baked option cards before generating final tool calls.

Card examples:
- Hinge type card with strength/complexity/printability scores
- Sourcing card with lead time and cost band
- Orientation card with likely support and weakness risks

Advantages:
- Fast to implement
- Easy to test with real users
- Works beside VS Code and SolidWorks

## 2) VS Code Webview Wizard

A side panel wizard that progressively asks:

1. Design intent
2. Printer/material profile
3. Joint family
4. Sourcing preference
5. Risk tolerance

Then emits a structured plan and ready-to-run prompts.

## 3) Hybrid Mode: Wizard + Prompt Console

Keep freeform chat but pair it with visual controls for key branch points.

- Visual UI decides branch options
- Prompt console keeps expert flexibility

## UX Blueprint for Prebaked Choices

- Step 1: Requirements intake (load, motion cycle, environment)
- Step 2: Candidate options list with reasons
- Step 3: Simulated outcomes (printability + sourcing)
- Step 4: Tool plan preview (MCP calls and expected artifacts)
- Step 5: Execute and log in SQLite memory

## Data Contract for UI Cards

Use a typed card payload so both UI and agents share structure:

```json
{
  "category": "hinge_choice",
  "options": [
    {
      "id": "ball_bearing_hinge",
      "label": "Ball-Bearing Hinge",
      "strength_score": 9,
      "printability_score": 5,
      "cost_band": "medium",
      "source_hint": "McMaster-Carr"
    }
  ]
}
```

## Proposed Implementation Order

1. Build FastMCP choice-card endpoint and static front-end panel.
2. Add SQLite-backed history ribbon (last 20 decisions/errors).
3. Add source recommendation module (McMaster-Carr vs alternatives).
4. Add optional VS Code webview once interaction model stabilizes.
