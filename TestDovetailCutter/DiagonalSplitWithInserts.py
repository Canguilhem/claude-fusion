"""
Diagonal Split with Perpendicular Inserts - Test Cutter Script

This script implements a locking strategy:
1. Splits U-channel with a diagonal plane (enables sliding assembly)
2. Creates perpendicular inserts that lock the pieces together

STRATEGY ANALYSIS:
-----------------
✓ Diagonal split: Allows pieces to slide together easily
✓ Perpendicular inserts: Prevent separation perpendicular to sliding direction
✓ Strong mechanical lock: Two mechanisms working together
✓ Good for: Track assembly, modular construction, removable connections

OPTIONAL: Custom cutter shapes (wavy/complex profiles) can be used instead of simple diagonal plane
"""

import adsk.core
import adsk.fusion
import traceback
import math

# ===================== PARAMETERS (cm) =====================

# U-channel dimensions
TRACK_WIDTH = 1.5         # Outer width (Y direction)
TRACK_HEIGHT = 1.0        # Wall height (Z direction)
TRACK_LENGTH = 5.0        # Length (X direction)
WALL_THICKNESS = 0.2      # Wall and floor thickness

# Diagonal split parameters
DIAGONAL_ANGLE = 15.0     # Angle of diagonal cut (degrees)
SPLIT_POSITION_X = 2.5    # X position where split occurs (center = TRACK_LENGTH/2)

# Insert parameters
INSERT_DIAMETER = 0.3     # Diameter of cylindrical insert (cm)
INSERT_LENGTH = 1.0       # Length of insert (extends through both pieces)
INSERT_COUNT = 2          # Number of inserts (one per branch)
INSERT_POSITION_Z = 0.5   # Z position (height) of inserts
INSERT_OFFSET_Y = 0.1     # Offset from inner wall (Y direction)

# Optional: Custom cutter shape (for wavy/complex profiles)
USE_CUSTOM_CUTTER_SHAPE = False  # Set to True to use custom shape instead of simple diagonal
CUSTOM_SHAPE_AMPLITUDE = 0.1     # Amplitude of wavy pattern (if using custom shape)
CUSTOM_SHAPE_FREQUENCY = 2.0     # Frequency of wavy pattern


def create_u_channel(root):
    """Create the base U-channel track."""
    sketches = root.sketches
    extrudes = root.features.extrudeFeatures
    
    # Create U-profile sketch
    sketch = sketches.add(root.yZConstructionPlane)
    sketch.name = "UChannelProfile"
    lines = sketch.sketchCurves.sketchLines
    
    w = TRACK_WIDTH
    h = TRACK_HEIGHT
    t = WALL_THICKNESS
    
    # U-channel profile points
    p1 = adsk.core.Point3D.create(0, 0, 0)
    p2 = adsk.core.Point3D.create(w, 0, 0)
    p3 = adsk.core.Point3D.create(w, h, 0)
    p4 = adsk.core.Point3D.create(w - t, h, 0)
    p5 = adsk.core.Point3D.create(w - t, t, 0)
    p6 = adsk.core.Point3D.create(t, t, 0)
    p7 = adsk.core.Point3D.create(t, h, 0)
    p8 = adsk.core.Point3D.create(0, h, 0)
    
    # Create closed profile
    lines.addByTwoPoints(p1, p2)
    lines.addByTwoPoints(p2, p3)
    lines.addByTwoPoints(p3, p4)
    lines.addByTwoPoints(p4, p5)
    lines.addByTwoPoints(p5, p6)
    lines.addByTwoPoints(p6, p7)
    lines.addByTwoPoints(p7, p8)
    lines.addByTwoPoints(p8, p1)
    
    # Extrude to create U-channel
    ext_input = extrudes.createInput(
        sketch.profiles.item(0),
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(TRACK_LENGTH))
    track_body = extrudes.add(ext_input).bodies.item(0)
    track_body.name = "UChannel"
    
    return track_body


