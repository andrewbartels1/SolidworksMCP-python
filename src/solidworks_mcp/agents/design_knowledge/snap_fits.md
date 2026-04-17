# Snap-Fit Design Guide for FDM 3D Printing

## Overview

Snap fits are one of the most useful joint types for 3D-printed assemblies. They allow
tool-free assembly and disassembly. FDM-specific design rules differ from injection
molding guidelines due to layer anisotropy and material properties.

## Types of Snap Fits

### 1. Cantilever Snap Fit (Most Common for FDM)

A cantilever snap fit is an arm that deflects laterally and then snaps into a recession
or over a ledge.

**Key geometry parameters:**

- Arm length (L): longer arm = easier deflection, less stress
- Arm width (b): wider = stiffer
- Arm thickness (h): thinner at base for controlled flex
- Deflection (δ): the snap travel before engagement
- Lead angle: 15–30° for easy entry, 90° for permanent lock, 45° for reusable

**FDM design rules:**

- Orient the cantilever so it bends parallel to the print layers (not through layers)
- Minimum arm length: 5× arm thickness at root to avoid crack at root
- Clearance on non-deflecting sides: 0.3–0.5 mm (PETG), 0.2–0.4 mm (PLA)
- Add a 0.5–1.0 mm fillet at the arm root to reduce stress concentration
- Recommended retention angle for reusable snap: 30–45°
- Recommended retention angle for permanent: 70–90°

**Material-specific max strain:**

- PLA: 2–3% safe strain limit
- PETG: 3–5% safe strain limit
- ABS: 3–5% safe strain limit
- TPU/TPE: 10–20% (very flexible, use thick snaps)
- Nylon PA12: 4–6%

**Deflection formula (cantilever):**
  δ = (strain × L²) / (1.5 × h)

where L = arm length, h = arm thickness at root, strain = material limit.

### 2. Annular (Ring) Snap Fit

Used for caps, lids, and cylindrical closures.

**FDM adaptation:**

- Print vertically when possible so the ring is printed in-plane
- Undercut depth: 0.5–1.0 mm for PLA/PETG
- Lead chamfer: 30° for easy assembly
- Oversize the male feature by 0.1–0.2 mm to preload the joint

### 3. Torsional Snap Fit

Less common but useful for panel inserts. The arm twists rather than bends.

**FDM consideration:** Torsion through layers is weak; keep torsional snap fits
in-plane with prints.

### 4. Ball-and-Socket Snap (Print-in-Place)

Popular for print-in-place joints:

- Minimum clearance between ball and socket: 0.4–0.6 mm (PETG), 0.3–0.5 mm (PLA)
- Print vertically for best-of-round socket
- Socket opening angle: 90–120° for good retention while allowing disassembly

## General FDM Snap Fit Clearances

| Interface        | PLA         | PETG        | ABS         | Nylon       |
|-----------------|-------------|-------------|-------------|-------------|
| Sliding fit     | 0.25–0.35 mm| 0.30–0.40 mm| 0.25–0.35 mm| 0.20–0.35 mm|
| Snap engagement | 0.20–0.30 mm| 0.25–0.35 mm| 0.20–0.30 mm| 0.15–0.25 mm|
| Press fit       | 0.00–0.10 mm| 0.05–0.15 mm| 0.00–0.10 mm| -0.05–0.10 mm|

## Common Snap Fit Failure Modes

1. **Root fracture**: Arm too short or fillet missing → add fillet, increase arm length
2. **No click/engagement**: Clearance too large → reduce by 0.1 mm increments
3. **Permanent deformation**: Strain too high → increase arm length or switch material
4. **Layer delamination**: Arm bending through layers → reorient print
5. **Wobble after assembly**: Mating side clearance too large → add a locating boss

## SolidWorks Implementation Tips

- Model snap fits as separate bodies to control print orientation per body
- Use the "Flex" feature to simulate deflection and check interference
- Add "Draft" to snap faces to ease assembly direction
- Use Equations to drive snap geometry from a single "clearance" variable
