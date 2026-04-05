# Interactive Design Foundation Plan

## Objective

Build a reliable human-in-the-loop SolidWorks design workflow where an LLM can:

- inspect an existing part, screenshot, or mock-up drawing
- retrieve the right CAD knowledge instead of guessing
- classify the feature family before building
- propose a sequence the human can critique and refine
- execute only after the workflow is grounded in evidence
- learn from failures so the system improves across parts and users

This is explicitly **not** a one-off “LLM drives SolidWorks” demo. The goal is a reusable foundation for others.

---

## Problem Statement

The Paper Airplane failure exposed three root issues:

1. Visual similarity is not enough. A sheet metal airplane and a flat plate silhouette can look similar in one view while requiring completely different feature sequences.
2. Raw tool access is not enough. An LLM can call `create_sketch` and `create_extrusion`, but still misunderstand the modeling root and produce the wrong dependency chain.
3. Docs-only guidance is not enough. We need code-backed classification, retrieval, and evaluation, not just hand-written prompt advice.

The system must learn the difference between:

- “looks like a bat, so revolve is likely correct”
- “looks like a thin plate, but the feature tree proves it is sheet metal”
- “looks like an assembly, so part-level modeling should stop and assembly planning should begin”

---

## Research Takeaways

### Retrieval-Augmented Generation (Lewis et al., 2020)

The main practical takeaway is that parametric LLM memory is not enough for knowledge-intensive tasks. For SolidWorks, that means the model should retrieve from explicit sources rather than rely on latent memory for API signatures, feature-order rules, or CAD best practices.

Applied here:

- keep a dense and indexable knowledge base of API docs, worked examples, failure patterns, and sample-part audits
- retrieve the most relevant evidence at planning time
- include provenance in the answer so the human can inspect why the plan was chosen

Source:

- `Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks` — <https://arxiv.org/abs/2005.11401>

### ReAct (Yao et al., 2022)

The main practical takeaway is that reasoning and acting should be interleaved. In our setting, the model should alternate between thought and observation:

- think: “This might be a revolve family”
- act: call `list_features`, `get_mass_properties`, `classify_feature_tree`
- observe: revise the plan from the returned evidence

That is better than either pure chain-of-thought or pure tool execution.

Applied here:

- use inspect-classify-delegate loops instead of “generate a full plan from one prompt”
- keep agent trajectories reviewable by the human
- make failure recovery editable at the reasoning step, not only after geometry is already wrong

Sources:

- `ReAct: Synergizing Reasoning and Acting in Language Models` — <https://arxiv.org/abs/2210.03629>
- project page — <https://react-lm.github.io/>

### SketchGraphs (Seff et al., 2020)

The main practical takeaway is that CAD sketches are not just images. They are relational geometry graphs: entities plus constraints plus downstream construction meaning. That supports a design where we index and reason over structured geometry instead of only screenshots and prose.

Applied here:

- store sketches and feature trees as structured records, not just text blobs
- treat lines, arcs, dimensions, constraints, planes, and parent-child relationships as retrieval targets
- use graph-like evidence to classify families and suggest missing constraints

Source:

- `SketchGraphs: A Large-Scale Dataset for Modeling Relational Geometry in Computer-Aided Design` — <https://arxiv.org/abs/2007.08506>

---

## Foundation Principles

1. Read before write.
2. Classify before plan.
3. Retrieve before guess.
4. Keep the human in the loop at decision boundaries.
5. Evaluate on real sample parts and practical print-ready parts.
6. Preserve provenance so users can inspect why the system chose a path.

---

## Proposed System Architecture

```text
User image / part / drawing
        ↓
Observation pass
  - open_model / image upload
  - get_model_info
  - list_features
  - get_mass_properties
  - classify_feature_tree
        ↓
Knowledge retrieval
  - API docs
  - sample-part audits
  - tool docs
  - error-memory database
  - video transcript chunks
        ↓
Interactive planning
  - propose family
  - explain evidence
  - present next 3–10 steps
  - human approves or corrects
        ↓
Execution
  - direct MCP or VBA-backed workflow
        ↓
Verification
  - feature-family match
  - mass properties
  - image equivalence
  - user review
        ↓
Memory
  - save failures, corrections, good plans, and demo artifacts
```

---

## Knowledge Base Design

### Tier 1 — Structured Local Evidence

This should be the highest-priority retrieval source because it is closest to the actual SolidWorks environment.

- API signatures and tool docs from the repo and generated SolidWorks docs index
- feature-tree snapshots from sample parts
- mass-property snapshots and image exports from validated runs
- tool failure catalog from `.solidworks_mcp/agent_memory.sqlite3`
- prompt/plan pairs that successfully rebuilt known parts

### Tier 2 — Semi-Structured Learning Assets

- docs pages in this repo
- how-to guides written around real sample parts
- macro snippets and VBA generation examples
- evaluation notes from integration runs

### Tier 3 — External Instructional Content

- SolidWorks how-to video transcripts
- blog/tutorial text chunks about specific feature families
- external CAD best-practice notes for sheet metal, assemblies, and printability

For videos, do not index the raw video URL as one chunk. Build an index of:

- transcript chunk
- inferred operation type
- linked feature family
- timestamp range
- screenshot or slide thumbnail if available

That makes retrieval action-oriented instead of “generic video search”.

---

## Retrieval Strategy

Use hybrid retrieval, not embeddings alone.

### What to index

- exact API names: `FeatureRevolve2`, `FeatureExtrusion3`, `Base-Flange`, `Sketched Bend`
- repo tool names: `list_features`, `classify_feature_tree`, `generate_vba_part_modeling`
- feature-family tags: `revolve`, `extrude`, `sheet_metal`, `assembly`, `advanced_solid`
- part-domain tags: `baseball_bat`, `u_joint`, `sprinkler`, `bracket`, `enclosure`

