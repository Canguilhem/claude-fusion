# TrackAutoCutter - Fusion 360 Add-In

## Overview

TrackAutoCutter is a Fusion 360 script that automatically cuts a race track model into 3D-printable pieces with interlocking dovetail connectors.

## Use Case

Creating a **backlit LED wall mural** of a race track circuit:
- Track is a **U-channel profile** (like a gutter) swept along a path
- The U-channel cavity holds LED strips
- The track is mounted on a wall with the **solid face visible** and **cavity facing the wall**
- Track is too long for a single 3D print, so it must be cut into pieces
- Pieces connect with **hidden dovetail joints** inside the U-channel (invisible from front)

```
Cross-section view:

    ┌─────────────┐   ← cavity (LEDs go here, faces wall)
    │             │
    │   ┌─────┐   │   ← dovetail connector (hidden inside)
    │   │▓▓▓▓▓│   │
    ├───┴─────┴───┤   ← inner floor surface
    │█████████████│   ← floor thickness (solid)
    └─────────────┘   ← outer face (visible when mounted)
```

## Track Geometry

### Profile Parameters
- **TRACK_WIDTH**: Total outer width of the U-channel
- **TRACK_HEIGHT**: Total height (depth) of the U-channel
- **WALL_THICKNESS**: Thickness of the U-channel walls (floor and sides)
- **SHELL_THICKNESS**: If using Fusion's Shell command, this is the wall thickness

### Derived Dimensions
- Inner cavity width = TRACK_WIDTH - (2 × WALL_THICKNESS)
- Inner cavity depth = TRACK_HEIGHT - WALL_THICKNESS

## Dovetail Connector Design

### Requirements
1. **Hidden**: Connector must be inside the U-channel cavity (not visible from outside)
2. **Structural**: Must provide mechanical interlocking between pieces
3. **Printable**: Must fit within 3D printer tolerances
4. **Joined**: Must be part of the track piece (not a separate body)

### Dovetail Parameters
- **DOVETAIL_WIDTH**: Width at the wide end of the trapezoid
- **DOVETAIL_NARROW**: Width at the narrow end
- **DOVETAIL_HEIGHT**: Height of the trapezoid profile
- **DOVETAIL_DEPTH**: How far the dovetail protrudes into the adjacent piece
- **TOLERANCE**: Gap for fit (typically 0.15-0.2mm for FDM printing)

### Positioning
The dovetail is positioned on the **inner floor surface** of the U-channel:
- Offset from centerline = (TRACK_HEIGHT / 2) - WALL_THICKNESS - (DOVETAIL_HEIGHT / 2)
- This places the dovetail resting on the inner floor, inside the cavity

## Workflow

### 1. Create Track Body
```
1. Create a sketch with the U-channel profile (rectangle with inner rectangle cut out)
2. Create a path sketch (the track centerline)
3. Use Sweep: profile along path
4. Result: solid U-channel track body
```

### 2. Run TrackAutoCutter
```
1. Scripts and Add-Ins → TrackAutoCutter
2. Enter max piece length (based on printer bed size)
3. Select the track body
4. Select the path sketch
5. Choose whether to add dovetail connectors
6. Script cuts the track and adds connectors at each junction
```

### 3. Export for Printing
```
1. Right-click each piece component
2. Save As Mesh → STL format
3. Print each piece
4. Assemble using dovetail joints
```

## Parameters Reference

```python
# Track Profile (cm)
TRACK_WIDTH = 1.5         # Total outer width
TRACK_HEIGHT = 1.0        # Total height/depth
WALL_THICKNESS = 0.2      # Wall/floor thickness

# Dovetail Connector (cm)
DOVETAIL_WIDTH = 0.5      # Wide end
DOVETAIL_NARROW = 0.3     # Narrow end
DOVETAIL_HEIGHT = 0.3     # Profile height
DOVETAIL_DEPTH = 0.25     # Protrusion depth
TOLERANCE = 0.015         # Fit tolerance

# Cutting
MAX_PIECE_LENGTH = 23.0   # Based on printer bed (cm)
```

## Troubleshooting

### Dovetails are separate bodies (not joined)
- The dovetail profile doesn't intersect with track solid material
- Reduce DOVETAIL_Y_OFFSET or check track dimensions
- Ensure dovetail is positioned on a wall, not in empty cavity

### Dovetails visible from outside
- DOVETAIL_Y_OFFSET is wrong direction or too small
- Calculate correct offset based on track dimensions
- Offset should place dovetail on INNER surface of floor

### Pieces don't fit together
- Increase TOLERANCE (try 0.02 cm)
- Check that dovetail and slot are aligned (same position)
- Verify extrusion directions are correct

### Wrong number of pieces
- Check total track length and max piece length
- Expected pieces = ceil(total_length / max_piece_length)
- Multiple bodies in original track will multiply piece count

## Files

- `TrackAutoCutter.py` - Main script
- `TrackAutoCutter.manifest` - Add-in manifest
- `README.md` - This documentation

## Future Improvements

- [ ] Auto-detect track profile dimensions from geometry
- [ ] Support for multiple dovetails per junction (for wider tracks)
- [ ] Option for different connector types (pins, puzzle joints)
- [ ] Automatic shell operation before cutting
- [ ] Preview mode before committing cuts
