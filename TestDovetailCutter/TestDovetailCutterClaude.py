import adsk.core, adsk.fusion, traceback

# Import helper functions for creating grooves on branches
def find_inner_faces_of_u_channel_simple(track_body):
    """
    SIMPLIFIED: Find the inner faces - just get any two vertical faces on opposite sides.
    """
    print(f"Searching for inner faces... TRACK_WIDTH={TRACK_WIDTH}")
    
    # Collect ALL planar faces
    all_faces = []
    
    for i, face in enumerate(track_body.faces):
        geom = face.geometry
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            normal = geom.normal
            bb = face.boundingBox
            
            center_y = (bb.minPoint.y + bb.maxPoint.y) / 2
            face_height = bb.maxPoint.z - bb.minPoint.z
            face_length = bb.maxPoint.x - bb.minPoint.x
            
            all_faces.append({
                'index': i,
                'face': face,
                'center_y': center_y,
                'normal': normal,
                'height': face_height,
                'length': face_length
            })
    
    print(f"Found {len(all_faces)} planar faces")
    
    # Find vertical faces that span dimensions
    vertical_faces = []
    for f in all_faces:
        is_vertical = abs(f['normal'].z) < 0.9
        spans_height = f['height'] > TRACK_HEIGHT * 0.1
        spans_length = f['length'] > TRACK_LENGTH * 0.1
        
        if is_vertical and spans_height and spans_length:
            vertical_faces.append(f)
            print(f"  Vertical face #{f['index']}: Y={f['center_y']:.3f}")
    
    if len(vertical_faces) < 2:
        print(f"ERROR: Only found {len(vertical_faces)} vertical faces")
        return (None, None)
    
    # Sort by Y position and take leftmost/rightmost
    vertical_faces.sort(key=lambda f: f['center_y'])
    left_face = vertical_faces[0]['face']
    right_face = vertical_faces[-1]['face']
    
    print(f"Selected LEFT face #{vertical_faces[0]['index']}, RIGHT face #{vertical_faces[-1]['index']}")
    return (left_face, right_face)


def find_inner_faces_of_u_channel(track_body):
    """
    Find the inner faces of the left and right vertical branches of the U-channel.
    
    The U-channel has:
    - Left wall inner face: faces toward +Y (center), at Y ≈ WALL_THICKNESS
    - Right wall inner face: faces toward -Y (center), at Y ≈ TRACK_WIDTH - WALL_THICKNESS
    - Both are vertical (normal.z ≈ 0)
    """
    import math
    
    inner_faces = []
    all_vertical_faces = []
    
    print(f"Searching for inner faces in U-channel...")
    print(f"  TRACK_WIDTH={TRACK_WIDTH}, WALL_THICKNESS={WALL_THICKNESS}, TRACK_HEIGHT={TRACK_HEIGHT}")
    
    # Expected positions
    expected_left_y = WALL_THICKNESS
    expected_right_y = TRACK_WIDTH - WALL_THICKNESS
    
    print(f"  Expected LEFT inner face Y position: {expected_left_y:.3f}")
    print(f"  Expected RIGHT inner face Y position: {expected_right_y:.3f}")
    
    for i, face in enumerate(track_body.faces):
        geom = face.geometry
        
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            normal = geom.normal
            bb = face.boundingBox
            
            center_y = (bb.minPoint.y + bb.maxPoint.y) / 2
            center_z = (bb.minPoint.z + bb.maxPoint.z) / 2
            center_x = (bb.minPoint.x + bb.maxPoint.x) / 2
            
            # Check if face is roughly vertical (normal.z is small)
            is_vertical = abs(normal.z) < 0.7  # More lenient threshold
            
            # Check if face spans the height (Z direction)
            face_height = bb.maxPoint.z - bb.minPoint.z
            spans_height = face_height > TRACK_HEIGHT * 0.8
            
            # Check if face spans the length (X direction)  
            face_length = bb.maxPoint.x - bb.minPoint.x
            spans_length = face_length > TRACK_LENGTH * 0.8
            
            if is_vertical and spans_height and spans_length:
                # This is likely a vertical wall face
                all_vertical_faces.append((i, center_y, center_z, normal, center_x))
                
                # Check if this is an inner face (faces toward center)
                # Left inner face: normal points +Y (toward center), center_y ≈ WALL_THICKNESS
                # Right inner face: normal points -Y (toward center), center_y ≈ TRACK_WIDTH - WALL_THICKNESS
                
                # More lenient check: any face with Y component pointing toward center
                if abs(normal.y) > 0.3:  # Has Y component
                    y_tolerance = WALL_THICKNESS * 0.5  # Allow some tolerance
                    
                    # Left inner face: normal.y > 0, center_y close to WALL_THICKNESS
                    if normal.y > 0.3 and abs(center_y - expected_left_y) < y_tolerance:
                        inner_faces.append(('left', face, center_y, center_z))
                        print(f"  ✓ Found LEFT inner face #{i}: center_y={center_y:.3f}, center_z={center_z:.3f}, normal=({normal.x:.2f}, {normal.y:.2f}, {normal.z:.2f})")
                    
                    # Right inner face: normal.y < 0, center_y close to TRACK_WIDTH - WALL_THICKNESS
                    elif normal.y < -0.3 and abs(center_y - expected_right_y) < y_tolerance:
                        inner_faces.append(('right', face, center_y, center_z))
                        print(f"  ✓ Found RIGHT inner face #{i}: center_y={center_y:.3f}, center_z={center_z:.3f}, normal=({normal.x:.2f}, {normal.y:.2f}, {normal.z:.2f})")
    
    # If we found multiple candidates, pick the ones closest to expected positions
    left_face = None
    right_face = None
    
    if len(inner_faces) == 0:
        print(f"  ERROR: No inner faces found!")
        print(f"  Found {len(all_vertical_faces)} vertical faces total:")
        for idx, cy, cz, n, cx in all_vertical_faces:
            print(f"    Face {idx}: center=({cx:.3f}, {cy:.3f}, {cz:.3f}), normal=({n.x:.2f}, {n.y:.2f}, {n.z:.2f})")
        print(f"\n  Trying alternative detection method...")
        
        # Alternative: Find faces closest to expected positions (more lenient)
        if len(all_vertical_faces) >= 2:
            # Sort by distance to expected Y positions
            left_candidates = sorted(all_vertical_faces, key=lambda f: abs(f[1] - expected_left_y))
            right_candidates = sorted(all_vertical_faces, key=lambda f: abs(f[1] - expected_right_y))
            
            # Check if best candidates have correct normal direction (more lenient)
            if len(left_candidates) > 0:
                best_left_idx, best_left_cy, best_left_cz, best_left_n, best_left_cx = left_candidates[0]
                # More lenient: just check that it's on the left side and roughly vertical
                if best_left_cy < TRACK_WIDTH / 2:  # Left side
                    left_face = track_body.faces.item(best_left_idx)
                    print(f"  ✓ Alternative: Selected LEFT face #{best_left_idx} (Y={best_left_cy:.3f}, normal.y={best_left_n.y:.2f})")
            
            if len(right_candidates) > 0:
                best_right_idx, best_right_cy, best_right_cz, best_right_n, best_right_cx = right_candidates[0]
                # More lenient: just check that it's on the right side and roughly vertical
                if best_right_cy > TRACK_WIDTH / 2:  # Right side
                    right_face = track_body.faces.item(best_right_idx)
                    print(f"  ✓ Alternative: Selected RIGHT face #{best_right_idx} (Y={best_right_cy:.3f}, normal.y={best_right_n.y:.2f})")
    else:
        # Find best matches
        expected_left_y = WALL_THICKNESS
        expected_right_y = TRACK_WIDTH - WALL_THICKNESS
        
        best_left = None
        best_right = None
        min_left_dist = float('inf')
        min_right_dist = float('inf')
        
        for side, face, cy, cz in inner_faces:
            if side == 'left':
                dist = abs(cy - expected_left_y)
                if dist < min_left_dist:
                    min_left_dist = dist
                    best_left = face
            elif side == 'right':
                dist = abs(cy - expected_right_y)
                if dist < min_right_dist:
                    min_right_dist = dist
                    best_right = face
        
        left_face = best_left
        right_face = best_right
        
        print(f"  Selected LEFT face: {'Found' if left_face else 'NOT FOUND'}")
        print(f"  Selected RIGHT face: {'Found' if right_face else 'NOT FOUND'}")
    
    return (left_face, right_face)


def find_inner_faces_alternative(track_body, ui=None):
    """
    Alternative method to find inner faces by analyzing all faces more carefully.
    """
    import math
    
    print("Using alternative face detection method...")
    
    # Collect all candidate faces
    candidates = []
    
    for i, face in enumerate(track_body.faces):
        geom = face.geometry
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            normal = geom.normal
            bb = face.boundingBox
            
            center_y = (bb.minPoint.y + bb.maxPoint.y) / 2
            center_z = (bb.minPoint.z + bb.maxPoint.z) / 2
            center_x = (bb.minPoint.x + bb.maxPoint.x) / 2
            
            # Calculate face dimensions
            face_height = bb.maxPoint.z - bb.minPoint.z
            face_length = bb.maxPoint.x - bb.minPoint.x
            face_width = bb.maxPoint.y - bb.minPoint.y
            
            # Check if this could be an inner wall face
            is_vertical = abs(normal.z) < 0.8
            spans_height = face_height > TRACK_HEIGHT * 0.5
            spans_length = face_length > TRACK_LENGTH * 0.5
            
            if is_vertical and spans_height and spans_length:
                candidates.append({
                    'index': i,
                    'face': face,
                    'center_y': center_y,
                    'center_z': center_z,
                    'center_x': center_x,
                    'normal': normal,
                    'height': face_height,
                    'length': face_length,
                    'width': face_width
                })
    
    print(f"Found {len(candidates)} candidate faces")
    
    # Find left and right faces
    left_face = None
    right_face = None
    
    # Expected positions
    expected_left_y = WALL_THICKNESS
    expected_right_y = TRACK_WIDTH - WALL_THICKNESS
    
    # Sort by distance to expected positions
    left_candidates = sorted(candidates, key=lambda c: abs(c['center_y'] - expected_left_y))
    right_candidates = sorted(candidates, key=lambda c: abs(c['center_y'] - expected_right_y))
    
    # Select best matches
    if len(left_candidates) > 0:
        best_left = left_candidates[0]
        # Prefer faces with normal pointing +Y (toward center)
        if best_left['normal'].y > -0.5:  # Allow some tolerance
            left_face = best_left['face']
            print(f"Selected LEFT face #{best_left['index']}: center_y={best_left['center_y']:.3f}, normal.y={best_left['normal'].y:.3f}")
    
    if len(right_candidates) > 0:
        best_right = right_candidates[0]
        # Prefer faces with normal pointing -Y (toward center)
        if best_right['normal'].y < 0.5:  # Allow some tolerance
            right_face = best_right['face']
            print(f"Selected RIGHT face #{best_right['index']}: center_y={best_right['center_y']:.3f}, normal.y={best_right['normal'].y:.3f}")
    
    return (left_face, right_face)


def analyze_all_faces(track_body):
    """Analyze all faces and return a detailed string description."""
    info = []
    info.append(f"Total faces: {track_body.faces.count}")
    info.append(f"\nAll faces:")
    
    for i in range(track_body.faces.count):
        face = track_body.faces.item(i)
        geom = face.geometry
        
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            normal = geom.normal
            bb = face.boundingBox
            
            center_y = (bb.minPoint.y + bb.maxPoint.y) / 2
            center_z = (bb.minPoint.z + bb.maxPoint.z) / 2
            center_x = (bb.minPoint.x + bb.maxPoint.x) / 2
            
            face_height = bb.maxPoint.z - bb.minPoint.z
            face_length = bb.maxPoint.x - bb.minPoint.x
            
            info.append(f"  Face {i}: center=({center_x:.2f}, {center_y:.2f}, {center_z:.2f}), "
                       f"normal=({normal.x:.2f}, {normal.y:.2f}, {normal.z:.2f}), "
                       f"size=({face_length:.2f}, {face_height:.2f})")
    
    return "\n".join(info)


