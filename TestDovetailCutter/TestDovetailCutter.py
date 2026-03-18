import adsk.core
import adsk.fusion
import traceback
import math

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        sketches = root.sketches
        extrudes = root.features.extrudeFeatures
        planes = root.constructionPlanes
        splits = root.features.splitBodyFeatures
        fillets = root.features.filletFeatures

        # =========================
        # PARAMETERS (cm)
        # =========================
        trackWidth = 1.5        # 15mm outer width (Y)
        wallHeight = 1.5        # 15mm wall height (Z)
        wallThick = 0.3         # 3mm wall thickness
        floorThick = 0.3        # 3mm floor
        totalLength = 10.0      # 100mm total (X)

        # Diagonal cut angle
        scarfAngle = 15.0       # degrees

        # Octagonal pin parameters
        pinInradius = 0.14      # 1.4mm flat-to-flat half-distance (bigger thanks to boss)
        pinLength = 0.5         # 5mm pin extends from cut face
        pinTolerance = 0.025    # 0.25mm clearance for socket
        holeLengthExtra = 0.1   # 1mm extra depth

        midX = totalLength / 2
        socketInradius = pinInradius + pinTolerance
        socketDepth = pinLength + holeLengthExtra

        # Shell and positioning
        minShell = 0.06         # 0.6mm minimum wall

        # Boss: reinforcement pad on floor at junction
        bossHeight = 0.2        # 2mm above floor inner surface
        bossFilletR = bossHeight # full radius ramp for smooth transition
        bossWidth = trackWidth - 2 * wallThick  # full inner channel width (wall to wall)
        bossLength = 1.5        # 15mm along X, centered at midX (extra room for end fillets)

        # Pin center: fits within floor + boss thickness
        pinY = trackWidth / 2
        pinZ = socketInradius + minShell

        # =========================
        # STEP 1: U-channel
        # =========================
        uSketch = sketches.add(root.yZConstructionPlane)
        uSketch.name = "U_Profile"
        ln = uSketch.sketchCurves.sketchLines
        pts = [(0, 0), (trackWidth, 0), (trackWidth, wallHeight),
               (trackWidth - wallThick, wallHeight), (trackWidth - wallThick, floorThick),
               (wallThick, floorThick), (wallThick, wallHeight), (0, wallHeight)]
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            ln.addByTwoPoints(adsk.core.Point3D.create(pts[i][0], pts[i][1], 0),
                              adsk.core.Point3D.create(pts[j][0], pts[j][1], 0))

        extU = extrudes.createInput(uSketch.profiles.item(0),
                                     adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        extU.setDistanceExtent(False, adsk.core.ValueInput.createByReal(totalLength))
        uBody = extrudes.add(extU).bodies.item(0)
        uBody.name = "Track_Working"

        # =========================
        # STEP 1.5: Reinforcement boss at junction
        # =========================
        bossPlaneInput = planes.createInput()
        bossPlaneInput.setByOffset(root.yZConstructionPlane,
                                    adsk.core.ValueInput.createByReal(midX - bossLength / 2))
        bossPlane = planes.add(bossPlaneInput)

        bossSketch = sketches.add(bossPlane)
        bossSketch.name = "Boss_Profile"
        bsl = bossSketch.sketchCurves.sketchLines
        by1 = pinY - bossWidth / 2
        by2 = pinY + bossWidth / 2
        bz1 = floorThick
        bz2 = floorThick + bossHeight
        bsl.addByTwoPoints(adsk.core.Point3D.create(by1, bz1, 0),
                           adsk.core.Point3D.create(by2, bz1, 0))
        bsl.addByTwoPoints(adsk.core.Point3D.create(by2, bz1, 0),
                           adsk.core.Point3D.create(by2, bz2, 0))
        bsl.addByTwoPoints(adsk.core.Point3D.create(by2, bz2, 0),
                           adsk.core.Point3D.create(by1, bz2, 0))
        bsl.addByTwoPoints(adsk.core.Point3D.create(by1, bz2, 0),
                           adsk.core.Point3D.create(by1, bz1, 0))

        bossExt = extrudes.createInput(bossSketch.profiles.item(0),
                                        adsk.fusion.FeatureOperations.JoinFeatureOperation)
        bossExt.setDistanceExtent(False, adsk.core.ValueInput.createByReal(bossLength))
        bossExt.participantBodies = [uBody]
        bossFeat = extrudes.add(bossExt)

        # Fillet boss edges for smooth transition
        try:
            bossEdges = adsk.core.ObjectCollection.create()
            for face in bossFeat.faces:
                for edge in face.edges:
                    bossEdges.add(edge)
            if bossEdges.count > 0:
                fi = fillets.createInput()
                fi.addConstantRadiusEdgeSet(bossEdges,
                    adsk.core.ValueInput.createByReal(bossFilletR), True)
                fillets.add(fi)
        except:
            pass  # skip if fillet fails on some edges

        # =========================
        # STEP 2: Diagonal split (scarf joint)
        # =========================
        axisSketch = sketches.add(root.xZConstructionPlane)
        axisSketch.name = "ScarfAxis"
        axisLine = axisSketch.sketchCurves.sketchLines.addByTwoPoints(
            adsk.core.Point3D.create(midX, -3, 0),
            adsk.core.Point3D.create(midX, 3, 0)
        )

        perpInput = planes.createInput()
        perpInput.setByOffset(root.yZConstructionPlane,
                               adsk.core.ValueInput.createByReal(midX))
        perpPlane = planes.add(perpInput)

        angledInput = planes.createInput()
        angledInput.setByAngle(axisLine,
            adsk.core.ValueInput.createByString(f"{scarfAngle} deg"), perpPlane)
        splitPlane = planes.add(angledInput)
        splitPlane.name = "DiagonalCut"

        splits.add(splits.createInput(uBody, splitPlane, True))

        # Identify pieces by center X
        male = None
        female = None
        for b in root.bRepBodies:
            if "Track" in b.name:
                cx = (b.boundingBox.minPoint.x + b.boundingBox.maxPoint.x) / 2
                if cx < midX:
                    male = b
                    male.name = "Track_Male"
                else:
                    female = b
                    female.name = "Track_Female"

        if not male or not female:
            ui.messageBox("Failed to identify pieces.")
            return

        # =========================
        # STEP 3: Octagonal pin on floor center
        # =========================
        def addOctagon(cy, cz, inradius, length, body, operation, name):
            """Create an octagonal prism at (midX, cy, cz).
            Oriented with flat top/bottom (horizontal edges) for FDM."""
            skPlaneInput = planes.createInput()
            skPlaneInput.setByOffset(root.yZConstructionPlane,
                                      adsk.core.ValueInput.createByReal(midX))
            skPlane = planes.add(skPlaneInput)

            sk = sketches.add(skPlane)
            sk.name = name
            sl = sk.sketchCurves.sketchLines

            circumR = inradius / math.cos(math.pi / 8)

            verts = []
            for i in range(8):
                angle = math.pi / 8 + i * math.pi / 4
                y = cy + circumR * math.cos(angle)
                z = cz + circumR * math.sin(angle)
                verts.append(adsk.core.Point3D.create(y, z, 0))

            for i in range(8):
                sl.addByTwoPoints(verts[i], verts[(i + 1) % 8])

            prof = sk.profiles.item(0)

            ext = extrudes.createInput(prof, operation)
            ext.setDistanceExtent(False,
                                   adsk.core.ValueInput.createByReal(length))
            ext.participantBodies = [body]
            extrudes.add(ext)

            sk.isLightBulbOn = False
            skPlane.isLightBulbOn = False

        # Pin on male (JOIN)
        addOctagon(pinY, pinZ, pinInradius, pinLength, male,
                   adsk.fusion.FeatureOperations.JoinFeatureOperation, "Pin_Center")

        # Socket on female (CUT)
        addOctagon(pinY, pinZ, socketInradius, socketDepth, female,
                   adsk.fusion.FeatureOperations.CutFeatureOperation, "Socket_Center")

        # Cleanup
        for sk in sketches:
            sk.isLightBulbOn = False
        for p in planes:
            p.isLightBulbOn = False

        pinDiameter = pinInradius * 2 * 10
        socketDiameter = socketInradius * 2 * 10
        totalThick = (floorThick + bossHeight) * 10
        ui.messageBox(
            "Diagonal Scarf + Octagonal Joint (with boss)\n\n"
            f"Track: {trackWidth*10:.0f}mm wide, "
            f"{wallThick*10:.0f}mm walls, "
            f"{wallHeight*10:.0f}mm tall\n"
            f"Scarf angle: {scarfAngle}\u00b0\n"
            f"Boss: {bossWidth*10:.1f}\u00d7{bossHeight*10:.1f}mm, "
            f"{bossLength*10:.0f}mm long "
            f"(total {totalThick:.1f}mm at junction)\n"
            f"Pin: {pinDiameter:.1f}mm octagon, "
            f"{pinLength*10:.0f}mm long\n"
            f"Socket: {socketDiameter:.1f}mm octagon, "
            f"{socketDepth*10:.0f}mm deep\n"
            f"Tolerance: {pinTolerance*10:.2f}mm"
        )

    except:
        if ui:
            ui.messageBox("Error:\n{}".format(traceback.format_exc()))
