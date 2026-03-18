# CLAUDE
import adsk.core, adsk.fusion, traceback, math

# =============================================================================
# DEFAULT PARAMETERS (used if Fusion parameters don't exist)
# =============================================================================
# All values in cm (Fusion internal unit)

DEFAULT_TRACK_HEIGHT = 1.5      # 15 mm
DEFAULT_TRACK_WIDTH = 1.0       # 10 mm
DEFAULT_WALL_THICKNESS = 0.2    # 2 mm
DEFAULT_DOVETAIL_WIDTH = 0.6    # 6 mm
DEFAULT_DOVETAIL_HEIGHT = 0.35  # 3.5 mm
DEFAULT_DOVETAIL_DEPTH = 0.3    # 3 mm
DEFAULT_TOLERANCE = 0.02        # 0.2 mm

# Cutting blade parameters
BLADE_SIZE = 5.0           # Size of cutting blade (larger than track)
BLADE_THICKNESS = 0.01     # Thickness of cutting blade


def get_parameter_value(design, param_name, default_value):
    """
    Get a user parameter value from the design.
    Returns value in cm (Fusion internal unit).
    If parameter doesn't exist, returns the default value.
    """
    try:
        user_params = design.userParameters
        param = user_params.itemByName(param_name)
        if param:
            # Parameter value is in internal units (cm)
            return param.value
        else:
            return default_value
    except:
        return default_value


