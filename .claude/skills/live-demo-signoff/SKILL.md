---
name: live-demo-signoff
description: Sign off a finished feature or tool with the user through short live SolidWorks demos, one at a time, each approved before the next. Use when a feature, tool or fix is implemented and unit-tested and needs the user's approval before push, PR or merge, or when the user asks to "demo", "show me it works", or "review the tools one by one".
---

# Live demo sign-off

The user approves every feature by watching it work in real SolidWorks.
Keep every step **clear, simple and concise**: one demo, one command, a short
read of the result, then wait for approval.

## 1. Before the first demo

- The unit suite passes and the work is committed (nothing pushed yet).
- Each feature has a live test in `tests/live/` that prints its proof as
  `[evidence] <label>: <payload>` lines (the tool's real response, or a
  measured value such as a volume). Write one if it is missing; a demo
  shows the real tool path an MCP client hits, plus one failure case.
- Print evidence with `tests.live.evidence.evidence(label, payload)`, never a
  bare `print`: during a demo it holds SolidWorks on each proven state
  (`SW_DEMO_HOLD_SECONDS`, set by `live_demo.ps1`), otherwise steps flash by
  and the test closes its part before the user sees it.
- List the demos in order, numbered, one line each. Show this list once.

## 2. Each demo (one at a time)

Give the user, in this order and nothing more:

1. **What it shows** in one sentence, and what to watch for in SolidWorks.
2. **The command**, ready to paste:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tests\scripts\live_demo.ps1 <tests/live/...::test_name>
   ```

3. The precondition, only on the first demo: SolidWorks open, idle, no
   documents, running 8+ minutes.

Then **stop and wait** for the user to paste the output.

## 3. Reading the result

- Say pass/fail first, then in 2-4 bullets what each `[evidence]` line
  proves (name the numbers: counts, radii, volumes).
- Explain anything that looks alarming but is expected (a deliberate
  negative case, log noise) in one or two sentences.
- If something is off, say so plainly, propose the fix, and redo that demo
  after fixing. Never move on past a failure.
- Small improvements spotted during a demo: name them in one line and ask;
  don't expand scope silently.
- Then give the next demo's sentence and command.

## 4. Safety (non-negotiable)

- Ask before the first live run of a session; never relaunch SolidWorks.
- One test per process, paced (`SW_TEST_PACE_SECONDS=8`), `-x`.
- No exploratory or destructive probes against the user's live session.

## 5. After the last demo

- Summarize what was approved in a few lines.
- Only then push, open the PR and merge (no AI attribution in commits or PR).
