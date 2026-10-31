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

The docs SHALL have a gallery page showing each demo GIF with one line on
what it shows and a link to the test or script that made it. The README
SHALL link to it.

#### Scenario: A visitor wants to see the demos

- **WHEN** a visitor follows the README's gallery link
- **THEN** every demo GIF in `docs/assets/demos/` is shown with its source
