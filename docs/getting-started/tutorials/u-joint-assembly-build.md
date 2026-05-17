# U-Joint Assembly: Build from Scratch Tutorial

Build a complete mechanical U-joint assembly using the Prefab UI and MCP server. This tutorial walks through creating each part from empty files, validating geometry, and assembling components into a fully functional joint.

**Target:** `C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\UJoint.SLDASM`

**Parts to build:**

- Yoke_male
- Yoke_female  
- Spider (cross)
- Pin
- Crank_shaft
- Crank_arm
- Crank_knob
- Bracket (mounting)

## Prerequisites

- SolidWorks 2019+ installed and launched at least once
- MCP server running: `.\.venv\Scripts\python.exe -m solidworks_mcp.server`
- MCP server connected (see [SolidWorks as Code](../solidworks-as-code.md) for session setup)
- **No pre-made parts** — you will create everything from scratch

## Phase 1: Setup and Part Planning

### Step 1: Start New Design

1. Open the Prefab UI dashboard.
2. Click **New Design** to start a blank session.
3. Enter the design goal:

```
Build a complete U-joint mechanical assembly from scratch. 
Assembly must include: Yoke_male, Yoke_female, Spider, Pin, 
Crank_shaft, Crank_arm, Crank_knob, Bracket. 
All parts must allow smooth rotation around the drive axis.
```

1. Enter manufacturing assumptions:

```
Steel/aluminum parts: 0.1mm nominal tolerances where mating.
Yokes and spider: rotational symmetry required.
Pin: ∅6mm (nominal) with ±0.05mm fit tolerance.
Assembly constraint: fully defined, no over-constraint.
```

1. Click **Approve Brief**.

### Step 2: Get Part Specifications

**Prompt (in Prefab UI design-goal or your LLM):**

```
Analyze the U-joint assembly structure and provide a build order 
and critical dimensions for each part:
- Part name
- Feature plan (sketch → extrude → refinements)
- Critical dimensions
- Mating interfaces (holes, bores, surfaces)
- Print orientation preference (if 3D-printed variant)

Focus on:
1. Yoke_male: rectangular outer profile, center bore for pin, drive flange connection
2. Yoke_female: same profile, accepts male yoke and spider
3. Spider: cross-shaped central hub, four bores for pins
4. Pin: ∅6mm shaft, length to bridge yoke pair
5. Crank_shaft: long drive shaft with yoke flange at one end
6. Crank_arm: lever arm for manual actuation
7. Crank_knob: grip handle at end of arm
8. Bracket: mounting base to attach assembly to frame
```

**Expected output:** Ordered build sequence and part-by-part geometry rules.

## Phase 2: Build Individual Parts

### Prompt Template for Each Part

For each part, use this template in the Prefab UI or direct MCP call:

```
**Part: [NAME]**

Create a new SolidWorks part named [NAME].SLDPRT with:

Feature plan:
- [Sketch1]: [profile description]
- [BaseExtrude]: [extrusion depth and direction]
- [Sketch2]: [holes/refinements]
- [RefineFeature]: [any additional details]

Critical dimensions:
- [DIM1]: [value with tolerance]
- [DIM2]: [value with tolerance]
- [DIM3]: [value with tolerance]

Mating interfaces:
- [HOLE/BORE]: diameter [value], location [reference]
- [SURFACE]: face reference for assembly mate

Rules:
- Save to docs/getting-started/tutorials/parts/[NAME].SLDPRT
- Validate geometry before export
- Export isometric PNG as [NAME]_isometric.png
- Report final feature tree order
```

### Part 1: Bracket (Exact Sample Match)

**Prompt:**

```
Build Bracket.SLDPRT from scratch and match the U-Joint sample bracket exactly.

Ensure all sketches are properly dimensioned using the 
Reference model:
- C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\bracket.sldprt

Use mm units and keep this exact feature order:
1. Sketch1
2. Base-Extrude-Thin
3. Sketch2
4. Cut-Extrude1

Sketch1 on Front Plane (connected lines in this order):
- (0.00, 0.00) -> (0.00, 82.55)
- (0.00, 82.55) -> (-57.15, 82.55)
- (-57.15, 82.55) -> (-77.216, 27.494)
- (-77.216, 27.494) -> (-44.45, 0.00)

Base-Extrude-Thin settings:
- Mid-plane depth: 38.10
- Thin-wall thickness: 6.35
- Auto-fillet corners: ON
- Corner radius: 3.175

Sketch2 on top planar face (offset from Top Plane at 88.90 if face selection is unstable):
- Centerline: (0.00, 0.00) -> (-57.15, 0.00)
- Hole circle center: (-44.45, 0.00)
- Hole diameter: 12.70

Cut-Extrude1:
- Blind depth: 10.00

Export isometric PNG to validate geometry before proceeding.
```

