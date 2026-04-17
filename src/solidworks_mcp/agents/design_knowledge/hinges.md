# Hinge Design Guide for FDM 3D Printing

## Overview

Hinges are rotational joints that allow controlled angular motion between two components.
For FDM printing, hinges divide into two major categories:

1. **Print-in-place hinges** — printed as a single assembly with a clearance gap; no assembly required
2. **Hardware-assisted hinges** — use an M-series pin, dowel, or standard hinge hardware

## Print-in-Place Hinges

### Living Hinge (Flexure Hinge)

A thin flexible web that bends instead of rotating.

**Best materials:** PETG, TPU, Nylon (flexible layer bonding required)
**Avoid:** PLA (brittle after repeated flex cycles)

**Geometry guidelines:**

- Minimum web thickness: 0.8–1.2 mm (PETG), 1.0–1.5 mm (Nylon), 0.4–0.8 mm (TPU)
- Web width: 2–5× web thickness for stability
- Transition fillets: R ≥ 1.5× web thickness to minimize stress concentration
- Max reliable flex angle: ±30° for PETG, ±45° for Nylon, ±90° for TPU
- Cycle life: PETG ~1000 cycles before fatigue crack; Nylon ~10,000+; TPU ~100,000+

**Print orientation:** The web MUST be printed flat (parallel to bed) for maximum inter-layer
adhesion in flex. Never print a living hinge on edge.

**Layer height:** Use 0.15 mm or finer for living hinges to maximize layer count through
the thin web. More layers = better fatigue life.

### Barrel / Knuckle Print-in-Place Hinge

Printed assembled with a clearance between pin and barrel.

**Clearance recommendation:**

| Material combo (pin/barrel) | Clearance |
|-----------------------------|-----------|
| PLA / PLA                   | 0.30–0.40 mm |
| PETG / PETG                 | 0.35–0.50 mm |
| ABS / ABS                   | 0.30–0.40 mm |
| TPU pin / PLA barrel        | 0.15–0.25 mm |

**Design rules:**

- Minimum barrel length: 8–10 mm to prevent pin from camming out under load
- Barrel wall thickness: ≥ 1.5 mm (3 perimeters at 0.4 mm nozzle)
- Pin diameter: 3–6 mm typical; larger for structural load
- Print orientation: hinge axis horizontal (pin parallel to bed) for round barrel geometry
- Add a small (1 mm) chamfer at barrel entrance to help pin pop in

**Assembly tip:** Print support removal easier if you use a 1.0 mm support gap and
0.3–0.5 mm Z-gap on support interface.

### Living Flexure with Stops

Add hard-stop features to limit rotation and protect the living section from over-rotation.

- Stop faces can be angled 0–90° to set max rotation
- Position stops ≥ 5 mm from hinge center to allow clean rotation before contact

## Hardware-Assisted Hinges

### M3 / M4 Shoulder Bolt Hinge

Use a stainless shoulder bolt as the hinge pin.

**Pin hole tolerance:**

- For M3 shoulder bolt (3.0 mm shank): print hole at Ø3.1–3.2 mm (clearance fit)
- For M4 shoulder bolt (4.0 mm shank): print hole at Ø4.1–4.2 mm

**Wear recommendation:** Insert a brass or steel M3/M4 heat-set insert as a sleeve if
the hinge will be used frequently. Heat set inserts greatly extend wear life.

**Wall thickness around pin:** minimum 2.5 mm on each side of pin hole.

### Dowel Pin Hinge

A 3 mm steel dowel pin is cheap and strong. Print hole at Ø3.1 mm and press the pin in.

### Piano Hinge (Continuous Hinge)

Mount a commercial piano hinge with M3 self-tapping or heat-set inserts.

- Boss diameter for M3 insert: 5.5 mm OD, 4.0 mm deep
- Boss OD should be ≥ 2× insert OD for sufficient wall

## Hinge Variants for SolidWorks Parametric Design

| Variant            | Recommended For                        | Key Parameter  |
|--------------------|----------------------------------------|----------------|
| Living hinge       | Light loads, frequent flex, TPU/Nylon  | web thickness  |
| Barrel hinge       | Panel doors, enclosure lids            | barrel clearance|
| Wrapped hinge      | Continuous flex (cable management)     | wrap radius    |
| Ratchet hinge      | One-way or indexed rotation            | tooth count    |
| Fold-flat hinge    | Portable structures, flat pack         | fold angle     |

## SolidWorks Workflow

1. Use **Revolve** for barrel/pin geometry
2. Use **Shell** to thin the web for living hinges
3. Use **Mates** to simulate rotation range and check interference
4. Use **Flex** to visualize living hinge deflection
5. Export as separate bodies for split-file printing if needed

## Common Hinge Failure Modes

| Failure                  | Cause                          | Fix                                     |
|--------------------------|--------------------------------|-----------------------------------------|
| Stiff / won't rotate     | Clearance too small            | Increase clearance 0.1 mm               |
| Pin falls out            | Clearance too large            | Decrease clearance or add detent        |
| Living web cracks        | Thickness too small / PLA      | Switch to PETG/Nylon, increase thickness |
| Barrel cracks at entry   | Wall too thin                  | Increase wall thickness to ≥ 2 mm       |
| Wobble / slop            | Barrel too short               | Extend barrel length                    |
