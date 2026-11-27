# Modelled threads: research notes (queue item 43)

The user's request, 2026-11-26: modelled threads, both external (male) and
internal (female), with a thread runout, at standard sizes with their coarse
and fine pitches and the right thread depths, all read from the standards'
tables rather than typed in by hand.

## What SolidWorks already has

- **A Thread feature** (Insert > Features > Thread, SolidWorks 2016 and
  later). From the API: `IFeatureManager.CreateDefinition(swFmSweepThread)`
  gives an `IThreadFeatureData`. Call `InitializeThreadData`, set its
  properties, then `CreateFeature`. Its properties are `Edge`, `StartEntity`,
  `Type`, `Size`, `Diameter`/`DiameterOverride`, `Pitch`/`PitchOverride`,
  `EndCondition` (blind, revolutions, up to selection), `BlindDepth`,
  `Revolutions`, `ThreadMethod` (cut or extrude), `RightHanded`,
  `MultipleStart`/`NumberOfStarts`, `Offset`, `ThreadStartAngle`,
  `TrimStartFace`/`TrimEndFace`, `MirrorProfile`, `RotationAngle` and
  `MaintainThreadLength`. The edge is a cylinder's circular edge. The help
  example selects it with `SelectByRay`.
  - Source: [Thread Features and ThreadFeatureData Objects](https://help.solidworks.com/2022/english/api/sldworksapiprogguide/OVERVIEW/Thread_Features_and_ThreadFeatureData_Objects.htm)
  - Source: [Create a Thread Feature Example (VBA)](https://help.solidworks.com/2019/english/api/sldworksapi/Create_a_Thread_Feature_Example_VB.htm)
- **Thread profiles.** On this machine they are in
  `C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2026\Thread Profiles\`: `Metric Die`,
  `Metric Tap`, `Inch Die`, `Inch Tap` and `SP4xx Bottle` (`.SLDLFP`). A die
  makes an external (male) thread and a tap an internal (female) one. The
  folder comes from System Options > File Locations > Thread Profiles, so
  read the location; never hard-code it.
- **Size tables.** These are in the Hole Wizard library this project already
  reads (`adapters/solidworks/hole_library.py`, `swbrowser.sldedb`):
  - `<P>_DATA_HW_TappedHole` has columns `SIZE`, `Pitch` and `DIAMETER`:
    - ISO has 62 rows, with coarse and fine (`M8`, `M8x1.0`, `M10x1.25`);
    - ANSI inch (`AI`) has 48 rows, UNC and UNF (`1/4-20`, `1/4-28`), with
      the pitch as threads per inch.
  - `<P>_DATA_HW_TapDrills` has `SIZE`, `DIAMETER` and `TAP_DRILL`.
  - `<P>_Type_CThread` exists for AI, AM, AS, BSI, DIN, GB, HCOILIN,
    HCOILMM, IS, ISO, JIS and KS. Its rows are "Machine Threads" and
    "Straight Pipe Tapped Thread".

  This covers "standard sizes with coarse and fine" without copying a
  standard into our code: we read what the user's SolidWorks has.

## Thread depth (geometry, public)

ISO 68-1 basic profile, for pitch P:

- H = (√3 / 2) P = 0.866025 P (the fundamental triangle);
- H1 = 5/8 H = 0.541266 P, the basic depth of engagement (internal);
- external thread depth to the root ≈ 17/24 H = 0.613435 P (with a rounded
  root).

The same 60° profile applies to UTS inch threads, ASME B1.1.

- Source: [ISO 68-1:1998 sample](https://cdn.standards.iteh.ai/samples/3707/43667a380e834371825604fbc6d63336/ISO-68-1-1998.pdf)
- Source: [ISO 261 (Wikipedia)](https://en.wikipedia.com/wiki/ISO_261)

To check on a live probe: whether the SolidWorks thread profiles already
model this depth, so that we only report it. They probably do; the profile
is a sketch scaled by the pitch.

## Thread runout

- ISO 4755 (with ISO 3508) and DIN 76-1 cover runouts and undercuts on
  external ISO metric threads. ISO 4755 has one undercut type, g2 max = 3P.
  DIN 76-1 adds type A (g2 max = 3.5P, normal) and type B (g2 max = 2.5P,
  short).
- x1 is the normal runout, used where nothing else is specified; x2 is the
  short runout.
- Internal-thread runouts are only in DIN 76-1, Table 2; ISO 3508 and 4755
  don't cover them.
- The numeric tables are paywalled. Their values by pitch must come from a
  licensed copy or the user, not be guessed. Until then, the runout is an
  input: a length in mm, or a count of pitches. Our default needs the user's
  decision.
  - Source: [TU Darmstadt: thread runouts for ISO metric threads](https://www.iim.maschinenbau.tu-darmstadt.de/CAD-Tutorial/CAD-Norminfo/3_important_standards_and_data_sheets/2_screws_and_threads/2_thread_runouts_for_iso_metric_threads_and_minimum_screwin_depth/index.en.html)
  - Source: [DIN 76-1 (DIN)](https://www.din.de/en/wdc-beuth:din21:394715258)
- How to model a runout: the Thread feature has no runout option. Two
  candidate ways, to settle in a live probe:
  - end the thread feature short and revolve-cut an undercut groove
    (DIN 76 type A or B);
  - a tapered (vanishing) end, made by a helix with a taper and a cut sweep
    (queue item 34) over the last x1 length.

## Runout: standard practice (follow-up research, 2026-11-26)

DIN 76-1 is the German national standard, built on two ISO standards that
are the international practice:

- **ISO 3508:1976, thread run-outs for external ISO metric threads.** Read
  in full in IS 1369 (Part 1):1993. That is BIS's identical adoption, free
  on Public.Resource.Org:
  [is.1369.1.1993.pdf](https://law.resource.org/pub/in/bis/S01/is.1369.1.1993.pdf).
  - Run-out x max is normal ≈ 2.5P (the default, "for all types of screws
    in product grades A, B and C") or short ≈ 1.25P ("only in cases where a
    short run-out is required for technical reasons").
  - Distance a (the last full thread to a head) is normal ≈ 3P (grade A),
    short 2P, or long 4P (grades B and C).
  - The table rounds the values, for example P 1.25 gives x 3.2 and 1.6,
    and P 1.75 gives x 4.3 and 2.2. It covers P 0.2 to 6.
- **ISO 4755:1983, thread undercuts for external ISO metric threads.** Read
  in full in IS 1369 (Part 2):1993:
  [is.1369.2.1993.pdf](https://law.resource.org/pub/in/bis/S01/is.1369.2.1993.pdf).
  It has one undercut type:
  - g2 max ≈ 3P;
  - g1 min, based on a 30° transition;
  - dg = d − (a value by pitch, for example d − 1.6 at P 1, d − 3 at P 2);
  - radius r, by pitch.

  The covering note says to use an undercut only where one is needed, for
  example on a plug threaded up to a shoulder.
- **Internal threads:** there is no ISO standard. IS 1369 Part 3 was "under
  preparation" in 1993; DIN 76-1 Table 2 is the only national table found.
  Blind tapped holes are usually handled by drilling deeper than the
  thread. SolidWorks's Hole Wizard already does this (drill depth against
  thread depth), so an internal thread should take the same default.
- **Inch (UTS) threads:** not verified yet. ASME B1.1 is paywalled. ASME
  B1.15 (UNJ) says external runouts are one to two pitches. Next, read NBS
  Handbook H28 (1969), a US government publication in the public domain:
  [nbshandbook28-1969p1.pdf](https://nvlpubs.nist.gov/nistpubs/Legacy/hb/nbshandbook28-1969p1.pdf).
- **Copyright:** BIS holds the copyright on these publications. Carrying the
  rule (normal ≈ 2.5P, short ≈ 1.25P, undercut ≈ 3P) and citing the
  standard is fine. Shipping the rounded tables as data needs a decision.

Proposed default: for an external metric thread, the ISO 3508 normal
runout (a vanishing thread over x), with `runout="short"` or a length to
override it, and `undercut=true` for an ISO 4755 groove. An internal thread
follows the Hole Wizard's drill depth, with no runout.

## Decisions (the user, 2026-11-26)

1. Standards: ISO metric and inch first, then ANSI where it applies. Don't
   guess at others.
2. Runout: DIN 76 is German practice; use what is international practice.
   This is the follow-up above: ISO 3508 and ISO 4755, with inch still to
   verify.
3. Tools: `create_thread` as sketched, plus `list_thread_sizes`.
4. `create_hole`: model no thread by default. When the user talks of
   fasteners, the agent may ask "add a modelled thread?". The tool
   description points to `create_thread` and where to find the sizes
   (`list_thread_sizes`).

## Open questions for the spec (first draft)

1. Standards in the first version: ISO metric and UTS inch, then the rest
   of the library's prefixes as they come.
2. Runout default: none, a length in pitches, or the DIN 76 value once a
   licensed table is to hand.
3. One tool, `create_thread(edge or face, kind=external|internal,
   standard, size, length or revolutions, runout, hand, starts)`, plus
   `list_thread_sizes(standard)` reading the tables above.
4. Whether `create_hole` with a tapped hole should be able to model the
   thread as well, not only show a cosmetic one.
