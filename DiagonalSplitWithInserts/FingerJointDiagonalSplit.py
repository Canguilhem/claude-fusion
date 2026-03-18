"""
Finger Joint Diagonal Split - Test Cutter Script

This script creates a finger joint (comb joint) along a diagonal split plane.
Instead of separate inserts, the pieces themselves interlock with alternating fingers.

ADVANTAGES:
- No separate parts needed
- Strong mechanical lock
- Large gluing surface area
- Clean, professional appearance
- Self-aligning during assembly
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

# Finger joint parameters
FINGER_WIDTH = 0.3        # Width of each finger (cm)
FINGER_DEPTH = 0.4        # Depth of fingers into the joint (cm)
FINGER_COUNT = 5          # Number of fingers per side
FINGER_ROUNDING_RADIUS = 0.05  # Radius for rounded finger ends (cm)
FINGER_TOLERANCE = 0.01   # Gap between fingers for fit (cm)


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
    """Create a diagonal construction plane for splitting."""
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


def create_finger_joint_cutter(root, split_plane, finger_width, finger_depth, finger_count, rounding_radius, tolerance):
    """
    Create a finger joint cutter that will be used to cut fingers into both pieces.
    
    The cutter creates alternating fingers and sockets along the diagonal split plane.
    """
    sketches = root.sketches
    extrudes = root.features.extrudeFeatures
    
    # Create sketch on the diagonal split plane
    sketch = sketches.add(split_plane)
    sketch.name = "FingerJointCutter"
    lines = sketch.sketchCurves.sketchLines
    arcs = sketch.sketchCurves.sketchArcs
    
    # Calculate dimensions
    # The joint spans the height of the track (Z direction in world, but varies in plane)
    # We'll create fingers along the diagonal plane
    
    # Get the plane's coordinate system
    # For a diagonal plane, we need to understand its orientation
    # The plane is rotated around Y axis, so it's diagonal in XZ plane
    
    # Create finger pattern: alternating fingers and sockets
    # Each finger is finger_width wide, with rounded ends
    
    # Start point (bottom of joint)
    start_y = 0
    current_y = start_y
    
    # Create alternating pattern
    for i in range(finger_count * 2):  # Create enough for both pieces
        is_finger = (i % 2 == 0)  # Alternate: finger, socket, finger, socket...
        
        if is_finger:
            # Create finger (protrusion)
            # Left edge
            p1 = adsk.core.Point3D.create(current_y, 0, 0)
            p2 = adsk.core.Point3D.create(current_y + finger_width, 0, 0)
            
            # Right edge with rounded end
            p3 = adsk.core.Point3D.create(current_y + finger_width, finger_depth, 0)
            p4 = adsk.core.Point3D.create(current_y, finger_depth, 0)
            
            # Create rectangle
            lines.addByTwoPoints(p1, p2)
            lines.addByTwoPoints(p2, p3)
            lines.addByTwoPoints(p3, p4)
            lines.addByTwoPoints(p4, p1)
            
            # Add rounded ends (arcs at top of finger)
            if rounding_radius > 0:
                # Top left corner arc
                arc_center_left = adsk.core.Point3D.create(current_y, finger_depth - rounding_radius, 0)
                arc1 = arcs.addByCenterStartSweep(
                    arc_center_left,
                    adsk.core.Point3D.create(current_y, finger_depth, 0),
                    math.pi / 2
                )
                
                # Top right corner arc
                arc_center_right = adsk.core.Point3D.create(current_y + finger_width, finger_depth - rounding_radius, 0)
                arc2 = arcs.addByCenterStartSweep(
                    arc_center_right,
                    adsk.core.Point3D.create(current_y + finger_width, finger_depth, 0),
                    math.pi / 2
                )
        else:
            # Create socket (recess) - slightly wider for tolerance
            socket_width = finger_width + tolerance
            p1 = adsk.core.Point3D.create(current_y, 0, 0)
            p2 = adsk.core.Point3D.create(current_y + socket_width, 0, 0)
            p3 = adsk.core.Point3D.create(current_y + socket_width, finger_depth, 0)
            p4 = adsk.core.Point3D.create(current_y, finger_depth, 0)
            
            # Create rectangle (will be cut out)
            lines.addByTwoPoints(p1, p2)
            lines.addByTwoPoints(p2, p3)
            lines.addByTwoPoints(p3, p4)
            lines.addByTwoPoints(p4, p1)
        
        # Move to next position
        current_y += finger_width
    
    # Create cutter body by extruding the profile
    if sketch.profiles.count > 0:
        # Extrude perpendicular to the plane to create cutter
        # The cutter should extend through the entire track width
        profile = sketch.profiles.item(0)
        ext_input = extrudes.createInput(
            profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        # Extrude along the plane's normal direction (perpendicular to diagonal plane)
        ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(TRACK_WIDTH + 1.0))
        
        cutter_body = extrudes.add(ext_input).bodies.item(0)
        cutter_body.name = "FingerJointCutter"
        
        return cutter_body
    
    return None


def create_finger_joint_on_split(root, piece1, piece2, split_plane, finger_width, finger_depth, finger_count, rounding_radius, tolerance):
    """
    Create finger joints on both pieces along the diagonal split plane.
    
    This creates alternating fingers and sockets that interlock.
    Piece 1 gets fingers at even positions, Piece 2 gets fingers at odd positions.
    """
    sketches = root.sketches
    extrudes = root.features.extrudeFeatures
    
    # Calculate total height needed for finger pattern
    # The pattern spans the height of the split face
    total_pattern_height = finger_count * finger_width * 2  # fingers + sockets
    
    # For each piece, create fingers and sockets
    for piece_idx, piece in enumerate([piece1, piece2], 1):
        # Find the split face (diagonal face)
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
            print(f"Warning: Could not find split face for piece {piece_idx}")
            continue
        
        # Get face bounding box to understand its dimensions
        face_bb = split_face.boundingBox
        face_height = max(
            abs(face_bb.maxPoint.z - face_bb.minPoint.z),
            abs(face_bb.maxPoint.y - face_bb.minPoint.y),
            abs(face_bb.maxPoint.x - face_bb.minPoint.x)
        )
        
        # Create sketch on the split face
        sketch = sketches.add(split_face)
        sketch.name = f"FingerJoint_Piece{piece_idx}"
        lines = sketch.sketchCurves.sketchLines
        arcs = sketch.sketchCurves.sketchArcs
        
        # Create finger pattern along the face
        # Piece 1: fingers at positions 0, 2, 4... (even indices)
        # Piece 2: fingers at positions 1, 3, 5... (odd indices)
        current_pos = 0
        
        for i in range(finger_count * 2):  # Create pattern for both pieces
            is_finger_for_this_piece = (piece_idx == 1 and i % 2 == 0) or (piece_idx == 2 and i % 2 == 1)
            
            if is_finger_for_this_piece:
                # Create finger (protrusion) - will be JOINED to piece
                # Finger: rectangle with rounded top end
                p1 = adsk.core.Point3D.create(current_pos, 0, 0)  # Bottom left
                p2 = adsk.core.Point3D.create(current_pos + finger_width, 0, 0)  # Bottom right
                p3 = adsk.core.Point3D.create(current_pos + finger_width, finger_depth - rounding_radius, 0)  # Top right (before rounding)
                p4 = adsk.core.Point3D.create(current_pos, finger_depth - rounding_radius, 0)  # Top left (before rounding)
                
                # Create rectangle base
                lines.addByTwoPoints(p1, p2)  # Bottom
                lines.addByTwoPoints(p2, p3)  # Right side
                lines.addByTwoPoints(p3, p4)  # Top (straight part)
                lines.addByTwoPoints(p4, p1)  # Left side
                
                # Add rounded top end (semicircle)
                if rounding_radius > 0:
                    arc_center = adsk.core.Point3D.create(current_pos + finger_width / 2, finger_depth - rounding_radius, 0)
                    arc_start = adsk.core.Point3D.create(current_pos, finger_depth - rounding_radius, 0)
                    # Create arc from left to right
                    arcs.addByCenterStartSweep(arc_center, arc_start, math.pi)
            else:
                # Create socket (recess) - will be CUT from piece
                # Socket: slightly wider for tolerance
                socket_width = finger_width + tolerance
                p1 = adsk.core.Point3D.create(current_pos, 0, 0)
                p2 = adsk.core.Point3D.create(current_pos + socket_width, 0, 0)
                p3 = adsk.core.Point3D.create(current_pos + socket_width, finger_depth, 0)
                p4 = adsk.core.Point3D.create(current_pos, finger_depth, 0)
                
                # Create rectangle
                lines.addByTwoPoints(p1, p2)
                lines.addByTwoPoints(p2, p3)
                lines.addByTwoPoints(p3, p4)
                lines.addByTwoPoints(p4, p1)
            
            current_pos += finger_width
        
        # Extrude each profile
        for profile_idx in range(sketch.profiles.count):
            profile = sketch.profiles.item(profile_idx)
            
            # Determine if this is a finger (join) or socket (cut)
            # Check profile bounding box position
            profile_bb = profile.boundingBox
            profile_center_x = (profile_bb.minPoint.x + profile_bb.maxPoint.x) / 2
            
            # Determine finger index based on X position
            finger_index = int(profile_center_x / finger_width)
            is_finger = (piece_idx == 1 and finger_index % 2 == 0) or (piece_idx == 2 and finger_index % 2 == 1)
            
            if is_finger:
                # Join finger to piece
                ext_input = extrudes.createInput(
                    profile,
                    adsk.fusion.FeatureOperations.JoinFeatureOperation
                )
                ext_input.participantBodies = [piece]
            else:
                # Cut socket from piece
                ext_input = extrudes.createInput(
                    profile,
                    adsk.fusion.FeatureOperations.CutFeatureOperation
                )
                ext_input.participantBodies = [piece]
            
            # Extrude perpendicular to split plane (into/out of the piece)
            ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(finger_depth))
            extrudes.add(ext_input)


def run(context):
    """
    Main function: Create U-channel, split diagonally, add finger joints.
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
        
        # Step 2: Create diagonal split plane
        ui.messageBox("Creating diagonal split plane...")
        split_plane = create_diagonal_split_plane(root, SPLIT_POSITION_X, DIAGONAL_ANGLE)
        
        # Step 3: Split the U-channel
        ui.messageBox("Splitting U-channel...")
        splits = root.features.splitBodyFeatures
        split_input = splits.createInput(track_body, split_plane, True)
        split_result = splits.add(split_input)
        
        pieces = list(split_result.bodies)
        if len(pieces) != 2:
            ui.messageBox("Failed to split U-channel into 2 pieces.")
            return
        
        piece1 = pieces[0]
        piece1.name = "Piece1"
        piece2 = pieces[1]
        piece2.name = "Piece2"
        
        # Step 4: Create finger joints on both pieces
        ui.messageBox("Creating finger joints...")
        create_finger_joint_on_split(
            root, piece1, piece2, split_plane,
            FINGER_WIDTH, FINGER_DEPTH, FINGER_COUNT,
            FINGER_ROUNDING_RADIUS, FINGER_TOLERANCE
        )
        
        # Success message
        ui.messageBox(
            f"SUCCESS!\n\n"
            f"Created finger joint diagonal split:\n\n"
            f"✓ U-channel created ({TRACK_LENGTH:.1f}cm × {TRACK_WIDTH:.1f}cm × {TRACK_HEIGHT:.1f}cm)\n"
            f"✓ Split at X={SPLIT_POSITION_X:.1f}cm with {DIAGONAL_ANGLE}° angle\n"
            f"✓ {FINGER_COUNT} fingers per piece created\n"
            f"✓ Finger width: {FINGER_WIDTH:.2f}cm, depth: {FINGER_DEPTH:.2f}cm\n"
            f"✓ Rounded ends: {FINGER_ROUNDING_RADIUS:.2f}cm radius\n\n"
            f"ASSEMBLY:\n"
            f"Pieces interlock naturally - no separate inserts needed!\n"
            f"Fingers provide strong mechanical lock."
        )
        
    except Exception as e:
        if ui:
            ui.messageBox(f"Error: {e}\n\n{traceback.format_exc()}")
        else:
            print(f"Error: {e}\n{traceback.format_exc()}")
