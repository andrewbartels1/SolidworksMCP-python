## ADDED Requirements

### Requirement: Live demos can be recorded with a motion-following frame rate

With recording turned on, a live demo SHALL capture the SolidWorks window
repeatedly while the test runs, keep only frames that differ from the one
before, and record each kept frame's time. The recorder SHALL NOT call
SolidWorks.

#### Scenario: A feature appears on screen

- **WHEN** a recorded demo builds a feature and SolidWorks redraws over
  several frames
- **THEN** each changed frame is kept with its time, up to the configured
  frames per second

#### Scenario: Nothing changes on screen

- **WHEN** the window does not change between captures
- **THEN** no new frame is kept

#### Scenario: Recording is off

- **WHEN** `SW_DEMO_RECORD` is not set
- **THEN** no recorder thread starts and the test runs as before

### Requirement: Recordings become high-resolution GIFs with real timing

The GIF builder SHALL turn a recording into one GIF per test, at a
configurable width (1280 px by default). Each frame SHALL be shown for as
long as it was on screen, capped at a configurable longest hold, with the
caption current at that moment beneath it.

#### Scenario: Building a recording

- **WHEN** `make_demo_gif.py --recording <capture dir>` runs on a recording
- **THEN** it writes `<test>-motion.gif` beside the stills' GIF
- **AND** a frame that stayed on screen for 8 s is held for the longest hold
- **AND** a frame taken 1/12 s before the next is held for 1/12 s

### Requirement: A demo gallery

The docs SHALL have a gallery page showing each demo GIF with what it
shows, the prompt, the tool calls it makes, and a link to the test or script
that made it. The prompt-driven demo SHALL show its real prompt and every
call from its transcript; a test that calls the tools directly SHALL show an
example prompt, labelled as such, that asks for the same calls. The README's
Demos section SHALL show the GIFs and link to the gallery page.

#### Scenario: A visitor wants to see the demos

- **WHEN** a visitor opens the README's Demos section
- **THEN** each demo GIF is shown, linked to its entry on the gallery page

#### Scenario: A visitor wants to know what a demo did

- **WHEN** a visitor reads a demo's entry on the gallery page
- **THEN** it shows the GIF, what it proves, the prompt, the tool calls and
  the source file
- **AND** every demo GIF in `docs/assets/demos/` has an entry
