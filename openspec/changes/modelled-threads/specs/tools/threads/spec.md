## ADDED Requirements

### Requirement: The standard sizes SolidWorks holds
`list_thread_sizes` SHALL take `standard` (`metric` or `inch`) and list the
sizes of SolidWorks's own Die thread profile for it, read from the Thread
Profiles folder SolidWorks names. Each entry SHALL give `size` (the name
`create_thread` takes, e.g. `M6x1.0` or `1/4-20`), `diameter_mm`,
`pitch_mm` (and `tpi` for inch), `pitch_class` (`coarse` for the coarsest
pitch listed at that diameter when there are several, `fine` for the
others, `only` when there is one), `basic_depth_mm` (ISO 68-1: 5/8 of the
fundamental triangle, 0.541266 × P) and `runout_mm` with its normal (2.5P)
and short (1.25P) values (ISO 3508). The reply SHALL say where the runout
rule comes from (`runout_basis`): ISO 3508 for metric, the ISO 3508 rule on
the inch pitch (1/TPI) for inch.

#### Scenario: Metric sizes
- **WHEN** it is called with `standard` `metric`
- **THEN** `M6x1.0` is listed with `pitch_mm` 1.0, `pitch_class` `coarse`
  and `runout_mm` normal 2.5 and short 1.25, and `M10x1.25` with
  `pitch_class` `fine`

### Requirement: A modelled thread
`create_thread` SHALL take `kind` (`external` or `internal`), `standard`,
`size`, `edge_point` (`[x, y, z]` mm on the circular edge where the thread
starts), `length` (mm) and `hand` (`right`, the default, or `left`), and
SHALL make SolidWorks's Thread feature with the Die profile for an external
thread or the Tap profile for an internal one, cutting the thread. The
reply SHALL give the feature's `name`, the size, its pitch and depth, the
runout, and the volume before, after and removed.

#### Scenario: An M6 external thread
- **WHEN** a 6 mm rod's top edge is picked and `create_thread` is called
  with `kind` external, `size` `M6x1.0` and `length` 12
- **THEN** a Thread feature is made, the part loses volume, and the reply
  gives `pitch_mm` 1.0 and `runout_mm` 2.5

### Requirement: Refused before anything is built
`create_thread` SHALL fail with `invalid_input`, changing nothing, when the
size isn't one the profile holds (the message names the nearest sizes),
the point is on no edge or on one that isn't circular, or the edge's
diameter doesn't suit the size: an external thread's cylinder within one
pitch of the nominal diameter, an internal thread's hole within one pitch
of the tap drill (nominal minus one pitch).

#### Scenario: The wrong size for the rod
- **WHEN** `M10x1.5` is asked for on a 6 mm rod
- **THEN** it fails with `invalid_input`, saying the edge is 6 mm and the
  size wants about 10 mm

### Requirement: A thread that cuts nothing is undone
A Thread feature that leaves the volume unchanged, or adds material, SHALL
be deleted and the call SHALL fail with `feature_not_built`.

#### Scenario: Nothing cut
- **WHEN** SolidWorks makes the feature but the volume is unchanged
- **THEN** the feature is deleted and the call fails
