import adsk.core, adsk.fusion, traceback, math

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Parameters
        pin_diameter = 0.3   # cm
        pin_length = 0.4     # cm
        hole_tolerance = 0.02  # cm extra for fit

        ui.messageBox(
            'Add Connectors Tool\n\n'
            'This will add a PIN on one piece and a HOLE on the adjacent piece.\n\n'
            'You will select:\n'
            '1. The face for the PIN (on piece N)\n'
            '2. The face for the HOLE (on piece N+1)\n\n'
            'Repeat for each junction.\n'
            'Click OK to start.'
        )

        while True:
            # Ask to continue or stop
            cont = ui.messageBox(
                'Add connector at a junction?\n\n'
                'YES = Select faces for pin/hole\n'
                'NO = Done, exit',
                'Add Connector',
                adsk.core.MessageBoxButtonTypes.YesNoButtonType
            )

            if cont == adsk.core.DialogResults.DialogNo:
                break

            # Select face for PIN
            sel_pin = ui.selectEntity(
                'Select the FLAT face for the PIN (piece that will have the protrusion)',
                'Faces'
            )
            if not sel_pin:
                continue

            pin_face = adsk.fusion.BRepFace.cast(sel_pin.entity)
            pin_body = pin_face.body

            # Get the component containing this body
            pin_comp = None
            for occ in root.allOccurrences:
                for body in occ.component.bRepBodies:
                    if body == pin_body:
                        pin_comp = occ.component
                        break

            # Select face for HOLE
            sel_hole = ui.selectEntity(
                'Select the FLAT face for the HOLE (adjacent piece)',
                'Faces'
            )
            if not sel_hole:
                continue

            hole_face = adsk.fusion.BRepFace.cast(sel_hole.entity)
            hole_body = hole_face.body

            # Get center point of pin face
            # Use the point on face as approximate center
            center_point = pin_face.pointOnFace

            try:
                # Create sketch on pin face
                if pin_comp:
                    pin_sketch = pin_comp.sketches.add(pin_face)
                else:
                    pin_sketch = root.sketches.add(pin_face)

                pin_sketch.name = 'PinSketch'

                # Project center point and draw circle
                sketch_point = pin_sketch.modelToSketchSpace(center_point)
                circle = pin_sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    adsk.core.Point3D.create(sketch_point.x, sketch_point.y, 0),
                    pin_diameter / 2
                )

                # Get profile and extrude
                if pin_sketch.profiles.count > 0:
                    profile = pin_sketch.profiles.item(0)

                    if pin_comp:
                        extrudes = pin_comp.features.extrudeFeatures
                    else:
                        extrudes = root.features.extrudeFeatures

                    # Extrude pin outward from face
                    pin_input = extrudes.createInput(
                        profile,
                        adsk.fusion.FeatureOperations.JoinFeatureOperation
                    )
                    pin_input.setDistanceExtent(
                        False,
                        adsk.core.ValueInput.createByReal(pin_length)
                    )
                    extrudes.add(pin_input)
                    ui.messageBox('PIN created!')

            except Exception as e:
                ui.messageBox(f'Failed to create pin: {str(e)}')
                continue

            try:
                # Create sketch on hole face
                hole_comp = None
                for occ in root.allOccurrences:
                    for body in occ.component.bRepBodies:
                        if body == hole_body:
                            hole_comp = occ.component
                            break

                if hole_comp:
                    hole_sketch = hole_comp.sketches.add(hole_face)
                else:
                    hole_sketch = root.sketches.add(hole_face)

                hole_sketch.name = 'HoleSketch'

                # Use same center point (projected)
                sketch_point = hole_sketch.modelToSketchSpace(center_point)
                circle = hole_sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    adsk.core.Point3D.create(sketch_point.x, sketch_point.y, 0),
                    (pin_diameter / 2) + hole_tolerance
                )

                # Extrude hole (cut)
                if hole_sketch.profiles.count > 0:
                    profile = hole_sketch.profiles.item(0)

                    if hole_comp:
                        extrudes = hole_comp.features.extrudeFeatures
                    else:
                        extrudes = root.features.extrudeFeatures

                    hole_input = extrudes.createInput(
                        profile,
                        adsk.fusion.FeatureOperations.CutFeatureOperation
                    )
                    hole_input.setDistanceExtent(
                        False,
                        adsk.core.ValueInput.createByReal(pin_length + 0.1)
                    )
                    extrudes.add(hole_input)
                    ui.messageBox('HOLE created!')

            except Exception as e:
                ui.messageBox(f'Failed to create hole: {str(e)}')

        ui.messageBox('Done adding connectors.')

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

def stop(context):
    pass
