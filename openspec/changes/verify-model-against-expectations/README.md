# Verify a model against what you expected

OpenSpec change for issue #173, the final step of the bracket demo (#147).
This page is the plain-English overview. The artifacts below are the source
of truth; if this page and an artifact disagree, the artifact wins.

| Read | For |
|------|-----|
| [proposal.md](proposal.md) | Why, and what changes |
| [design.md](design.md) | Decisions D1–D10 and the risks |
| [specs/tools/model-verification](specs/tools/model-verification/spec.md) | The `verify_model` tool |
| [specs/tools/model-geometry-summary](specs/tools/model-geometry-summary/spec.md) | The new adapter read |
| [specs/tools/measured-feature-change](specs/tools/measured-feature-change/spec.md) | Before/after numbers on extrude, revolve and cut |
| [tasks.md](tasks.md) | Progress, as checkboxes |

## The problem

A modelling tool can return "success" when SolidWorks quietly did nothing,
for example a cut that removes 0 mm³. Before this change an agent had to
piece together four read tools to check its work, and still could not read
the model's size, body count or mate count.

## What it adds

1. **`verify_model` tool.** Pass only the expectations you know; each becomes
   a check, and there is one overall result.
   - Volume and mass within 1 % (adjustable); overall size within 0.1 mm per
     axis (adjustable); exact counts of features and solid bodies.
   - Assemblies only: component count, mate count, and whether any parts
     overlap.
   - Result: `pass`, `fail`, `inconclusive` (something could not be measured,
     which never counts as a pass) or `report_only` (no expectations given).
   - Errors for an assembly-only check on a part, a drawing as the active
     document, or a misspelt expectation.
2. **One new adapter read** for size, bodies, volume and counts. It never
   rebuilds the model or clears the selection. Part sizes come from each
   body's extreme points (exact on round parts), falling back to the part box;
   assemblies use SolidWorks' assembly box, which can be slightly loose.
3. **Before/after numbers on extrude, revolve and cut.** Each reply gains a
   `measured_change` block, plus a warning when the feature changed no
   volume. Measuring never fails the feature.

Feature count leaves out sketches, the origin, folders, the mate group and
the three default planes, so "2 extrudes + 1 fillet" is 3, and the reply
lists the names it counted.

## Status

Built and unit-tested without SolidWorks (sections 1–6 of
[tasks.md](tasks.md)). What remains needs real SolidWorks and the
maintainer's go-ahead, run at `SW_TEST_PACE_SECONDS=4` on new scratch
documents closed without saving:

1. A safe probe on a 100 × 50 × 10 block: extreme-point size, volume 50 000
   mm³, one body, selection untouched.
2. Live tests: a Ø20 shaft, a two-part assembly with two mates, an extrude
   and a cut checked against hand calculations.
3. A COM pitfall note on the extreme-point read, from what the probe shows.
4. A live demo to the maintainer, then the PR that closes #173.

When every task is done, archive the change (`openspec archive
verify-model-against-expectations`), which merges these specs into
`openspec/specs/`.