def load_parameters(design):
    """
    Load all parameters from Fusion 360 design.
    Returns a dictionary with all parameter values in cm.
    """
    params = {
        'TRACK_HEIGHT': get_parameter_value(design, 'TRACK_HEIGHT', DEFAULT_TRACK_HEIGHT),
        'TRACK_WIDTH': get_parameter_value(design, 'TRACK_WIDTH', DEFAULT_TRACK_WIDTH),
        'WALL_THICKNESS': get_parameter_value(design, 'WALL_THICKNESS', DEFAULT_WALL_THICKNESS),
        'DOVETAIL_WIDTH': get_parameter_value(design, 'DOVETAIL_WIDTH', DEFAULT_DOVETAIL_WIDTH),
        'DOVETAIL_HEIGHT': get_parameter_value(design, 'DOVETAIL_HEIGHT', DEFAULT_DOVETAIL_HEIGHT),
        'DOVETAIL_DEPTH': get_parameter_value(design, 'DOVETAIL_DEPTH', DEFAULT_DOVETAIL_DEPTH),
        'TOLERANCE': get_parameter_value(design, 'TOLERANCE', DEFAULT_TOLERANCE),
    }

    # Calculate derived values
    # DOVETAIL_NARROW is 2/3 of DOVETAIL_WIDTH (creates the taper)
    params['DOVETAIL_NARROW'] = params['DOVETAIL_WIDTH'] * 0.67

    # Calculate dovetail Y position (inside the U-channel cavity)
    # Position dovetail on the INNER FLOOR surface
    #
    # Cross-section (Y=0 is path centerline):
    #   Y = +TRACK_HEIGHT/2  → top of U (open cavity)
    #   Y = inner_floor      → inner floor surface
    #   Y = -TRACK_HEIGHT/2  → outer face (visible when mounted)
    #
    inner_floor_y = -params['TRACK_HEIGHT']/2 + params['WALL_THICKNESS']
    params['DOVETAIL_Y_OFFSET'] = inner_floor_y + (params['DOVETAIL_HEIGHT'] / 2)

    return params


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # === LOAD PARAMETERS FROM DESIGN ===
        params = load_parameters(design)

        # === ASK USER WHAT TO DO ===
        result = ui.messageBox(
            'TrackAutoCutter\n\n'
            'Do you have a track body to cut?\n\n'
            'YES = Select body to cut into pieces\n'
            'NO = Show help and current parameters',
            'Track Auto Cutter',
            adsk.core.MessageBoxButtonTypes.YesNoButtonType
        )

        if result == adsk.core.DialogResults.DialogNo:
            ui.messageBox(
                'To create your track:\n\n'
                '1. Create a profile sketch (U-channel)\n'
                '2. Create a path sketch (centerline)\n'
                '3. Use Sweep: profile along path\n'
                '4. Run this script and select YES\n\n'
                '--- Current Parameters (from Fusion) ---\n'
                f'TRACK_HEIGHT: {params["TRACK_HEIGHT"]*10:.1f} mm\n'
                f'TRACK_WIDTH: {params["TRACK_WIDTH"]*10:.1f} mm\n'
                f'WALL_THICKNESS: {params["WALL_THICKNESS"]*10:.1f} mm\n'
                f'DOVETAIL_WIDTH: {params["DOVETAIL_WIDTH"]*10:.1f} mm\n'
                f'DOVETAIL_HEIGHT: {params["DOVETAIL_HEIGHT"]*10:.1f} mm\n'
                f'DOVETAIL_DEPTH: {params["DOVETAIL_DEPTH"]*10:.1f} mm\n'
                f'TOLERANCE: {params["TOLERANCE"]*10:.2f} mm\n'
                f'DOVETAIL_Y_OFFSET: {params["DOVETAIL_Y_OFFSET"]*10:.2f} mm\n\n'
                'Edit parameters in: Modify > Change Parameters'
            )
            return

        # === GET MAX PIECE LENGTH ===
        ret_length, cancelled = ui.inputBox(
            'Max piece length (cm) for your 3D printer:',
            'Track Auto Cutter',
            '23.0'
        )
        if cancelled:
            return

        try:
            max_piece_length = float(ret_length)
        except:
            ui.messageBox('Invalid number.')
            return

        # === SELECT TRACK BODY ===
        sel_body = ui.selectEntity('Select the TRACK body to cut', 'Bodies')
        if not sel_body:
            return
        track_body = adsk.fusion.BRepBody.cast(sel_body.entity)

        # === SELECT PATH ===
        ui.messageBox(
            'Now select the PATH (centerline) used for the sweep.\n'
            'This determines where cuts will be made.'
        )

        sel = ui.selectEntity(
            'Select the PATH sketch or curve',
            'Sketches,SketchCurves'
        )
        if not sel:
            return

        # Get the sketch
        selected_entity = sel.entity
        if hasattr(selected_entity, 'sketchCurves'):
            path_sketch = selected_entity
        elif hasattr(selected_entity, 'parentSketch'):
            path_sketch = selected_entity.parentSketch
        else:
            ui.messageBox('Please select a sketch or sketch curve.')
            return

        # === COLLECT CURVES AND CALCULATE LENGTH ===
        all_curves = []
        total_length = 0.0

        for curve in path_sketch.sketchCurves:
            all_curves.append(curve)
            if hasattr(curve, 'geometry'):
                evaluator = curve.geometry.evaluator
                success, sp, ep = evaluator.getParameterExtents()
                if success:
                    success, length = evaluator.getLengthAtParameter(sp, ep)
                    if success:
                        total_length += length

        if not all_curves:
            ui.messageBox('No curves found in the sketch.')
            return

        # === CREATE PATH ===
        path_collection = adsk.core.ObjectCollection.create()
        for curve in all_curves:
            path_collection.add(curve)

        sweep_path = root.features.createPath(path_collection, True)

        # === CALCULATE PIECES ===
        num_pieces = math.ceil(total_length / max_piece_length)
        if num_pieces < 2:
            ui.messageBox(
                f'Track length: {total_length:.1f} cm\n'
                f'Fits in one piece - no cuts needed!'
            )
            return

        # === ASK ABOUT DOVETAILS ===
        add_dovetails = ui.messageBox(
            f'Track length: {total_length:.1f} cm\n'
            f'Will cut into {num_pieces} pieces (~{total_length/num_pieces:.1f} cm each)\n\n'
            'Add dovetail connectors at each junction?\n\n'
            'YES = Add interlocking dovetails (recommended)\n'
            'NO = Flat cuts only',
            'Add Dovetails?',
            adsk.core.MessageBoxButtonTypes.YesNoButtonType
        ) == adsk.core.DialogResults.DialogYes

        ui.messageBox(
            f'Creating {num_pieces} pieces with {num_pieces-1} cuts...\n\n'
            f'{"Using DOVETAIL cutters for interlocking joints." if add_dovetails else "Using flat cuts only."}'
        )

        # === CUT WITH DOVETAIL CUTTERS ===
        # Each cutter is shaped like a blade with a dovetail protrusion.
        # When used with Split Body, this creates interlocking male/female joints!

        blade_size = BLADE_SIZE
        blade_thickness = BLADE_THICKNESS

        track_body.name = 'Track_Working'

        cuts_made = 0
        dovetails_made = 0
        cut_planes = []

        for i in range(1, num_pieces):
            ratio = i / num_pieces

            try:
                # --- Create construction plane at cut location ---
                plane_input = root.constructionPlanes.createInput()
                distance_value = adsk.core.ValueInput.createByReal(ratio)
                plane_input.setByDistanceOnPath(sweep_path, distance_value)
                cut_plane = root.constructionPlanes.add(plane_input)
                cut_plane.name = f'CutPlane_{i}'
                cut_planes.append(cut_plane)

                # --- Create the cutter body ---
                if add_dovetails:
                    # Create dovetail-shaped cutter
                    cutter_body = create_dovetail_cutter_body(
                        root, cut_plane, params, i, blade_size, blade_thickness
                    )
                else:
                    # Create flat blade cutter
                    cutter_body = create_flat_blade(
                        root, cut_plane, i, blade_size, blade_thickness
                    )

                if cutter_body is None:
                    continue

                # --- Find bodies to split ---
                bodies_to_split = []
                for body in root.bRepBodies:
                    if body.name.startswith('Track_') and body != cutter_body:
                        if bodies_intersect(body, cutter_body):
                            bodies_to_split.append(body)

                # --- Split with the dovetail cutter ---
                split_feats = root.features.splitBodyFeatures

                for body in bodies_to_split:
                    try:
                        split_input = split_feats.createInput(body, cutter_body, True)
                        split_result = split_feats.add(split_input)

                        # Mark new bodies
                        for new_body in split_result.bodies:
                            new_body.name = 'Track_Piece'

                        cuts_made += 1
                        if add_dovetails:
                            dovetails_made += 1

                    except:
                        pass  # Body doesn't intersect cutter

                # --- Delete cutter ---
                try:
                    cutter_body.deleteMe()
                except:
                    pass

            except Exception as e:
                ui.messageBox(f'Cut {i} failed: {str(e)}')

        # === RENAME AND SORT PIECES ===
        piece_bodies = [b for b in root.bRepBodies if b.name.startswith('Track_')]
        piece_bodies = sort_bodies_along_path(piece_bodies, all_curves)

        for idx, body in enumerate(piece_bodies):
            body.name = f'Track_Piece_{idx + 1}'

        # Hide construction planes
        for plane in cut_planes:
            plane.isLightBulbOn = False

        # === CREATE COMPONENTS ===
        create_comps = ui.messageBox(
            f'Done!\n\n'
            f'{len(piece_bodies)} pieces created\n'
            f'{cuts_made} cuts made\n'
            f'{dovetails_made} dovetail junctions added\n\n'
            'Create separate components for each piece?\n'
            '(Makes STL export easier)',
            'Create Components?',
            adsk.core.MessageBoxButtonTypes.YesNoButtonType
        )

        if create_comps == adsk.core.DialogResults.DialogYes:
            create_piece_components(root, piece_bodies)
            ui.messageBox(
                'Components created!\n\n'
                'To export as STL:\n'
                '• Right-click component → Save As Mesh'
            )

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def bodies_intersect(body_a, body_b):
    """Check if two bodies intersect using bounding box overlap."""
    bb_a = body_a.boundingBox
    bb_b = body_b.boundingBox

    # Check for bounding box overlap
    return (
        bb_a.minPoint.x <= bb_b.maxPoint.x and
        bb_a.maxPoint.x >= bb_b.minPoint.x and
        bb_a.minPoint.y <= bb_b.maxPoint.y and
        bb_a.maxPoint.y >= bb_b.minPoint.y and
        bb_a.minPoint.z <= bb_b.maxPoint.z and
        bb_a.maxPoint.z >= bb_b.minPoint.z
    )