**Validation checklist:**

- [ ] Sketch1 coordinates match the listed points
- [ ] Base-Extrude-Thin uses 38.10 depth and 6.35 wall thickness
- [ ] Sketch2 hole center and diameter match exactly
- [ ] Cut-Extrude1 depth is 10.00
- [ ] Feature tree is exactly Sketch1 -> Base-Extrude-Thin -> Sketch2 -> Cut-Extrude1
- [ ] Isometric PNG captured and saved
- [ ] Isometric PNG visually matches the sample bracket

### Part 2: Yoke_male

**Prompt:**

```
Build Yoke_male.SLDPRT from scratch.

Geometry:
- Main body: rectangular profile 80mm x 40mm, extruded 8mm
- Two parallel arms extending upward: each 60mm tall, 15mm wide, 8mm thick
- Center bore between arms: ∅8mm diameter, full height
- Flange mount on bottom: ∅60mm circular pad, 3mm tall
- Four corner fillets on arms: 1mm radius
- Four clearance holes on flange (M4): arranged in ∅50mm circle

Feature sequence:
1. Sketch1: main body rectangle (80x40mm)
2. BaseExtrude: extrude 8mm up
3. Sketch2: upper arms profile (two 60x15mm boxes)
4. ArmsExtrude: extrude 52mm up (total arm height 60mm)
5. Sketch3: ∅8mm center bore
6. CenterBore: cut extrude through arms
7. Sketch4: ∅60mm flange circle on bottom
8. FlangeExtrude: extrude 3mm down
9. Sketch5: four ∅4.2mm holes on ∅50mm circle
10. FlangeHoles: cut extrude through flange
11. FilletCorners: 1mm fillet on arm edges

Export isometric PNG.
```

**Validation checklist:**

- [ ] Main body 80 x 40 x 8 mm
- [ ] Two arms 60mm tall, 15mm wide
- [ ] Center bore ∅8mm full height
- [ ] Flange ∅60mm x 3mm on bottom
- [ ] Four M4 holes on flange (∅50mm circle)
- [ ] All corners filleted 1mm
- [ ] Feature tree in correct sequence

### Part 3: Yoke_female

**Prompt:**

```
Build Yoke_female.SLDPRT from scratch. Geometry is identical to Yoke_male.

Geometry:
- Main body: rectangular profile 80mm x 40mm, extruded 8mm
- Two parallel arms extending upward: each 60mm tall, 15mm wide, 8mm thick
- Center bore between arms: ∅8mm diameter, full height
- Flange mount on bottom: ∅60mm circular pad, 3mm tall
- Four corner fillets on arms: 1mm radius
- Four clearance holes on flange (M4): arranged in ∅50mm circle

Feature sequence: (identical to Yoke_male)
1. Sketch1: main body rectangle (80x40mm)
2. BaseExtrude: extrude 8mm up
3. Sketch2: upper arms profile
4. ArmsExtrude: extrude 52mm up
5. Sketch3: ∅8mm center bore
6. CenterBore: cut extrude
7. Sketch4: ∅60mm flange
8. FlangeExtrude: extrude 3mm down
9. Sketch5: four ∅4.2mm holes
10. FlangeHoles: cut extrude
11. FilletCorners: 1mm fillet

Export isometric PNG.
```

**Validation checklist:**

- [ ] Geometry matches Yoke_male
- [ ] Both parts have identical arm heights and bore sizes
- [ ] Both flanges have same hole pattern

### Part 4: Spider (Cross Hub)

**Prompt:**

