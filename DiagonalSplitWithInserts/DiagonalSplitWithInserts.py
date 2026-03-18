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
INSERT_LENGTH = 1.0       # Length of insert (extends through both pieces along Y direction)
INSERT_COUNT = 2          # Number of inserts (one per branch)
INSERT_OFFSET_Y = 0.1     # Offset from inner wall (Y direction)
# Note: Inserts are inserted from TOP of walls (Z = TRACK_HEIGHT), making them invisible from outside

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


def create_insert_holes(root, piece1, piece2, split_x, track_width, track_height, wall_thickness, insert_diameter, insert_length, insert_y_positions):
    """
    Create holes in both pieces for the perpendicular inserts.
    Holes are drilled from the TOP of U-channel walls, perpendicular to the diagonal cut plane.
    This makes inserts invisible from the outside while still locking pieces together.
    
    Args:
        split_x: X position where split occurs (where holes should be)
        track_width: Total width of track
        track_height: Height of track walls
        wall_thickness: Thickness of walls
        insert_y_positions: List of Y positions for each insert (one per branch)
    
    Returns: List of created hole features
    """
    sketches = root.sketches
    extrudes = root.features.extrudeFeatures
    
    holes_created = []
    
    # Create holes in both pieces
    for piece_idx, piece in enumerate([piece1, piece2], 1):
        # Find TOP faces of U-channel walls (horizontal faces at Z = track_height)
        # These are the top surfaces of the left and right walls
        top_faces = []
        
        for face in piece.faces:
            geom = face.geometry
            if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                normal = geom.normal
                bb = face.boundingBox
                face_z = (bb.minPoint.z + bb.maxPoint.z) / 2
                face_y = (bb.minPoint.y + bb.maxPoint.y) / 2
                
                # Look for horizontal top faces (normal points up in Z direction)
                # Top face: Z ≈ track_height, normal.z ≈ +1
                is_horizontal = abs(normal.z) > 0.7  # Roughly horizontal (large Z component)
                is_top = abs(face_z - track_height) < 0.1  # At top of track
                is_wall = (face_y > 0.1) and (face_y < track_width - 0.1)  # On wall, not floor
                
                if is_horizontal and is_top and is_wall:
                    top_faces.append((face, face_y))
        
        if len(top_faces) == 0:
            print(f"Warning: Could not find top faces for insert holes in piece {piece_idx}")
            # Fallback: try to find any horizontal face at top
            for face in piece.faces:
                geom = face.geometry
                if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                    normal = geom.normal
                    bb = face.boundingBox
                    face_z = (bb.minPoint.z + bb.maxPoint.z) / 2
                    if abs(normal.z) > 0.7 and abs(face_z - track_height) < 0.2:
                        top_faces.append((face, (bb.minPoint.y + bb.maxPoint.y) / 2))
                        break
        
        # Create holes for each insert position
        # Holes start from TOP surface, go DOWN through wall, then extend along Y (perpendicular to diagonal cut)
        for insert_idx, y_pos in enumerate(insert_y_positions):
            # Find the top face closest to this Y position (left or right wall)
            target_face = None
            if len(top_faces) > 0:
                # Find closest top face
                min_dist = float('inf')
                for face, face_y in top_faces:
                    dist = abs(y_pos - face_y)
                    if dist < min_dist:
                        min_dist = dist
                        target_face = face
            
            if target_face is None:
                print(f"Warning: Could not find target top face for insert {insert_idx} in piece {piece_idx}")
                continue
            
            # Create sketch on the TOP face (horizontal surface at Z = track_height)
            sketch = sketches.add(target_face)
            sketch.name = f"InsertHole_Piece{piece_idx}_Insert{insert_idx}"
            
            # Create hole center point at split location (X) and insert position (Y)
            # Z position is at the top of the wall (track_height)
            hole_center_world = adsk.core.Point3D.create(split_x, y_pos, track_height)
            hole_center_sketch = sketch.modelToSketchSpace(hole_center_world)
            
            # Create circle for hole on top surface
            try:
                circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    adsk.core.Point3D.create(hole_center_sketch.x, hole_center_sketch.y, 0),
                    insert_diameter / 2
                )
                
                # Create L-shaped hole: DOWN through wall, then along Y through both pieces
                if sketch.profiles.count > 0:
                    profile = sketch.profiles.item(0)
                    
                    # Step 1: Extrude DOWN through the wall (Z direction)
                    ext_input_down = extrudes.createInput(
                        profile,
                        adsk.fusion.FeatureOperations.CutFeatureOperation
                    )
                    ext_input_down.participantBodies = [piece]
                    # Go down through wall thickness (negative Z direction)
                    # Wall thickness is from Z=track_height down to Z=wall_thickness
                    wall_depth = track_height - wall_thickness
                    ext_input_down.setDistanceExtent(True, adsk.core.ValueInput.createByReal(wall_depth + 0.1))
                    extrudes.add(ext_input_down)
                    
                    # Step 2: Create horizontal hole along Y direction (perpendicular to diagonal cut)
                    # This hole should be at the wall level (Z = WALL_THICKNESS or slightly above)
                    # Create XZ plane at Y position (horizontal plane)
                    planes = root.constructionPlanes
                    y_plane_input = planes.createInput()
                    y_plane_input.setByOffset(
                        root.xZConstructionPlane,
                        adsk.core.ValueInput.createByReal(y_pos)
                    )
                    y_plane = planes.add(y_plane_input)
                    
                    sketch_y = sketches.add(y_plane)
                    sketch_y.name = f"InsertHoleY_Piece{piece_idx}_Insert{insert_idx}"
                    
                    # Create circle at X = split_x, Z = wall level (where vertical hole ends)
                    # This should be at Z = wall_thickness (top of floor, bottom of wall)
                    # The wall extends from Z = wall_thickness to Z = track_height
                    circle_y = sketch_y.sketchCurves.sketchCircles.addByCenterRadius(
                        adsk.core.Point3D.create(split_x, wall_thickness, 0),
                        insert_diameter / 2
                    )
                    
                    # Extrude along Y direction (perpendicular to diagonal cut) through BOTH walls
                    # The hole should extend from one side of the track to the other to lock both pieces
                    if sketch_y.profiles.count > 0:
                        profile_y = sketch_y.profiles.item(0)
                        ext_input_y = extrudes.createInput(
                            profile_y,
                            adsk.fusion.FeatureOperations.CutFeatureOperation
                        )
                        ext_input_y.participantBodies = [piece]
                        # Extrude along Y direction to go through the entire width
                        # This ensures it passes through both left and right walls
                        # Extrude from current Y position outward to cover both walls
                        # Use DistanceExtentDefinition for two-sided extent
                        left_extent = adsk.fusion.DistanceExtentDefinition.create(
                            adsk.core.ValueInput.createByReal(y_pos)
                        )
                        right_extent = adsk.fusion.DistanceExtentDefinition.create(
                            adsk.core.ValueInput.createByReal(track_width - y_pos)
                        )
                        ext_input_y.setTwoSidesExtent(left_extent, right_extent)
                        hole_feature = extrudes.add(ext_input_y)
                        holes_created.append(hole_feature)
                    
            except Exception as e:
                print(f"Error creating hole {insert_idx} in piece {piece_idx}: {e}")
                import traceback
                print(traceback.format_exc())
    
    return holes_created