def find_faces_fallback(track_body):
    """
    Final fallback: Just find any two vertical faces that span height and length.
    This is the most lenient method - it will find faces even if they don't match perfectly.
    """
    print("Using fallback face detection (most lenient)...")
    
    candidates = []
    
    for i, face in enumerate(track_body.faces):
        geom = face.geometry
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            normal = geom.normal
            bb = face.boundingBox
            
            center_y = (bb.minPoint.y + bb.maxPoint.y) / 2
            face_height = bb.maxPoint.z - bb.minPoint.z
            face_length = bb.maxPoint.x - bb.minPoint.x
            
            # Very lenient: just needs to be roughly vertical and span dimensions
            if abs(normal.z) < 0.95 and face_height > TRACK_HEIGHT * 0.2 and face_length > TRACK_LENGTH * 0.2:
                candidates.append((i, face, center_y))
    
    print(f"Fallback found {len(candidates)} candidate faces")
    
    if len(candidates) >= 2:
        # Sort by Y position
        candidates.sort(key=lambda c: c[2])
        
        # Take leftmost and rightmost
        left_face = candidates[0][1]  # Leftmost
        right_face = candidates[-1][1]  # Rightmost
        
        print(f"Fallback selected: Left face #{candidates[0][0]}, Right face #{candidates[-1][0]}")
        return (left_face, right_face)
    
    return (None, None)


def create_dovetail_groove_on_face(root, face, groove_positions_z, groove_length, dovetail_width_top, dovetail_width_bottom, dovetail_height, dovetail_depth):
    """
    Create dovetail grooves on a face at specified Z positions.
    
    Creates trapezoidal dovetails: wide at top, narrow at bottom.
    """
    try:
        import traceback
        
        print(f"Creating grooves on face {face.index}...")
        
        # Create sketch on the face
        sketch = root.sketches.add(face)
        sketch.name = f"DovetailGrooves_{face.index}"
        
        lines = sketch.sketchCurves.sketchLines
        
        # Get face bounding box
        bb = face.boundingBox
        
        print(f"  Face bounding box: X=[{bb.minPoint.x:.2f}, {bb.maxPoint.x:.2f}], Y=[{bb.minPoint.y:.2f}, {bb.maxPoint.y:.2f}], Z=[{bb.minPoint.z:.2f}, {bb.maxPoint.z:.2f}]")
        
        # For each groove position (in world Z coordinates)
        for groove_idx, z_pos_world in enumerate(groove_positions_z):
            z_bottom_world = z_pos_world - dovetail_height / 2
            z_top_world = z_pos_world + dovetail_height / 2
            
            # Use face's Y position (constant for vertical face)
            face_y = (bb.minPoint.y + bb.maxPoint.y) / 2
            
            # Points along the length (X direction) - span full groove_length
            x_center = (bb.minPoint.x + bb.maxPoint.x) / 2
            x_start = max(bb.minPoint.x, x_center - groove_length / 2)
            x_end = min(bb.maxPoint.x, x_center + groove_length / 2)
            
            # Convert center points to sketch coordinates
            center_bottom_world = adsk.core.Point3D.create((x_start + x_end) / 2, face_y, z_bottom_world)
            center_top_world = adsk.core.Point3D.create((x_start + x_end) / 2, face_y, z_top_world)
            center_bottom_sketch = sketch.modelToSketchSpace(center_bottom_world)
            center_top_sketch = sketch.modelToSketchSpace(center_top_world)
            
            # Get length in sketch coordinates
            start_world = adsk.core.Point3D.create(x_start, face_y, z_pos_world)
            end_world = adsk.core.Point3D.create(x_end, face_y, z_pos_world)
            start_sketch = sketch.modelToSketchSpace(start_world)
            end_sketch = sketch.modelToSketchSpace(end_world)
            
            # Center and dimensions in sketch
            cx = center_bottom_sketch.x
            cy_bottom = center_bottom_sketch.y
            cy_top = center_top_sketch.y
            length_sketch = abs(end_sketch.x - start_sketch.x)
            
            # Half-widths (depth into face)
            hw_top = dovetail_width_top / 2
            hw_bottom = dovetail_width_bottom / 2
            
            # Create simple trapezoid: 4 points, wide at top, narrow at bottom
            # The trapezoid spans the full length
            # Try X offset for depth (perpendicular to face)
            p1 = adsk.core.Point3D.create(start_sketch.x - hw_bottom, cy_bottom, 0)  # Bottom left
            p2 = adsk.core.Point3D.create(end_sketch.x + hw_bottom, cy_bottom, 0)     # Bottom right
            p3 = adsk.core.Point3D.create(end_sketch.x + hw_top, cy_top, 0)          # Top right (wide)
            p4 = adsk.core.Point3D.create(start_sketch.x - hw_top, cy_top, 0)        # Top left (wide)
            
            # Create closed trapezoid (4 lines)
            lines.addByTwoPoints(p1, p2)  # Bottom edge (narrow, spans length)
            lines.addByTwoPoints(p2, p3)  # Right side
            lines.addByTwoPoints(p3, p4)  # Top edge (wide, spans length)
            lines.addByTwoPoints(p4, p1)  # Left side
            
            print(f"    Created dovetail trapezoid {groove_idx} at Z={z_pos_world:.2f}, length={length_sketch:.2f}")
        
        if sketch.profiles.count == 0:
            print(f"ERROR: No profiles created in sketch for face {face.index}")
            print(f"  Sketch has {sketch.sketchCurves.count} curves")
            sketch.isLightBulbOn = False
            return False
        
        print(f"  Created {sketch.profiles.count} profile(s)")
        
        extrudes = root.features.extrudeFeatures
        
        for i in range(sketch.profiles.count):
            profile = sketch.profiles.item(i)
            ext_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.CutFeatureOperation)
            ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(dovetail_depth))
            
            try:
                extrudes.add(ext_input)
                print(f"  Created extrude cut #{i}")
            except Exception as e:
                print(f"  ERROR creating extrude #{i}: {e}")
                import traceback
                print(traceback.format_exc())
                return False
        
        sketch.isLightBulbOn = False
        return True
        
    except Exception as e:
        import traceback
        error_msg = f"Error creating dovetail groove: {e}\n{traceback.format_exc()}"
        print(error_msg)
        return False

# ===================== PARAMETERS (cm) =====================

# U-channel track dimensions
TRACK_WIDTH = 1.5         # Total outer width (Y direction)
TRACK_HEIGHT = 1.0        # Total height (Z direction)
TRACK_LENGTH = 5.0        # Length of track piece (X direction)
WALL_THICKNESS = 0.2      # Thickness of walls and floor

# Arrow/chevron joint on floor AND walls
# The arrow creates an interlocking joint that locks when assembled
DOVETAIL_DEPTH = 0.15     # How far arrow tip protrudes into piece 2 (cm)
TAPER_ANGLE = 5           # Taper angle in degrees (creates locking wedge across width)

# Profile shape selection
USE_DOVETAIL_SHAPES = True  # Set to True for trapezoidal dovetails, False for arrow/chevron shapes

# Tapered sliding dovetail parameters
# A tapered sliding dovetail tapers along the sliding direction (X-axis)
# This creates a locking mechanism - pieces slide together but lock when fully assembled
USE_TAPERED_SLIDING_DOVETAIL = False  # Set to True for tapered sliding dovetail
SLIDING_TAPER_ANGLE = 2.0  # Taper angle along X-axis (degrees) - how much dovetail widens/narrows as you slide
SLIDING_TAPER_START_DEPTH = 0.1  # Dovetail depth at start of slide (cm)
SLIDING_TAPER_END_DEPTH = 0.2    # Dovetail depth at end of slide (cm) - deeper = tighter lock

# Dovetail shape parameters (for actual dovetail, not arrows)
# CLASSIC DOVETAIL: Wide at TOP, narrow at BOTTOM (like traditional woodworking dovetail joints)
# This creates the locking mechanism - pieces slide together from the wide opening but lock at the narrow base
DOVETAIL_WIDTH_TOP = 0.3         # Width at TOP of dovetail (wide opening, cm) - where pieces slide in
DOVETAIL_WIDTH_BOTTOM = 0.15     # Width at BOTTOM of dovetail (narrow base, cm) - creates the lock
DOVETAIL_HEIGHT = 0.2            # Height of each dovetail (cm)
DOVETAIL_SPACING = 0.15          # Spacing between dovetails (cm)
REMOVE_FLAT_SEGMENTS = True      # Set to True to eliminate flat segments between dovetails

# Tolerance for 3D printing fit (gap between pieces)
# 0.015 cm = 0.15 mm - typical for FDM printing
# Set to 0 for perfect fit (laser cutting, CNC, or testing)
TOLERANCE = 0.015

# Groove creation mode: Create dovetail grooves on inner faces of branches
# Set to True to create grooves on left/right branch inner faces (for sliding piece)
# Set to False to use the original split method (for connecting track pieces)
CREATE_GROOVES_ON_BRANCHES = True  # NEW: Create grooves on branch inner faces

# ===================== USE EXISTING SKETCHES =====================
# OPTION 1: Use a single symmetric sketch (will be copied to both left and right planes with taper)
# Set USE_EXISTING_SKETCH = True to use your own symmetric sketch
USE_EXISTING_SKETCH = False  # Set to True to use your existing sketch
EXISTING_SKETCH_NAME = "SymmetricProfile"  # Name of your symmetric sketch

# OPTION 2: Use two separate sketches (one for left, one for right - for custom taper)
# Set USE_TWO_EXISTING_SKETCHES = True to use your own left and right sketches
USE_TWO_EXISTING_SKETCHES = False  # Set to True to use your two existing sketches
LEFT_SKETCH_NAME = "ProfileLeft"   # Name of your left profile sketch
RIGHT_SKETCH_NAME = "ProfileRight" # Name of your right profile sketch