```
Build Spider.SLDPRT from scratch.

Geometry:
- Center cube: 12mm x 12mm x 12mm
- Four radial arms extending from cube faces: each 50mm long, 8mm x 8mm cross-section
- Four clearance bores: ∅6.2mm diameter, one at end of each arm
- Center boss: ∅6mm + 2mm height, on cube top for pin alignment

Feature sequence:
1. Sketch1: center cube 12x12x12mm
2. BaseExtrude: extrude 12mm
3. Sketch2: four arm profiles (cross profile 8x8mm at four faces)
4. ArmExtrudes: extrude each 50mm radially
5. Sketch3: four ∅6.2mm bore locations on arm ends
6. ArmBores: cut extrude 6mm depth on each arm
7. Sketch4: ∅6mm center boss top
8. CenterBoss: extrude 2mm up on cube top
9. FilletEdges: 0.5mm fillet on arm transitions

Export isometric PNG.
```

**Validation checklist:**

- [ ] Center cube 12 x 12 x 12 mm
- [ ] Four arms 50mm long, 8mm x 8mm
- [ ] Four bores ∅6.2mm at arm ends
- [ ] Center boss ∅6mm x 2mm on top
- [ ] All fillets applied
- [ ] Feature tree matches sequence

### Part 5: Pin

**Prompt:**

```
Build Pin.SLDPRT from scratch.

Geometry:
- Cylindrical shaft: ∅6mm diameter, 40mm length
- Head flange: ∅12mm diameter, 2mm thick, at one end
- Retaining groove (optional): 0.5mm deep around shaft at 5mm from head

Feature sequence:
1. Sketch1: ∅6mm circle on XY plane
2. ShaftExtrude: extrude 40mm along Z
3. Sketch2: ∅12mm circle at one end
4. HeadExtrude: extrude 2mm (head flange)
5. FilletShaft: 0.5mm fillet where head meets shaft

Export isometric PNG.
```

**Validation checklist:**

- [ ] Shaft ∅6mm x 40mm length
- [ ] Head flange ∅12mm x 2mm
- [ ] Fillet at shaft-head junction
- [ ] Feature tree correct

### Part 6: Crank_shaft

**Prompt:**

```
Build Crank_shaft.SLDPRT from scratch.

Geometry:
- Main drive shaft: ∅10mm diameter, 120mm length
- Yoke mounting flange at one end: ∅40mm diameter, 5mm thick
- Four clearance holes on flange (M4): arranged in ∅30mm circle
- Center bore through flange: ∅10mm (for main shaft)

Feature sequence:
1. Sketch1: ∅10mm circle
2. ShaftExtrude: extrude 120mm
3. Sketch2: ∅40mm circle at one end
4. FlangeExtrude: extrude 5mm
5. Sketch3: center ∅10mm bore on flange
6. CenterBore: cut extrude through flange
7. Sketch4: four ∅4.2mm holes on ∅30mm circle
8. FlangeHoles: cut extrude through flange

Export isometric PNG.
```

**Validation checklist:**

- [ ] Shaft ∅10mm x 120mm
- [ ] Flange ∅40mm x 5mm
- [ ] Center bore ∅10mm through flange
- [ ] Four M4 holes on flange

### Part 7: Crank_arm

**Prompt:**

```
Build Crank_arm.SLDPRT from scratch.

Geometry:
- Base pad: 60mm long, 12mm wide, 8mm tall
- Connection to crank_shaft: top end has ∅10mm bore
- Grip section at bottom: 30mm x 12mm x 20mm tall
- Two corner fillets: 2mm radius on grip edges

Feature sequence:
1. Sketch1: 60mm x 12mm rectangle
2. BaseExtrude: extrude 8mm
3. Sketch2: ∅10mm bore at top end
4. ShaftBore: cut extrude through thickness
5. Sketch3: grip section 30x12x20mm on base
6. GripExtrude: extrude 20mm up
7. FilletGrip: 2mm fillet on grip edges

Export isometric PNG.
```

**Validation checklist:**

- [ ] Arm 60mm long, 12mm wide
- [ ] Shaft bore ∅10mm at connection end
- [ ] Grip section 30 x 12 x 20 mm

### Part 8: Crank_knob

**Prompt:**

