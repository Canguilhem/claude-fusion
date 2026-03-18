import adsk.core, adsk.fusion, traceback

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

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
                ui.messageBox(f'Could not move {body.name}: {str(e)}')

        ui.messageBox(
            f'Done!\n\n'
            f'Created Track_Assembly with {len(piece_bodies)} sub-components.\n\n'
            f'To export as STL:\n'
            f'• Right-click component → Save As Mesh\n\n'
            f'To check junctions:\n'
            f'• Use eye icon to show/hide components'
        )

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

def stop(context):
    pass
