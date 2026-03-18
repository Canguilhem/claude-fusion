# Diagonal Split with Perpendicular Inserts - Strategy Analysis

## Overview

This document explains the locking strategy implemented in `DiagonalSplitWithInserts.py`: splitting a U-channel with a diagonal plane and using perpendicular inserts to lock the pieces together.

## Strategy Components

### 1. **Diagonal Split (Yellow Cut Plan)**

**What it does:**
- Splits the U-channel at an angle (typically 15-30°) instead of perpendicular
- Creates mating surfaces that are angled relative to the track length

**Advantages:**
- ✅ **Easy Assembly**: Pieces can slide together along the diagonal angle
- ✅ **Self-Aligning**: The diagonal cut helps guide pieces into correct position
- ✅ **Increased Surface Area**: Diagonal cut provides more contact area than perpendicular cut
- ✅ **Shear Resistance**: Diagonal surfaces resist forces better than perpendicular cuts

**Disadvantages:**
- ⚠️ **Not Self-Locking**: Pieces can still slide apart along the diagonal
- ⚠️ **Requires Additional Locking**: Needs inserts or other mechanism to prevent separation

### 2. **Perpendicular Inserts (Red Inserts)**

**What it does:**
- Creates cylindrical holes through both pieces, perpendicular to the diagonal split
- Inserts pins/dowels through these holes to lock pieces together

**Advantages:**
- ✅ **Strong Lock**: Prevents separation perpendicular to sliding direction
- ✅ **Removable**: Inserts can be removed for disassembly
- ✅ **Simple Manufacturing**: Standard cylindrical holes and pins
- ✅ **Reliable**: Mechanical lock that doesn't depend on friction or tolerances

**Disadvantages:**
- ⚠️ **Requires Access**: Need access to insert pins (may not work for all designs)
- ⚠️ **Additional Parts**: Requires separate insert pins to be manufactured

## Combined Strategy: Why It Works

The combination of **diagonal split + perpendicular inserts** creates a **dual-locking mechanism**:

1. **Primary Lock (Diagonal Split)**:
   - Enables easy sliding assembly
   - Provides large contact area for strength
   - Resists forces along the track direction

2. **Secondary Lock (Perpendicular Inserts)**:
   - Prevents separation perpendicular to sliding direction
   - Provides removable connection
   - Adds redundancy for critical applications

## Comparison to Other Strategies

| Strategy | Assembly Ease | Locking Strength | Removability | Manufacturing Complexity |
|----------|---------------|-----------------|--------------|-------------------------|
| **Diagonal + Inserts** | ⭐⭐⭐⭐ Easy | ⭐⭐⭐⭐⭐ Very Strong | ⭐⭐⭐⭐ Removable | ⭐⭐⭐ Moderate |
| Simple Perpendicular Split | ⭐⭐⭐ Moderate | ⭐⭐ Weak | ⭐⭐⭐⭐ Removable | ⭐⭐ Simple |
| Dovetail Joint | ⭐⭐ Difficult | ⭐⭐⭐⭐ Strong | ⭐⭐ Permanent | ⭐⭐⭐⭐ Complex |
| Tapered Dovetail | ⭐⭐⭐ Moderate | ⭐⭐⭐⭐⭐ Very Strong | ⭐ Permanent | ⭐⭐⭐⭐ Complex |

## Custom Cutter Shapes

The script supports using **custom cutter shapes** instead of a simple diagonal plane:

### Wavy/Complex Profiles (Images 2 & 3)

**Advantages:**
- ✅ **Unique Locking**: Custom shapes create unique interlocking patterns
- ✅ **Aesthetic**: Can create decorative or branded joint patterns
- ✅ **Increased Security**: Complex shapes are harder to replicate
- ✅ **Custom Fit**: Can optimize shape for specific load requirements

**Implementation:**
- Use `USE_CUSTOM_CUTTER_SHAPE = True`
- Adjust `CUSTOM_SHAPE_AMPLITUDE` and `CUSTOM_SHAPE_FREQUENCY` for wavy patterns
- Can be extended to use splines, arcs, or any arbitrary profile

**Example Use Cases:**
- Puzzle-piece style joints
- Branded/logo-shaped cuts
- Optimized stress distribution patterns
- Decorative track connections

## Recommended Parameters

### For Standard Diagonal Split:
```python
DIAGONAL_ANGLE = 15.0      # Good balance: easy assembly, good strength
SPLIT_POSITION_X = 2.5     # Center of track (or wherever split needed)
INSERT_DIAMETER = 0.3      # 3mm pin (adjust based on wall thickness)
INSERT_COUNT = 2           # One per branch (left and right walls)
```

### For Custom Shapes:
```python
USE_CUSTOM_CUTTER_SHAPE = True
CUSTOM_SHAPE_AMPLITUDE = 0.1    # 1mm wave amplitude
CUSTOM_SHAPE_FREQUENCY = 2.0    # 2 waves along length
```

## Assembly Instructions

1. **Prepare Pieces**: Ensure both pieces are clean and deburred
2. **Align**: Position pieces so diagonal surfaces align
3. **Slide**: Slide pieces together along the diagonal angle
4. **Insert Pins**: Once fully engaged, insert pins through holes
5. **Verify**: Check that pins are fully seated and pieces are locked

## Manufacturing Considerations

### 3D Printing:
- ✅ Works well with FDM and SLA
- ⚠️ Ensure holes are large enough for printer resolution
- ⚠️ Consider support material for overhangs on diagonal cut

### CNC Machining:
- ✅ Excellent for precise diagonal cuts
- ✅ Can create complex custom shapes easily
- ✅ Holes can be drilled accurately

### Laser Cutting:
- ⚠️ Limited to 2D cuts (would need multiple passes)
- ✅ Good for flat inserts

## Conclusion

The **diagonal split + perpendicular inserts** strategy is an excellent choice for:

- ✅ **Modular track systems** (like race tracks)
- ✅ **Removable connections** (need to disassemble)
- ✅ **Strong mechanical locks** (safety-critical applications)
- ✅ **Easy assembly** (user-friendly)

It combines the best of both worlds: easy assembly from the diagonal cut, and strong locking from the perpendicular inserts.
