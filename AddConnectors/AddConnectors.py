import adsk.core, adsk.fusion, traceback, math

# Dovetail parameters (cm)
DOVETAIL_WIDTH = 0.8      # width at the wide end
DOVETAIL_NARROW = 0.5     # width at the narrow end
DOVETAIL_HEIGHT = 0.4     # height of trapezoid
DOVETAIL_DEPTH = 0.3      # how deep into piece
TOLERANCE = 0.02          # extra space for fit


def get_face_center(face):
    """Get the true center of a face using bounding box."""
    bb = face.boundingBox
    return adsk.core.Point3D.create(
        (bb.minPoint.x + bb.maxPoint.x) / 2,
        (bb.minPoint.y + bb.maxPoint.y) / 2,
        (bb.minPoint.z + bb.maxPoint.z) / 2
    )


def get_cut_faces(body):
    """
    Find the flat cut faces at the ends of a track piece.
    These are typically the smallest planar faces.
    Returns list of (face, area) sorted by area.
    """
    planar_faces = []

    for face in body.faces:
        geom = face.geometry
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            area = face.area
            planar_faces.append((face, area))

    # Sort by area (smallest first - cut faces are usually smaller)
    planar_faces.sort(key=lambda x: x[1])
    return planar_faces


def find_matching_faces(body_a, body_b):
    """
    Find the junction faces between two adjacent track pieces.
    Returns (face_a, face_b) - the faces that should connect.
    """
    faces_a = get_cut_faces(body_a)
    faces_b = get_cut_faces(body_b)

    best_pair = None
    min_distance = float('inf')

    # Check pairs of planar faces
    for face_a, area_a in faces_a[:4]:  # Check up to 4 smallest faces
        center_a = get_face_center(face_a)
        normal_a = face_a.geometry.normal

        for face_b, area_b in faces_b[:4]:
            center_b = get_face_center(face_b)
            normal_b = face_b.geometry.normal

            # Check if normals are opposite (faces would mate)
            dot = (normal_a.x * normal_b.x +
                   normal_a.y * normal_b.y +
                   normal_a.z * normal_b.z)

            if dot < -0.9:  # Roughly opposite
                # Distance between centers
                dist = math.sqrt(
                    (center_a.x - center_b.x)**2 +
                    (center_a.y - center_b.y)**2 +
                    (center_a.z - center_b.z)**2
                )

                if dist < min_distance:
                    min_distance = dist
                    best_pair = (face_a, face_b)

    return best_pair


def create_dovetail_on_face(face, comp, is_male, junction_num):
    """
    Create a dovetail (male) or slot (female) on a face.
    The dovetail is centered on the face.
    """
    # Get face center in sketch coordinates
    sketch = comp.sketches.add(face)
    sketch.name = f'{"Dovetail" if is_male else "Slot"}_{junction_num}'

    # Get center point
    center_model = get_face_center(face)
    center_sketch = sketch.modelToSketchSpace(center_model)
    cx, cy = center_sketch.x, center_sketch.y

    # Dimensions with tolerance for female
    if is_male:
        hw = DOVETAIL_WIDTH / 2
        hn = DOVETAIL_NARROW / 2
        h = DOVETAIL_HEIGHT
        depth = DOVETAIL_DEPTH
    else:
        hw = (DOVETAIL_WIDTH / 2) + TOLERANCE
        hn = (DOVETAIL_NARROW / 2) + TOLERANCE
        h = DOVETAIL_HEIGHT + TOLERANCE
        depth = DOVETAIL_DEPTH + 0.1  # Cut slightly deeper

    # Draw trapezoid centered on face center
    lines = sketch.sketchCurves.sketchLines

    # Trapezoid: wide at bottom, narrow at top
    p1 = adsk.core.Point3D.create(cx - hw, cy - h/2, 0)  # bottom left
    p2 = adsk.core.Point3D.create(cx + hw, cy - h/2, 0)  # bottom right
    p3 = adsk.core.Point3D.create(cx + hn, cy + h/2, 0)  # top right
    p4 = adsk.core.Point3D.create(cx - hn, cy + h/2, 0)  # top left

    lines.addByTwoPoints(p1, p2)
    lines.addByTwoPoints(p2, p3)
    lines.addByTwoPoints(p3, p4)
    lines.addByTwoPoints(p4, p1)

    if sketch.profiles.count == 0:
        return False

    profile = sketch.profiles.item(0)
    extrudes = comp.features.extrudeFeatures

    operation = (adsk.fusion.FeatureOperations.JoinFeatureOperation
                 if is_male else
                 adsk.fusion.FeatureOperations.CutFeatureOperation)

    ext_input = extrudes.createInput(profile, operation)
    ext_input.setDistanceExtent(
        False,
        adsk.core.ValueInput.createByReal(depth)
    )

    extrudes.add(ext_input)
    return True


def get_component_for_body(root, body):
    """Find the component/occurrence that contains a body."""
    # Check root component
    for b in root.bRepBodies:
        if b == body:
            return root, None

    # Check all occurrences
    for occ in root.allOccurrences:
        comp = occ.component
        for b in comp.bRepBodies:
            if b == body:
                return comp, occ

    return None, None


