"""
Function to create dovetail grooves on the inner faces of U-channel branches.

This creates sliding dovetail grooves on the left and right vertical walls
of the U-channel, allowing a separate sliding piece to engage with them.
"""

import adsk.core, adsk.fusion, traceback

def find_inner_faces_of_u_channel(track_body):
    """
    Find the inner faces of the left and right vertical branches of the U-channel.
    
    Returns: (left_inner_face, right_inner_face) or (None, None) if not found
    """
    # The U-channel has inner faces on the vertical walls
    # We need to identify which faces are the inner faces of the left and right branches
    
    inner_faces = []
    
    for face in track_body.faces:
        geom = face.geometry
        
        # Check if it's a planar face
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            # Get the face normal
            normal = geom.normal
            
            # Inner faces of vertical branches:
            # - Left branch inner face: normal points in +Y direction (toward center)
            # - Right branch inner face: normal points in -Y direction (toward center)
            # - They should be roughly vertical (Z component should be small)
            
            # Check if face is roughly vertical (normal.z is small)
            if abs(normal.z) < 0.1:  # Vertical face
                # Check if normal points toward center (Y direction)
                if abs(normal.y) > 0.7:  # Strong Y component
                    # Get face center to determine if it's left or right
                    bb = face.boundingBox
                    center_y = (bb.minPoint.y + bb.maxPoint.y) / 2
                    
                    # Left branch: center_y should be negative (left side)
                    # Right branch: center_y should be positive (right side)
                    if normal.y > 0 and center_y < 0:
                        # Left inner face
                        inner_faces.append(('left', face))
                    elif normal.y < 0 and center_y > 0:
                        # Right inner face
                        inner_faces.append(('right', face))
    
    # Return the faces
    left_face = None
    right_face = None
    
    for side, face in inner_faces:
        if side == 'left':
            left_face = face
        elif side == 'right':
            right_face = face
    
    return (left_face, right_face)


def create_dovetail_groove_on_face(root, face, groove_positions_z, groove_length, dovetail_width_top, dovetail_width_bottom, dovetail_height, dovetail_depth):
    """
    Create dovetail grooves on a face at specified Z positions.
    
    Parameters:
    - root: Root component
    - face: Face to cut grooves into
    - groove_positions_z: List of Z positions where grooves should be created
    - groove_length: Length of grooves along X-axis
    - dovetail_width_top: Width at top of dovetail (wide opening)
    - dovetail_width_bottom: Width at bottom of dovetail (narrow base)
    - dovetail_height: Height of each dovetail
    - dovetail_depth: Depth of groove into the face
    """
    try:
        # Create sketch on the face
        sketch = root.sketches.add(face)
        sketch.name = f"DovetailGrooves_{face.index}"
        
        lines = sketch.sketchCurves.sketchLines
        
        # Get the face's coordinate system
        # The sketch will be in the face's local coordinate system
        
        # For each groove position, create a dovetail profile
        for z_pos in groove_positions_z:
            # Dovetail trapezoid: wide at top, narrow at bottom
            z_bottom = z_pos - dovetail_height / 2
            z_top = z_pos + dovetail_height / 2
            
            # X positions (in sketch coordinates)
            # The groove extends along X-axis (length of track)
            x_start = 0
            x_end = groove_length
            
            # Width positions (Y in sketch coordinates, but this is the depth direction)
            # Wide at top, narrow at bottom
            y_wide = dovetail_width_top / 2  # Half-width at top
            y_narrow = dovetail_width_bottom / 2  # Half-width at bottom
            
            # Create trapezoid profile
            # Bottom left (narrow)
            p1 = adsk.core.Point3D.create(x_start, z_bottom, -y_narrow)
            # Bottom right (narrow)
            p2 = adsk.core.Point3D.create(x_end, z_bottom, -y_narrow)
            # Top right (wide)
            p3 = adsk.core.Point3D.create(x_end, z_top, -y_wide)
            # Top left (wide)
            p4 = adsk.core.Point3D.create(x_start, z_top, -y_wide)
            
            # Draw the trapezoid
            lines.addByTwoPoints(p1, p2)
            lines.addByTwoPoints(p2, p3)
            lines.addByTwoPoints(p3, p4)
            lines.addByTwoPoints(p4, p1)
        
        # Get profiles from sketch
        if sketch.profiles.count == 0:
            sketch.isLightBulbOn = False
            return False
        
        # Extrude cut each profile
        extrudes = root.features.extrudeFeatures
        
        for i in range(sketch.profiles.count):
            profile = sketch.profiles.item(i)
            
            # Create extrude cut input
            ext_input = extrudes.createInput(
                profile,
                adsk.fusion.FeatureOperations.CutFeatureOperation
            )
            
            # Extrude into the face (cut direction)
            ext_input.setDistanceExtent(
                False,
                adsk.core.ValueInput.createByReal(dovetail_depth)
            )
            
            # Add the extrude feature
            extrudes.add(ext_input)
        
        sketch.isLightBulbOn = False
        return True
        
    except Exception as e:
        import traceback
        print(f"Error creating dovetail groove: {e}\n{traceback.format_exc()}")
        return False
