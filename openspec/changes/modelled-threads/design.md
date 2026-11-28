## Context

Motivation: see proposal.md. Research and the user's decisions:
`openspec/research/modelled-threads.md` (decisions 1-7).

**Probe (SolidWorks 2026 SP4, 2026-11-28; scratch parts, closed unsaved):**

- The profiles are `.SLDLFP` files in the folder
  `GetUserPreferenceStringValue(swFileLocationsThreadProfiles = 107)` names
  (`C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2026\Thread Profiles`): Metric Die,
  Metric Tap (69 sizes each, `M1.2x0.25` ... ), Inch Die, Inch Tap (63,
  `#0-80` ... ), SP4xx Bottle. Each size is a configuration, read without
  opening the file by `ISldWorks.GetConfigurationNames(path)`.
- `IFeatureManager.CreateDefinition(swFmSweepThread = 87)` gives an
  `IThreadFeatureData`; `InitializeThreadData()`; set `Edge` (the circular
  edge picked with `SelectByID2(..., "EDGE", ...)` and read with
  `GetSelectedObject6`), `Type` (the profile's name, e.g. "Metric Die";
  SolidWorks resolves the file), `Size` (a configuration name),
  `ThreadMethod` 0 (cut), `EndCondition` 0 (blind), `BlindDepth` (m);
  `CreateFeature(data)` gives "Thread1" (type `SweepThread`).
- A die M10x1.5 on a Ø10 rod, 20 mm: 2,356.2 -> 2,088.2 mm³. A tap M10x1.5
  in a Ø8.5 hole, 15 mm: 16,865.1 -> 16,712.5 mm³ (SolidWorks set the
  diameter to 8.5 mm itself). Both pictures show the thread.
- The Hole Wizard library has no M1 or M1.4 coarse rows; the profiles have
  `M1.2x0.25` and `M1.4x0.3` but no M1. Sizes come from the profiles: they
  are what the feature accepts.

## Goals / Non-Goals

**Goals:** standard sizes read from SolidWorks; external and internal
threads; depth and runout reported by the agreed rules; checked before and
measured after.

**Non-Goals:**
- Modelling the runout as geometry (an ISO 4755 undercut groove or a
  vanishing thread). The Thread feature has no runout; the runout is
  computed and reported. Modelling it is a question for the user.
- Extruded (added) threads, multiple starts, offsets, the Bottle profile.
- Other standards (DIN, JIS ...) and pipe threads.
- Threads in assemblies.

## Decisions

1. **Sizes from the profiles, not the Hole Wizard.** The profiles' sizes
   are what the Thread feature accepts; listing anything else would offer
   sizes that fail.
2. **Coarse or fine from the list itself.** At one diameter, the coarsest
   pitch listed is `coarse`, the others `fine`, a lone one `only`. This is
   true to the list without a separate table (`#0-80` is UNF only and is
   reported `only`, not coarse).
3. **Diameters.** Metric: the number after M. Inch: a number size `#N` is
   0.060 + 0.013 N in (ASME B1.1 numbered sizes); a fraction is itself;
   both in mm.
4. **Depth.** ISO 68-1 basic depth of engagement H1 = 5/8 H, H = √3/2 P,
   so 0.541266 P. The same 60° profile serves inch threads.
5. **Runout.** ISO 3508: normal 2.5P (default), short 1.25P, rounded to
   0.01 mm. Inch: the same rule on P = 25.4/TPI, with `runout_basis` saying
   it is a reasoned default (decision 6).
6. **Diameter check.** External: the edge's diameter within one pitch of
   the nominal. Internal: within one pitch of nominal − P (about the tap
   drill). Outside, refused before building, naming both diameters.
7. **Measured.** Through `_measured(direction=-1)`: no change or added
   material deletes the feature and fails.
