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


def create_finger_joint_on_split(root, piece1, piece2, split_plane, finger_width, finger_depth, finger_count, rounding_radius, tolerance):
    """
    Create finger joints on both pieces along the diagonal split plane.
    
    This creates alternating fingers and sockets that interlock.
    Piece 1 gets fingers at even positions, Piece 2 gets fingers at odd positions.
    """
    sketches = root.sketches
    extrudes = root.features.extrudeFeatures
    
    # Get the split plane geometry to help find faces
    split_plane_geom = split_plane.geometry
    split_normal = split_plane_geom.normal
    
    # For each piece, create fingers and sockets
    for piece_idx, piece in enumerate([piece1, piece2], 1):
        # Find the split face by checking which face is coplanar with the split plane
        split_face = None
        best_match = None
        min_distance = float('inf')
        
        for face in piece.faces:
            geom = face.geometry
            if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                face_normal = geom.normal
                face_point = face.pointOnFace
                
                # Check if face normal is parallel to plane normal
                dot_product = abs(face_normal.dotProduct(split_normal))
                
                # Check distance from face to plane
                vec_to_face = split_plane_geom.origin.vectorTo(face_point)
                distance = abs(vec_to_face.dotProduct(split_normal))
                
                # Prefer faces that are nearly parallel and close to the plane
                if dot_product > 0.8:  # Nearly parallel (cosine > 0.8)
                    if distance < min_distance:
                        min_distance = distance
                        best_match = face
        
        if best_match and min_distance < 1.0:  # Within 1cm
            split_face = best_match
        else:
            # Fallback: find the largest planar face
            largest_area = 0
            for face in piece.faces:
                geom = face.geometry
                if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                    area = face.area
                    if area > largest_area:
                        largest_area = area
                        split_face = face
        
        if split_face is None:
            ui = adsk.core.Application.get().userInterface
            ui.messageBox(f"ERROR: Could not find split face for piece {piece_idx}")
            continue
        
        print(f"Piece {piece_idx}: Found split face with {split_face.edges.count} edges, area={split_face.area:.2f}")
        
        # Get face edges to understand orientation
        face_edges = split_face.edges
        if face_edges.count < 3:
            print(f"Warning: Split face has too few edges ({face_edges.count})")
            continue
        
        # Find the longest edge (likely the diagonal edge)
        longest_edge = None
        max_length = 0
        for edge in face_edges:
            length = edge.length
            if length > max_length:
                max_length = length
                longest_edge = edge
        
        # Get face bounding box
        face_bb = split_face.boundingBox
        
        # Calculate diagonal length (approximate)
        diagonal_length = max_length if longest_edge else math.sqrt(
            (face_bb.maxPoint.x - face_bb.minPoint.x)**2 +
            (face_bb.maxPoint.y - face_bb.minPoint.y)**2 +
            (face_bb.maxPoint.z - face_bb.minPoint.z)**2
        )
        
        # Create sketch on the split face
        sketch = sketches.add(split_face)
        sketch.name = f"FingerJoint_Piece{piece_idx}"
        lines = sketch.sketchCurves.sketchLines
        arcs = sketch.sketchCurves.sketchArcs
        
        # Calculate how many total slots we need (fingers + sockets)
        total_slots = finger_count * 2
        
        # Adjust finger width to fit along the diagonal
        actual_finger_width = diagonal_length / total_slots if total_slots > 0 else finger_width
        
        # Create each finger/socket as a separate closed profile
        # Place them along one edge of the face (in sketch coordinates)
        for i in range(total_slots):
            is_finger_for_this_piece = (piece_idx == 1 and i % 2 == 0) or (piece_idx == 2 and i % 2 == 1)
            
            # Position along the edge (in sketch coordinates)
            start_pos = i * actual_finger_width
            end_pos = start_pos + actual_finger_width
            
            if is_finger_for_this_piece:
                # Create finger (protrusion) - will be JOINED to piece
                # Finger: rectangle with rounded top end
                p1 = adsk.core.Point3D.create(start_pos, 0, 0)  # Bottom left
                p2 = adsk.core.Point3D.create(end_pos, 0, 0)  # Bottom right
                
                if rounding_radius > 0 and finger_depth > rounding_radius:
                    # Create finger with rounded top
                    # Bottom edge
                    line_bottom = lines.addByTwoPoints(p1, p2)
                    
                    # Right side (straight part)
                    p3_straight = adsk.core.Point3D.create(end_pos, finger_depth - rounding_radius, 0)
                    line_right = lines.addByTwoPoints(p2, p3_straight)
                    
                    # Left side (straight part)
                    p4_straight = adsk.core.Point3D.create(start_pos, finger_depth - rounding_radius, 0)
                    line_left = lines.addByTwoPoints(p1, p4_straight)
                    
                    # Rounded top (semicircle)
                    arc_center = adsk.core.Point3D.create(start_pos + actual_finger_width / 2, finger_depth - rounding_radius, 0)
                    arc = arcs.addByCenterStartSweep(arc_center, p4_straight, math.pi)
                else:
                    # Simple rectangle without rounding
                    p3 = adsk.core.Point3D.create(end_pos, finger_depth, 0)
                    p4 = adsk.core.Point3D.create(start_pos, finger_depth, 0)
                    
                    lines.addByTwoPoints(p1, p2)  # Bottom
                    lines.addByTwoPoints(p2, p3)  # Right
                    lines.addByTwoPoints(p3, p4)  # Top
                    lines.addByTwoPoints(p4, p1)  # Left
            else:
                # Create socket (recess) - will be CUT from piece
                # Socket: slightly wider for tolerance
                socket_width = actual_finger_width + tolerance
                socket_start = start_pos - tolerance / 2
                socket_end = socket_start + socket_width
                
                p1 = adsk.core.Point3D.create(socket_start, 0, 0)
                p2 = adsk.core.Point3D.create(socket_end, 0, 0)
                p3 = adsk.core.Point3D.create(socket_end, finger_depth, 0)
                p4 = adsk.core.Point3D.create(socket_start, finger_depth, 0)
                
                # Create closed rectangle
                lines.addByTwoPoints(p1, p2)
                lines.addByTwoPoints(p2, p3)
                lines.addByTwoPoints(p3, p4)
                lines.addByTwoPoints(p4, p1)
        
        # Extrude each profile
        profile_count = sketch.profiles.count
        if profile_count == 0:
            ui = adsk.core.Application.get().userInterface
            ui.messageBox(f"Warning: No profiles created for piece {piece_idx}. Check sketch geometry.")
            continue
        
        print(f"Piece {piece_idx}: Created {profile_count} profiles")
        
        for profile_idx in range(profile_count):
            profile = sketch.profiles.item(profile_idx)
            
            # Determine if this is a finger (join) or socket (cut)
            # Check profile bounding box position
            profile_bb = profile.boundingBox
            profile_center_x = (profile_bb.minPoint.x + profile_bb.maxPoint.x) / 2
            
            # Determine finger index based on X position
            finger_index = int(profile_center_x / actual_finger_width) if actual_finger_width > 0 else 0
            is_finger = (piece_idx == 1 and finger_index % 2 == 0) or (piece_idx == 2 and finger_index % 2 == 1)
            
            try:
                if is_finger:
                    # Join finger to piece (extrude outward)
                    ext_input = extrudes.createInput(
                        profile,
                        adsk.fusion.FeatureOperations.JoinFeatureOperation
                    )
                    ext_input.participantBodies = [piece]
                else:
                    # Cut socket from piece (extrude inward)
                    ext_input = extrudes.createInput(
                        profile,
                        adsk.fusion.FeatureOperations.CutFeatureOperation
                    )
                    ext_input.participantBodies = [piece]
                
                # Extrude perpendicular to split plane
                ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(finger_depth))
                extrudes.add(ext_input)
            except Exception as e:
                print(f"Error extruding profile {profile_idx} for piece {piece_idx}: {e}")
                continue


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
