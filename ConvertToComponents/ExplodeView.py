import adsk.core, adsk.fusion, traceback, math

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Find Track_Assembly component
        track_assembly = None
        for occ in root.occurrences:
            if 'Track_Assembly' in occ.component.name:
                track_assembly = occ.component
                break

        if not track_assembly:
            ui.messageBox('Track_Assembly not found.\nRun ConvertToComponents first.')
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
            'Explode distance (cm) between pieces:',
            'Explode View',
            '2.0'
        )
        if cancelled:
            return

        try:
            explode_distance = float(ret_dist)
        except:
            ui.messageBox('Invalid number.')
            return

        # Calculate centroid of each piece and direction to next
        piece_data = []
        for occ in pieces:
            # Get the body in this component
            bodies = occ.component.bRepBodies
            if bodies.count > 0:
                body = bodies.item(0)
                props = body.physicalProperties
                if props:
                    centroid = props.centerOfMass
                    # Transform to root coordinate system
                    transform = occ.transform
                    centroid.transformBy(transform)
                    piece_data.append({
                        'occ': occ,
                        'centroid': centroid,
                        'num': get_piece_num(occ)
                    })

        if len(piece_data) < 2:
            ui.messageBox('Not enough pieces to create exploded view.')
            return

        # Calculate overall center of the track
        center_x = sum(p['centroid'].x for p in piece_data) / len(piece_data)
        center_z = sum(p['centroid'].z for p in piece_data) / len(piece_data)

        ui.messageBox(
            f'Creating exploded view for {len(piece_data)} pieces.\n'
            f'Distance: {explode_distance} cm\n\n'
            f'Click OK to proceed.'
        )

        # Move each piece outward from center
        for i, data in enumerate(piece_data):
            occ = data['occ']
            centroid = data['centroid']

            # Calculate direction from center to piece
            dir_x = centroid.x - center_x
            dir_z = centroid.z - center_z
            length = math.sqrt(dir_x**2 + dir_z**2)

            if length > 0.01:
                # Normalize direction
                dir_x /= length
                dir_z /= length

                # Calculate offset (pieces further from center move more)
                # Also add progressive offset based on piece order
                radial_offset = explode_distance * (length / 50)  # Scale based on distance from center
                sequential_offset = explode_distance * 0.5 * i  # Progressive offset

                total_offset_x = dir_x * (radial_offset + sequential_offset * 0.3)
                total_offset_z = dir_z * (radial_offset + sequential_offset * 0.3)

                # Also lift in Y for better visibility
                offset_y = explode_distance * 0.2 * i

                # Create transform
                transform = occ.transform
                translation = transform.translation
                translation.x += total_offset_x
                translation.y += offset_y
                translation.z += total_offset_z
                transform.translation = translation

                occ.transform = transform

        ui.messageBox(
            f'Exploded view created!\n\n'
            f'To reset: Ctrl+Z (undo)\n\n'
            f'To inspect junctions:\n'
            f'• Zoom in on gaps between pieces\n'
            f'• Check for pin/hole alignment'
        )

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

def stop(context):
    pass
