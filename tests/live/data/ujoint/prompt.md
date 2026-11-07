I want to build a small hand-cranked universal joint in SolidWorks: eight parts, a crank sub-assembly, and the main assembly. It's a mechanism: turning the knob turns the crank, which drives the joint through an angle, so the assemblies must still move the way described in sections 9 and 10. Please reason through each part before you start drawing, check every part once it's built, and tell me if something can't be done with the tools rather than guessing. All sizes are in millimetres (the original was drawn in inches, so the numbers are odd). SolidWorks' Y axis is up. Save every part and both assemblies in this folder, with the names given below.

**1. bracket.SLDPRT: a bent plate, 6.35 mm thick and 38.1 mm wide.**
Seen from the side (sketch on the Right plane, Y up, Z towards the front), the inside outline of the bend is an open chain:
- a back wall going straight up 82.55 mm from the origin;
- from its top, a top arm going forward 57.15 mm;
- from the origin, a bottom foot going forward 44.45 mm;
- from the front of the foot, a lip rising at 40° for 42.77 mm (it ends 27.49 mm up and 77.22 mm forward).
The 6.35 mm thickness is on the outside of that outline: above the top arm, behind the back wall and under the foot. The 38.1 mm width is centred on the Right plane. Drill a 12.7 mm hole straight down through the top arm and on through the foot below it (one cut, both plates), centred across the width and 38.1 mm forward of the back wall's inside face.

**2. Yoke_male.SLDPRT: a fork with a stub shaft.**
- Start with a 38.1 mm diameter cylinder, 47.625 mm tall, standing on the Top plane.
- Its bottom becomes a fork with two ears. Each ear is 19.05 mm wide and 8.89 mm thick, and the gap between them is 20.32 mm, centred. Each ear has a rounded end: a full radius of 9.525 mm, centred 9.525 mm above the bottom. Where an ear meets the solid part of the cylinder, round the shoulder with a 9.525 mm radius, so the solid part starts 29.21 mm above the bottom.
- Drill a 9.525 mm cross hole through both ears at the centre of their rounded ends, square to the ears.
- On top, add a 12.7 mm diameter stub, 19.05 mm tall, on the cylinder's axis. Chamfer its top edge 1.27 mm at 60°.
- Cut a flat on the stub, 12.7 mm long down from its top. The flat is 4.7625 mm from the axis, so it is 1.5875 mm deep.

**3. Yoke_female.SLDPRT:** the same 38.1 x 47.625 mm cylinder with the same fork and the same cross hole as the male yoke, but no stub. Instead, a 9.525 mm hole goes all the way through along its axis.

**4. spider.SLDPRT:** a 19.05 mm cube centred on the origin. It has two 9.525 mm holes, both through its centre: one front to back, and one left to right.

**5. pin.SLDPRT:** a 9.398 mm diameter rod, 38.1 mm long.

**6. crank-shaft.SLDPRT: a 12.573 mm diameter shaft, 40 mm long, standing on the Top plane.**
- Around its bottom 15.875 mm, a collar 18.923 mm in diameter.
- A 4.763 mm fillet where the collar meets the shaft, and a 4.763 mm fillet on the collar's top outer edge.
- In the bottom, a D-shaped socket 12.7 mm deep. It is a 12.954 mm circle with a flat 4.889 mm from the axis, to take the male yoke's stub.
- A 2.381 mm cross hole through the collar wall, square to the socket's flat and 6.35 mm up from the bottom.
- At the top, a matching flat 6.35 mm long, 4.889 mm from the axis.
- A 0.794 mm x 45° chamfer on the top end.

**7. crank-arm.SLDPRT: a flat bar, 75 x 19.05 x 6.35 mm.**
- Near one end, a 12.7 mm D-hole centred 9.525 mm from the end and on the bar's centreline. Its flat is 4.889 mm from the hole's centre, towards that end. It fits the shaft's top flat.
- Near the other end, a 4.763 mm hole 9.525 mm from that end, also on the centreline.

**8. crank-knob.SLDPRT: a mushroom-shaped knob, revolved 360° about the vertical axis.** Going up from the bottom, its profile has:
- a 4.572 mm diameter shank, 6.35 mm long;
- a step out to a 9.525 mm diameter;
- a concave quarter-round of radius 6.35 mm that flares out to 22.225 mm diameter, 12.7 mm up;
- a convex half-round of radius 4.7625 mm that reaches 31.75 mm diameter at its widest;
- a flat top 22.225 mm in diameter, 22.225 mm above the bottom.

**9. crank sub.SLDASM:**
- The crank shaft is fixed.
- The crank arm's D-hole goes on the shaft's top flat: the hole is concentric with the shaft, the flats are parallel, and the arm sits on the shoulder where the flat starts. The flats lock the arm to the shaft, so they turn together.
- The knob's shank goes into the arm's small hole, with the knob's step resting on the arm's top face. The knob stays free to spin in its hole, like a handle.

**10. UJoint.SLDASM:**
- The bracket is fixed.
- The male yoke hangs under the bracket's top arm. Its stub goes up through the bracket's hole (concentric), and the top of its cylinder is flat against the underside of the arm. It must stay free to turn in that hole.
- The spider sits centred between the male yoke's ears, with one of its holes lined up with the ears' cross hole. It pivots on that axis.
- The female yoke's ears go around the spider's other hole, centred on the spider. Its top face is parallel to the bracket's sloped lip, so its axis points down and forward. It pivots on the spider and turns about its own axis.
- Put one pin through the male yoke's ears and the spider, and one pin through the female yoke's ears and the spider. Each pin's ends are flush with its yoke's round outside, and each pin turns with its yoke.
- Insert the crank sub-assembly. Its shaft's D-socket goes over the male yoke's stub: concentric, with the flats parallel, and the bottom of the shaft 1 mm above the top of the bracket. The flats lock the crank to the male yoke.
- The result should be a mechanism with one free motion: turning the knob around the crank shaft's axis turns the male yoke, the spider rocks on its pins, and the female yoke turns about its tilted axis. Choose mates that leave exactly those rotations free and lock everything else.

When it's all built, check each part's size and the assembly's component and mate counts, say which rotations your mates leave free, and tell me what you couldn't do.