def create_diagonal_split_plane(root, split_x, angle_deg):
    """
    Create a diagonal construction plane for splitting.
    
    The plane is perpendicular to Y-axis and rotated by angle_deg around Y-axis.
    This creates a diagonal cut in the XZ plane.
    """
    planes = root.constructionPlanes
    
    # First create a plane at the split position (perpendicular to X)
    perp_input = planes.createInput()
    perp_input.setByOffset(
        root.yZConstructionPlane,
        adsk.core.ValueInput.createByReal(split_x)
    )
    perp_plane = planes.add(perp_input)
    perp_plane.name = "PerpendicularPlane"
    
    # Create an axis line along Y for rotation
    sketches = root.sketches
    axis_sketch = sketches.add(root.xZConstructionPlane)
    axis_line = axis_sketch.sketchCurves.sketchLines.addByTwoPoints(
        adsk.core.Point3D.create(split_x, -3, 0),
        adsk.core.Point3D.create(split_x, 3, 0)
    )
    
    # Create angled plane
    angled_input = planes.createInput()
    angled_input.setByAngle(
        axis_line,
        adsk.core.ValueInput.createByString(f"{angle_deg} deg"),
        perp_plane
    )
    diagonal_plane = planes.add(angled_input)
    diagonal_plane.name = "DiagonalSplitPlane"
    
    return diagonal_plane


def create_custom_shape_cutter(root, split_x, amplitude, frequency):
    """
    Create a custom wavy/complex shape cutter instead of simple diagonal plane.
    
    This creates a surface with a wavy profile that can be used for splitting.
    The shape is defined by a mathematical function (sine wave) but can be
    customized to any arbitrary profile.
    """
    sketches = root.sketches
    lofts = root.features.loftFeatures
    
    # Create two sketches with wavy profiles (for lofting)
    # Left sketch
    plane_left = root.constructionPlanes.createInput()
    plane_left.setByOffset(root.xZConstructionPlane, adsk.core.ValueInput.createByReal(-0.5))
    plane_left_obj = root.constructionPlanes.add(plane_left)
    
    sketch_left = sketches.add(plane_left_obj)
    sketch_left.name = "CustomShapeLeft"
    
    # Right sketch
    plane_right = root.constructionPlanes.createInput()
    plane_right.setByOffset(root.xZConstructionPlane, adsk.core.ValueInput.createByReal(TRACK_WIDTH + 0.5))
    plane_right_obj = root.constructionPlanes.add(plane_right)
    
    sketch_right = sketches.add(plane_right_obj)
    sketch_right.name = "CustomShapeRight"
    
    # Create wavy profiles
    num_points = 20
    points_left = adsk.core.ObjectCollection.create()
    points_right = adsk.core.ObjectCollection.create()
    
    for i in range(num_points + 1):
        # X position along length
        x_pos = split_x + (i / num_points - 0.5) * TRACK_LENGTH * 0.3
        
        # Z position with wavy pattern
        z_base = TRACK_HEIGHT / 2
        z_offset = amplitude * math.sin(frequency * math.pi * i / num_points)
        z_pos = z_base + z_offset
        
        # Create spline points
        pt_left = adsk.core.Point3D.create(x_pos, 0, z_pos)
        pt_right = adsk.core.Point3D.create(x_pos, 0, z_pos)
        
        points_left.add(pt_left)
        points_right.add(pt_right)
    
    # Create splines
    spline_left = sketch_left.sketchCurves.sketchFittedSplines.add(points_left)
    spline_right = sketch_right.sketchCurves.sketchFittedSplines.add(points_right)
    
    # Loft between the two splines to create surface
    loft_input = lofts.createInput(
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    loft_input.loftSections.add(spline_left)
    loft_input.loftSections.add(spline_right)
    loft_input.isSolid = False  # Create surface, not solid
    
    try:
        loft_feature = lofts.add(loft_input)
        # Return the surface (would need to extract from loft feature)
        return None  # Placeholder - would need to return surface entity
    except:
        return None


def split_u_channel(root, track_body, split_plane_or_surface):
    """
    Split the U-channel using the diagonal plane or custom surface.
    
    Returns: (piece1, piece2) - the two resulting bodies
    """
    splits = root.features.splitBodyFeatures
    
    # Create split input
    split_input = splits.createInput(track_body, split_plane_or_surface, True)
    
    try:
        split_result = splits.add(split_input)
        pieces = list(split_result.bodies)
        
        if len(pieces) != 2:
            return (None, None)
        
        # Name the pieces
        pieces[0].name = "Piece1"
        pieces[1].name = "Piece2"
        
        return (pieces[0], pieces[1])
    except Exception as e:
        print(f"Split failed: {e}")
        return (None, None)


def create_insert_holes(root, piece1, piece2, insert_diameter, insert_length, insert_z, insert_y_offset):
    """
    Create holes in both pieces for the perpendicular inserts.
    Holes are drilled perpendicular to the split plane (along Y-axis).
    
    Returns: List of created hole features
    """
    sketches = root.sketches
    extrudes = root.features.extrudeFeatures
    
    holes_created = []
    
    # Create holes in both pieces
    for piece_idx, piece in enumerate([piece1, piece2], 1):
        # Get bounding box to find center
        bb = piece.boundingBox
        center_x = (bb.minPoint.x + bb.maxPoint.x) / 2
        
        # Find the split face (diagonal face) - this is where we'll drill perpendicular
        split_face = None
        for face in piece.faces:
            geom = face.geometry
            if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                normal = geom.normal
                # Split face should be roughly diagonal (has X and Z components)
                if abs(normal.x) > 0.3 and abs(normal.z) > 0.3:
                    split_face = face
                    break
        
        if split_face is None:
            # Fallback: find any large face
            largest_face = None
            largest_area = 0
            for face in piece.faces:
                area = face.area
                if area > largest_area:
                    largest_area = area
                    largest_face = face
            split_face = largest_face
        
        if split_face is None:
            print(f"Warning: Could not find suitable face for insert hole in piece {piece_idx}")
            continue
        
        # Create sketch on the split face
        sketch = sketches.add(split_face)
        sketch.name = f"InsertHole_Piece{piece_idx}"
        
        # Get a point on the face and convert to sketch coordinates
        face_point = split_face.pointOnFace
        # Adjust Y position for offset
        hole_center_world = adsk.core.Point3D.create(
            center_x,
            face_point.y + insert_y_offset,
            insert_z
        )
        hole_center_sketch = sketch.modelToSketchSpace(hole_center_world)
        
        # Create circle for hole
        try:
            circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
                adsk.core.Point3D.create(hole_center_sketch.x, hole_center_sketch.y, 0),
                insert_diameter / 2
            )
            
            # Extrude cut to create hole (perpendicular to face, into the piece)
            if sketch.profiles.count > 0:
                profile = sketch.profiles.item(0)
                ext_input = extrudes.createInput(
                    profile,
                    adsk.fusion.FeatureOperations.CutFeatureOperation
                )
                # Extrude through the piece (use TwoSidesExtent to ensure it goes through)
                ext_input.setTwoSidesExtent(
                    adsk.core.ValueInput.createByReal(insert_length / 2),
                    adsk.core.ValueInput.createByReal(insert_length / 2)
                )
                hole_feature = extrudes.add(ext_input)
                holes_created.append(hole_feature)
        except Exception as e:
            print(f"Error creating hole in piece {piece_idx}: {e}")
    
    return holes_created