def create_insert_pin(root, insert_diameter, insert_length, position_x, position_y, track_height, track_width, wall_thickness, tolerance=0.01):
    """
    Create a cylindrical insert pin that fits into the holes.
    Pin starts from TOP surface, goes DOWN through wall, then extends along Y (perpendicular to diagonal cut).
    This makes the pin invisible from the outside.
    
    Args:
        track_height: Height of track walls
        wall_thickness: Thickness of walls
        tolerance: Clearance between pin and hole
    
    Returns: The insert body
    """
    sketches = root.sketches
    extrudes = root.features.extrudeFeatures
    planes = root.constructionPlanes
    
    # Pin diameter is slightly smaller than hole for clearance
    pin_diameter = insert_diameter - tolerance
    
    # Step 1: Create pin that goes DOWN from top surface through the wall
    # Create sketch on top surface (XZ plane at Y position, Z = track_height)
    top_plane_input = planes.createInput()
    top_plane_input.setByOffset(
        root.xZConstructionPlane,
        adsk.core.ValueInput.createByReal(position_y)
    )
    top_plane = planes.add(top_plane_input)
    
    sketch_top = sketches.add(top_plane)
    sketch_top.name = f"InsertPinTop_{position_x:.1f}"
    
    # Create circle at X=position_x, Z=track_height (top of wall)
    circle_top = sketch_top.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(position_x, track_height, 0),
        pin_diameter / 2
    )
    
    # Extrude DOWN through the wall
    if sketch_top.profiles.count > 0:
        profile_top = sketch_top.profiles.item(0)
        ext_input_down = extrudes.createInput(
            profile_top,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        # Go down through wall thickness (negative Z direction)
        ext_input_down.setDistanceExtent(True, adsk.core.ValueInput.createByReal(wall_thickness + 0.1))
        pin_body_down = extrudes.add(ext_input_down).bodies.item(0)
        
        # Step 2: Create pin that extends along Y direction from the bottom of the vertical hole
        # Create sketch on XZ plane at Y position, Z = floor level (or just below wall)
        y_plane_input = planes.createInput()
        y_plane_input.setByOffset(
            root.xZConstructionPlane,
            adsk.core.ValueInput.createByReal(position_y)
        )
        y_plane = planes.add(y_plane_input)
        
        sketch_y = sketches.add(y_plane)
        sketch_y.name = f"InsertPinY_{position_x:.1f}"
        
        # Create circle at X=position_x, Z = wall_thickness (bottom of wall, top of floor)
        # This is where the vertical pin ends and horizontal pin starts
        circle_y = sketch_y.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(position_x, wall_thickness, 0),
            pin_diameter / 2
        )
        
        # Extrude along Y direction (perpendicular to diagonal cut) through BOTH walls
        if sketch_y.profiles.count > 0:
            profile_y = sketch_y.profiles.item(0)
            ext_input_y = extrudes.createInput(
                profile_y,
                adsk.fusion.FeatureOperations.JoinFeatureOperation  # Join with existing pin body
            )
            ext_input_y.participantBodies = [pin_body_down]
            
            # Extrude along Y direction to go through both walls
            # Extrude from current Y position outward to cover both walls
            left_extent = adsk.fusion.DistanceExtentDefinition.create(
                adsk.core.ValueInput.createByReal(position_y)
            )
            right_extent = adsk.fusion.DistanceExtentDefinition.create(
                adsk.core.ValueInput.createByReal(track_width - position_y)
            )
            ext_input_y.setTwoSidesExtent(left_extent, right_extent)
            pin_feature = extrudes.add(ext_input_y)
            
            # Get the final combined body
            insert_body = pin_feature.bodies.item(0)
            insert_body.name = f"InsertPin_X{position_x:.1f}"
            
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
        
        # Step 4: Calculate insert Y positions (one per branch)
        insert_y_positions = []
        if INSERT_COUNT == 1:
            insert_y_positions.append(TRACK_WIDTH / 2)  # Center
        else:
            # Distribute inserts along Y (one per branch)
            for i in range(INSERT_COUNT):
                y_pos = WALL_THICKNESS + INSERT_OFFSET_Y + (i * (TRACK_WIDTH - 2 * WALL_THICKNESS - 2 * INSERT_OFFSET_Y) / max(1, INSERT_COUNT - 1))
                insert_y_positions.append(y_pos)
        
        # Step 5: Create insert holes in both pieces (from TOP of walls, perpendicular to diagonal cut)
        ui.messageBox("Creating insert holes from top of walls...")
        holes = create_insert_holes(
            root, piece1, piece2, SPLIT_POSITION_X, TRACK_WIDTH, TRACK_HEIGHT, WALL_THICKNESS,
            INSERT_DIAMETER, INSERT_LENGTH,
            insert_y_positions
        )
        
        # Step 6: Create insert pins at the same positions (starting from top, invisible from outside)
        ui.messageBox("Creating insert pins from top of walls...")
        insert_pins = []
        for y_pos in insert_y_positions:
            insert_pin = create_insert_pin(
                root, INSERT_DIAMETER, INSERT_LENGTH,
                SPLIT_POSITION_X, y_pos, TRACK_HEIGHT, TRACK_WIDTH, WALL_THICKNESS
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
