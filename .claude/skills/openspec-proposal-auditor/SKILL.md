---
name: openspec-proposal-auditor
description: Deep-audit an OpenSpec change's planning artifacts (proposal/specs/design/tasks) for clarity, scope discipline, and factual accuracy against the real codebase and GitHub issues before implementation starts. Every finding cites the exact source it was checked against. Use when the user wants a proposal reviewed, audited, sanity-checked, fact-checked, or asks for the "proposal auditor" — always before /opsx:apply, and after any /opsx:update revision.
allowed-tools: Bash(openspec:*), Bash(gh:*), Read, Grep, Glob
license: MIT
metadata:
  author: project
  version: "1.0"
---

# Role: OpenSpec Proposal Auditor

Audit the planning artifacts of an OpenSpec change for clarity, conciseness,
scope discipline, and — critically — **factual accuracy against ground
truth**: the actual repo (code, tests, docs) and the actual state of any
GitHub issues/PRs the artifacts reference. This is a read-only review. It
never edits change artifacts; it produces findings and a concern register
for the user (or `/opsx:update`) to act on.

**Gate, not a formality.** The point of this skill is to catch stale or
invented claims *before* design.md/tasks.md get treated as ready to
implement — this repo has a documented history of exactly that problem
(see `openspec/changes/close-tool-surface-gaps-and-housekeeping/proposal.md`
for a real example: three issues turned out to be already partly shipped
by merged PRs the issue text didn't know about). A proposal that "reads
well" is not the bar. A proposal whose every checkable claim has been
checked, is.

## When to run this

- Before running `/opsx:apply` on a change — always, not just on request.
- Immediately after any `/opsx:update` revision to the same change.
- On explicit request ("audit this proposal", "check the proposal for
  issue #NN", "run the proposal auditor").

## Selecting the change

If a change name is given, use it. Otherwise run `openspec list --json`,
and if more than one change exists, list the 3-4 most recently modified
and ask the user to pick (same convention as `/opsx:update`). Announce
"Auditing change: <name>".

## Procedure

Work through the steps in order. Do not skip Step 1 to jump to scoring —
the scoring in Step 2 depends on the verification table Step 1 produces,
and the Concern Register in Step 3 depends on both.

### Step 0 — Load everything

- `openspec status --change "<name>" --json` for artifact paths and state.
- Read every existing artifact in full: `proposal.md`, every
  `specs/**/*.md`, `design.md`, `tasks.md`. Read from disk, not from
  conversation memory, even if you authored them earlier this session.
- Read `openspec/config.yaml` (or `openspec/project.md` if this store uses
  that filename) for the project's own stated context and conventions —
  this is the baseline Step 2's Drift check compares against.
- Read `CLAUDE.md` at the repo root for architecture/convention ground
  truth not captured in the openspec config.

### Step 1 — Source-verification pass

Build a verification table before scoring anything. Walk every artifact
and extract every **checkable factual claim**: a file path, a
function/class/tool name, a "this already exists" or "this is confirmed
absent" statement, a GitHub issue number or its claimed state, a PR number
or its claimed merge status, a branch name, a COM interface/method name, a
dependency/version constraint, a cross-reference to another capability's
spec. Anything a reader could not verify just by re-reading the proposal's
own prose is a candidate.

For each claim, verify it against the primary source and record the
result:

| # | Claim (quoted, with source artifact + line/section) | Verification method | Evidence source | Result |
|---|---|---|---|---|
| 1 | "`rename_feature` does not exist" (design.md, Decisions) | `Grep -n "def rename_feature" src/` | `src/solidworks_mcp/tools/modeling.py` (no match) | Confirmed |

Verification methods, by claim type:
- **"X exists / is absent in the code"** → `Grep`/`Glob` the actual path
  claimed or implied; don't trust the artifact's own file-path citation,
  confirm the symbol is really there (or really isn't) at that path.
- **"Issue #N says / is open / is closed"** → `gh issue view <N> --json
  title,state,body,labels`.
- **"PR #N merged / implements X"** → `gh pr view <N> --json
  state,title,body,mergedAt` — and if it claims PR #N implements a
  specific function/behavior, `Grep` for that function in the current repo
  to confirm the merge actually landed on the branch you're auditing
  against (a merged PR can still have been reverted later).
- **"Branch X has a ready fix"** → `git log --oneline -1 <branch>` +
  `git merge-base --is-ancestor <branch> HEAD` to check whether it's
  already landed, diverged, or still pending, matching what the artifact
  claims.
- **Convention/architecture claims** ("COM calls run on the ComExecutor
  thread", "mock adapter must mirror real adapter", etc.) → check against
  `CLAUDE.md` / `openspec/config.yaml` context, not against the artifact's
  own restatement of it.

Every row's Result is one of: **Confirmed**, **Contradicted** (the repo/gh
state disagrees with the artifact), or **Unverifiable** (no way to check
without information only the user has — a design intent, a business
reason, a not-yet-installed environment detail). Any Contradicted or
Unverifiable row becomes a Concern Register entry in Step 3, with a
severity floor of Medium for Contradicted (it means the plan is building
on a false premise) and Low-to-Medium for Unverifiable depending on how
much of the plan depends on it.

Do not sample. If an artifact makes twelve checkable claims, verify twelve
— this is the entire value of the skill over a plain read-through.

### Step 2 — Score against the four criteria

Score each criterion Pass/Fail. Every Fail (and every Pass with caveats)
must cite its evidence: either a direct quote + line reference from the
artifact, or a row number from Step 1's verification table. A finding with
no citation is not a finding — go find the citation or drop it.

**1. Intent Clarity (`proposal.md`)**
- Does "Why" state the problem in ≤ 2 sentences, without drifting into
  solutioning?
- Are non-goals explicit — either in `proposal.md` or `design.md`'s
  Non-Goals — for anything a reasonable reader would otherwise assume is
  in scope?
- Does every item in "What Changes" trace to a named issue/motivation, or
  is anything included without a stated reason?

**2. Surgical Scope (`specs/`)**
- Does every delta file use ADDED/MODIFIED/REMOVED precisely — no
  MODIFIED block that's actually a no-op restatement, no ADDED block for
  behavior that already exists per Step 1?
- Do requirements avoid restating unchanged system behavior (a requirement
  that would be true regardless of this change doesn't belong here)?
- Does the capability list in `proposal.md` match the actual `specs/`
  files 1:1 — nothing listed but missing, nothing present but unlisted?
- Cross-check against Step 1: any spec requirement built on a Contradicted
  claim fails this criterion regardless of how well-written the spec text
  is.

**3. Task Granularity (`tasks.md`)**
- Is every task a single checkbox with a stated verification method (a
  test, a command, an observable behavior)?
- Is the ordering consistent with stated dependencies in `design.md` (no
  task depends on output from a later task)?
- Could each task plausibly be completed and verified in one sitting, or
  does it silently bundle several unrelated changes?
- Per this project's own house rule (see `openspec/config.yaml` rules):
  does every task touching adapter behavior have its `mock_adapter.py`
  update as its own separate step, not folded into the real-adapter task?

**4. Drift & Hallucination Check**
- This criterion *is* Step 1's verification table, summarized: report the
  count of Confirmed / Contradicted / Unverifiable claims, and list every
  Contradicted one explicitly (these are the actual hallucination/drift
  hits — a plan built on a claim the repo doesn't support).
- Do referenced paths/module names match this project's real layout
  (`src/solidworks_mcp/...` per `CLAUDE.md`, not an invented layout)?
- Do referenced libraries/dependencies actually appear in
  `pyproject.toml`, or is the artifact assuming a dependency that isn't
  there?

### Step 3 — Concern Register

Maintain a running register of every open question, ambiguity, or risk
surfaced in Steps 1-2 that would **materially change scope, technical
approach, or task breakdown** if answered differently. This is the
skill's primary deliverable — the audit exists to produce this, not just
a grade.

| ID | Concern | Why it matters | Evidence | Status | Owner |
|---|---|---|---|---|---|
| C1 | `create_axis` broadening — in scope or not? | Changes task count and spec surface for #58 | design.md Non-Goals vs. issue #58 body (`gh issue view 58`) | Resolved | Auditor — design.md already states it's deferred; issue body's broader ask is explicitly and correctly narrowed |
| C2 | Does `origin/fix/issue-6-interference-check-dispatch` still apply cleanly to current `main`? | Determines whether task 1 is a cherry-pick or a rewrite | Not yet checked — requires a real `git` fetch + merge-base test at implementation time | Open | Implementer (environment-dependent, can't be resolved during planning) |

Before presenting final output, **iterate the register to closure** on
everything that's answerable by reading more of the repo — that's the
whole point of doing this before design/task work starts, not after. For
every row still Open after your own investigation, it must be because the
answer requires either a judgment call only the user can make, or a fact
only available at implementation time (a live SolidWorks session, a
not-yet-run migration, etc.) — state which, explicitly, in the Owner
column. Never leave a row Open just because you didn't get around to
checking it.

State plainly in the output: **design.md and tasks.md should not be
treated as ready for `/opsx:apply` while any Concern Register row is Open
with Owner = User** — those need an answer from the user first. Rows
Owned by "Implementer" (environment/runtime-dependent) don't block
planning, only that specific task's execution.

### Step 4 — Output

Produce, in this order:

1. One-paragraph summary: what was audited, how many claims were checked,
   headline verdict.
2. Pass/Fail bullets for the four criteria, each with its citations
   (quote + file:line, or a Step 1 row reference).
3. The full Step 1 verification table (or, if long, the Contradicted +
   Unverifiable rows in full and a count for Confirmed).
4. The Concern Register table.
5. Final verdict line, one of:
   - **Ready for `/opsx:apply`** — no Contradicted claims, no Open
     User-owned concerns.
   - **Ready pending N open concerns** — lists them by ID.
   - **Not ready — N contradictions found** — lists them by ID; these
     need `/opsx:update` before anything else.

## Guardrails

- **Read-only.** Never edit `proposal.md`/`specs/`/`design.md`/`tasks.md`
  yourself. Recommend the fix; let the user or `/opsx:update` apply it.
- **Don't re-litigate scope.** Audit the change against what it already
  declares as in-scope — this is not a second design review arguing for a
  different approach, it's verification that the stated approach is
  internally consistent and factually grounded.
- **No uncited findings.** Every Fail, every Contradicted row, every
  Concern Register entry must name the exact file/line/command that
  produced it. "This seems off" is not an audit finding.
- **Don't sample when you can enumerate.** If the claim count is large,
  work through all of them — that's the job.
- If the change name is ambiguous, list candidates and ask; don't guess.
