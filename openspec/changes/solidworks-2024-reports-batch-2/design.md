## Context

Without a 2024 install, the only evidence is the reports and what 2026 does.
So every report was first written as a live test following the reporter's
steps and run on 2026. A failure there means our code is wrong; a pass means
the difference is in 2024.

## Decisions

### 1. Reproduce on 2026 first

`tests/live/test_live_sw_2024_reports_batch2.py` has one test per report.
On 2026: #266, #268, #270, #271, #272, #273, #274 failed, #267 failed in our
wrapper, #265 and #275 passed. Probes settled what the fixes needed:

- #271: the hole wall's nearest point was 0.043 mm from the reporter's point;
  the face picker allowed 0.01 mm. The edge picker already allows 0.5 mm, so
  0.1 mm is conservative; the nearest face is always the one taken.
- #274: `M8x1.25`, `M8X1.25` and `M8 x 1.25` all stored `M8x1.0`; `M8` stored
  `M8`. ISO tables list coarse threads without a pitch.
- #273: the section view's outline sat on the parent's x; `RemoveAlignment`
  plus `Position` moves it.
- #269: `AddRelation` with a line's start point and `Point1@Origin`
  (`EXTSKETCHPOINT`, read back from the selection) adds the relation; the
  legacy `SketchAddConstraints` adds nothing.
- #262: an anchored BOM won't move (`SetPosition` False, `Anchored` can't be
  cleared); deleting its `BomFeat` and inserting it unanchored works.

### 2. Two kinds of release difference, two mechanisms

- **Same member, other dispatch kind** (#265): `compat.invoke` / `read`.
  Not a per-year table: a table needs the year's behaviour known in advance,
  and we can't measure 2024. Trying the 2026 form first and falling back only
  on the one error that means "wrong kind" needs no knowledge of the release
  and can't change 2026. What fell back is reported, which builds the
  knowledge a table would need, from users' reports.
- **Same call, other result** (#275): measure and correct. 2026 already puts
  a note's top-left at the point, so the correction is a no-op there.
- **Same member, other argument list** (#255): fixed at the call by using the
  form every release has, recorded in the pitfalls.

### 3. Leave 2026's paths as they are

Each fix keeps the 2026 path where it worked: `set_dimension` changes only
with several configurations; `create_extrusion` selects by name only when
nothing is selected; the note and section-view corrections do nothing when
already in place.

## Risks / Trade-offs

- [The retry hides a real missing member] → it only retries on "Member not
  found" and re-raises the retry's own error, which names the member.
- [Widening the face tolerance picks a face for a point slightly off it] →
  0.1 mm is far below any feature size; the nearest face still wins.
