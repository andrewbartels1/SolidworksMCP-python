# FDM Tolerancing and Clearance Guide for SolidWorks

## Overview

FDM (Fused Deposition Modeling) printed parts have dimensional error sources that injection-molded
parts do not. Understanding these helps design parts that fit on the first print.

## Sources of Dimensional Error in FDM

1. **Line width expansion**: Extruded lines are slightly wider than nozzle diameter. A 0.4 mm
   nozzle typically produces 0.42–0.48 mm lines.
2. **First-layer squish**: The first layer is intentionally compressed for adhesion, widening it
   by 0.05–0.15 mm.
3. **Thermal shrinkage**: Parts shrink slightly on cooling. PLA ~0.1–0.3%, ABS ~0.5–1.0%,
   PETG ~0.2–0.4%.
4. **Elephant foot**: First few layers bow outward by 0.1–0.3 mm radius at base.
5. **Hole undersizing**: Circular holes are undersized by 0.1–0.3 mm diameter (typical).
6. **Overhangs and support artifacts**: Overhangs > 45° add surface roughness of 0.2–0.5 mm.

## Recommended Clearances by Fit Class

### Sliding Fit (e.g., drawer, lid that slides)

| Material          | Clearance per side | Total gap |
|-------------------|--------------------|-----------|
| PLA               | 0.15–0.25 mm       | 0.30–0.50 mm |
| PETG              | 0.20–0.30 mm       | 0.40–0.60 mm |
| ABS               | 0.15–0.25 mm       | 0.30–0.50 mm |
| Nylon             | 0.20–0.30 mm       | 0.40–0.60 mm |

### Rotating Fit (axle in bearing or hole — free spin)

| Material          | Clearance per side |
|-------------------|--------------------|
| PLA               | 0.20–0.30 mm       |
| PETG              | 0.25–0.35 mm       |
| ABS               | 0.20–0.30 mm       |

### Press Fit (e.g., insert or shaft pressed in without heat)

| Material          | Interference per side |
|-------------------|-----------------------|
| PLA               | 0.00–0.15 mm         |
| PETG              | 0.05–0.20 mm         |
| ABS               | 0.05–0.20 mm         |

### Mating Parts (two printed surfaces that touch but don't move)

Minimum clearance to avoid fusion/welding: 0.15 mm per side (0.30 mm total).

### Hole Diameter Correction

Because holes print undersized, add the following to nominal hole diameters:

| Hole type        | Correction |
|-----------------|-----------|
| Vertical holes   | +0.2 mm   |
| Horizontal holes | +0.3 mm   |
| Hex nut trap     | +0.3 mm on flat-to-flat, +0.1 mm on height |
| M3 clearance     | Print at 3.4 mm (nominal 3.2 mm + compensation) |
| M4 clearance     | Print at 4.5 mm |
| M5 clearance     | Print at 5.6 mm |

## Material-Specific Notes

### PLA
- Easy to print, dimensionally accurate (~0.2% shrinkage)
- Paint the clearance table values above as starting points
- PLA warps minimally; well-calibrated machines may use the lower end of clearance ranges

### PETG
- More flexible than PLA; use the mid-range clearances
- PETG sticks to itself: always use ≥ 0.3 mm gap on support or mating faces
- PETG absorbs moisture slightly; store dry for best dimensional stability

### ABS
- Significant shrinkage (~0.5%); use an enclosure to reduce warp
- Increase clearances by 0.05–0.10 mm vs PLA
- Post-process with acetone vapor for tighter fits

### Nylon (PA12, PA6)
- Absorbs moisture aggressively; prints MUST dried (70°C/12h in oven before printing)
- Dimensional stability excellent when dry; expands ~0.2% when wet
- Use the upper end of clearance ranges

### TPU/TPE
- Flexible; normal clearance rules don't apply
- For rigid-to-flexible interface: use 0.0–0.1 mm clearance (flexible part compresses)
- Use Shore A hardness to gauge stiffness: 95A is nearly rigid, 70A is very soft

## Thread Design

### Printed Threads (in-part)
- Use coarse threads (M3–M8 typical)
- For best results: cut threads with a tap after printing
- Printed thread pitch: use M3×0.5, M4×0.7 — coarser pitch = more material, stronger
- Add 0.2 mm clearance on thread form radius when printing both mating threads

### Heat-Set Inserts (preferred for mechanical joints)
| Insert size | Hole diameter | Depth |
|-------------|---------------|-------|
| M2          | 3.2 mm        | 4.0 mm |
| M3          | 4.2 mm        | 5.7 mm |
| M4          | 5.6 mm        | 7.0 mm |
| M5          | 6.4 mm        | 8.0 mm |

Knurled M3 inserts (Ruthex RX-M3×5.7 or similar): dominant choice for robust joints.

## SolidWorks Parametric Tolerancing Approach

Use a **global equation** for clearance to drive all mating geometry:

```
"print_clearance" = 0.30mm  ' adjust per material and printer
"hole_comp" = 0.20mm        ' hole undersizing compensation
"press_fit_interference" = 0.10mm
```

Then reference these equations on all mating extrudes, holes, and cuts. A single value
change recalibrates the entire assembly.

## Recommended Test Protocol Before Final Print

1. Print a **tolerance test coupon** (25 mm cube with holes at 3 mm, 4 mm, 5 mm and
   slots at 0.2, 0.3, 0.4, 0.5 mm clearances)
2. Measure with calipers; compare to print_clearance global variable
3. Update the global variable to match reality
4. Reprint coupon once to confirm, then proceed to final part
