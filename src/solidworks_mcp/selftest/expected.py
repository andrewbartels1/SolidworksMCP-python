"""The selftest's hand calculations: every value it expects, and why.

Lengths are mm, volumes mm³. The block is sketched on the Top Plane, so in
model axes it spans x -20..20, y 0..10 (the extrude) and z -10..10.
"""

from __future__ import annotations

import math

#: Volume within 0.01 % of the hand calculation.
VOLUME_TOLERANCE = 1e-4
#: Lengths within 0.01 mm.
LENGTH_TOLERANCE_MM = 0.01

# The block: a 40 x 20 mm rectangle centred on the origin, extruded 10 mm.
BLOCK_X_MM, BLOCK_Z_MM, BLOCK_HEIGHT_MM = 40.0, 20.0, 10.0
BLOCK_BOX_MM = [BLOCK_X_MM, BLOCK_HEIGHT_MM, BLOCK_Z_MM]
BLOCK_VOLUME_MM3 = BLOCK_X_MM * BLOCK_Z_MM * BLOCK_HEIGHT_MM  # 8,000

# The hole: a Ø10 circle at the origin, cut through all.
HOLE_RADIUS_MM = 5.0
HOLE_VOLUME_MM3 = BLOCK_VOLUME_MM3 - math.pi * HOLE_RADIUS_MM**2 * BLOCK_HEIGHT_MM
# = 8,000 - π·5²·10 = 7,214.60

# The fillet: r 2 on the 40 mm top edge at z = 10, picked by its midpoint
# (in metres, as the tool takes edge points). A fillet of radius r along an
# edge of length L removes the corner square less a quarter circle:
# (1 - π/4)·r²·L.
FILLET_RADIUS_MM = 2.0
FILLET_EDGE = "0,0.01,0.01"
FILLET_VOLUME_MM3 = (
    HOLE_VOLUME_MM3 - (1 - math.pi / 4) * FILLET_RADIUS_MM**2 * BLOCK_X_MM
)
# = 7,214.602 - 34.336 = 7,180.27

# The pin: a Ø9.5 circle extruded 20 mm; 0.25 mm clearance in the Ø10 hole.
PIN_RADIUS_MM = 4.75
PIN_LENGTH_MM = 20.0
PIN_BOX_MM = [2 * PIN_RADIUS_MM, PIN_LENGTH_MM, 2 * PIN_RADIUS_MM]
PIN_VOLUME_MM3 = math.pi * PIN_RADIUS_MM**2 * PIN_LENGTH_MM  # 1,417.64

# The assembly: the pin concentric in the hole, its bottom flush with the
# block's. Face points are in each part's own coordinates, in mm.
HOLE_WALL_POINT = [HOLE_RADIUS_MM, BLOCK_HEIGHT_MM / 2, 0.0]
PIN_SIDE_POINT = [PIN_RADIUS_MM, PIN_LENGTH_MM / 2, 0.0]
BLOCK_BOTTOM_POINT = [-15.0, 0.0, 0.0]  # clear of the hole
PIN_BOTTOM_POINT = [0.0, 0.0, 0.0]
COMPONENT_COUNT = 2
MATE_COUNT = 2

# The drawing: one isometric view of the block.
DRAWING_VIEW_COUNT = 1
