## Context

`FeatureCut4`'s arguments start `Sd, Flip, Dir, T1, T2, D1, D2`.
- `Sd` is "single direction": `True` cuts Direction 1 only, and `False`
  also cuts Direction 2 using `T2` and `D2`.
- Direction 1 follows the sketch plane's normal, and `Dir` reverses it.

PR #192 builds the arguments in one function and tries a list of
`(label, Sd, T1, T2)` forms in order. Before each retry it reselects the
sketch, and it tries `FeatureCut4` and then `FeatureCut3` for every form.

**Live probe, SW 2026, 2026-11-01.** The setup is a Ø5.5 × 6 mm hole from a
Top Plane sketch, under a 30 × 30 × 15 block extruded up from Top. Each case
ran in its own fresh part:

| Form | Result |
|---|---|
| `Sd=False`, `D2=0` | no feature |
| `Sd=True`, `Dir=False` | no feature |
| `Sd=True`, `Dir=True` | 142.55 mm³ (exact) |
| `Sd=True`, then `Sd=False` | no feature |

In the earlier live runs, from a Front Plane sketch through the middle of a
block: `Sd=True` cut 37.70 mm³ (exact), and `Sd=False` with `D2=0` built
nothing.

## Goals / Non-Goals

**Goals:**
- One-way cuts work from internal, face and edge-plane sketches.
- A caller never has to guess `reverse_direction` or decode a silent
  failure: the tool says what it did, and what to change when nothing works.

**Non-Goals:**
- New end conditions (Up To Surface, Offset From Surface).
- Choosing the direction from geometry before cutting, e.g. by
  ray-casting the body. The retry costs one extra pair of calls, only when
  the first direction misses.
- Changing `OptimizeGeometry`.

## Decisions

**A one-way cut is single-ended, and is retried once with `Dir` reversed.**
The forms become `(label, Sd, T1, T2, Dir)`:
- `("", True, t1, Blind, reverse)`, then
- `(" [direction flipped]", True, t1, Blind, not reverse)`,

where `t1` is Blind or Through All. Through All both ways keeps #192's two
forms, with `Dir = reverse`.

The probe shows that a failed attempt does not spoil the retry. Case D fails
only because `Sd=False` never works there; case A fails the same way on its
own.

*Rejected: fall back to `Sd=False`.* That form builds nothing in every case
probed. It only looked right on main because of the `FeatureCut3` bug.

*Rejected: honour `reverse_direction` strictly and fail.* When the requested
direction finds no material, the only cut that removes anything is the
opposite one. The SolidWorks UI picks that one too. Failing would push
agents back to guessing. The flip is reported, not hidden.

**Say what happened, where agents read it.**
- `parameters.direction_flipped` on the adapter result, and
  `cut_extrude.direction_flipped` on the tool reply, plus a sentence in the
  tool's message.
- The no-feature error lists the forms tried and the depth.
- `error_classifier` gets a `feature_not_built` rule, matching
  "built no feature", whose hint says to change the inputs rather than
  retry. It sits before `not_found` because the first matching rule wins.
- The tool and field descriptions state the direction rule, so an agent
  knows it before calling.

**Order: after #192.** This builds on #192's forms loop and argument
builder.

## Risks / Trade-offs

- [A caller asked for `reverse_direction` and the cut went the other way] →
  Only when the requested way removed nothing, and the reply says
  `direction_flipped: true`.
- [A cut that misses both ways costs twice the calls] → Four calls and
  three reselects, each with the 0.25 s settle pause, then a
  `feature_not_built` error that tells the caller to change the inputs.
- [SW 2025 not on hand] → The 2025 branch differs only in
  `OptimizeGeometry`.
