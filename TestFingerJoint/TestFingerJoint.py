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
        combines = root.features.combineFeatures

        # =========================
        # PARAMETERS (cm)
        # =========================
        trackWidth = 1.5        # 15mm outer width (Y)
        wallHeight = 1.5        # 15mm wall height (Z)
        wallThick = 0.3         # 3mm wall thickness
        floorThick = 0.3        # 3mm floor
        totalLength = 10.0      # 100mm total (X)

        # Finger joint parameters
        numFingers = 3           # fingers per wall
        fingerDepth = 0.5        # 5mm depth along X (how far fingers extend)
        tolerance = 0.02         # 0.2mm per side (FDM sliding fit)

        midX = totalLength / 2

        # Derived
        innerHeight = wallHeight - floorThick
        fingerHeight = innerHeight / numFingers

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
        # STEP 2: Create finger cutter body
        # A single body spanning full U cross-section with finger steps
        # Profile on XZ plane at Y=0, extruded through full width
        # =========================
        # The cutter profile is a stepped/zigzag outline viewed from the side.
        # It spans from midX-fingerDepth to midX+fingerDepth in X,
        # and from 0 to wallHeight in Z.
        #
        # For each wall, fingers alternate sides:
        #   odd fingers extend LEFT (toward male piece)
        #   even fingers extend RIGHT (toward female piece)
        # The floor gets a straight cut at midX.
        #
        # Profile (stepped shape spanning the full height):
        #   Bottom at Z=0, top at Z=wallHeight
        #   Steps at each finger boundary

        cutSketch = sketches.add(root.xZConstructionPlane)
        cutSketch.name = "FingerProfile"
        sl = cutSketch.sketchCurves.sketchLines

        # Build the stepped profile as a closed polyline
        # X axis = along track, Z axis = height
        # Left edge = midX - fingerDepth, right edge = midX + fingerDepth
        xL = midX - fingerDepth
        xR = midX + fingerDepth

        # Floor region: straight cut at midX, thin slab
        # We'll make the cutter a solid block from xL to xR,
        # then add/remove steps for the fingers.
        #
        # Simpler approach: draw the full stepped outline
        # Starting from bottom-left, going clockwise
        #
        # The step pattern on the wall portion (floorThick to wallHeight):
        # For finger i (0-indexed from bottom):
        #   if i is even: finger extends to xR (right/female side)
        #   if i is odd:  finger extends to xL (left/male side)
        # Floor (0 to floorThick): straight cut, extends to xR

        profile_pts = []

        # Start at bottom-left of floor
        profile_pts.append((xL, 0))
        # Bottom-right of floor
        profile_pts.append((xR, 0))
        # Up to floor top
        profile_pts.append((xR, floorThick))

        # Now step through each finger
        for i in range(numFingers):
            zBot = floorThick + i * fingerHeight
            zTop = floorThick + (i + 1) * fingerHeight

            if i % 2 == 0:
                # Finger extends RIGHT (xR side) - already there from floor or prev step
                # Stay at xR, go up
                profile_pts.append((xR, zTop))
                # Step left if not last
                if i < numFingers - 1:
                    profile_pts.append((xL, zTop))
            else:
                # Finger extends LEFT (xL side)
                # We need to be at xL, go up
                profile_pts.append((xL, zTop))
                # Step right if not last
                if i < numFingers - 1:
                    profile_pts.append((xR, zTop))

        # Close at top - go to top-left
        # Last finger ends at wallHeight
        lastX = xR if (numFingers - 1) % 2 == 0 else xL
        if lastX != xL:
            profile_pts.append((xL, wallHeight))

        # Close the profile (back to start)
        # profile_pts already ends at (xL, wallHeight) or we need to get there
        # Add final point to close
        # The loop from last point back to (xL, 0) closes it

        # Draw the profile
        for i in range(len(profile_pts)):
            j = (i + 1) % len(profile_pts)
            sl.addByTwoPoints(
                adsk.core.Point3D.create(profile_pts[i][0], profile_pts[i][1], 0),
                adsk.core.Point3D.create(profile_pts[j][0], profile_pts[j][1], 0))

        # Extrude cutter through full track width (along Y)
        cutProfile = cutSketch.profiles.item(0)
        cutExt = extrudes.createInput(cutProfile,
                                       adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        cutExt.setDistanceExtent(False, adsk.core.ValueInput.createByReal(trackWidth))
        cutterBody = extrudes.add(cutExt).bodies.item(0)
        cutterBody.name = "FingerCutter"

        # =========================
        # STEP 3: Split U-channel with cutter
        # =========================
        splitFeats = root.features.splitBodyFeatures
        splitInput = splitFeats.createInput(uBody, cutterBody, True)
        splitFeats.add(splitInput)

        # Remove the cutter body
        cutterToRemove = None
        for b in root.bRepBodies:
            if b.name == "FingerCutter":
                cutterToRemove = b
                break
        if cutterToRemove:
            root.features.removeFeatures.add(cutterToRemove)

        # Identify pieces: the one starting at X=0 is male (left)
        bodies = [b for b in root.bRepBodies]
        bodies.sort(key=lambda b: b.boundingBox.minPoint.x)
        male = bodies[0] if len(bodies) >= 2 else None
        female = bodies[1] if len(bodies) >= 2 else None

        if male:
            male.name = "Track_Male"
        if female:
            female.name = "Track_Female"

        if not male or not female:
            names = [b.name for b in root.bRepBodies]
            ui.messageBox(f"Failed to identify pieces.\n"
                          f"Bodies: {names}")
            return

        # =========================
        # STEP 4: Apply tolerance
        # Offset the cut faces on the female (socket) side
        # by creating slightly enlarged finger blocks and cutting them
        # =========================
        t = tolerance

        # For each finger on the female piece, cut a slightly oversized slot
        for i in range(numFingers):
            zBot = floorThick + i * fingerHeight
            zTop = floorThick + (i + 1) * fingerHeight

            if i % 2 == 0:
                # Even fingers: male has the tab extending right
                # Female needs a slightly oversized pocket
                skTol = sketches.add(root.xZConstructionPlane)
                skTol.name = f"Tol_F{i}"
                slT = skTol.sketchCurves.sketchLines
                # Pocket extends from midX-t to midX+fingerDepth (already cut)
                # but we just need to widen by tolerance on all sides
                x0 = midX - t
                x1 = midX + fingerDepth + t
                z0 = zBot - t
                z1 = zTop + t
                # Clamp to valid range
                z0 = max(z0, floorThick)
                z1 = min(z1, wallHeight)
                rectPts = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
                for ri in range(4):
                    rj = (ri + 1) % 4
                    slT.addByTwoPoints(
                        adsk.core.Point3D.create(rectPts[ri][0], rectPts[ri][1], 0),
                        adsk.core.Point3D.create(rectPts[rj][0], rectPts[rj][1], 0))

                tolExt = extrudes.createInput(skTol.profiles.item(0),
                                               adsk.fusion.FeatureOperations.CutFeatureOperation)
                tolExt.setDistanceExtent(False, adsk.core.ValueInput.createByReal(trackWidth))
                tolExt.participantBodies = [female]
                extrudes.add(tolExt)
            else:
                # Odd fingers: female has the tab extending left
                # Male needs a slightly oversized pocket
                skTol = sketches.add(root.xZConstructionPlane)
                skTol.name = f"Tol_F{i}"
                slT = skTol.sketchCurves.sketchLines
                x0 = midX - fingerDepth - t
                x1 = midX + t
                z0 = zBot - t
                z1 = zTop + t
                z0 = max(z0, floorThick)
                z1 = min(z1, wallHeight)
                rectPts = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
                for ri in range(4):
                    rj = (ri + 1) % 4
                    slT.addByTwoPoints(
                        adsk.core.Point3D.create(rectPts[ri][0], rectPts[ri][1], 0),
                        adsk.core.Point3D.create(rectPts[rj][0], rectPts[rj][1], 0))

                tolExt = extrudes.createInput(skTol.profiles.item(0),
                                               adsk.fusion.FeatureOperations.CutFeatureOperation)
                tolExt.setDistanceExtent(False, adsk.core.ValueInput.createByReal(trackWidth))
                tolExt.participantBodies = [male]
                extrudes.add(tolExt)

        # Cleanup
        for sk in sketches:
            sk.isLightBulbOn = False
        for p in planes:
            p.isLightBulbOn = False

        ui.messageBox(
            "Finger Joint Test\n\n"
            f"Track: {trackWidth*10:.0f}mm wide, "
            f"{wallThick*10:.0f}mm walls, "
            f"{wallHeight*10:.0f}mm tall\n"
            f"Fingers: {numFingers} per wall, "
            f"{fingerDepth*10:.0f}mm deep\n"
            f"Finger height: {fingerHeight*10:.1f}mm\n"
            f"Tolerance: {tolerance*10:.1f}mm per side\n\n"
            "Pieces interlock by pressing together."
        )

    except:
        if ui:
            ui.messageBox("Error:\n{}".format(traceback.format_exc()))
