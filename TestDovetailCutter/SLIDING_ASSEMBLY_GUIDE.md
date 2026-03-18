# Sliding Assembly Design for U-Shaped Track Pieces

## Overview

This guide explains how to design two U-shaped track pieces that can be assembled by sliding them together, creating a seamless connection that prevents light leaks (important for LED backlit tracks).

## Design Principles

### 1. U-Shape Cross-Section
- **Base (Floor)**: Horizontal bottom surface
- **Left Branch**: Left vertical wall
- **Right Branch**: Right vertical wall
- **Inner Faces**: The surfaces that face each other when pieces connect

### 2. Sliding Assembly Mechanism

When you split a U-channel with a tapered double-arrow cutter, you get:

**Piece 1 (First Half)**:
- Has **SLOTS** (female/recessed) on the cut face
- The slots are shaped like the negative of the cutter profile

**Piece 2 (Second Half)**:
- Has **TONGUES** (male/protruding) on the cut face
- The tongues match the cutter profile shape

### 3. How Sliding Works

```
Before Assembly:
┌─────────┐    ┌─────────┐
│ Piece 1 │    │ Piece 2 │
│  (slot) │    │ (tongue)│
└─────────┘    └─────────┘
     ↓              ↓
   Slide together along X-axis
     ↓              ↓
┌─────────────────────┐
│   Assembled Track    │
│  (interlocked)       │
└─────────────────────┘
```

### 4. Double Arrow Pattern

The double arrow wedged pattern creates:
- **Multiple contact points** for secure connection
- **Self-aligning** - the arrows guide the pieces together
- **Resistance to separation** - the wedge shape locks pieces together

### 5. Taper (Critical for Light Leak Prevention)

The taper angle creates a **locking wedge**:

```
Without Taper (parallel):
┌──┐  ┌──┐  → Light can leak through gaps
│  │  │  │
└──┘  └──┘

With Taper (wedged):
┌──┐  ┌──┐  → Tight fit, no light leaks
│  │╲╱│  │
└──┘  └──┘
```

**How Taper Works**:
- Left profile: arrows offset by `-taper_half`
- Right profile: arrows offset by `+taper_half`
- Creates a wedge that gets tighter as pieces slide together
- Prevents light leaks by ensuring tight contact

## Implementation Details

### Current Code Approach

1. **Create U-Channel**: Standard U-shape profile
2. **Create Cutter**: Double arrow profile with taper
3. **Split Body**: Cut the U-channel in half
4. **Result**: Two interlocking pieces

### Key Parameters

```python
TRACK_WIDTH = 1.5      # Width of U-channel (Y direction)
TRACK_HEIGHT = 1.0     # Height of U-channel (Z direction)
TRACK_LENGTH = 5.0     # Length of track piece (X direction)
WALL_THICKNESS = 0.2   # Thickness of walls and floor
DOVETAIL_DEPTH = 0.15  # How far arrows protrude
TAPER_ANGLE = 5        # Taper angle in degrees
TOLERANCE = 0.015      # Gap for 3D printing fit
```

### Profile Design

The double arrow profile is applied to:
- **Base (floor)**: Z = 0 to t
- **Vertical walls**: Z = t+offset to h-offset (positioned lower/centered)

This ensures:
- Arrows on floor for bottom connection
- Arrows on both vertical branches for side connection
- All surfaces have matching profiles for consistent sliding

## Assembly Process

### Step-by-Step

1. **Create Track Pieces**: Run the script to generate two pieces
2. **Orient Pieces**: Align them so the tongue faces the slot
3. **Slide Together**: Move Piece 2 along X-axis toward Piece 1
4. **Lock**: The taper creates a tight, locked connection

### Visual Guide

```
Side View (XZ plane):
                   
Piece 1 (Slot):        Piece 2 (Tongue):
┌─────────────┐        ┌─────────────┐
│             │        │             │
│  ╱╲  ╱╲    │        │    ╱╲  ╱╲  │
│ ╱  ╲╱  ╲   │        │   ╱  ╲╱  ╲ │
│             │        │             │
└─────────────┘        └─────────────┘
     ↓                        ↓
     └──────────┬─────────────┘
                ↓
        Assembled:
     ┌──────────────────┐
     │                  │
     │  ╱╲  ╱╲  ╱╲  ╱╲ │
     │ ╱  ╲╱  ╲╱  ╲╱  ╲│
     │                  │
     └──────────────────┘
```

## Preventing Light Leaks

### Why Taper is Essential

1. **Tight Fit**: Taper creates progressively tighter fit as pieces slide
2. **No Gaps**: Wedge shape eliminates gaps that would let light through
3. **Consistent Contact**: Double arrows ensure contact at multiple points
4. **Manufacturing Tolerance**: Taper compensates for 3D printing variations

### Tolerance Considerations

- **TOLERANCE = 0.015 cm**: Typical for FDM 3D printing
- **Adjust for your printer**: Test and adjust based on your printer's accuracy
- **Tighter = Better**: Smaller tolerance = less light leak, but harder to assemble

## Tips for Complex Tracks

### For Race Track Circuits (like Spa-Francorchamps)

1. **Multiple Pieces**: Create multiple segments along the track path
2. **Consistent Profile**: Use same cutter profile for all connections
3. **Curved Sections**: The sliding mechanism works even on curved tracks
4. **LED Integration**: Ensure tight fit to prevent light leaks around LEDs

### Design Considerations

- **Track Length**: Longer pieces = fewer connections = less light leak
- **Connection Points**: Minimize number of joints for cleaner appearance
- **Assembly Direction**: Design so pieces slide in one direction (easier assembly)
- **Access**: Ensure you can reach connection points for assembly

## Troubleshooting

### Pieces Won't Slide Together
- Check tolerance - may be too tight
- Verify profiles match exactly
- Ensure pieces are aligned correctly

### Light Leaks at Joints
- Increase taper angle (but not too much - makes assembly harder)
- Decrease tolerance
- Check that arrows are properly positioned on vertical walls

### Pieces Too Loose
- Decrease tolerance
- Increase taper angle slightly
- Check manufacturing accuracy

## Future Enhancements

Potential improvements:
- **Snap-fit features**: Add small bumps for tactile feedback
- **Alignment guides**: Visual markers for easier assembly
- **Variable taper**: Different taper angles for different sections
- **Curved joints**: Support for non-linear sliding paths