```
Build Crank_knob.SLDPRT from scratch.

Geometry:
- Main knob: ∅25mm sphere or rounded cube (choose sphere for simplicity)
- Connection post: ∅6mm diameter, 15mm height
- Base flange: ∅10mm diameter, 3mm thick (on connection post bottom)

Feature sequence:
1. Sketch1: ∅25mm circle on XY plane (if using sphere)
2. KnobRevolved: revolve 180° around XY to create sphere
   OR KnobExtrude: extrude ∅25mm cylinder 25mm if using rounded cube
3. Sketch2: ∅6mm circle on bottom face
4. PostExtrude: extrude 15mm down
5. Sketch3: ∅10mm circle at post bottom
6. FlangeExtrude: extrude 3mm down
7. FilletAll: 1mm fillet on all edges

Export isometric PNG.
```

**Validation checklist:**

- [ ] Knob ∅25mm round shape
- [ ] Connection post ∅6mm x 15mm
- [ ] Flange ∅10mm x 3mm at base
- [ ] All edges filleted

## Phase 3: Assembly Build

### Prompt: Build UJoint Assembly

```
Create assembly UJoint.SLDASM from scratch.

Parts to insert:
1. Bracket.SLDPRT - fixed/grounded base
2. Crank_shaft.SLDPRT - insert into Bracket boss
3. Yoke_male.SLDPRT - attach to crank_shaft flange
4. Yoke_female.SLDPRT - position parallel to yoke_male
5. Spider.SLDPRT - insert between yokes
6. Pin.SLDPRT (qty 4) - connect spider to yokes
7. Crank_arm.SLDPRT - attach to crank_shaft free end
8. Crank_knob.SLDPRT - attach to crank_arm grip

Assembly rules:
- Ground Bracket to origin
- Concentric mate: crank_shaft bore to bracket M8 boss
- Coincident mate: yoke_male flange to crank_shaft flange (coplanar)
- Concentric mate: spider center bore to yoke_male center bore
- Concentric mate: spider to yoke_female center bore
- Pin mates: four pins bridge yoke arms to spider arm bores (concentric)
- Concentric mate: crank_arm bore to crank_shaft free end
- Concentric mate: crank_knob to crank_arm grip section

Validation:
- Report total mate count
- Confirm assembly is fully defined (all DOFs constrained)
- No interference detected between parts
- Joints rotate smoothly (simulated or inspected)
- Export isometric PNG of full assembly

Export:
- Save as UJoint.SLDASM
- Export assembly isometric PNG
```

**Validation checklist:**

- [ ] All 8 parts inserted
- [ ] Assembly fully defined
- [ ] No interference warnings
- [ ] Rotational joints move freely
- [ ] Final assembly PNG captured

## Phase 4: Validation and Export

### Prompt: Final Assembly Validation

```
Perform final validation of UJoint.SLDASM:

Checklist:
- [ ] All 8 parts present in assembly tree
- [ ] All mates are coincident/concentric (no over-constraints)
- [ ] Assembly rebuild succeeds without errors
- [ ] No interference between components
- [ ] Crank_shaft rotates 360° freely
- [ ] Spider rotates 360° between yokes
- [ ] Pin connections are rigid
- [ ] Bracket is fixed to origin
- [ ] All parts have correct feature trees (no extra/missing features)

Generate report:
- Assembly statistics (part count, mate count)
- Feature tree for each part
- Mass properties if material assignments available
- Export images: isometric view from three angles (0°, 45°, 90°)
- Final pass/fail verdict with any corrective actions needed
```

## Troubleshooting

**Issue:** Part bore diameter too large, pin moves freely

→ Re-run Prompt for that part, specify bore tolerance -0.1mm (tight fit)

**Issue:** Assembly fully constrained but components don't articulate

→ Check mate types; replace coincident with concentric on rotation axes

**Issue:** Feature tree has extra sketches or features

→ Re-run part build prompt, emphasize "only use features in this exact sequence"

## Next Steps

After completing this tutorial:

- Export each part and assembly to STL for 3D printing (if needed)
- Modify dimensions for your application (bearing sizes, flange spacing, etc.)
- Add material properties and compute mass
- Use the assembly as a template for other drive mechanisms

---

**Related docs:**

- [SolidWorks as Code](../solidworks-as-code.md)
- [Tool Catalog](../../user-guide/tool-catalog/index.md)
- [Integration Testing](../../user-guide/integration-testing.md)