def create_insert_pin(root, insert_diameter, insert_length, position_x, position_y, position_z, tolerance=0.01):
    """
    Create a cylindrical insert pin that fits into the holes.
    Pin is slightly smaller than hole diameter for clearance fit.
    
    Returns: The insert body
    """
    sketches = root.sketches
    extrudes = root.features.extrudeFeatures
    
    # Pin diameter is slightly smaller than hole for clearance
    pin_diameter = insert_diameter - tolerance
    
    # Create sketch on YZ plane (perpendicular to X-axis, along Y-axis)
    # This creates a pin that extends along Y direction
    sketch = sketches.add(root.yZConstructionPlane)
    sketch.name = f"InsertPin_{position_x:.1f}"
    
    # Create circle at the correct position
    circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(position_y, position_z, 0),
        pin_diameter / 2
    )
    
    # Extrude along Y direction to create cylinder
    if sketch.profiles.count > 0:
        profile = sketch.profiles.item(0)
        ext_input = extrudes.createInput(
            profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        # Extrude along Y direction (perpendicular to split plane)
        ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(insert_length))
        
        insert_body = extrudes.add(ext_input).bodies.item(0)
        insert_body.name = f"InsertPin_X{position_x:.1f}"
        
        # Move to correct X position using move feature
        # For now, we'll create it and let user position manually if needed
        # In a full implementation, we'd use transform features
        
        return insert_body
    
    return None