### Retrieval modes

1. lexical lookup for exact tool/API names
2. embedding search for conceptual similarity
3. graph/metadata filtering for feature families and document types
4. failure-memory lookup for known tool mistakes

### Retrieval outputs

Every planning cycle should return:

- top evidence used
- why it was selected
- confidence level
- any contradictory evidence

---

## Interactive Human-LLM Design Loop

### Phase A — Observe

If the original model exists:

- `open_model`
- `get_model_info`
- `list_features(include_suppressed=True)`
- `get_mass_properties`
- `classify_feature_tree`

If only an image exists:

- describe the geometry provisionally
- explicitly mark the result as provisional
- retrieve similar feature-family examples from the knowledge base
- ask the human for one correction or confirmation before build planning

### Phase B — Classify

Output should be concise and inspectable:

- likely family
- confidence
- evidence
- warnings
- recommended workflow

### Phase C — Plan Together

The plan should be incremental, not monolithic.

Good:

- “I think this is a revolve family with medium confidence. Here are the first four steps and what evidence they depend on.”

Bad:

- “Here is a 20-step build plan” before the modeling root is agreed.

### Phase D — Execute Conservatively

Execute only after:

- the family is accepted
- the modeling root is accepted
- unsupported features are clearly routed to VBA or deferred

### Phase E — Verify and Learn

Capture:

- final family
- whether the classifier was right
- which retrieval items were useful
- which user correction mattered most
- which tool call or assumption failed

---

## Data Models We Should Add

### `FeatureTreeSnapshot`

- document type
- active configuration
- feature list
- evidence confidence

### `FeatureFamilyClassification`

- family
- confidence
- evidence
- warnings
- recommended workflow

### `DesignIntentSession`

- user goal
- retrieved evidence
- accepted classification
- accepted plan checkpoints
- execution results
- human corrections

### `RetrievalEvidence`

- source type
- source id/path/url
- chunk text or structured data
- relevance score
- why selected

---

## Evaluation Plan

We should not call this successful until it passes a repeatable eval set.

### Evaluation dimensions

1. family classification accuracy
2. correct delegation path accuracy
3. first-feature correctness
4. parent-child dependency preservation
5. tool-call success rate
6. human correction count before first valid build

### Suggested benchmark set

#### Easier / should work first

- Baseball Bat
- U-Joint Pin
- simple bracket
- print-ready battery cover or snap-fit enclosure

#### Intermediate

- U-Joint yoke or spider
- garden trowel approximation with explicit VBA boundary
- revolve + cut combinations

#### Advanced

- Paper Airplane sheet metal workflow
- Sprinkler sub-parts
- full U-Joint assembly

---

## Demo Roadmap

### Demo 1 — Baseball Bat

Why first:

- clear revolve family
- easy to inspect manually
- direct MCP path exists
- good example of “classifier confidence high, direct MCP okay”

### Demo 2 — U-Joint Pin or Yoke

Why next:

- introduces more geometric ambiguity
- still bounded enough for interactive planning

### Demo 3 — Practical 3D-Printed Part

Recommended practical candidate:

- mounting bracket
- snap-fit battery cover
- Raspberry Pi enclosure lid or hinge

These are useful because they combine CAD correctness with printability and are easier to explain to users than some SolidWorks sample-library parts.

### Demo 4 — Sprinkler or Full U-Joint

Why later:

- good stress test for assembly planning
- valuable as a showcase once the foundation is stable

---

## Implementation Phases

### Phase 1 — Grounding and Delegation

- dedicated feature-tree reconstruction prompt or skill
- code-backed feature-family classifier around `list_features`
- docs updated to teach inspect-classify-delegate
- Baseball Bat walkthrough migrated to the new flow

### Phase 2 — Structured Capture

- `capture_part_state` workflow
- structured feature-tree JSON
- named-sketch geometry read tools
- eval fixtures for sample parts

### Phase 3 — Knowledge Base

- local retrieval index over docs, audits, failures, and tool docs
- video transcript ingestion with timestamps and operation tags
- source provenance shown in agent answers

### Phase 4 — Interactive Design Sessions

- persistent `DesignIntentSession` memory
- user correction tracking
- critique-and-replan loop
- executable checkpoint plans instead of one-shot plans

---

## Immediate Next Steps

These are the concrete next steps to execute now:

1. Add a dedicated feature-tree reconstruction skill or prompt so the main agent can invoke the same inspect-classify-delegate workflow with less ambiguity.
2. Update the docs nav and any remaining sample/tutorial pages that still assume silhouette-first reconstruction.
3. Build a small structured “feature family classifier” helper around `list_features` so delegation can become code-backed instead of doc-backed.

Additional near-term steps:

1. Add `capture_part_state` as a first-class workflow target in the roadmap and tooling plans.
2. Build a small benchmark set around Baseball Bat, U-Joint Pin, Paper Airplane, and one practical print-ready part.
3. Start indexing validated feature-tree audits and failure remediations as the first local retrieval corpus.
4. Prototype transcript ingestion for a small number of SolidWorks how-to videos, indexed by operation type and feature family instead of by whole-video blobs.

---

## Success Criteria

We should consider the foundation solid when:

- the agent can classify the correct family for the benchmark set with high accuracy
- the human can see the evidence behind the chosen workflow
- simpler parts like Baseball Bat and U-Joint Pin can be rebuilt through an inspect-classify-delegate loop with minimal correction
- complex parts like Paper Airplane fail safely into “inspect more” or “VBA-backed sheet metal plan” instead of producing confidently wrong geometry
- the same foundation can support both sample-part reconstruction and practical 3D-printable design sessions
