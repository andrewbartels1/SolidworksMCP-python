# Research: measuring whether a skill improves the agent (#207)

Tabled on 2026-11-09, by the maintainer's decision. The skill work in #207 needs
research before it can become an OpenSpec change. This note records why and
what the research has to answer, so the work can restart from here.

## Why it's tabled

The one measurement so far (#207) found that the skill changed *how* the agent
worked, not *what* it built. Running the comparison again with a different
skill won't show more on its own:

- One U-joint run takes over 20 minutes and about 400k output tokens, and each
  arm needs several runs before a difference means anything.
- There's no harness to run the sessions, collect their tool calls and score
  the results. Comparing many prompt or skill variants would mean building one,
  and that harness is effectively a small framework of its own.
- "Better" isn't defined yet. Without a definition, a run can't pass or fail.

## Questions the research has to answer

### 1. What does "better" or "more robust" mean?

These are candidate measures. They can disagree with one another, so the
research has to pick which matter and how to weigh them:

- **Result quality:** do the parts match the answer key (volumes, bounding
  boxes, mates, motion)? This is the measure #207 says counts most.
- **Fewer tool calls:** less work for the same result.
- **Time and tokens:** wall-clock time and output tokens per finished model.
- **Tool choice:** did the agent pick the right tool the first time, or reach
  a result through workarounds (for example, building planes from angle and
  perpendicular pairs)?
- **Planning:** did it plan the build before calling tools? Did it replan
  after an error rather than repeat it? Did it check its work (`verify_model`)
  at sensible points?
- **Failures:** how many calls errored, how many errors repeated, and did any
  leave the model in a broken state?
- **Robustness:** how much the result varies across runs of the same arm, and
  across models and effort levels.

### 2. How do we run it?

- A harness that runs N sessions per arm (with and without the skill, or with
  skill A and skill B). It has to record the model, the effort level, every
  tool call with its result, the time and the tokens.
- A scorer that grades each session against the answer key in
  `tests/live/data/ujoint/` and against the measures chosen in question 1.
- Whether shorter prompts (one part, one sub-assembly) can stand in for the
  full U-joint. Short prompts would make many runs affordable; the open
  question is whether their results predict the full build.
- Whether tool calls can be optimised offline. One option is to replay
  recorded sessions against the mock adapter, so prompt variants are compared
  without SolidWorks. The research has to say what that misses: the mock has
  no geometry.

### 3. What could a skill teach that the tools don't?

From #207: mates that leave motion free, recipes for reference geometry,
sheet-metal and thin-plate features, design-intent checks, and when to stop
and ask about an ambiguous spec. Each is a hypothesis for the harness to
test, not a skill to write yet.

## Before restarting

Read the current literature and tooling on evaluating agents and tool use
(agent benchmarks, trajectory scoring, LLM-as-judge for planning quality), and
what others measure when they compare prompts or skills. Then turn questions
1 and 2 into an OpenSpec change for the harness. Write the skills after that.