def run(context):
    """
    Create a U-channel with TAPERED DOUBLE ARROW joints for SLIDING ASSEMBLY.
    
    DEVELOPMENT TIP:
    ================
    For faster iteration:
    1. Keep Add-Ins dialog open (Cmd+Shift+A / Ctrl+Shift+A)
    2. After editing code, click Stop → Run to reload
    3. Check console output (View → Show Text Commands) for errors
    
    See QUICK_RELOAD.md for detailed reload instructions.
    """
    """
    Create a U-channel with TAPERED DOUBLE ARROW joints for SLIDING ASSEMBLY.
    
    SLIDING ASSEMBLY DESIGN:
    ========================
    This creates two U-shaped track pieces that can be assembled by sliding them together.
    Perfect for creating complex race track circuits (like Spa-Francorchamps) from multiple pieces.
    
    HOW IT WORKS:
    ------------
    1. Creates a U-channel track with U-shape cross-section:
       - Base (floor): horizontal bottom
       - Left branch: left vertical wall  
       - Right branch: right vertical wall
    
    2. Splits the track with a tapered double-arrow cutter:
       - Piece 1 gets SLOTS (female/recessed) on cut face
       - Piece 2 gets TONGUES (male/protruding) on cut face
    
    3. Assembly: Slide Piece 2's tongue into Piece 1's slot along X-axis
    
    4. Taper creates LOCKING WEDGE:
       - Prevents pieces from sliding apart
       - Eliminates gaps that would cause light leaks (critical for LED backlit tracks)
       - Creates tight, secure connection
    
    JOINT FEATURES:
    --------------
    - DOUBLE ARROWS on the floor (bottom of U)
    - DOUBLE ARROWS on the left vertical branch (inner face)
    - DOUBLE ARROWS on the right vertical branch (inner face)
    - TAPER across the width creates a LOCKING WEDGE
    
    RESULT:
    ------
    - Piece 1: has double arrow-shaped SLOTS (female)
    - Piece 2: has double arrow-shaped TONGUES (male)
    - Both branches use the same double arrow wedged pattern
    - Pieces can slide together but taper prevents them from sliding apart
    - Tight fit prevents light leaks for LED backlit applications
    
    See SLIDING_ASSEMBLY_GUIDE.md for detailed documentation.
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

        track = create_u_channel(root)
        track.name = "UChannel"

        # NEW APPROACH: Create dovetail grooves on inner faces of branches
        # This creates grooves on the left and right vertical walls for a sliding piece
        if CREATE_GROOVES_ON_BRANCHES:
            # Find inner faces of left and right branches - use simplified method first
            print("Finding inner faces of U-channel branches...")
            
            left_face, right_face = find_inner_faces_of_u_channel_simple(track)
            
            # If simplified method fails, try the complex one
            if left_face is None or right_face is None:
                print("Simplified method failed, trying complex method...")
                left_face, right_face = find_inner_faces_of_u_channel(track)
            
            # Collect debug info
            debug_info = []
            debug_info.append(f"Face detection results:")
            debug_info.append(f"  Left face: {'Found' if left_face else 'NOT FOUND'}")
            debug_info.append(f"  Right face: {'Found' if right_face else 'NOT FOUND'}")
            
            if left_face is None or right_face is None:
                # Try alternative: manually select faces by analyzing all faces
                ui.messageBox("Primary detection failed. Trying alternative method...")
                print("Primary detection failed. Trying alternative method...")
                left_face, right_face = find_inner_faces_alternative(track, ui)
                
                debug_info.append(f"\nAfter alternative method:")
                debug_info.append(f"  Left face: {'Found' if left_face else 'NOT FOUND'}")
                debug_info.append(f"  Right face: {'Found' if right_face else 'NOT FOUND'}")
            
            if left_face is None or right_face is None:
                # Final attempt: use the first two vertical faces found
                ui.messageBox("Alternative method failed. Trying final fallback...")
                left_face, right_face = find_faces_fallback(track)
                
                debug_info.append(f"\nAfter fallback method:")
                debug_info.append(f"  Left face: {'Found' if left_face else 'NOT FOUND'}")
                debug_info.append(f"  Right face: {'Found' if right_face else 'NOT FOUND'}")
            
            if left_face is None or right_face is None:
                error_msg = "Could not find inner faces of U-channel branches.\n\n"
                error_msg += "\n".join(debug_info)
                error_msg += "\n\nAnalyzing all faces..."
                
                # Analyze all faces and show details
                all_faces_info = analyze_all_faces(track)
                error_msg += "\n\n" + all_faces_info
                error_msg += f"\n\nExpected positions:"
                error_msg += f"\n  Left inner face Y: {WALL_THICKNESS:.3f}"
                error_msg += f"\n  Right inner face Y: {TRACK_WIDTH - WALL_THICKNESS:.3f}"
                error_msg += f"\n\nTry setting CREATE_GROOVES_ON_BRANCHES = False to use split method instead."
                
                # Also print to console
                print(error_msg)
                ui.messageBox(error_msg)
                return
            
            # Define groove positions along Z (height)
            # Create grooves at top and bottom of each branch
            groove_positions_z = [
                WALL_THICKNESS / 2,  # Bottom groove
                TRACK_HEIGHT - WALL_THICKNESS / 2  # Top groove
            ]
            
            # Create grooves on left branch
            success_left = create_dovetail_groove_on_face(
                root, left_face, groove_positions_z, TRACK_LENGTH,
                DOVETAIL_WIDTH_TOP, DOVETAIL_WIDTH_BOTTOM, DOVETAIL_HEIGHT, DOVETAIL_DEPTH
            )
            
            # Create grooves on right branch
            success_right = create_dovetail_groove_on_face(
                root, right_face, groove_positions_z, TRACK_LENGTH,
                DOVETAIL_WIDTH_TOP, DOVETAIL_WIDTH_BOTTOM, DOVETAIL_HEIGHT, DOVETAIL_DEPTH
            )
            
            if success_left and success_right:
                ui.messageBox(
                    f"SUCCESS!\n\n"
                    f"Created dovetail grooves on U-channel branches.\n\n"
                    f"- Left branch: {len(groove_positions_z)} grooves\n"
                    f"- Right branch: {len(groove_positions_z)} grooves\n"
                    f"- Groove length: {TRACK_LENGTH} cm\n"
                    f"- Dovetail shape: {DOVETAIL_WIDTH_TOP}cm wide (top) × {DOVETAIL_WIDTH_BOTTOM}cm narrow (bottom)\n\n"
                    f"A separate sliding piece can now engage with these grooves!"
                )
            else:
                ui.messageBox(f"Failed to create some grooves. Left: {success_left}, Right: {success_right}")
            
            return

        cut_x = TRACK_LENGTH / 2

        # ========================================================================
        # TWO APPROACHES FOR CREATING ARBITRARY SHAPE CUTTERS:
        # ========================================================================
        # 
        # METHOD 1: Sketch → Surface → Thicken (RECOMMENDED)
        #   - Creates two sketches with offset profiles (for taper)
        #   - Lofts between them as a surface
        #   - Thickens the surface to create a solid cutter body
        #   - More flexible: can use any arbitrary sketch profile
        #   - Taper applied by offsetting profiles: taper_offset = ±tan(angle) * distance
        #   - Thickness adjustable independently
        #   - Better for preventing light leaks with proper taper
        #
        # METHOD 2: Loft Surface (ORIGINAL)
        #   - Creates two sketches with offset profiles
        #   - Lofts directly as a surface (no thickening)
        #   - Uses surface for splitting
        #   - Simpler but less flexible
        #
        # ========================================================================
        # NOTE: Surface method (False) creates proper interlocking shapes on both pieces
        # Thicken method (True) may sometimes create flat faces - use with caution
        use_thicken_method = False  # Set to True to try thicken method (may have issues)
        
        if use_thicken_method:
            cutter_body = create_arbitrary_shape_cutter(root, cut_x)
            if cutter_body is None:
                # Fallback to original method if new method fails
                ui.messageBox(
                    "Thicken method failed, falling back to original loft surface method..."
                )
                use_thicken_method = False  # Will continue to original method below
            else:
                # Success - use the new method
                # Check if we got a surface or solid body
                is_surface = cutter_body.faces.count > 0 and cutter_body.volume == 0
                
                ui.messageBox(
                    f"Cutter {'surface' if is_surface else 'body'} created!\n"
                    f"Faces: {cutter_body.faces.count}\n"
                    f"Type: {'Surface' if is_surface else 'Solid'}\n\n"
                    f"Now splitting..."
                )
                
                # Use cutter for splitting (works with both surface and solid)
                split_feats = root.features.splitBodyFeatures
                # Create split input - ensure tool extends fully through body
                split_input = split_feats.createInput(track, cutter_body, True)  # True = extend splitting tool
                
                # Note: SplitBody creates matching profiles on both pieces:
                # - One piece gets SLOTS (female/recessed) where cutter was
                # - Other piece gets TONGUES (male/protruding) matching cutter shape
                # Both should show the profile shape, just inverted
                # If one is flat, the cutter might not be extending fully through
                
                try:
                    split_result = split_feats.add(split_input)
                    pieces = list(split_result.bodies)
                    
                    cutter_body.deleteMe()
                    
                    pieces.sort(key=lambda b: b.physicalProperties.centerOfMass.x)
                    for i, p in enumerate(pieces):
                        p.name = f"Track_Piece_{i+1}"
                    
                    method_type = "surface+thicken" if not is_surface else "surface-only"
                    ui.messageBox(
                        f"SUCCESS!\n\n"
                        f"Created {len(pieces)} pieces using {method_type} method.\n\n"
                        f"- Floor: DOUBLE ARROW shape\n"
                        f"- Left Wall: DOUBLE ARROW shape\n"
                        f"- Right Wall: DOUBLE ARROW shape\n"
                        f"- Taper: {TAPER_ANGLE}° (creates locking wedge)\n"
                        f"- Pieces can slide along the double arrow wedged lines!"
                    )
                    return
                except Exception as e:
                    ui.messageBox(f"Split failed: {e}\n\nFalling back to original method...")
                    use_thicken_method = False  # Fallback to original method
        
        # Original loft surface method (or fallback if new method failed)
        if not use_thicken_method:
            # Check if tapered sliding dovetail is enabled
            if USE_TAPERED_SLIDING_DOVETAIL:
                # Use tapered sliding dovetail (tapers along X-axis)
                surface = create_tapered_sliding_dovetail_surface(root, cut_x)
            else:
                # Regular sliding dovetail (taper only across width)
                surface = create_sliding_dovetail_surface(root, cut_x)

            if surface is None:
                # Check if it's because sketch wasn't found
                if USE_TWO_EXISTING_SKETCHES:
                    ui.messageBox(
                        f"Failed to create cutting surface.\n\n"
                        f"Could not find sketches:\n"
                        f"- Left: '{LEFT_SKETCH_NAME}'\n"
                        f"- Right: '{RIGHT_SKETCH_NAME}'\n\n"
                        f"Please:\n"
                        f"1. Make sure both sketches exist and are named correctly\n"
                        f"2. Update LEFT_SKETCH_NAME and RIGHT_SKETCH_NAME at the top of the file\n"
                        f"3. Your sketches should be symmetric and on the correct planes\n"
                        f"4. Or set USE_TWO_EXISTING_SKETCHES = False to use generated profiles"
                    )
                elif USE_EXISTING_SKETCH:
                    ui.messageBox(
                        f"Failed to create cutting surface.\n\n"
                        f"Could not find sketch '{EXISTING_SKETCH_NAME}'.\n\n"
                        f"Please:\n"
                        f"1. Make sure your sketch is named '{EXISTING_SKETCH_NAME}'\n"
                        f"2. Or update EXISTING_SKETCH_NAME at the top of the file to match your sketch name\n"
                        f"3. Your sketch should be on the XZ plane and symmetric about Z = {TRACK_HEIGHT/2}\n"
                        f"4. Or set USE_EXISTING_SKETCH = False to use generated profile"
                    )
                else:
                    import traceback
                    error_details = traceback.format_exc()
                    ui.messageBox(
                        f"Failed to create cutting surface.\n\n"
                        f"Error details:\n{error_details}\n\n"
                        f"Possible causes:\n"
                        f"1. Profile generation failed (check console for details)\n"
                        f"2. Invalid geometry in dovetail profile\n"
                        f"3. Path creation failed\n\n"
                        f"Try:\n"
                        f"- Set USE_DOVETAIL_SHAPES = False to use arrow shapes\n"
                        f"- Set REMOVE_FLAT_SEGMENTS = False\n"
                        f"- Check DOVETAIL_HEIGHT, DOVETAIL_WIDTH_BOTTOM, DOVETAIL_WIDTH_TOP values"
                    )
                return

            ui.messageBox(
                f"Surface created!\n"
                f"Faces: {surface.faces.count}\n\n"
                f"Now splitting..."
            )

            split_feats = root.features.splitBodyFeatures
            split_input = split_feats.createInput(track, surface, True)  # True = extend splitting tool

            try:
                split_result = split_feats.add(split_input)
                pieces = list(split_result.bodies)
                
                # IMPORTANT: Both pieces should show matching sliding profiles:
                # - Piece 1: SLOTS (female/recessed) - shows profile as indentations
                # - Piece 2: TONGUES (male/protruding) - shows profile as protrusions
                # Both should show the double arrow pattern, just inverted
                # If one is flat, the cutter didn't extend properly through the body

                surface.deleteMe()

                pieces.sort(key=lambda b: b.physicalProperties.centerOfMass.x)
                for i, p in enumerate(pieces):
                    p.name = f"Track_Piece_{i+1}"

                ui.messageBox(
                    f"SUCCESS!\n\n"
                    f"Created {len(pieces)} pieces with tapered arrow joints.\n\n"
                    f"- Floor: DOUBLE ARROW shape\n"
                    f"- Left Wall: DOUBLE ARROW shape\n"
                    f"- Right Wall: DOUBLE ARROW shape\n"
                    f"- Taper: {TAPER_ANGLE}° (creates locking wedge)\n"
                    f"- Pieces can slide along the double arrow wedged lines!"
                )

            except Exception as e:
                ui.messageBox(f"Split failed: {e}")

    except Exception as e:
        if ui:
            error_msg = f"Error in TestDovetailCutter:\n\n{str(e)}\n\n{traceback.format_exc()}"
            ui.messageBox(error_msg)
        else:
            print(f"Error in TestDovetailCutter: {e}")
            traceback.print_exc()


def create_u_channel(root):
    sk = root.sketches.add(root.yZConstructionPlane)
    sk.name = "UChannelProfile"
    lines = sk.sketchCurves.sketchLines

    w = TRACK_WIDTH
    h = TRACK_HEIGHT
    t = WALL_THICKNESS

    p1 = adsk.core.Point3D.create(0, 0, 0)
    p2 = adsk.core.Point3D.create(w, 0, 0)
    p3 = adsk.core.Point3D.create(w, h, 0)
    p4 = adsk.core.Point3D.create(w - t, h, 0)
    p5 = adsk.core.Point3D.create(w - t, t, 0)
    p6 = adsk.core.Point3D.create(t, t, 0)
    p7 = adsk.core.Point3D.create(t, h, 0)
    p8 = adsk.core.Point3D.create(0, h, 0)

    lines.addByTwoPoints(p1, p2)
    lines.addByTwoPoints(p2, p3)
    lines.addByTwoPoints(p3, p4)
    lines.addByTwoPoints(p4, p5)
    lines.addByTwoPoints(p5, p6)
    lines.addByTwoPoints(p6, p7)
    lines.addByTwoPoints(p7, p8)
    lines.addByTwoPoints(p8, p1)

    sk.isLightBulbOn = False

    extrudes = root.features.extrudeFeatures
    ext = extrudes.addSimple(
        sk.profiles.item(0),
        adsk.core.ValueInput.createByReal(TRACK_LENGTH),
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )

    return ext.bodies.item(0)


def create_arbitrary_shape_cutter(root, cut_x):
    """
    Create an arbitrary shape cutter using: SKETCH → SURFACE → THICKEN approach.
    
    This method implements the intuitive workflow:
    1. Create TWO sketches with offset profiles (for taper)
    2. Loft between them as a SURFACE (not solid)
    3. Thicken the surface to create a solid cutter body
    4. Return the solid cutter body for use in split operations
    
    HOW TAPER WORKS:
    - Taper is achieved by creating two profiles at different Y positions
    - The profiles are offset by taper_offset = ±taper_half
    - taper_half = (width/2 + margin) * tan(taper_angle)
    - This creates a wedge shape that prevents light leaks when assembled
    - The taper angle determines how much the cutter widens/narrows across the width
    
    ADVANTAGES:
    - More flexible: can use any arbitrary sketch profile
    - Taper is applied by offsetting the profiles (easy to understand and modify)
    - Thickness can be adjusted independently (cutter_thickness parameter)
    - Works well for preventing light leaks with proper taper
    - Solid body cutter is more robust than surface-only splitting
    
    PARAMETERS:
    - cutter_thickness: How thick the cutter body is (thin = cleaner cut)
    - TAPER_ANGLE: Angle in degrees (positive = wider at end, creates locking wedge)
    """
    import math
    margin = 0.5
    w = TRACK_WIDTH
    # Cutter thickness must be large enough to fully cut through the track
    # Make it thicker than track width to ensure complete cut
    cutter_thickness = max(0.1, TRACK_WIDTH + 0.5)  # Ensure it extends beyond track width
    
    planes = root.constructionPlanes
    
    # Calculate taper offset
    taper_half = (w / 2 + margin) * math.tan(math.radians(TAPER_ANGLE))
    
    # Create two planes for lofting (with taper)
    # Left plane (Y = -margin)
    plane_left_input = planes.createInput()
    plane_left_input.setByOffset(
        root.xZConstructionPlane,
        adsk.core.ValueInput.createByReal(-margin)
    )
    plane_left = planes.add(plane_left_input)
    plane_left.name = "CutterLeftPlane"
    
    # Right plane (Y = w + margin)
    plane_right_input = planes.createInput()
    plane_right_input.setByOffset(
        root.xZConstructionPlane,
        adsk.core.ValueInput.createByReal(w + margin)
    )
    plane_right = planes.add(plane_right_input)
    plane_right.name = "CutterRightPlane"
    
    # STEP 1: Create sketches on both planes with offset profiles (for taper)
    try:
        sk_left = root.sketches.add(plane_left)
        sk_left.name = "CutterProfileLeft"
        path_left = draw_arrow_profile_simple(sk_left, cut_x, margin, taper_offset=-taper_half)
        
        if path_left is None:
            return None
        
        sk_right = root.sketches.add(plane_right)
        sk_right.name = "CutterProfileRight"
        path_right = draw_arrow_profile_simple(sk_right, cut_x, margin, taper_offset=+taper_half)
        
        if path_right is None:
            return None
        
        sk_left.isLightBulbOn = False
        sk_right.isLightBulbOn = False
        plane_left.isLightBulbOn = False
        plane_right.isLightBulbOn = False
        
        # STEP 2: Loft between profiles as SURFACE (not solid)
        lofts = root.features.loftFeatures
        loft_input = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        
        # Validate paths before adding
        if path_left is None or path_right is None:
            return None
        
        loft_input.loftSections.add(path_left)
        loft_input.loftSections.add(path_right)
        loft_input.isSolid = False  # Create surface, not solid
        
        try:
            loft_result = lofts.add(loft_input)
        except Exception as loft_error:
            # Loft failed - return None to trigger fallback
            return None
        
        if loft_result.bodies.count == 0:
            return None
        
        surface_body = loft_result.bodies.item(0)
        surface_body.name = "CutterSurface"
        
        # STEP 3: Thicken the surface to create solid cutter
        thicken_features = root.features.thickenFeatures
        
        # Get faces from the surface body
        if surface_body.faces.count == 0:
            # Return surface if no faces (shouldn't happen, but handle it)
            return surface_body
        
        # Create ObjectCollection of faces to thicken
        faces_to_thicken = adsk.core.ObjectCollection.create()
        for i in range(surface_body.faces.count):
            faces_to_thicken.add(surface_body.faces.item(i))
        
        # Create thicken input
        # Note: Thicken can fail if the surface is too complex or self-intersecting
        # If it fails, we'll use the surface directly (which also works for splitting!)
        try:
            # Create thicken input with faces collection
            # Use half thickness since we thicken on both sides
            half_thickness = cutter_thickness / 2
            thicken_input = thicken_features.createInput(
                faces_to_thicken,
                adsk.core.ValueInput.createByReal(half_thickness),
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )
            
            # Set to thicken on both sides (symmetric thickening)
            # This ensures the cutter extends equally on both sides of the surface
            thicken_input.isBothSides = True
            
            # Add the thicken feature
            thicken_result = thicken_features.add(thicken_input)
            
            if thicken_result.bodies.count == 0:
                # Thicken created no bodies - return surface instead
                # Surface can be used directly for splitting
                return surface_body
            
            cutter_body = thicken_result.bodies.item(0)
            cutter_body.name = "ArbitraryShapeCutter"
            
            # Delete the intermediate surface body (we now have the solid)
            surface_body.deleteMe()
            
            return cutter_body
            
        except Exception as thicken_error:
            # Thicken operation failed - this is OK!
            # Return the surface body instead - it can be used directly for splitting
            # Many users prefer surfaces for splitting anyway
            return surface_body
        
    except Exception as e:
        # Return None if any step fails
        import traceback
        error_msg = f"Error in create_arbitrary_shape_cutter: {str(e)}\n{traceback.format_exc()}"
        # Can't use ui here, so just return None
        return None


def create_tapered_sliding_dovetail_surface(root, cut_x):
    """
    Create a TAPERED SLIDING DOVETAIL surface that tapers along the sliding direction (X-axis).
    
    A tapered sliding dovetail:
    - Tapers along the X-axis (track length direction) - depth varies along X
    - Starts with SLIDING_TAPER_START_DEPTH, ends with SLIDING_TAPER_END_DEPTH
    - Creates a locking mechanism - pieces slide together but lock when fully assembled
    - The dovetail gets deeper as you slide along the track (or shallower, depending on settings)
    
    SIMPLIFIED APPROACH:
    - Use the regular two-sketch method but vary depth based on X position
    - Create profiles at start (X=0) and end (X=TRACK_LENGTH) with different depths
    - The depth variation creates the sliding taper effect
    """
    import math
    margin = 0.5
    w = TRACK_WIDTH
    
    planes = root.constructionPlanes
    
    # Calculate width taper (Y-direction) - for light leak prevention
    taper_half = (w / 2 + margin) * math.tan(math.radians(TAPER_ANGLE))
    
    # Use the same approach as regular method, but create profiles at start and end
    # Left plane (Y = -margin) - will create profiles at different X positions
    plane_left_input = planes.createInput()
    plane_left_input.setByOffset(
        root.xZConstructionPlane,
        adsk.core.ValueInput.createByReal(-margin)
    )
    plane_left = planes.add(plane_left_input)
    plane_left.name = "LeftPlane"
    
    # Right plane (Y = w + margin)
    plane_right_input = planes.createInput()
    plane_right_input.setByOffset(
        root.xZConstructionPlane,
        adsk.core.ValueInput.createByReal(w + margin)
    )
    plane_right = planes.add(plane_right_input)
    plane_right.name = "RightPlane"
    
    # Create profiles at START (X=0) with START depth - using ACTUAL DOVETAIL shapes
    sk_start_left = root.sketches.add(plane_left)
    sk_start_left.name = "TaperedStartLeft"
    path_start_left = draw_dovetail_profile_tapered(sk_start_left, 0, margin, -taper_half, SLIDING_TAPER_START_DEPTH)
    
    sk_start_right = root.sketches.add(plane_right)
    sk_start_right.name = "TaperedStartRight"
    path_start_right = draw_dovetail_profile_tapered(sk_start_right, 0, margin, +taper_half, SLIDING_TAPER_START_DEPTH)
    
    # Create profiles at END (X=TRACK_LENGTH) with END depth - using ACTUAL DOVETAIL shapes
    sk_end_left = root.sketches.add(plane_left)
    sk_end_left.name = "TaperedEndLeft"
    path_end_left = draw_dovetail_profile_tapered(sk_end_left, TRACK_LENGTH, margin, -taper_half, SLIDING_TAPER_END_DEPTH)
    
    sk_end_right = root.sketches.add(plane_right)
    sk_end_right.name = "TaperedEndRight"
    path_end_right = draw_dovetail_profile_tapered(sk_end_right, TRACK_LENGTH, margin, +taper_half, SLIDING_TAPER_END_DEPTH)
    
    # Hide sketches
    sk_start_left.isLightBulbOn = False
    sk_start_right.isLightBulbOn = False
    sk_end_left.isLightBulbOn = False
    sk_end_right.isLightBulbOn = False
    plane_left.isLightBulbOn = False
    plane_right.isLightBulbOn = False
    
    if not (path_start_left and path_start_right and path_end_left and path_end_right):
        return None
    
    # Create loft with all 4 profiles to create tapered surface
    # Order: start_left -> start_right -> end_right -> end_left -> start_left (closed)
    lofts = root.features.loftFeatures
    loft_input = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    
    # Add profiles in order to create proper loft
    loft_input.loftSections.add(path_start_left)
    loft_input.loftSections.add(path_start_right)
    loft_input.loftSections.add(path_end_right)
    loft_input.loftSections.add(path_end_left)
    loft_input.isSolid = False
    
    try:
        loft_result = lofts.add(loft_input)
        if loft_result.bodies.count > 0:
            return loft_result.bodies.item(0)
        return None
    except Exception as e:
        import traceback
        print(f"Error creating tapered sliding dovetail: {e}\n{traceback.format_exc()}")
        return None


def draw_dovetail_profile_simple(sketch, cut_x, margin, taper_offset):
    """
    Draw ACTUAL DOVETAIL shapes (trapezoids) - simple version without X-axis taper.
    
    Creates trapezoidal dovetail shapes (wide at TOP, narrow at BOTTOM) along the height.
    This is the standard dovetail profile for regular sliding dovetail joints.
    
    Parameters:
    - sketch: Sketch to draw on (XZ plane)
    - cut_x: X position of cut plane
    - margin: Margin for extending
    - taper_offset: Taper offset for width (Y-direction) - for light leak prevention
    """
    import math
    import traceback
    
    try:
        print(f"draw_dovetail_profile_simple called: cut_x={cut_x}, margin={margin}, taper_offset={taper_offset}")
        lines = sketch.sketchCurves.sketchLines
        
        t = WALL_THICKNESS
        h = TRACK_HEIGHT
        
        print(f"  TRACK_HEIGHT={h}, WALL_THICKNESS={t}")
        print(f"  DOVETAIL_HEIGHT={DOVETAIL_HEIGHT}, DOVETAIL_WIDTH_TOP={DOVETAIL_WIDTH_TOP}, DOVETAIL_WIDTH_BOTTOM={DOVETAIL_WIDTH_BOTTOM}")
        
        # Validate parameters
        if DOVETAIL_HEIGHT <= 0 or DOVETAIL_WIDTH_BOTTOM <= 0 or DOVETAIL_WIDTH_TOP <= 0:
            print(f"Error: Invalid dovetail parameters - HEIGHT={DOVETAIL_HEIGHT}, WIDTH_BOTTOM={DOVETAIL_WIDTH_BOTTOM}, WIDTH_TOP={DOVETAIL_WIDTH_TOP}")
            return None
        
        # Classic dovetail: TOP should be WIDER than BOTTOM (creates locking mechanism)
        if DOVETAIL_WIDTH_TOP <= DOVETAIL_WIDTH_BOTTOM:
            print(f"Warning: DOVETAIL_WIDTH_TOP ({DOVETAIL_WIDTH_TOP}) should be GREATER than DOVETAIL_WIDTH_BOTTOM ({DOVETAIL_WIDTH_BOTTOM}) for proper dovetail locking")
    
        # X positions - dovetail extends forward from cut plane
        x_flat = cut_x - TOLERANCE / 2  # Back (flat) position
        x_tip_base = cut_x + DOVETAIL_DEPTH + taper_offset  # Forward (tip) position
        
        print(f"  x_flat={x_flat}, x_tip_base={x_tip_base}, DOVETAIL_DEPTH={DOVETAIL_DEPTH}")
        
        # Use global REMOVE_FLAT_SEGMENTS setting
        use_continuous = REMOVE_FLAT_SEGMENTS
        points = []  # Initialize points list
        print(f"  use_continuous (REMOVE_FLAT_SEGMENTS)={use_continuous}")
        
        if use_continuous:
            # CONTINUOUS dovetail pattern - NO FLAT SEGMENTS between dovetails
            # Dovetails connect directly to each other, creating a continuous interlocking profile
            points.append(adsk.core.Point3D.create(x_flat, -margin, 0))  # Start at bottom margin
            points.append(adsk.core.Point3D.create(x_flat, 0, 0))  # Start of profile
            
            # Calculate how many dovetails fit in the height
            # Make them overlap so they connect seamlessly without flat segments
            # Use a reasonable overlap factor to ensure connection
            overlap_factor = 0.8  # 20% overlap
            num_dovetails = max(2, int(h / (DOVETAIL_HEIGHT * overlap_factor)))
            
            if num_dovetails < 2:
                # Fallback: use the non-REMOVE_FLAT_SEGMENTS method
                print("Warning: Not enough space for continuous dovetails, using flat segments")
                use_continuous = False
            else:
                dovetail_spacing = h / num_dovetails if num_dovetails > 1 else DOVETAIL_HEIGHT
                
                # Calculate width ratio for trapezoidal shape
                width_ratio = DOVETAIL_WIDTH_TOP / DOVETAIL_WIDTH_BOTTOM if DOVETAIL_WIDTH_BOTTOM > 0 else 0.5
                
                # Create continuous dovetail pattern
                for i in range(num_dovetails):
                    # Center Z position of this dovetail
                    dovetail_z = i * dovetail_spacing + DOVETAIL_HEIGHT / 2
                    
                    # Ensure we don't exceed height
                    if dovetail_z + DOVETAIL_HEIGHT / 2 > h:
                        dovetail_z = h - DOVETAIL_HEIGHT / 2
                    
                    z_bottom = max(0, dovetail_z - DOVETAIL_HEIGHT / 2)
                    z_top = min(h, dovetail_z + DOVETAIL_HEIGHT / 2)
                    
                    # Validate z_bottom < z_top
                    if z_bottom >= z_top:
                        print(f"Warning: Invalid dovetail geometry at i={i}, z_bottom={z_bottom}, z_top={z_top}")
                        continue
                    
                    # X positions for trapezoid
                    # CLASSIC DOVETAIL: Wide at TOP, narrow at BOTTOM (like the image)
                    width_ratio = DOVETAIL_WIDTH_TOP / DOVETAIL_WIDTH_BOTTOM if DOVETAIL_WIDTH_BOTTOM > 0 else 0.5
                    x_top_right = x_tip_base  # TOP extends full depth forward (WIDE part)
                    x_bottom_right = x_flat + (x_tip_base - x_flat) * width_ratio  # BOTTOM extends less (NARROW part)
                    
                    if i == 0:
                        # First dovetail: start from bottom
                        points.append(adsk.core.Point3D.create(x_flat, z_bottom, 0))
                    else:
                        # Connect directly from previous dovetail's top-left to this bottom-left
                        # Get the last point's Z position
                        last_z = points[-1].y if points else z_bottom
                        if last_z < z_bottom:
                            # Add connection point if there's a gap
                            points.append(adsk.core.Point3D.create(x_flat, z_bottom, 0))
                        elif last_z > z_bottom:
                            # Overlapping: adjust z_bottom to connect smoothly
                            z_bottom = last_z
                            points.append(adsk.core.Point3D.create(x_flat, z_bottom, 0))
                        # If last_z == z_bottom, we're already at the right position
                    
                    # Dovetail trapezoid: wide at TOP, narrow at BOTTOM (classic dovetail shape)
                    # Bottom left (narrow end, flat position)
                    # Bottom right (narrow end, extends forward less) - narrow base
                    points.append(adsk.core.Point3D.create(x_bottom_right, z_bottom, 0))
                    # Top right (wide end, extends forward more) - wide opening
                    points.append(adsk.core.Point3D.create(x_top_right, z_top, 0))
                    # Top left (wide end, back to flat) - connects to next dovetail
                    points.append(adsk.core.Point3D.create(x_flat, z_top, 0))
                    
                    # Stop if we've reached the top
                    if z_top >= h:
                        break
                
                # Connect to top (no flat segment - connect directly from last dovetail)
                last_z = points[-1].y if points else h
                if last_z < h:
                    points.append(adsk.core.Point3D.create(x_flat, h, 0))
                
                points.append(adsk.core.Point3D.create(x_flat, h + margin, 0))  # End at top margin
        
        # If REMOVE_FLAT_SEGMENTS was disabled or failed, use the original method
        if not use_continuous or len(points) < 3:
            # ORIGINAL: Flat sections between dovetails (for traditional dovetail joints)
            # Create multiple dovetails along the height (Z direction)
            # Symmetric pattern: dovetails at bottom, middle, and top sections
            points = []
            points.append(adsk.core.Point3D.create(x_flat, -margin, 0))  # Start at bottom margin
            
            dovetails_z_positions = []
            
            # Bottom dovetail (near Z=0, on floor/base)
            dovetails_z_positions.append(t / 2)
            
            # Middle dovetail (center, on vertical walls)
            dovetails_z_positions.append(h / 2)
            
            # Top dovetail (near Z=h, on vertical walls)
            dovetails_z_positions.append(h - t / 2)
            
            current_z = 0
            
            for dovetail_z in dovetails_z_positions:
                # Flat section before dovetail
                if current_z < dovetail_z - DOVETAIL_HEIGHT / 2:
                    points.append(adsk.core.Point3D.create(x_flat, current_z, 0))
                    points.append(adsk.core.Point3D.create(x_flat, dovetail_z - DOVETAIL_HEIGHT / 2, 0))
                
                # Dovetail trapezoid: wide at bottom, narrow at top
                z_bottom = dovetail_z - DOVETAIL_HEIGHT / 2
                z_top = dovetail_z + DOVETAIL_HEIGHT / 2
                
                # Calculate X positions for dovetail trapezoid
                # CLASSIC DOVETAIL: Wide at TOP, narrow at BOTTOM (like the image)
                # This creates the locking mechanism - slides in from top (wide) but locks at bottom (narrow)
                width_ratio = DOVETAIL_WIDTH_TOP / DOVETAIL_WIDTH_BOTTOM if DOVETAIL_WIDTH_BOTTOM > 0 else 0.5
                x_top_right = x_tip_base  # TOP extends full depth forward (WIDE part)
                x_bottom_right = x_flat + (x_tip_base - x_flat) * width_ratio  # BOTTOM extends less (NARROW part)
                
                # Bottom left (narrow end, flat position)
                points.append(adsk.core.Point3D.create(x_flat, z_bottom, 0))
                # Bottom right (narrow end, extends forward less) - narrow base
                points.append(adsk.core.Point3D.create(x_bottom_right, z_bottom, 0))
                # Top right (wide end, extends forward more) - wide opening
                points.append(adsk.core.Point3D.create(x_top_right, z_top, 0))
                # Top left (wide end, back to flat)
                points.append(adsk.core.Point3D.create(x_flat, z_top, 0))
                
                current_z = z_top
            
            # Flat section to top
            if current_z < h:
                points.append(adsk.core.Point3D.create(x_flat, current_z, 0))
                points.append(adsk.core.Point3D.create(x_flat, h, 0))
            
            points.append(adsk.core.Point3D.create(x_flat, h + margin, 0))  # End at top margin
        
        # Draw connected lines - remove duplicate consecutive points and add error handling
        print(f"  Created {len(points)} points for dovetail profile")
        if len(points) < 2:
            print(f"Error in draw_dovetail_profile_simple: Not enough points ({len(points)} points)")
            print(f"  REMOVE_FLAT_SEGMENTS={REMOVE_FLAT_SEGMENTS}")
            return None
        
        # Remove duplicate consecutive points
        cleaned_points = [points[0]]
        for i in range(1, len(points)):
            prev_pt = cleaned_points[-1]
            curr_pt = points[i]
            # Check if points are different (with small tolerance)
            if abs(prev_pt.x - curr_pt.x) > 0.001 or abs(prev_pt.y - curr_pt.y) > 0.001:
                cleaned_points.append(curr_pt)
        
        if len(cleaned_points) < 2:
            print(f"Error in draw_dovetail_profile_simple: Not enough unique points after cleaning ({len(cleaned_points)} points)")
            return None
        
        curves = adsk.core.ObjectCollection.create()
        for i in range(len(cleaned_points) - 1):
            line = lines.addByTwoPoints(cleaned_points[i], cleaned_points[i + 1])
            if line:
                curves.add(line)
        
        if curves.count == 0:
            print(f"Error in draw_dovetail_profile_simple: No curves created from {len(cleaned_points)} points")
            return None
        
        path = adsk.fusion.Path.create(curves, False)
        if path is None:
            print(f"Error in draw_dovetail_profile_simple: Failed to create path from {curves.count} curves")
            return None
        
        print(f"  Successfully created path with {curves.count} curves")
        return path
        
    except Exception as e:
        error_msg = f"Error in draw_dovetail_profile_simple: {e}\n{traceback.format_exc()}"
        print(error_msg)
        return None


def draw_dovetail_profile_tapered(sketch, x_position, margin, taper_offset, dovetail_depth):
    """
    Draw ACTUAL DOVETAIL shapes (trapezoids) that taper along X (sliding direction).
    
    A tapered sliding dovetail:
    - Uses trapezoidal dovetail shapes (wide at TOP, narrow at BOTTOM - classic dovetail)
    - The dovetail width tapers along X (sliding direction) - gets wider/narrower as you slide
    - Creates proper locking mechanism - pieces slide together but lock when fully assembled
    
    Parameters:
    - sketch: Sketch to draw on (XZ plane)
    - x_position: X position along track (0 to TRACK_LENGTH) - determines taper
    - margin: Margin for extending
    - taper_offset: Taper offset for width (Y-direction) - for light leak prevention
    - dovetail_depth: Depth of dovetail at this X position (varies for sliding taper)
    """
    import math
    lines = sketch.sketchCurves.sketchLines
    
    t = WALL_THICKNESS
    h = TRACK_HEIGHT
    
    # Calculate taper along X (sliding direction)
    # Both depth and width vary from start to end based on X position
    t_normalized = x_position / TRACK_LENGTH if TRACK_LENGTH > 0 else 0.5  # 0 to 1
    
    # Depth taper: dovetail gets deeper as you slide (creates locking mechanism)
    # This is the primary taper for sliding dovetail
    depth_taper_factor = SLIDING_TAPER_START_DEPTH + t_normalized * (SLIDING_TAPER_END_DEPTH - SLIDING_TAPER_START_DEPTH)
    actual_dovetail_depth = depth_taper_factor
    
    # Width taper: dovetail also gets wider as you slide (secondary taper)
    # Positive angle = wider at end = tighter lock
    width_taper_factor = 1.0 + t_normalized * math.tan(math.radians(SLIDING_TAPER_ANGLE))
    dovetail_width_bottom = DOVETAIL_WIDTH_BOTTOM * width_taper_factor
    dovetail_width_top = DOVETAIL_WIDTH_TOP * width_taper_factor
    
    # X positions - dovetail extends forward from cut plane
    x_flat = x_position - TOLERANCE / 2  # Back (flat) position
    x_tip_base = x_position + actual_dovetail_depth + taper_offset  # Forward (tip) position
    
    # Create multiple dovetails along the height (Z direction)
    # Symmetric pattern: dovetails at bottom, middle, and top sections
    dovetails_z_positions = []
    
    # Bottom dovetail (near Z=0, on floor/base)
    dovetails_z_positions.append(t / 2)
    
    # Middle dovetail (center, on vertical walls)
    dovetails_z_positions.append(h / 2)
    
    # Top dovetail (near Z=h, on vertical walls)
    dovetails_z_positions.append(h - t / 2)
    
    # Build profile: flat sections with dovetail trapezoids
    points = []
    points.append(adsk.core.Point3D.create(x_flat, -margin, 0))  # Start at bottom margin
    
    current_z = 0
    
    for dovetail_z in dovetails_z_positions:
        # Flat section before dovetail
        if current_z < dovetail_z - DOVETAIL_HEIGHT / 2:
            points.append(adsk.core.Point3D.create(x_flat, current_z, 0))
            points.append(adsk.core.Point3D.create(x_flat, dovetail_z - DOVETAIL_HEIGHT / 2, 0))
        
        # Dovetail trapezoid: wide at TOP, narrow at BOTTOM (classic dovetail shape)
        # This creates the locking mechanism - wide opening at top, narrow lock at bottom
        z_bottom = dovetail_z - DOVETAIL_HEIGHT / 2
        z_top = dovetail_z + DOVETAIL_HEIGHT / 2
        
        # Calculate X positions for dovetail trapezoid
        # CLASSIC DOVETAIL: Wide at TOP, narrow at BOTTOM (like the image)
        # The width ratio determines how much less the bottom extends
        width_ratio = dovetail_width_top / dovetail_width_bottom if dovetail_width_bottom > 0 else 0.5
        x_top_right = x_tip_base  # TOP extends full depth forward (WIDE part)
        x_bottom_right = x_flat + (x_tip_base - x_flat) * width_ratio  # BOTTOM extends less (NARROW part)
        
        # Bottom left (narrow end, flat position)
        points.append(adsk.core.Point3D.create(x_flat, z_bottom, 0))
        # Bottom right (narrow end, extends forward less) - narrow base
        points.append(adsk.core.Point3D.create(x_bottom_right, z_bottom, 0))
        # Top right (wide end, extends forward more) - wide opening
        points.append(adsk.core.Point3D.create(x_top_right, z_top, 0))
        # Top left (wide end, back to flat)
        points.append(adsk.core.Point3D.create(x_flat, z_top, 0))
        
        current_z = z_top
    
    # Flat section to top
    if current_z < h:
        points.append(adsk.core.Point3D.create(x_flat, current_z, 0))
        points.append(adsk.core.Point3D.create(x_flat, h, 0))
    
    points.append(adsk.core.Point3D.create(x_flat, h + margin, 0))  # End at top margin
    
    # Draw connected lines
    curves = adsk.core.ObjectCollection.create()
    for i in range(len(points) - 1):
        curves.add(lines.addByTwoPoints(points[i], points[i + 1]))
    
    return adsk.fusion.Path.create(curves, False)


def draw_arrow_profile_with_depth(sketch, x_position, margin, taper_offset, dovetail_depth):
    """
    Draw arrow profile with a specific dovetail depth (for tapered sliding dovetail).
    
    Works on either XZ planes (for regular taper) or YZ planes (for sliding taper).
    The sketch plane determines the coordinate system.
    
    Parameters:
    - sketch: Sketch to draw on (on XZ or YZ plane)
    - x_position: X position where this profile is located (for YZ planes)
    - margin: Margin for extending
    - taper_offset: Taper offset (for width taper)
    - dovetail_depth: Depth of dovetail at this X position (varies for sliding taper)
    """
    lines = sketch.sketchCurves.sketchLines
    
    t = WALL_THICKNESS
    h = TRACK_HEIGHT
    
    # Determine if sketch is on XZ plane or YZ plane
    # Check the sketch's coordinate system
    sketch_origin = sketch.origin
    # For XZ plane: Y is constant, X and Z vary
    # For YZ plane: X is constant, Y and Z vary
    
    # Same symmetric pattern as before
    z_bottom = -margin
    z_top_margin = h + margin
    
    # Bottom section: double arrow pattern
    z_bottom_start = 0
    z_bottom_arrow1 = h / 12
    z_bottom_mid1 = h / 6
    z_bottom_arrow2 = h / 4
    z_bottom_mid2 = h / 3
    z_center = h / 2
    
    # Top section: mirror of bottom
    z_top_arrow2 = h - h / 4
    z_top_mid1 = h - h / 6
    z_top_arrow1 = h - h / 12
    z_top_end = h
    
    # Calculate positions - depends on plane type
    # For XZ plane: X varies, Z varies, Y is constant (plane offset)
    # For YZ plane: Y varies, Z varies, X is constant (plane offset)
    
    # Assume XZ plane for now (same as original)
    # X positions - use provided dovetail_depth instead of DOVETAIL_DEPTH
    x_flat = x_position - TOLERANCE / 2
    x_tip = x_position + dovetail_depth + taper_offset  # Use variable depth
    
    # Points (same pattern as before, but depth varies)
    points = [
        adsk.core.Point3D.create(x_flat, z_bottom, 0),
        adsk.core.Point3D.create(x_tip, z_bottom_start, 0),
        adsk.core.Point3D.create(x_flat, z_bottom_mid1, 0),
        adsk.core.Point3D.create(x_tip, z_bottom_arrow1, 0),
        adsk.core.Point3D.create(x_flat, z_bottom_mid2, 0),
        adsk.core.Point3D.create(x_tip, z_bottom_arrow2, 0),
        adsk.core.Point3D.create(x_flat, z_center, 0),
        adsk.core.Point3D.create(x_tip, z_top_arrow2, 0),
        adsk.core.Point3D.create(x_flat, z_top_mid1, 0),
        adsk.core.Point3D.create(x_tip, z_top_arrow1, 0),
        adsk.core.Point3D.create(x_tip, z_top_end, 0),
        adsk.core.Point3D.create(x_flat, z_top_margin, 0),
    ]
    
    # Draw connected lines
    curves = adsk.core.ObjectCollection.create()
    for i in range(len(points) - 1):
        curves.add(lines.addByTwoPoints(points[i], points[i + 1]))
    
    return adsk.fusion.Path.create(curves, False)


def create_sliding_dovetail_surface(root, cut_x):
    """
    Create a cutting surface using TWO SKETCH APPROACH (normal and required for taper).

    TWO SKETCH APPROACH IS NORMAL AND REQUIRED:
    -------------------------------------------
    We use TWO sketches (ProfileLeft and ProfileRight) because:
    1. Taper requires offset profiles at different Y positions
    2. Left sketch at Y = -margin with taper_offset = -taper_half
    3. Right sketch at Y = w + margin with taper_offset = +taper_half
    4. Lofting between them creates the tapered wedge shape
    5. This taper prevents light leaks and creates locking mechanism
    
    Process:
    1. Draw arrow profile on LEFT plane (Y = -margin) with negative taper offset
    2. Draw arrow profile on RIGHT plane (Y = w + margin) with positive taper offset
    3. Loft between the two profiles as SURFACE (not solid)
    4. Use the surface to split the body

    The taper makes the arrow tips shift across Y, creating the locking wedge.
    This is the standard approach for creating tapered interlocking joints.
    """
    import math
    margin = 0.5
    w = TRACK_WIDTH

    planes = root.constructionPlanes

    # Calculate symmetric taper: both profiles get same arrow shape,
    # but shifted in opposite directions for locking wedge
    taper_half = (w / 2 + margin) * math.tan(math.radians(TAPER_ANGLE))

    # Left plane (Y = -margin)
    plane_left_input = planes.createInput()
    plane_left_input.setByOffset(
        root.xZConstructionPlane,
        adsk.core.ValueInput.createByReal(-margin)
    )
    plane_left = planes.add(plane_left_input)
    plane_left.name = "LeftPlane"

    # Right plane (Y = w + margin)
    plane_right_input = planes.createInput()
    plane_right_input.setByOffset(
        root.xZConstructionPlane,
        adsk.core.ValueInput.createByReal(w + margin)
    )
    plane_right = planes.add(plane_right_input)
    plane_right.name = "RightPlane"

    # Draw profiles on both planes
    # OPTION 1: Use two existing sketches (one for left, one for right) - BEST for custom taper
    # OPTION 2: Use one symmetric sketch (copied to both planes with taper offset)
    # OPTION 3: Use custom profile points
    # OPTION 4: Generate profile programmatically (default)
    
    USE_CUSTOM_PROFILE = False  # Set to True to use custom profile points
    
    if USE_TWO_EXISTING_SKETCHES:
        # Use your two existing sketches directly
        # These sketches should already be created and positioned correctly
        # They will be used as-is for the loft (taper is already in the sketches)
        path_left = get_path_from_existing_sketch(root, LEFT_SKETCH_NAME, plane_left, cut_x, margin, -taper_half)
        path_right = get_path_from_existing_sketch(root, RIGHT_SKETCH_NAME, plane_right, cut_x, margin, +taper_half)
        
        if path_left is None or path_right is None:
            return None  # Error will be handled by caller
        
        # Don't hide the sketches since they're user-created
        plane_left.isLightBulbOn = False
        plane_right.isLightBulbOn = False
    
    else:
        # Create new sketches on the planes
        sk_left = root.sketches.add(plane_left)
        sk_left.name = "ProfileLeft"
        
        if USE_EXISTING_SKETCH:
            # Use your existing symmetric sketch (copied to left plane with negative taper)
            path_left = copy_sketch_to_plane_with_taper(root, EXISTING_SKETCH_NAME, plane_left, cut_x, margin, -taper_half)
            if path_left is None:
                return None
        elif USE_CUSTOM_PROFILE:
            # Define your custom profile here:
            # z_points: List of Z positions (heights) from 0 to TRACK_HEIGHT
            # x_is_tip: List of booleans - True for arrow tip (x_tip), False for flat (x_flat)
            # Example for symmetric double arrow:
            custom_z_points = [0, 0.05, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 0.95, 1.0]
            custom_x_is_tip = [True, False, True, False, True, False, True, False, True, False, True]
            path_left = draw_custom_profile_from_points(sk_left, cut_x, margin, -taper_half, custom_z_points, custom_x_is_tip)
        else:
            # Choose between dovetail shapes or arrow shapes
            if USE_DOVETAIL_SHAPES:
                print(f"Creating left dovetail profile with cut_x={cut_x}, margin={margin}, taper_offset={-taper_half}")
                path_left = draw_dovetail_profile_simple(sk_left, cut_x, margin, taper_offset=-taper_half)
                if path_left is None:
                    print("ERROR: draw_dovetail_profile_simple returned None for left profile")
            else:
                path_left = draw_arrow_profile_simple(sk_left, cut_x, margin, taper_offset=-taper_half)
        
        # Check if left path was created successfully
        if path_left is None:
            print(f"ERROR: Failed to create left path. USE_DOVETAIL_SHAPES={USE_DOVETAIL_SHAPES}")
            sk_left.isLightBulbOn = False
            plane_left.isLightBulbOn = False
            plane_right.isLightBulbOn = False
            return None

        sk_right = root.sketches.add(plane_right)
        sk_right.name = "ProfileRight"
        
        if USE_EXISTING_SKETCH:
            # Use your existing symmetric sketch (copied to right plane with positive taper)
            path_right = copy_sketch_to_plane_with_taper(root, EXISTING_SKETCH_NAME, plane_right, cut_x, margin, +taper_half)
            if path_right is None:
                return None
        elif USE_CUSTOM_PROFILE:
            # Use same profile points for right side (with positive taper offset)
            path_right = draw_custom_profile_from_points(sk_right, cut_x, margin, +taper_half, custom_z_points, custom_x_is_tip)
        else:
            # Choose between dovetail shapes or arrow shapes
            if USE_DOVETAIL_SHAPES:
                print(f"Creating right dovetail profile with cut_x={cut_x}, margin={margin}, taper_offset={+taper_half}")
                path_right = draw_dovetail_profile_simple(sk_right, cut_x, margin, taper_offset=+taper_half)
                if path_right is None:
                    print("ERROR: draw_dovetail_profile_simple returned None for right profile")
            else:
                path_right = draw_arrow_profile_simple(sk_right, cut_x, margin, taper_offset=+taper_half)
        
        # Check if right path was created successfully
        if path_right is None:
            print(f"ERROR: Failed to create right path. USE_DOVETAIL_SHAPES={USE_DOVETAIL_SHAPES}")
            sk_left.isLightBulbOn = False
            sk_right.isLightBulbOn = False
            plane_left.isLightBulbOn = False
            plane_right.isLightBulbOn = False
            return None
        
        sk_left.isLightBulbOn = False
        sk_right.isLightBulbOn = False

    plane_left.isLightBulbOn = False
    plane_right.isLightBulbOn = False

    # Check if paths were created successfully
    if path_left is None or path_right is None:
        import traceback
        print(f"Error in create_sliding_dovetail_surface: Failed to create paths")
        print(f"  path_left: {path_left is not None}")
        print(f"  path_right: {path_right is not None}")
        return None

    # Loft between the two profiles
    lofts = root.features.loftFeatures
    loft_input = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    loft_input.loftSections.add(path_left)
    loft_input.loftSections.add(path_right)
    loft_input.isSolid = False  # Create surface, not solid

    try:
        loft_result = lofts.add(loft_input)
        return loft_result.bodies.item(0)
    except:
        return None


def get_path_from_existing_sketch(root, sketch_name, target_plane, cut_x, margin, taper_offset=0):
    """
    Get a path from an existing sketch that's already on the target plane.
    
    This is for when you have TWO sketches (one for left, one for right) already created.
    The sketches should already be positioned correctly on their respective planes.
    
    Parameters:
    - root: Root component
    - sketch_name: Name of your existing sketch (should be on target_plane)
    - target_plane: The plane the sketch is on (for validation)
    - cut_x: X position of cut plane
    - margin: Margin
    - taper_offset: Taper offset (already applied in your sketch, or will be applied)
    
    Returns: Path object, or None if sketch not found
    """
    try:
        # Find the sketch
        sketches = root.sketches
        source_sketch = None
        
        for i in range(sketches.count):
            sk = sketches.item(i)
            if sk.name == sketch_name:
                source_sketch = sk
                break
        
        if source_sketch is None:
            return None
        
        # Extract curves from the sketch and create a path
        source_curves = source_sketch.sketchCurves
        curves = adsk.core.ObjectCollection.create()
        
        # Collect all curves from the sketch
        for i in range(source_curves.count):
            curve = source_curves.item(i)
            # Add the curve directly - it should already be in the correct position
            curves.add(curve)
        
        if curves.count > 0:
            # Create path from the curves
            # The curves are already positioned correctly on the plane
            return adsk.fusion.Path.create(curves, False)
        
        return None
        
    except Exception as e:
        import traceback
        print(f"Error getting path from sketch: {e}\n{traceback.format_exc()}")
        return None


def copy_sketch_to_plane_with_taper(root, sketch_name, target_plane, cut_x, margin, taper_offset=0):
    """
    Copy an existing sketch to a target plane and apply taper offset.
    
    This function:
    1. Finds your existing symmetric sketch by name
    2. Copies its geometry to the target plane (left or right)
    3. Applies taper offset to the X coordinates (for creating the wedge)
    
    Your sketch should be on the XZ plane with:
    - X coordinates relative to the cut position
    - Z coordinates from 0 to TRACK_HEIGHT
    - Symmetric about Z = TRACK_HEIGHT/2
    
    Parameters:
    - root: Root component
    - sketch_name: Name of your existing symmetric sketch
    - target_plane: Plane to copy to (left or right plane)
    - cut_x: X position of cut plane
    - margin: Margin for extending
    - taper_offset: Taper offset to apply (±taper_half)
    
    Returns: Path object for loft, or None if sketch not found
    """
    try:
        # Find the source sketch
        sketches = root.sketches
        source_sketch = None
        
        for i in range(sketches.count):
            sk = sketches.item(i)
            if sk.name == sketch_name:
                source_sketch = sk
                break
        
        if source_sketch is None:
            return None
        
        # Create target sketch
        target_sketch = root.sketches.add(target_plane)
        target_sketch.name = f"Copy_{sketch_name}"
        target_lines = target_sketch.sketchCurves.sketchLines
        
        x_flat = cut_x - TOLERANCE / 2
        x_tip = cut_x + DOVETAIL_DEPTH + taper_offset
        
        # Extract points from source sketch curves
        # We'll collect all endpoints from lines
        points_dict = {}  # z -> (x, is_tip)
        
        source_curves = source_sketch.sketchCurves
        for i in range(source_curves.count):
            curve = source_curves.item(i)
            if curve.curveType == adsk.core.Curve3DTypes.Line3DCurveType:
                line = adsk.core.Line3D.cast(curve.geometry)
                
                # Get points in sketch coordinates
                start_sketch = source_sketch.modelToSketchSpace(line.startPoint)
                end_sketch = source_sketch.modelToSketchSpace(line.endPoint)
                
                # Determine if points are tips (forward) or flat (back)
                # Check X coordinate - if it's significantly forward, it's a tip
                # The source sketch X should be relative to cut_x
                start_x_abs = start_sketch.x  # Assuming sketch X is relative
                end_x_abs = end_sketch.x
                
                # Heuristic: if X > some threshold, it's a tip
                # We'll use the fact that tips extend forward
                threshold = DOVETAIL_DEPTH / 2
                start_is_tip = abs(start_x_abs) > threshold
                end_is_tip = abs(end_x_abs) > threshold
                
                # Store points (Z coordinate, X position, is_tip)
                z_start = start_sketch.y  # In XZ plane, Y in sketch = Z in model
                z_end = end_sketch.y
                
                x_start = x_tip if start_is_tip else x_flat
                x_end = x_tip if end_is_tip else x_flat
                
                points_dict[z_start] = (x_start, z_start)
                points_dict[z_end] = (x_end, z_end)
        
        # Sort points by Z
        sorted_points = sorted(points_dict.values(), key=lambda p: p[1])
        
        if len(sorted_points) < 2:
            return None
        
        # Draw lines connecting points
        curves = adsk.core.ObjectCollection.create()
        for i in range(len(sorted_points) - 1):
            p1 = sorted_points[i]
            p2 = sorted_points[i + 1]
            pt1 = adsk.core.Point3D.create(p1[0], p1[1], 0)
            pt2 = adsk.core.Point3D.create(p2[0], p2[1], 0)
            curves.add(target_lines.addByTwoPoints(pt1, pt2))
        
        if curves.count > 0:
            return adsk.fusion.Path.create(curves, False)
        
        return None
        
    except Exception as e:
        import traceback
        print(f"Error copying sketch: {e}\n{traceback.format_exc()}")
        return None


def use_existing_sketch_as_profile(root, sketch_name, target_plane, cut_x, margin, taper_offset=0):
    """
    Use an existing sketch as the profile and project it onto the target plane with taper offset.
    
    This allows you to:
    1. Create a sketch manually in Fusion 360 with your desired symmetric profile
    2. Name it (e.g., "SymmetricProfile" or "DesiredProfile")
    3. This function will find it, project it onto the target plane, and apply taper offset
    
    Parameters:
    - root: Root component
    - sketch_name: Name of the existing sketch to use
    - target_plane: Plane to project the sketch onto (for left or right profile)
    - cut_x: X position of the cut plane
    - margin: Margin for extending beyond profile
    - taper_offset: Offset to apply for taper (positive or negative)
    
    Returns: Path object for use in loft, or None if sketch not found
    """
    try:
        # Find the sketch by name
        sketches = root.sketches
        source_sketch = None
        
        for i in range(sketches.count):
            sk = sketches.item(i)
            if sk.name == sketch_name:
                source_sketch = sk
                break
        
        if source_sketch is None:
            return None
        
        # Create a new sketch on the target plane
        target_sketch = root.sketches.add(target_plane)
        target_sketch.name = f"Projected_{sketch_name}"
        
        # Get curves from source sketch and project them
        # We need to transform the points from source sketch to target sketch
        source_curves = source_sketch.sketchCurves
        target_lines = target_sketch.sketchCurves.sketchLines
        
        # Collect points from source sketch curves
        points = []
        
        # Extract points from sketch curves
        for i in range(source_curves.count):
            curve = source_curves.item(i)
            if curve.curveType == adsk.core.Curve3DTypes.Line3DCurveType:
                line = adsk.core.Line3D.cast(curve.geometry)
                # Transform start and end points
                start_pt = source_sketch.modelToSketchSpace(line.startPoint)
                end_pt = source_sketch.modelToSketchSpace(line.endPoint)
                
                # Convert to target sketch coordinates and apply taper offset
                # The sketch is in XZ plane, so:
                # - X coordinate becomes X in target (with taper_offset added to tips)
                # - Z coordinate stays the same
                # - Y is 0 (on the plane)
                
                # Determine if this is a tip (extends forward) or flat (back)
                # We'll check if the X coordinate is at the forward position
                x_flat = cut_x - TOLERANCE / 2
                x_tip = cut_x + DOVETAIL_DEPTH + taper_offset
                
                # Use the X coordinate to determine if it's a tip or flat
                # If X is closer to cut_x + DOVETAIL_DEPTH, it's a tip
                start_x_target = start_pt.x + cut_x  # Adjust based on source sketch origin
                end_x_target = end_pt.x + cut_x
                
                # Simple heuristic: if X is significantly forward, it's a tip
                threshold = cut_x + DOVETAIL_DEPTH / 2
                start_is_tip = start_x_target > threshold
                end_is_tip = end_x_target > threshold
                
                start_x = x_tip if start_is_tip else x_flat
                end_x = x_tip if end_is_tip else x_flat
                
                points.append((start_x, start_pt.y, start_is_tip))
                points.append((end_x, end_pt.y, end_is_tip))
        
        # Remove duplicates and sort by Z
        unique_points = {}
        for x, z, is_tip in points:
            if z not in unique_points:
                unique_points[z] = (x, z, is_tip)
        
        sorted_points = sorted(unique_points.values(), key=lambda p: p[1])
        
        # Draw lines connecting the points
        curves = adsk.core.ObjectCollection.create()
        for i in range(len(sorted_points) - 1):
            p1 = sorted_points[i]
            p2 = sorted_points[i + 1]
            pt1 = adsk.core.Point3D.create(p1[0], p1[1], 0)
            pt2 = adsk.core.Point3D.create(p2[0], p2[1], 0)
            curves.add(target_lines.addByTwoPoints(pt1, pt2))
        
        if curves.count > 0:
            return adsk.fusion.Path.create(curves, False)
        
        return None
        
    except Exception as e:
        import traceback
        print(f"Error using existing sketch: {e}\n{traceback.format_exc()}")
        return None


def draw_custom_profile_from_points(sketch, cut_x, margin, taper_offset, z_points, x_is_tip):
    """
    Draw a custom profile from a list of Z positions and whether each point is a tip or flat.
    
    Parameters:
    - sketch: The sketch to draw on
    - cut_x: X position of the cut plane
    - margin: Margin for extending beyond the profile
    - taper_offset: Offset for taper (applied to tips)
    - z_points: List of Z positions (heights) for the profile points
    - x_is_tip: List of booleans - True if point should be at x_tip, False if at x_flat
    
    Example:
    z_points = [0, 0.1, 0.2, 0.5, 0.8, 0.9, 1.0]
    x_is_tip = [True, False, True, False, True, False, True]
    This creates: tip at 0, flat at 0.1, tip at 0.2, flat at 0.5, tip at 0.8, flat at 0.9, tip at 1.0
    """
    lines = sketch.sketchCurves.sketchLines
    
    x_flat = cut_x - TOLERANCE / 2
    x_tip = cut_x + DOVETAIL_DEPTH + taper_offset
    
    z_bottom = -margin
    z_top = TRACK_HEIGHT + margin
    
    points = []
    points.append(adsk.core.Point3D.create(x_flat, z_bottom, 0))  # Start with bottom margin
    
    for i, z in enumerate(z_points):
        if 0 <= z <= TRACK_HEIGHT:  # Only add points within valid range
            x_pos = x_tip if x_is_tip[i] else x_flat
            points.append(adsk.core.Point3D.create(x_pos, z, 0))
    
    points.append(adsk.core.Point3D.create(x_flat, z_top, 0))  # End with top margin
    
    # Draw connected lines
    curves = adsk.core.ObjectCollection.create()
    for i in range(len(points) - 1):
        curves.add(lines.addByTwoPoints(points[i], points[i + 1]))
    
    return adsk.fusion.Path.create(curves, False)


def draw_arrow_profile_simple(sketch, cut_x, margin, taper_offset=0):
    """
    Draw SYMMETRIC arrow profile for proper sliding assembly.

    The profile is SYMMETRIC about Z = h/2 (center height).
    This ensures both pieces have matching interlocking shapes when split.
    
    CRITICAL: The profile MUST be symmetric for proper sliding assembly!
    - Bottom half (Z = 0 to h/2) mirrors top half (Z = h/2 to h)
    - When split, both pieces show matching double arrow patterns
    - One piece gets slots (female), one gets tongues (male)
    - Both pieces can slide together because profiles match
    
    TO USE A CUSTOM PROFILE:
    - Modify the z_points and x_is_tip lists below, or
    - Use draw_custom_profile_from_points() function with your own points

    Profile view (X horizontal, Z vertical):

        Z ^
          |
    H+m   |  ●                    <- Top margin
     H    |  ●                    <- Top end (flat)
          |   ╲
          |    ● TOP ARROW 1      <- Upper arrow (mirrors bottom_start)
          |   ╱
    3H/4  |  ●                    <- Top middle (back in)
          |   ╲
          |    ● TOP ARROW 2      <- Upper arrow (mirrors bottom_arrow1)
          |   ╱
     H/2  |  ●                    <- CENTER (Z = h/2) - symmetry point
          |   ╲
          |    ● BOTTOM ARROW 2   <- Lower arrow
          |   ╱
     H/4  |  ●                    <- Bottom middle (back in)
          |   ╲
          |    ● BOTTOM ARROW 1   <- Lower arrow
          |   ╱
     0    |  ●                    <- Bottom start (arrow tip)
          |  │
    -m    |  ●                    <- Bottom margin
          └─────────────────────> X
            x_flat    x_tip
    
    SYMMETRY: Top half is mirror of bottom half about Z = h/2
    """
    lines = sketch.sketchCurves.sketchLines

    t = WALL_THICKNESS
    h = TRACK_HEIGHT

    # Z positions - IDENTICAL double-arrow pattern on BASE and WALLS
    # Using same arrow spacing for all sections
    arrow_spacing = t / 3  # Distance between arrow features

    z_bottom = -margin
    z_top_margin = h + margin
    
    # SYMMETRIC PROFILE: Mirror the pattern about the center (Z = h/2)
    # This ensures both pieces have matching interlocking shapes when split
    center_z = h / 2
    
    # Define the pattern for the bottom half (Z = 0 to h/2)
    # This pattern will be mirrored for the top half (Z = h/2 to h)
    
    # SYMMETRIC DOUBLE ARROW PATTERN
    # Bottom section: double arrow pattern starting at Z=0
    # Must have TWO arrows near bottom for "second double arrow" on bottom face
    z_bottom_start = 0                # Start at Z=0 with arrow tip
    z_bottom_arrow1 = h / 12          # First arrow (very close to bottom)
    z_bottom_mid1 = h / 6             # First middle (back in)
    z_bottom_arrow2 = h / 4           # Second arrow (for bottom face double arrow)
    z_bottom_mid2 = h / 3             # Second middle (back in)
    z_bottom_arrow3 = h / 2.4         # Third arrow (approaching center)
    z_center = h / 2                  # Center point (Z = h/2)
    
    # Top section: mirror of bottom (symmetric)
    z_top_arrow3 = h - h / 2.4        # Third arrow (mirrors bottom_arrow3)
    z_top_mid2 = h - h / 3            # Second middle (mirrors bottom_mid2)
    z_top_arrow2 = h - h / 4          # Second arrow (mirrors bottom_arrow2)
    z_top_mid1 = h - h / 6            # First middle (mirrors bottom_mid1)
    z_top_arrow1 = h - h / 12         # First arrow (mirrors bottom_arrow1, very close to top)
    z_top_end = h                     # Top end at Z=h with arrow tip

    # X positions - taper shifts the arrow tips
    # For proper interlocking, the profile should extend on both sides of cut_x
    # x_flat: base position (slightly before cut plane for tolerance)
    # x_tip: arrow tip position (extends forward, creating the interlocking shape)
    # The split will create matching slot/tongue on both pieces
    x_flat = cut_x - TOLERANCE / 2
    x_tip = cut_x + DOVETAIL_DEPTH + taper_offset
    
    # Ensure the profile extends far enough to create proper interlocking
    # The tip should extend well beyond the cut plane to create visible tongues
    min_tip_extension = 0.2  # Minimum extension beyond cut plane
    if (x_tip - cut_x) < min_tip_extension:
        x_tip = cut_x + min_tip_extension + taper_offset

    # Points (bottom to top) - SYMMETRIC double arrow pattern
    # Pattern is symmetric about Z = h/2 (center)
    # BOTTOM FACE: Has TWO arrows near Z=0 (double arrow on bottom face)
    # TOP FACE: Has TWO arrows near Z=h (mirror of bottom, symmetric)
    points = [
        adsk.core.Point3D.create(x_flat, z_bottom, 0),        # 0: Bottom margin
        # BOTTOM FACE - double arrow pattern starting at Z=0
        adsk.core.Point3D.create(x_tip, z_bottom_start, 0),   # 1: BOTTOM ARROW 1 (Z=0, first arrow on bottom face)
        adsk.core.Point3D.create(x_flat, z_bottom_mid1, 0),   # 2: Bottom middle 1 (back in)
        adsk.core.Point3D.create(x_tip, z_bottom_arrow1, 0),  # 3: BOTTOM ARROW 2 (very close to Z=0, second arrow on bottom face)
        adsk.core.Point3D.create(x_flat, z_bottom_mid2, 0),   # 4: Bottom middle 2 (back in)
        adsk.core.Point3D.create(x_tip, z_bottom_arrow2, 0),  # 5: BOTTOM ARROW 3 (third arrow)
        adsk.core.Point3D.create(x_flat, z_center, 0),        # 6: Center point (Z = h/2, back in)
        # TOP FACE - mirror of bottom (symmetric)
        adsk.core.Point3D.create(x_tip, z_top_arrow3, 0),     # 7: TOP ARROW 3 (mirrors bottom_arrow2)
        adsk.core.Point3D.create(x_flat, z_top_mid2, 0),      # 8: Top middle 2 (back in)
        adsk.core.Point3D.create(x_tip, z_top_arrow2, 0),     # 9: TOP ARROW 2 (mirrors bottom_arrow1, second arrow on top face)
        adsk.core.Point3D.create(x_flat, z_top_mid1, 0),      # 10: Top middle 1 (back in)
        adsk.core.Point3D.create(x_tip, z_top_arrow1, 0),     # 11: TOP ARROW 1 (mirrors bottom_start, first arrow on top face)
        adsk.core.Point3D.create(x_tip, z_top_end, 0),        # 12: Top end (Z = h, ends with arrow tip for symmetry)
        adsk.core.Point3D.create(x_flat, z_top_margin, 0),    # 13: Top margin
    ]

    # Draw connected lines
    curves = adsk.core.ObjectCollection.create()
    for i in range(len(points) - 1):
        curves.add(lines.addByTwoPoints(points[i], points[i + 1]))

    return adsk.fusion.Path.create(curves, False)


def stop(context):
    pass