def get_sorted_track_pieces(root):
    """
    Find Track_Assembly and return pieces sorted by name.
    Returns list of (component, occurrence, body) tuples.
    """
    pieces = []

    for occ in root.allOccurrences:
        comp = occ.component
        name = comp.name.lower()

        # Look for piece components
        if 'piece' in name or 'track_piece' in name:
            if comp.bRepBodies.count > 0:
                body = comp.bRepBodies.item(0)
                # Extract piece number
                import re
                match = re.search(r'(\d+)', comp.name)
                num = int(match.group(1)) if match else 0
                pieces.append((num, comp, occ, body))

    # Sort by piece number
    pieces.sort(key=lambda x: x[0])
    return [(p[1], p[2], p[3]) for p in pieces]


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Ask user for mode
        mode = ui.messageBox(
            'Dovetail Connector Tool\n\n'
            'Choose mode:\n\n'
            'YES = AUTO mode (process all Track pieces)\n'
            'NO = MANUAL mode (select faces yourself)',
            'Add Dovetails',
            adsk.core.MessageBoxButtonTypes.YesNoButtonType
        )

        if mode == adsk.core.DialogResults.DialogYes:
            # === AUTO MODE ===
            run_auto_mode(ui, root)
        else:
            # === MANUAL MODE ===
            run_manual_mode(ui, root)

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def run_auto_mode(ui, root):
    """Automatically add dovetails to all track piece junctions."""

    # Find all track pieces
    pieces = get_sorted_track_pieces(root)

    if len(pieces) < 2:
        ui.messageBox(
            'Could not find track pieces.\n\n'
            'Make sure you have components named "Piece_1", "Piece_2", etc.\n'
            'or use MANUAL mode to select faces.'
        )
        return

    ui.messageBox(
        f'Found {len(pieces)} track pieces.\n\n'
        f'Will create {len(pieces)-1} dovetail junctions.\n\n'
        f'Dovetail size: {DOVETAIL_WIDTH}cm x {DOVETAIL_HEIGHT}cm\n\n'
        f'Click OK to proceed.'
    )

    junctions_created = 0

    # Process each pair of adjacent pieces
    for i in range(len(pieces) - 1):
        comp_a, occ_a, body_a = pieces[i]
        comp_b, occ_b, body_b = pieces[i + 1]

        try:
            # Find matching junction faces
            result = find_matching_faces(body_a, body_b)

            if result:
                face_a, face_b = result

                # Create dovetail (protrusion) on piece A
                success1 = create_dovetail_on_face(
                    face_a, comp_a, True, i + 1
                )

                # Create slot (cavity) on piece B
                success2 = create_dovetail_on_face(
                    face_b, comp_b, False, i + 1
                )

                if success1 and success2:
                    junctions_created += 1

        except Exception as e:
            ui.messageBox(f'Junction {i+1} failed: {str(e)}')

    ui.messageBox(
        f'Done!\n\n'
        f'{junctions_created} of {len(pieces)-1} junctions created.\n\n'
        f'The pieces will now interlock when assembled.'
    )


def run_manual_mode(ui, root):
    """Manually select faces for dovetail creation."""

    ui.messageBox(
        'MANUAL MODE\n\n'
        'For each junction, you will select:\n'
        '1. Face for DOVETAIL (protrusion)\n'
        '2. Face for SLOT (cavity)\n\n'
        f'Dovetail size: {DOVETAIL_WIDTH}cm x {DOVETAIL_HEIGHT}cm'
    )

    junction_count = 0

    while True:
        cont = ui.messageBox(
            f'Junctions created: {junction_count}\n\n'
            'Add another dovetail junction?\n\n'
            'YES = Select faces\n'
            'NO = Done',
            'Add Dovetail',
            adsk.core.MessageBoxButtonTypes.YesNoButtonType
        )

        if cont == adsk.core.DialogResults.DialogNo:
            break

        # Select face for dovetail
        sel_tail = ui.selectEntity(
            'Select face for DOVETAIL (protrusion)',
            'Faces'
        )
        if not sel_tail:
            continue

        tail_face = adsk.fusion.BRepFace.cast(sel_tail.entity)
        tail_body = tail_face.body
        tail_comp, tail_occ = get_component_for_body(root, tail_body)

        if not tail_comp:
            tail_comp = root

        # Select face for slot
        sel_slot = ui.selectEntity(
            'Select face for SLOT (cavity)',
            'Faces'
        )
        if not sel_slot:
            continue

        slot_face = adsk.fusion.BRepFace.cast(sel_slot.entity)
        slot_body = slot_face.body
        slot_comp, slot_occ = get_component_for_body(root, slot_body)

        if not slot_comp:
            slot_comp = root

        try:
            # Create dovetail
            success1 = create_dovetail_on_face(
                tail_face, tail_comp, True, junction_count + 1
            )

            # Create slot
            success2 = create_dovetail_on_face(
                slot_face, slot_comp, False, junction_count + 1
            )

            if success1 and success2:
                junction_count += 1
                ui.messageBox(f'Junction {junction_count} created!')
            else:
                ui.messageBox('Failed to create dovetail profiles.')

        except Exception as e:
            ui.messageBox(f'Failed: {str(e)}')

    ui.messageBox(
        f'Done!\n\n'
        f'{junction_count} dovetail junctions created.'
    )


def stop(context):
    pass