def run(context):
    """
    Main function: Create U-channel, split diagonally, add perpendicular inserts.
    """
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        
        if design is None:
            ui.messageBox("No active design. Please create or open a design first.")
            return
        
        root = design.rootComponent
        
        # Step 1: Create U-channel
        ui.messageBox("Creating U-channel...")
        track_body = create_u_channel(root)
        
        # Step 2: Create diagonal split plane (or custom shape)
        ui.messageBox("Creating diagonal split plane...")
        
        if USE_CUSTOM_CUTTER_SHAPE:
            # Use custom wavy/complex shape
            split_surface = create_custom_shape_cutter(
                root, SPLIT_POSITION_X, CUSTOM_SHAPE_AMPLITUDE, CUSTOM_SHAPE_FREQUENCY
            )
            if split_surface is None:
                ui.messageBox("Failed to create custom shape cutter. Using diagonal plane instead.")
                split_plane = create_diagonal_split_plane(root, SPLIT_POSITION_X, DIAGONAL_ANGLE)
                split_entity = split_plane
            else:
                split_entity = split_surface
        else:
            # Use simple diagonal plane
            split_plane = create_diagonal_split_plane(root, SPLIT_POSITION_X, DIAGONAL_ANGLE)
            split_entity = split_plane
        
        # Step 3: Split the U-channel
        ui.messageBox("Splitting U-channel...")
        piece1, piece2 = split_u_channel(root, track_body, split_entity)
        
        if piece1 is None or piece2 is None:
            ui.messageBox("Failed to split U-channel. Check console for details.")
            return
        
        # Step 4: Create insert holes in both pieces
        ui.messageBox("Creating insert holes...")
        holes = create_insert_holes(
            root, piece1, piece2,
            INSERT_DIAMETER, INSERT_LENGTH,
            INSERT_POSITION_Z, INSERT_OFFSET_Y
        )
        
        # Step 5: Create insert pins
        ui.messageBox("Creating insert pins...")
        bb = track_body.boundingBox
        center_x = SPLIT_POSITION_X  # Position at split location
        
        insert_pins = []
        for i in range(INSERT_COUNT):
            # Position inserts along Y (one per branch)
            if INSERT_COUNT == 1:
                y_pos = TRACK_WIDTH / 2  # Center
            else:
                y_pos = WALL_THICKNESS + INSERT_OFFSET_Y + (i * (TRACK_WIDTH - 2 * WALL_THICKNESS - 2 * INSERT_OFFSET_Y) / max(1, INSERT_COUNT - 1))
            
            insert_pin = create_insert_pin(
                root, INSERT_DIAMETER, INSERT_LENGTH,
                center_x, y_pos, INSERT_POSITION_Z
            )
            if insert_pin:
                insert_pins.append(insert_pin)
        
        # Success message
        cutter_type = "Custom wavy shape" if USE_CUSTOM_CUTTER_SHAPE else f"Diagonal plane ({DIAGONAL_ANGLE}°)"
        
        ui.messageBox(
            f"SUCCESS!\n\n"
            f"Created diagonal split with perpendicular inserts:\n\n"
            f"✓ U-channel created ({TRACK_LENGTH:.1f}cm × {TRACK_WIDTH:.1f}cm × {TRACK_HEIGHT:.1f}cm)\n"
            f"✓ Split at X={SPLIT_POSITION_X:.1f}cm using {cutter_type}\n"
            f"✓ {len(holes)} insert holes created in pieces\n"
            f"✓ {len(insert_pins)} insert pins created\n\n"
            f"ASSEMBLY INSTRUCTIONS:\n"
            f"1. Slide Piece1 and Piece2 together along the diagonal cut\n"
            f"2. Align the insert holes\n"
            f"3. Insert pins through the holes to lock pieces together\n\n"
            f"This creates a strong mechanical lock:\n"
            f"- Diagonal cut: Enables easy sliding assembly\n"
            f"- Perpendicular inserts: Prevent separation"
        )
        
    except Exception as e:
        if ui:
            ui.messageBox(f"Error: {e}\n\n{traceback.format_exc()}")
        else:
            print(f"Error: {e}\n{traceback.format_exc()}")
