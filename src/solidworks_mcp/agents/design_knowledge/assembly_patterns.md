# FDM Print-in-Place and Assembly Design Patterns

## Overview

This guide covers design patterns for functional 3D-printed assemblies with a focus on
reducing or eliminating post-print hardware.

## Interlocking Joints

### Dovetail Joint
- Classic woodworking joint adapted for FDM
- Angle: 14–18° is typical (wider = stronger pull resistance, harder to assemble)
- Clearance: 0.25–0.35 mm per side for PETG
- Print the male (tail) piece upright; female (pin) piece can be flat
- Add 0.5 mm chamfer at entry to guide assembly

### Mortise and Tenon
- Simple rectangular tab and slot
- Clearance: 0.20–0.30 mm per side
- Tenon width should be 1/3 of joint width for best strength ratio
- Add 1:5 taper on tenon faces for self-aligning entry

### T-Slot / Extrusion Runner
- Allows sliding and locking at any position
- T-slot clearance: 0.30–0.45 mm (accounting for layer stepping on angled face)
- Lock mechanism: quarter-turn cam, set screw boss, or wedge

## Multi-Material Print-in-Place

### Rigid + Flexible Combination
- Print rigid structural frame in PLA/PETG
- Print flexible gasket or grip in TPU (dual-extrusion or manual switch)
- TPU-to-PLA interface: 0.0 mm clearance (TPU compresses to seal)
- TPU-to-PETG: same, or -0.05 mm undersizing on TPU for preload seal

### Dissolvable Support for Embedded Components
- Use PVA (water soluble) or BVOH as support for internal channels and print-in-place joints
- Soak in warm water 2–6 hours post-print

## Living Assemblies (Mechanisms in One Print)

### Universal Joint (Printed in One Piece)
- Two yokes + crosspiece, assembled in-print
- Crosspiece clearance: 0.4–0.5 mm (PETG)
- Yoke knuckle clearance: 0.3–0.4 mm
- Print axis: crosspiece horizontal for best print quality

### Gear Train (In-Place)
- Module 1.5–2.0 recommended (coarser = more robust)
- Clearance on gear flanks (backlash): 0.15–0.25 mm total
- Print gears with 5–6 top/bottom layers and 4+ perimeters for tooth strength
- Infill 40–60% for gears under moderate load

### Flexible Linkage / Compliant Mechanism
- Use topology-optimization-inspired curved beams
- Minimum wall for reliable flex: 0.8 mm (PETG/Nylon), 0.6 mm (TPU)
- Print in a single orientation — never reorient mid-print

## Structural Patterns for FDM

### Ribs and Gussets
- Rib thickness: 60–70% of wall thickness to reduce sink marks
- Rib height-to-thickness: max 3:1 without risk of print instability
- Gusset angle: 45° for equal XY and Z load distribution

### Honeycomb Infill for Panels
- For large flat panels, print 20–30% gyroid or honeycomb infill
- Use 3–4 perimeters for lateral stiffness
- Add filet radius at panel border (improves layer adhesion under peel loads)

### Column / Pillar Features
- Hollow columns with 2–3 perimeter walls and spiral vase-mode walls are light and stiff
- Minimum column OD: 6 mm for 0.4 mm nozzle with 2 walls
- Internal strengthening ribs at 3–6 mm pitch for taller columns

## Fastener Boss Design

### Heat-Set Insert Boss
```
Boss OD = insert OD × 2.0 (minimum 1.5× for space-constrained parts)
Boss depth = insert length + 0.5 mm clearance at bottom
Boss ID = (see tolerancing guide table)
```

### Self-Tapping Screw Boss
```
Boss OD = screw OD × 2.5
Pilot hole = screw OD × 0.75 (e.g., M3: drill at 2.25 mm)
Boss depth = screw length - 1.5 mm
```

### Through-Hole with Counter-bore
```
Through hole = bolt OD + 0.4 mm (M3: 3.4 mm)
Counter-bore = washer OD + 0.5 mm (M3 washer: 7.0 mm → 7.5 mm bore)
Counter-bore depth = washer thickness + 0.5 mm
```

## Print Orientation Rules for Mechanical Parts

| Feature               | Best Orientation                          |
|-----------------------|--------------------------------------------|
| Snap fit arm          | Arm bends parallel to layers (horizontal)  |
| Living hinge          | Web horizontal (flat to bed)               |
| Gear teeth            | Teeth grow vertically (parallel to Z)      |
| Threaded hole (tapped)| Thread axis vertical                       |
| Tensile member        | Load axis parallel to X or Y (not Z)       |
| Bearing surface       | Bore axis horizontal for rounder hole      |

## Support-Free Design Tips

1. Keep overhangs ≤ 45° from horizontal (or use chamfers instead of undercuts)
2. Use internal chamfers (45°) instead of horizontal shelves
3. Replace bridge > 50 mm with an arch or intermediate support pillar
4. Tilt parts 5–15° to eliminate a single flat overhang without adding supports
5. Use "teardrop" holes (circle + triangle point at top) for horizontal holes that self-support

## Design Checklist Before Printing

- [ ] All clearances set for target material (see tolerancing guide)
- [ ] No unsupported overhangs > 45° (or supports planned)
- [ ] Snap fit arms oriented parallel to bed
- [ ] Living hinges web horizontal
- [ ] Boss walls ≥ 1.5× insert OD
- [ ] Thread/hole diameters compensated for hole undersizing
- [ ] Part fits printer build volume (check with SolidWorks mass properties envelope)
- [ ] Infill and wall count appropriate for load case