def create_flat_blade(root, cut_plane, blade_num, blade_size, blade_thickness):
    """Create a simple flat cutting blade."""
    try:
        blade_sketch = root.sketches.add(cut_plane)
        blade_sketch.name = f'Blade_{blade_num}'

        lines = blade_sketch.sketchCurves.sketchLines
        hs = blade_size / 2

        p1 = adsk.core.Point3D.create(-hs, -hs, 0)
        p2 = adsk.core.Point3D.create(hs, -hs, 0)
        p3 = adsk.core.Point3D.create(hs, hs, 0)
        p4 = adsk.core.Point3D.create(-hs, hs, 0)

        lines.addByTwoPoints(p1, p2)
        lines.addByTwoPoints(p2, p3)
        lines.addByTwoPoints(p3, p4)
        lines.addByTwoPoints(p4, p1)

        if blade_sketch.profiles.count == 0:
            return None

        profile = blade_sketch.profiles.item(0)
        extrudes = root.features.extrudeFeatures

        blade_input = extrudes.createInput(
            profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        blade_input.setSymmetricExtent(
            adsk.core.ValueInput.createByReal(blade_thickness / 2),
            True
        )
        blade_feature = extrudes.add(blade_input)

        if blade_feature.bodies.count == 0:
            return None

        blade_body = blade_feature.bodies.item(0)
        blade_body.name = f'Blade_{blade_num}'

        blade_sketch.isLightBulbOn = False
        return blade_body

    except:
        return None


def create_dovetail_cutter_body(root, cut_plane, params, cutter_num, blade_size, blade_thickness):
    """
    Create a dovetail-shaped cutting tool.

    Method (proven to work):
    1. Create thin blade (NewBody)
    2. Create dovetail protrusion (NewBody, extruded THROUGH blade)
    3. Combine them with JOIN

    When used with Split Body, the resulting pieces have interlocking
    male/female dovetail joints!

    Returns the cutter body, or None if failed.
    """
    try:
        extrudes = root.features.extrudeFeatures

        # === STEP 1: Create the base blade ===
        blade_sketch = root.sketches.add(cut_plane)
        blade_sketch.name = f'Blade_{cutter_num}'

        lines = blade_sketch.sketchCurves.sketchLines
        hs = blade_size / 2

        p1 = adsk.core.Point3D.create(-hs, -hs, 0)
        p2 = adsk.core.Point3D.create(hs, -hs, 0)
        p3 = adsk.core.Point3D.create(hs, hs, 0)
        p4 = adsk.core.Point3D.create(-hs, hs, 0)

        lines.addByTwoPoints(p1, p2)
        lines.addByTwoPoints(p2, p3)
        lines.addByTwoPoints(p3, p4)
        lines.addByTwoPoints(p4, p1)

        if blade_sketch.profiles.count == 0:
            return None

        profile = blade_sketch.profiles.item(0)

        # Extrude thin blade
        blade_input = extrudes.createInput(
            profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        blade_input.setSymmetricExtent(
            adsk.core.ValueInput.createByReal(blade_thickness / 2),
            True
        )
        blade_feature = extrudes.add(blade_input)

        if blade_feature.bodies.count == 0:
            return None

        blade_body = blade_feature.bodies.item(0)
        blade_body.name = f'Blade_{cutter_num}'

        blade_sketch.isLightBulbOn = False

        # === STEP 2: Create dovetail protrusion as separate body ===
        dovetail_sketch = root.sketches.add(cut_plane)
        dovetail_sketch.name = f'Dovetail_{cutter_num}'

        # Draw dovetail trapezoid at center (0,0)
        # For track, we position based on DOVETAIL_Y_OFFSET
        hw = params['DOVETAIL_WIDTH'] / 2
        hn = params['DOVETAIL_NARROW'] / 2
        h = params['DOVETAIL_HEIGHT']
        y_offset = params['DOVETAIL_Y_OFFSET']

        lines2 = dovetail_sketch.sketchCurves.sketchLines

        # Trapezoid centered at (0, y_offset)
        cx = 0
        cy = y_offset

        d1 = adsk.core.Point3D.create(cx - hw, cy - h/2, 0)
        d2 = adsk.core.Point3D.create(cx + hw, cy - h/2, 0)
        d3 = adsk.core.Point3D.create(cx + hn, cy + h/2, 0)
        d4 = adsk.core.Point3D.create(cx - hn, cy + h/2, 0)

        lines2.addByTwoPoints(d1, d2)
        lines2.addByTwoPoints(d2, d3)
        lines2.addByTwoPoints(d3, d4)
        lines2.addByTwoPoints(d4, d1)

        if dovetail_sketch.profiles.count == 0:
            dovetail_sketch.isLightBulbOn = False
            return blade_body  # Return blade only

        dovetail_profile = dovetail_sketch.profiles.item(0)
        depth = params['DOVETAIL_DEPTH']

        # KEY: Extrude dovetail THROUGH the blade (both directions)
        # This ensures intersection for successful Combine
        dovetail_input = extrudes.createInput(
            dovetail_profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        overlap = blade_thickness  # Pass through blade

        dovetail_input.setTwoSidesExtent(
            adsk.fusion.DistanceExtentDefinition.create(
                adsk.core.ValueInput.createByReal(depth)
            ),
            adsk.fusion.DistanceExtentDefinition.create(
                adsk.core.ValueInput.createByReal(overlap)
            )
        )

        dovetail_feat = extrudes.add(dovetail_input)

        if dovetail_feat.bodies.count == 0:
            dovetail_sketch.isLightBulbOn = False
            return blade_body

        dovetail_body = dovetail_feat.bodies.item(0)
        dovetail_body.name = f'DovetailProtrusion_{cutter_num}'

        dovetail_sketch.isLightBulbOn = False

        # === STEP 3: Combine blade + dovetail ===
        combines = root.features.combineFeatures

        tool_coll = adsk.core.ObjectCollection.create()
        tool_coll.add(dovetail_body)

        combine_input = combines.createInput(blade_body, tool_coll)
        combine_input.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
        combine_input.isKeepToolBodies = False

        combines.add(combine_input)

        blade_body.name = f'DovetailCutter_{cutter_num}'
        return blade_body

    except:
        return None


def sort_bodies_along_path(bodies, curves):
    """Sort bodies by their position along the path."""
    # Sample points along path
    path_points = []
    for curve in curves:
        ev = curve.geometry.evaluator
        success, sp, ep = ev.getParameterExtents()
        if success:
            for i in range(20):
                t = i / 19.0
                param = sp + t * (ep - sp)
                success, pt = ev.getPointAtParameter(param)
                if success:
                    path_points.append(pt)

    def get_order(body):
        props = body.physicalProperties
        if not props:
            return float('inf')
        c = props.centerOfMass

        min_idx = 0
        min_dist = float('inf')
        for idx, pt in enumerate(path_points):
            dist = math.sqrt(
                (pt.x - c.x)**2 + (pt.y - c.y)**2 + (pt.z - c.z)**2
            )
            if dist < min_dist:
                min_dist = dist
                min_idx = idx
        return min_idx

    return sorted(bodies, key=get_order)


def create_piece_components(root, piece_bodies):
    """Create a component for each piece body."""
    # Create parent assembly
    assembly_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    assembly_comp = assembly_occ.component
    assembly_comp.name = 'Track_Assembly'

    for idx, body in enumerate(piece_bodies):
        # Create sub-component
        piece_occ = assembly_comp.occurrences.addNewComponent(
            adsk.core.Matrix3D.create()
        )
        piece_comp = piece_occ.component
        piece_comp.name = f'Piece_{idx + 1}'

        # Move body to component
        try:
            body.moveToComponent(piece_occ)
        except:
            try:
                body.copyToComponent(piece_occ)
            except:
                pass


def stop(context):
    pass
