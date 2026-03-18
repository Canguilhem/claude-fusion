import adsk.core, adsk.fusion, traceback, math

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Ask what to do
        result = ui.messageBox(
            'Track Piece Tools\n\n'
            'What do you want to do?\n\n'
            'YES = Convert bodies to components\n'
            'NO = Create exploded view (components must exist)',
            'Track Tools',
            adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType
        )

        if result == adsk.core.DialogResults.DialogCancel:
            return
        elif result == adsk.core.DialogResults.DialogYes:
            convert_to_components(ui, design, root)
        else:
            create_exploded_view(ui, design, root)

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def convert_to_components(ui, design, root):
    """Convert Track_Piece bodies to separate components."""

    # Find all Track_Piece bodies
    piece_bodies = []
    for body in root.bRepBodies:
        if body.name.startswith('Track_Piece'):
            piece_bodies.append(body)

    if not piece_bodies:
        ui.messageBox('No Track_Piece bodies found.\nRun TrackAutoCutter first.')
        return

    # Sort by piece number
    def get_piece_num(body):
        try:
            return int(body.name.split('_')[-1])
        except:
            return 0

    piece_bodies.sort(key=get_piece_num)

    ui.messageBox(f'Found {len(piece_bodies)} track pieces.\nCreating components...')

    # Create parent component
    track_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    track_comp = track_occ.component
    track_comp.name = 'Track_Assembly'

    # Move each piece to its own sub-component
    for idx, body in enumerate(piece_bodies):
        piece_num = get_piece_num(body)

        # Create sub-component
        piece_occ = track_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        piece_comp = piece_occ.component
        piece_comp.name = f'Piece_{piece_num}'

        # Move body to component
        try:
            body.moveToComponent(piece_occ)
        except Exception as e:
            pass  # Skip if move fails

    ui.messageBox(
        f'Done!\n\n'
        f'Created Track_Assembly with {len(piece_bodies)} sub-components.\n\n'
        f'Run this script again and select NO for exploded view.'
    )


def create_exploded_view(ui, design, root):
    """Create an exploded view of Track_Assembly components."""

    # Find Track_Assembly component
    track_assembly = None
    track_occ = None
    for occ in root.occurrences:
        if 'Track_Assembly' in occ.component.name:
            track_assembly = occ.component
            track_occ = occ
            break

    if not track_assembly:
        ui.messageBox('Track_Assembly not found.\nRun "Convert to components" first (YES option).')
        return

    # Get all piece occurrences
    pieces = []
    for occ in track_assembly.occurrences:
        if 'Piece_' in occ.component.name:
            pieces.append(occ)

    if not pieces:
        ui.messageBox('No pieces found in Track_Assembly.')
        return

    # Sort by piece number
    def get_piece_num(occ):
        try:
            name = occ.component.name
            return int(name.split('_')[-1])
        except:
            return 0

    pieces.sort(key=get_piece_num)

    # Ask for explode distance
    ret_dist, cancelled = ui.inputBox(
        'Explode distance (cm) between pieces:\n(Enter 0 to reset to original position)',
        'Explode View',
        '3.0'
    )
    if cancelled:
        return

    try:
        explode_distance = float(ret_dist)
    except:
        ui.messageBox('Invalid number.')
        return

    # If distance is 0, reset positions
    if explode_distance == 0:
        for occ in pieces:
            occ.transform = adsk.core.Matrix3D.create()
        ui.messageBox('Positions reset.')
        return

    # Calculate centroid of each piece
    piece_data = []
    for occ in pieces:
        bodies = occ.component.bRepBodies
        if bodies.count > 0:
            body = bodies.item(0)
            props = body.physicalProperties
            if props:
                centroid = props.centerOfMass
                piece_data.append({
                    'occ': occ,
                    'centroid': centroid,
                    'num': get_piece_num(occ)
                })

    if len(piece_data) < 2:
        ui.messageBox('Not enough pieces.')
        return

    # Calculate center of track
    center_x = sum(p['centroid'].x for p in piece_data) / len(piece_data)
    center_z = sum(p['centroid'].z for p in piece_data) / len(piece_data)

    # Move each piece outward
    for i, data in enumerate(piece_data):
        occ = data['occ']
        centroid = data['centroid']

        # Direction from center
        dir_x = centroid.x - center_x
        dir_z = centroid.z - center_z
        length = math.sqrt(dir_x**2 + dir_z**2)

        if length > 0.01:
            dir_x /= length
            dir_z /= length

            # Offset calculation
            offset_multiplier = 1.0 + (i * 0.15)  # Progressive increase
            offset_x = dir_x * explode_distance * offset_multiplier
            offset_z = dir_z * explode_distance * offset_multiplier
            offset_y = explode_distance * 0.1 * i  # Slight lift

            # Apply transform
            transform = adsk.core.Matrix3D.create()
            transform.translation = adsk.core.Vector3D.create(offset_x, offset_y, offset_z)
            occ.transform = transform

    ui.messageBox(
        f'Exploded view created!\n\n'
        f'{len(piece_data)} pieces spread out.\n\n'
        f'To reset: run script again, enter 0 for distance\n'
        f'To undo: Ctrl+Z'
    )


def stop(context):
    pass
