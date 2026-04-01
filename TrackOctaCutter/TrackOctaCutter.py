import adsk.core, adsk.fusion, traceback, math


def _all_bodies(root):
    """Return all bRep bodies from root component AND every sub-component.

    When the user answers YES to 'Create separate components', all Track_
    bodies move into Track_Assembly sub-components and disappear from
    root.bRepBodies.  This helper collects them regardless of nesting.
    Duplicate guards prevent double-counting multi-instance components.
    """
    seen = set()
    bodies = []
    for b in root.bRepBodies:
        if id(b) not in seen:
            seen.add(id(b))
            bodies.append(b)
    try:
        for occ in root.allOccurrences:
            try:
                for b in occ.component.bRepBodies:
                    if id(b) not in seen:
                        seen.add(id(b))
                        bodies.append(b)
            except:
                pass
    except:
        pass
    return bodies

# =============================================================================
# DEFAULT PARAMETERS (used if Fusion parameters don't exist)
# =============================================================================
# All values in cm (Fusion internal unit)

# Track dimensions
DEFAULT_TRACK_HEIGHT = 1.0      # 10 mm
DEFAULT_TRACK_WIDTH = 1.5       # 15 mm
DEFAULT_WALL_THICKNESS = 0.3    # 3 mm

# Clip connector parameters
DEFAULT_KEY_DEPTH = 1.0         # 10 mm per side — clip extends 10 mm into each piece (20 mm total)
DEFAULT_KEY_CLEARANCE = 0.03    # 0.3 mm insertion clearance per side (at entry end of legs)
DEFAULT_CLIP_THICKNESS = 0.15   # 1.5 mm leg / floor wall thickness
DEFAULT_TAPER_DEPTH = 0.04      # 0.4 mm: each leg inner face moves this far inward end-to-end
DEFAULT_LEG_DEPTH = 0.70        # 7 mm leg depth past wall tips (toward track floor)
DEFAULT_FLOOR_HEIGHT = 0.30     # 3 mm clip floor height above/past wall tips (sits in open space)
DEFAULT_FLOOR_THICKNESS = 0.6   # unused by pin connector (boss-based); kept for M2 plate ref.


def get_parameter_value(design, param_name, default_value):
    """Get a user parameter value from the design, or return the default."""
    try:
        param = design.userParameters.itemByName(param_name)
        if param:
            return param.value
        return default_value
    except:
        return default_value


def load_parameters(design):
    """Load all parameters from Fusion 360 design."""
    params = {
        'TRACK_HEIGHT':     get_parameter_value(design, 'TRACK_HEIGHT',     DEFAULT_TRACK_HEIGHT),
        'TRACK_WIDTH':      get_parameter_value(design, 'TRACK_WIDTH',      DEFAULT_TRACK_WIDTH),
        'WALL_THICKNESS':   get_parameter_value(design, 'WALL_THICKNESS',   DEFAULT_WALL_THICKNESS),
        'KEY_DEPTH':        get_parameter_value(design, 'KEY_DEPTH',        DEFAULT_KEY_DEPTH),
        'KEY_CLEARANCE':    get_parameter_value(design, 'KEY_CLEARANCE',    DEFAULT_KEY_CLEARANCE),
        'CLIP_THICKNESS':   get_parameter_value(design, 'CLIP_THICKNESS',   DEFAULT_CLIP_THICKNESS),
        'TAPER_DEPTH':      get_parameter_value(design, 'TAPER_DEPTH',      DEFAULT_TAPER_DEPTH),
        'LEG_DEPTH':        get_parameter_value(design, 'LEG_DEPTH',        DEFAULT_LEG_DEPTH),
        'FLOOR_HEIGHT':      get_parameter_value(design, 'FLOOR_HEIGHT',      DEFAULT_FLOOR_HEIGHT),
        'FLOOR_THICKNESS':  get_parameter_value(design, 'FLOOR_THICKNESS',  DEFAULT_FLOOR_THICKNESS),
    }
    return params


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent
        params = load_parameters(design)

        # === MAIN MENU ===
        result = ui.messageBox(
            'TrackOctaCutter\n\n'
            'Phase 1: Place cut planes along path\n'
            'Phase 2: Cut track at existing CutPlane_* planes\n\n'
            'Start Phase 1 (place cut planes)?',
            'Track Octa Cutter',
            adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType
        )

        if result == adsk.core.DialogResults.DialogYes:
            place_cut_planes(root, ui, design, params)
        elif result == adsk.core.DialogResults.DialogNo:
            result2 = ui.messageBox(
                'Phase 2: Cut track at CutPlane_* planes?\n\n'
                'YES = Select body and cut at all CutPlane_* planes\n'
                'NO = Show help and current parameters',
                'Track Octa Cutter',
                adsk.core.MessageBoxButtonTypes.YesNoButtonType
            )
            if result2 == adsk.core.DialogResults.DialogYes:
                cut_at_planes(root, ui, design, params)
            else:
                show_help(ui, params)

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def show_help(ui, params):
    """Show help and current parameters."""
    ui.messageBox(
        'TrackOctaCutter — Two-phase workflow\n\n'
        'Phase 1: Place Cut Planes\n'
        '  1. Select path sketch (sweep centerline)\n'
        '  2. Enter max piece length\n'
        '  3. Construction planes are created along path\n'
        '  4. Review: move/delete planes as needed\n\n'
        'Phase 2: Cut at Planes\n'
        '  1. Select the track body\n'
        '  2. Select the path sketch (for accurate piece ordering)\n'
        '  3. All CutPlane_* planes are processed:\n'
        '     - Body split at each plane\n'
        '     - Clip_N bridge plate created at each junction\n'
        '  Assembly:\n'
        '   M2 plate: plate inside channel, 2\u00d7 M2 screws from channel side.\n'
        '   H-key: identical sockets in both pieces, shared Connector_Key body.\n'
        '     Slide key into piece A, push piece B onto protruding half.\n\n'
        '--- Current Parameters ---\n'
        f'TRACK_HEIGHT:   {params["TRACK_HEIGHT"]*10:.1f} mm\n'
        f'TRACK_WIDTH:    {params["TRACK_WIDTH"]*10:.1f} mm\n'
        f'WALL_THICKNESS: {params["WALL_THICKNESS"]*10:.1f} mm\n'
        f'KEY_DEPTH:      {params["KEY_DEPTH"]*10:.1f} mm per side ({params["KEY_DEPTH"]*20:.0f} mm total plate length)\n'
        f'FLOOR_HEIGHT:   {params["FLOOR_HEIGHT"]*10:.1f} mm (bridge plate thickness)\n\n'
        'Edit defaults in TrackOctaCutter.py constants at the top of the file.'
    )


# =============================================================================
# PHASE 1: Place Cut Planes
# =============================================================================

def place_cut_planes(root, ui, design, params):
    """Create construction planes along the sweep path at equal intervals."""

    ret_length, cancelled = ui.inputBox(
        'Max piece length (cm) for your 3D printer:',
        'Phase 1: Place Cut Planes',
        '23.0'
    )
    if cancelled:
        return
    try:
        max_piece_length = float(ret_length)
    except:
        ui.messageBox('Invalid number.')
        return

    sel = ui.selectEntity(
        'Select the PATH sketch or curve (sweep centerline)',
        'Sketches,SketchCurves'
    )
    if not sel:
        return

    selected_entity = sel.entity
    if hasattr(selected_entity, 'sketchCurves'):
        path_sketch = selected_entity
    elif hasattr(selected_entity, 'parentSketch'):
        path_sketch = selected_entity.parentSketch
    else:
        ui.messageBox('Please select a sketch or sketch curve.')
        return

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

    path_collection = adsk.core.ObjectCollection.create()
    for curve in all_curves:
        path_collection.add(curve)

    sweep_path = root.features.createPath(path_collection, True)

    num_pieces = math.ceil(total_length / max_piece_length)
    if num_pieces < 2:
        ui.messageBox(
            f'Track length: {total_length:.1f} cm\n'
            f'Fits in one piece — no cuts needed!'
        )
        return

    planes_created = 0
    for i in range(1, num_pieces):
        ratio = i / num_pieces
        try:
            plane_input = root.constructionPlanes.createInput()
            distance_value = adsk.core.ValueInput.createByReal(ratio)
            plane_input.setByDistanceOnPath(sweep_path, distance_value)
            cut_plane = root.constructionPlanes.add(plane_input)
            cut_plane.name = f'CutPlane_{i}'
            planes_created += 1
        except Exception as e:
            ui.messageBox(f'Plane {i} failed: {str(e)}')

    ui.messageBox(
        f'Phase 1 complete!\n\n'
        f'Track length: {total_length:.1f} cm\n'
        f'{planes_created} cut planes created\n'
        f'Expected pieces: {num_pieces} (~{total_length/num_pieces:.1f} cm each)\n\n'
        'Review the CutPlane_* planes in the browser.\n'
        'You can move or delete any plane before Phase 2.\n\n'
        'When ready, run the add-in again and choose Phase 2.'
    )


# =============================================================================
# PHASE 2: Cut at Planes
# =============================================================================

def cut_at_planes(root, ui, design, params):
    """Process all CutPlane_* construction planes: split + U-clip connectors."""

    # === SELECT TRACK BODY ===
    sel_body = ui.selectEntity('Select the TRACK body to cut', 'Bodies')
    if not sel_body:
        return
    track_body = adsk.fusion.BRepBody.cast(sel_body.entity)
    track_body.name = 'Track_Working'

    # === SELECT PATH SKETCH (optional) ===
    path_sketch_ref = None
    try:
        sel_path = ui.selectEntity(
            'Select the PATH sketch (track centerline used in Phase 1)\n'
            'Press Escape to skip — automatic detection will be used',
            'Sketches,SketchCurves'
        )
        if sel_path:
            ent = sel_path.entity
            if hasattr(ent, 'sketchCurves'):
                path_sketch_ref = ent
            elif hasattr(ent, 'parentSketch'):
                path_sketch_ref = ent.parentSketch
    except:
        pass

    # === FIND ALL CutPlane_* PLANES ===
    # Deduplicate by name: if Phase 1 was run more than once, duplicate
    # construction planes with the same name exist at the same position.
    # Keep only one plane per unique name to avoid creating 2 clips per junction.
    name_to_plane = {}
    for i in range(root.constructionPlanes.count):
        plane = root.constructionPlanes.item(i)
        if plane.name.startswith('CutPlane_'):
            name_to_plane[plane.name] = plane  # last duplicate wins

    if not name_to_plane:
        ui.messageBox('No CutPlane_* construction planes found.\nRun Phase 1 first.')
        return

    cut_planes = sorted(name_to_plane.values(),
                        key=lambda p: int(p.name.replace('CutPlane_', ''))
                        if p.name.replace('CutPlane_', '').isdigit() else 0)

    num_cuts = len(cut_planes)

    # === CHOOSE CONNECTOR TYPE ===
    conn_choice = ui.messageBox(
        f'Found {num_cuts} cut planes.\n\n'
        f'Choose connector type:\n\n'
        f'  YES  = M2 screw plate (current)\n'
        f'         Flat plate inside channel + 2\u00d7 M2 screws\n'
        f'         Requires: heat-set inserts + M2 screws\n'
        f'         Fully hidden inside channel (wall-facing side)\n\n'
        f'  NO   = H-key (no hardware, approach B)\n'
        f'         Identical socket cut in BOTH adjacent pieces\n'
        f'         One shared Connector_Key body (print 1 per junction)\n'
        f'         Slide key between pieces — fully hidden in floor\n\n'
        f'  CANCEL = Abort',
        'Choose Connector',
        adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType
    )
    if conn_choice == adsk.core.DialogResults.DialogCancel:
        return
    use_pin_connector = (conn_choice == adsk.core.DialogResults.DialogNo)

    # === STEP 1: Split at each plane ===
    cuts_made = 0
    for idx, cut_plane in enumerate(cut_planes):
        adsk.doEvents()
        try:
            split_surface = create_local_split_surface(root, cut_plane, params, None, idx + 1, ui)
            if split_surface is None:
                continue
            if not isinstance(split_surface, adsk.fusion.BRepBody):
                continue

            min_piece_vol = 0.05
            track_candidates = []
            for b in root.bRepBodies:
                if b.name.startswith('Track_') and b != split_surface:
                    try:
                        vol = b.physicalProperties.volume
                    except:
                        vol = 0
                    track_candidates.append((vol, b))
            track_candidates.sort(key=lambda x: x[0], reverse=True)
            track_bodies = [b for v, b in track_candidates if v >= min_piece_vol]
            if not track_bodies:
                track_bodies = [b for _, b in track_candidates]
            if not track_bodies:
                try:
                    split_surface.deleteMe()
                except:
                    pass
                continue

            split_feats = root.features.splitBodyFeatures
            for target_body in track_bodies:
                try:
                    split_input = split_feats.createInput(target_body, split_surface, False)
                    split_result = split_feats.add(split_input)
                    for new_body in split_result.bodies:
                        new_body.name = 'Track_Piece'
                    cuts_made += 1
                    break
                except:
                    pass

            try:
                split_surface.deleteMe()
            except:
                pass

        except Exception as e:
            ui.messageBox(f'Cut {idx + 1} ({cut_plane.name}) failed: {str(e)}')

    if cuts_made == 0:
        ui.messageBox(
            f'Warning: No cuts were made!\n\n'
            f'{num_cuts} cut planes found but 0 successful splits.\n'
            f'Check that the track body intersects the cut planes.',
            'Debug Info'
        )

    # === STEP 2.5: Merge sliver pieces into adjacent tracks ===
    min_volume = 0.05
    slivers_removed = 0

    for body in list(root.bRepBodies):
        try:
            if body.name.startswith('SplitSurface'):
                body.deleteMe()
        except:
            pass

    # Clean up SplitSurface sketches left by create_local_split_surface.
    for sk in list(root.sketches):
        try:
            if sk.name.startswith('SplitSurface'):
                sk.deleteMe()
        except:
            pass

    for _pass in range(20):
        adsk.doEvents()
        slivers = []
        tracks = []
        for body in root.bRepBodies:
            if not body.name.startswith('Track_'):
                continue
            try:
                vol = body.physicalProperties.volume
                if vol < min_volume:
                    slivers.append(body)
                else:
                    tracks.append(body)
            except:
                pass

        if not slivers:
            break

        merged_any = False
        for sliver in slivers:
            joined = False
            # Pass 1: bbox overlap
            for track in tracks:
                bb_a = sliver.boundingBox
                bb_b = track.boundingBox
                if (bb_a.minPoint.x <= bb_b.maxPoint.x and bb_a.maxPoint.x >= bb_b.minPoint.x and
                    bb_a.minPoint.y <= bb_b.maxPoint.y and bb_a.maxPoint.y >= bb_b.minPoint.y and
                    bb_a.minPoint.z <= bb_b.maxPoint.z and bb_a.maxPoint.z >= bb_b.minPoint.z):
                    try:
                        combines = root.features.combineFeatures
                        tc = adsk.core.ObjectCollection.create()
                        tc.add(sliver)
                        ci = combines.createInput(track, tc)
                        ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                        ci.isKeepToolBodies = False
                        combines.add(ci)
                        slivers_removed += 1
                        joined = True
                        merged_any = True
                        break
                    except:
                        pass
            if not joined:
                # Pass 2: centroid-distance fallback (bbox fails on tight hairpin curves)
                try:
                    s_com = sliver.physicalProperties.centerOfMass
                    best_dist = float('inf')
                    best_track = None
                    for track in tracks:
                        try:
                            t_com = track.physicalProperties.centerOfMass
                            d = math.sqrt((s_com.x - t_com.x) ** 2 +
                                          (s_com.y - t_com.y) ** 2 +
                                          (s_com.z - t_com.z) ** 2)
                            if d < best_dist:
                                best_dist = d
                                best_track = track
                        except:
                            pass
                    if best_track is not None and best_dist < 5.0:
                        combines = root.features.combineFeatures
                        tc = adsk.core.ObjectCollection.create()
                        tc.add(sliver)
                        ci = combines.createInput(best_track, tc)
                        ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                        ci.isKeepToolBodies = False
                        combines.add(ci)
                        slivers_removed += 1
                        joined = True
                        merged_any = True
                except:
                    pass
            if not joined:
                try:
                    sliver.deleteMe()
                    slivers_removed += 1
                    merged_any = True
                except:
                    # Cannot delete — rename to remove from Track_ namespace so it
                    # doesn't get counted as a real piece and doesn't block future passes.
                    try:
                        sliver.name = 'Sliver_residual'
                        merged_any = True
                    except:
                        pass

        if not merged_any:
            break

    # === STEP 2: Create connectors at each junction ===
    clips_made = 0
    clip_errors = []
    for idx, cut_plane in enumerate(cut_planes):
        adsk.doEvents()
        try:
            if use_pin_connector:
                ok = create_pin_connector(root, cut_plane, params, idx + 1, ui)
            else:
                ok = create_junction_clip(root, cut_plane, params, idx + 1, None, ui)
            if ok:
                clips_made += 1
        except Exception as e:
            clip_errors.append(f'Cut {idx + 1}: {str(e)}')

    if clip_errors:
        ui.messageBox(
            f'Connector errors ({len(clip_errors)}):\n' +
            '\n'.join(clip_errors[:5]),
            'Connector Debug'
        )

    # === STEP 3: Rename pieces ===
    piece_bodies = [b for b in root.bRepBodies if b.name.startswith('Track_')]

    try:
        path_curves = []
        if path_sketch_ref:
            for curve in path_sketch_ref.sketchCurves:
                path_curves.append(curve)
        if not path_curves:
            for sketch in root.sketches:
                if not any(sketch.name.startswith(p) for p in ('Clip_', 'SplitSurface_', 'Blade_')):
                    for curve in sketch.sketchCurves:
                        path_curves.append(curve)
        if path_curves:
            piece_bodies = sort_bodies_along_path(piece_bodies, path_curves)
    except:
        pass

    for idx, body in enumerate(piece_bodies):
        body.name = f'Track_Piece_{idx + 1}'

    if use_pin_connector:
        connector_bodies = [b for b in root.bRepBodies if b.name.startswith('Connector_Key_')]
        connector_label  = (f'{clips_made}/{num_cuts} socket pairs cut + '
                            f'{len(connector_bodies)} Connector_Key bodies created')
        assembly_tip = (
            'Assembly tip: all pieces are identical — each end has the same socket.\n'
            'Print one Connector_Key per junction. Slide key into piece A socket\n'
            'until centred, then push piece B onto the protruding half.\n'
            'Press-fit, no hardware. Key hidden inside floor material.'
        )
        connector_export = '\u2022 Right-click each Connector_Key_N body \u2192 Save As Mesh'
    else:
        connector_bodies = [b for b in root.bRepBodies if b.name.startswith('Clip_')]
        connector_label  = f'{clips_made}/{num_cuts} bridge plates created (Clip_N)'
        assembly_tip = (
            'Assembly tip: press M2 heat-set inserts into the floor holes.\n'
            'Slide the Clip_N plate into the channel; drive 2\u00d7 M2 screws\n'
            'from the channel (wall-facing) side — heads stay hidden.'
        )
        connector_export = '\u2022 Right-click Clip_N body \u2192 Save As Mesh'

    for plane in cut_planes:
        plane.isLightBulbOn = False

    # === STEP 4: Create components ===
    sliver_msg = f' ({slivers_removed} slivers merged)' if slivers_removed > 0 else ''
    create_comps = ui.messageBox(
        f'Done!\n\n'
        f'{len(piece_bodies)} track pieces created{sliver_msg}\n'
        f'{cuts_made} cuts made\n'
        f'{connector_label}\n\n'
        'Create separate components for each piece?\n'
        '(Connector bodies stay as loose bodies for separate STL export)',
        'Create Components?',
        adsk.core.MessageBoxButtonTypes.YesNoButtonType
    )

    if create_comps == adsk.core.DialogResults.DialogYes:
        create_piece_components(root, piece_bodies)
        ui.messageBox(
            'Components created!\n\n'
            'Track pieces are in Track_Assembly.\n'
            'Connector bodies remain as root bodies.\n\n'
            'To export as STL:\n'
            '\u2022 Right-click component \u2192 Save As Mesh\n'
            f'{connector_export}\n\n'
            f'{assembly_tip}'
        )


# =============================================================================
# SECTION ANALYSIS
# =============================================================================

def analyze_u_section(root, cut_plane, params, track_body):
    """Analyze the U-channel cross-section on the cut plane.

    Samples a grid in sketch-local 2-D space, tests each point against the
    original track body, and determines which side of the U is open.
    Returns a dict with bbox and open_side, or None on failure.
    """
    try:
        temp_sketch = root.sketches.add(cut_plane)
        transform = temp_sketch.transform

        normal = adsk.core.Vector3D.create(
            transform.getCell(0, 2),
            transform.getCell(1, 2),
            transform.getCell(2, 2)
        )
        normal.normalize()

        scan_half = 2.0 * max(params['TRACK_HEIGHT'], params['TRACK_WIDTH'])
        grid_n = 15  # 15x15 = 225 samples (was 30x30 = 900) — still accurate for U-channel
        step = (2.0 * scan_half) / (grid_n - 1)

        inside_points = []

        for ix in range(grid_n):
            sx = -scan_half + ix * step
            for iy in range(grid_n):
                sy = -scan_half + iy * step
                pt_sketch = adsk.core.Point3D.create(sx, sy, 0)
                pt_model = pt_sketch.copy()
                pt_model.transformBy(transform)
                pt_model.x += normal.x * 0.005
                pt_model.y += normal.y * 0.005
                pt_model.z += normal.z * 0.005
                containment = track_body.pointContainment(pt_model)
                if containment == adsk.fusion.PointContainment.PointInsidePointContainment:
                    inside_points.append((sx, sy))

        if len(inside_points) < 10:
            temp_sketch.deleteMe()
            return None

        xs = [p[0] for p in inside_points]
        ys = [p[1] for p in inside_points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        inset = 0.15

        sides = {
            'min_y': (cx, min_y + inset),
            'max_y': (cx, max_y - inset),
            'min_x': (min_x + inset, cy),
            'max_x': (max_x - inset, cy),
        }

        open_side = None
        for side_name, (tx, ty) in sides.items():
            pt_s = adsk.core.Point3D.create(tx, ty, 0)
            pt_m = pt_s.copy()
            pt_m.transformBy(transform)
            pt_m.x += normal.x * 0.005
            pt_m.y += normal.y * 0.005
            pt_m.z += normal.z * 0.005
            containment = track_body.pointContainment(pt_m)
            if containment != adsk.fusion.PointContainment.PointInsidePointContainment:
                open_side = side_name
                break

        temp_sketch.deleteMe()

        if open_side is None:
            return None

        return {
            'bbox_cx': cx, 'bbox_cy': cy,
            'bbox_half_w': (max_x - min_x) / 2.0,
            'bbox_half_h': (max_y - min_y) / 2.0,
            'min_x': min_x, 'max_x': max_x,
            'min_y': min_y, 'max_y': max_y,
            'open_side': open_side,
        }

    except:
        return None


# =============================================================================
# JUNCTION CLIP
# =============================================================================

def _scan_bodies_in_sketch(sketch, bodies, params):
    """Grid scan in sketch 2D space to find the bounding box of the cross-section.

    Works for both straight and curved track regardless of B-Rep face structure.
    Mirrors the logic in analyze_u_section but operates on an existing sketch
    and a list of (already-split) bodies instead of the original track body.
    Returns (min_x, max_x, min_y, max_y) in sketch local 2D, or None on failure.
    """
    try:
        transform = sketch.transform
        normal = adsk.core.Vector3D.create(
            transform.getCell(0, 2), transform.getCell(1, 2), transform.getCell(2, 2))
        normal.normalize()

        scan_half = 2.0 * max(params['TRACK_HEIGHT'], params['TRACK_WIDTH'])
        grid_n    = 15
        step      = (2.0 * scan_half) / (grid_n - 1)

        inside_pts = []
        INSIDE = adsk.fusion.PointContainment.PointInsidePointContainment
        for ix in range(grid_n):
            sx = -scan_half + ix * step
            for iy in range(grid_n):
                sy = -scan_half + iy * step
                pt_base = adsk.core.Point3D.create(sx, sy, 0)
                pt_base.transformBy(transform)
                found = False
                # Try both sides of the cut plane with a robust 0.5 mm offset.
                for sign in (1.0, -1.0):
                    pt_m = adsk.core.Point3D.create(
                        pt_base.x + sign * normal.x * 0.05,
                        pt_base.y + sign * normal.y * 0.05,
                        pt_base.z + sign * normal.z * 0.05,
                    )
                    for body in bodies:
                        try:
                            if body.pointContainment(pt_m) == INSIDE:
                                inside_pts.append((sx, sy))
                                found = True
                                break
                        except:
                            pass
                    if found:
                        break

        if len(inside_pts) < 10:
            return None

        xs = [p[0] for p in inside_pts]
        ys = [p[1] for p in inside_pts]
        return min(xs), max(xs), min(ys), max(ys)
    except:
        return None


def create_junction_clip(root, cut_plane, params, joint_num, section, ui=None):
    """M2 screw bridge plate inside the U-channel at floor level.

    Plate is sketched on the INNER FLOOR FACE (floor_sk), not on the cut_plane.
    This means hole circles are drawn in the same sketch as the plate rectangle —
    one consistent coordinate system, zero secondary-transform issues.

    Extrusion direction: positive = anti_hole = from floor toward channel opening.
      - Plate:         +anti_hole by plate_h  → slab sitting on inner floor
      - Insert bores:  -anti_hole by wt-0.02  → blind holes into floor material

    Clearance holes (2.4 mm dia) are subtracted FROM the plate profile in floor_sk
    (the rectangle-minus-circles profile), so no separate clearance-bore extrude.
    Insert holes (3.0 mm dia) are cut into track_bodies in a second step using a
    fresh sketch on the same floor_cp — but we use that sketch's OWN transform.
    """
    key_depth = params['KEY_DEPTH']
    wt        = params['WALL_THICKNESS']
    plate_h   = params.get('FLOOR_HEIGHT', DEFAULT_FLOOR_HEIGHT)  # 2 mm

    M2_CLEAR_R  = 0.12   # 1.2 mm radius → 2.4 mm dia (clearance in plate)
    M2_INSERT_R = 0.15   # 1.5 mm radius → 3.0 mm dia (insert in track floor)
    CL          = 0.03   # 0.3 mm side clearance so plate slides past walls

    # Guard: skip if already created.
    for b in root.bRepBodies:
        if b.name == f'Clip_{joint_num}':
            return True

    # ----------------------------------------------------------------
    # Step 1: detect cross-section bbox and open side.
    # Use a temporary sketch on cut_plane — no drawing, detection only.
    # ----------------------------------------------------------------
    detect_sk = root.sketches.add(cut_plane)
    s_min_x = s_max_x = s_min_y = s_max_y = None
    open_side = None

    adjacent  = find_bodies_at_cut(root, cut_plane)
    adj_bodies = [b for b, _ in adjacent]

    # Grid scan in detect_sk against adjacent split pieces.
    # This works for both straight and curved track because it does NOT rely
    # on face.vertices (which gives incomplete bbox for curved B-Rep faces).
    if adj_bodies:
        scan_result = _scan_bodies_in_sketch(detect_sk, adj_bodies, params)
        if scan_result:
            s_min_x, s_max_x, s_min_y, s_max_y = scan_result
            open_side = detect_open_side_from_sketch(
                detect_sk, s_min_x, s_max_x, s_min_y, s_max_y, adj_bodies
            )

    # Capture detect_sk transform while alive (needed for world-space conversions).
    detect_tr = detect_sk.transform.copy()
    try:
        detect_sk.deleteMe()
    except:
        detect_sk.isLightBulbOn = False

    if s_min_x is None or open_side is None:
        return False

    # ----------------------------------------------------------------
    # Step 2: derive geometry from bbox.
    # ----------------------------------------------------------------
    def _col3(m, c):
        v = adsk.core.Vector3D.create(m.getCell(0,c), m.getCell(1,c), m.getCell(2,c))
        v.normalize(); return v

    _sx = _col3(detect_tr, 0)   # detect_sk X axis in world (across track)
    _sy = _col3(detect_tr, 1)   # detect_sk Y axis in world

    # anti_hole: direction from floor toward channel opening.
    # Junction origin: path point (0, 0) IS the inner floor centre — the track
    # path is drawn on the inner floor surface, so detect_sk origin = inner floor.
    # This matches exactly how hex pins use (0, 0).  Do NOT derive from the scan
    # bbox: the 15×15 grid (step ≈ 4.3 mm) is too coarse to resolve 3 mm walls,
    # so scan-derived jx/jy/inner_hw are badly wrong.
    jx = 0.0
    jy = 0.0
    # inner half-width of channel from params (same for all open_side orientations)
    inner_hw = params['TRACK_WIDTH'] / 2.0 - wt - CL
    if open_side == 'max_y':
        anti_hole = adsk.core.Vector3D.create(_sy.x, _sy.y, _sy.z)
    elif open_side == 'min_y':
        anti_hole = adsk.core.Vector3D.create(-_sy.x, -_sy.y, -_sy.z)
    elif open_side == 'max_x':
        anti_hole = adsk.core.Vector3D.create(_sx.x, _sx.y, _sx.z)
    else:  # min_x
        anti_hole = adsk.core.Vector3D.create(-_sx.x, -_sx.y, -_sx.z)

    # ----------------------------------------------------------------
    # Step 3: find the inner floor face of an adjacent track body.
    # ----------------------------------------------------------------
    track_bodies = [b for b, _ in adjacent if b.name.startswith('Track_')]
    if not track_bodies:
        return False

    # Among faces whose outward normal ≈ anti_hole (dot > 0.7), pick the one
    # DEEPEST in the channel (minimum position along anti_hole).
    # Wall-tip faces share the same normal direction as the inner floor face but
    # are near the channel OPENING, not the floor — sorting by position fixes this.
    floor_face = None
    best_pos   = float('inf')   # want MINIMUM = deepest in channel = actual floor
    floor_face_dot = -2.0
    for tb in track_bodies:
        for face in tb.faces:
            ev = face.evaluator
            ok, n = ev.getNormalAtPoint(face.pointOnFace)
            if ok:
                d = n.x*anti_hole.x + n.y*anti_hole.y + n.z*anti_hole.z
                if d > 0.7:   # face points toward channel opening
                    p = face.pointOnFace
                    pos = p.x*anti_hole.x + p.y*anti_hole.y + p.z*anti_hole.z
                    if pos < best_pos:   # deepest = smallest component along anti_hole
                        best_pos       = pos
                        floor_face     = face
                        floor_face_dot = d

    if floor_face is None:
        return False

    planes   = root.constructionPlanes
    plane_in = planes.createInput()
    plane_in.setByOffset(floor_face, adsk.core.ValueInput.createByReal(plate_h))
    floor_cp = planes.add(plane_in)
    floor_cp.isLightBulbOn = False

    # ----------------------------------------------------------------
    # Step 4: create ONE sketch on floor_cp for EVERYTHING.
    # Compute all positions from detect_sk world points projected onto
    # floor_sk using floor_sk's OWN transform — no secondary sketch needed.
    # ----------------------------------------------------------------
    floor_sk = root.sketches.add(floor_cp)
    floor_sk.name = f'Clip_{joint_num}'

    # floor_sk inverse transform (world → floor_sk 2D)
    _fsk_inv = floor_sk.transform.copy()
    _fsk_inv.invert()

    def _ps_to_w(px, py):
        """Plate-sketch 2D → world 3D."""
        p = adsk.core.Point3D.create(px, py, 0)
        p.transformBy(detect_tr)
        return p

    def _w_to_fsk(pw):
        """World 3D → floor_sk 2D (x, y); drop Z (distance from plane)."""
        p = pw.copy()
        p.transformBy(_fsk_inv)
        return p.x, p.y

    _cpn = cut_plane.geometry.normal; _cpn.normalize()

    def _off_w(pt, dist):
        return adsk.core.Point3D.create(
            pt.x + _cpn.x*dist, pt.y + _cpn.y*dist, pt.z + _cpn.z*dist
        )

    # Key world points (all from detect_sk, on the cut_plane at z=0)
    jw    = _ps_to_w(jx, jy)                         # junction on inner floor face
    if open_side in ('max_y', 'min_y'):
        ca_w = _ps_to_w(jx - inner_hw, jy)
        cb_w = _ps_to_w(jx + inner_hw, jy)
    else:
        ca_w = _ps_to_w(jx, jy - inner_hw)
        cb_w = _ps_to_w(jx, jy + inner_hw)

    # Plate ends (along track path, ±key_depth from junction)
    pe0_w = _off_w(jw,  key_depth)
    pe1_w = _off_w(jw, -key_depth)

    # Hole centres (±key_depth/2 from junction, one per piece)
    h0_w = _off_w(jw,  key_depth / 2.0)
    h1_w = _off_w(jw, -key_depth / 2.0)

    # Project everything to floor_sk 2D
    jc   = _w_to_fsk(jw)
    ca   = _w_to_fsk(ca_w)
    cb   = _w_to_fsk(cb_w)
    pe0  = _w_to_fsk(pe0_w)
    pe1  = _w_to_fsk(pe1_w)
    h0   = _w_to_fsk(h0_w)
    h1   = _w_to_fsk(h1_w)

    # Rectangle corners (vector arithmetic: side-edge ± half path-length from jc)
    dpe0 = (pe0[0] - jc[0], pe0[1] - jc[1])
    dpe1 = (pe1[0] - jc[0], pe1[1] - jc[1])
    c1 = (ca[0] + dpe1[0], ca[1] + dpe1[1])
    c2 = (ca[0] + dpe0[0], ca[1] + dpe0[1])
    c3 = (cb[0] + dpe0[0], cb[1] + dpe0[1])
    c4 = (cb[0] + dpe1[0], cb[1] + dpe1[1])

    sk_lines = floor_sk.sketchCurves.sketchLines
    corners  = [c1, c2, c3, c4]
    for i in range(4):
        a, b = corners[i], corners[(i+1) % 4]
        sk_lines.addByTwoPoints(
            adsk.core.Point3D.create(a[0], a[1], 0),
            adsk.core.Point3D.create(b[0], b[1], 0)
        )

    # Clearance circles drawn INSIDE the rectangle → plate profile = rect - circles
    sk_circles = floor_sk.sketchCurves.sketchCircles
    sk_circles.addByCenterRadius(adsk.core.Point3D.create(h0[0], h0[1], 0), M2_CLEAR_R)
    sk_circles.addByCenterRadius(adsk.core.Point3D.create(h1[0], h1[1], 0), M2_CLEAR_R)

    if floor_sk.profiles.count == 0:
        floor_sk.isLightBulbOn = False
        try: floor_cp.deleteMe()
        except: pass
        return False

    # Pick the plate profile: the one with the most loops (outer rect + 2 inner holes)
    plate_profile = None
    best_nloops   = -1
    for i in range(floor_sk.profiles.count):
        p = floor_sk.profiles.item(i)
        nl = p.profileLoops.count
        if nl > best_nloops:
            best_nloops   = nl
            plate_profile = p

    # Extrude plate: positive direction = anti_hole = from floor toward channel
    extrudes = root.features.extrudeFeatures
    ext_in = extrudes.createInput(
        plate_profile,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    # Negative distance = against floor_cp normal = into channel (floor_cp normal points outward)
    ext_in.setDistanceExtent(False, adsk.core.ValueInput.createByReal(-plate_h))
    ext_feat = extrudes.add(ext_in)

    plate_body = None
    for i in range(ext_feat.bodies.count):
        b = ext_feat.bodies.item(i)
        if i == 0:
            b.name = f'Clip_{joint_num}'
            plate_body = b
        else:
            try: b.deleteMe()
            except: pass

    floor_sk.isLightBulbOn = False

    if plate_body is None:
        try: floor_cp.deleteMe()
        except: pass
        return False

    # ----------------------------------------------------------------
    # Step 5: insert bores into track floor.
    # We know the exact world positions of the hole centres from floor_sk.
    # For the insert sketch we read ITS OWN transform to avoid axis mismatch.
    # ----------------------------------------------------------------
    # Use the original world positions directly — avoids any floor_sk transform
    # drift that can occur after the plate extrusion updates the timeline.
    h0_exact = h0_w
    h1_exact = h1_w

    insert_bore_depth = wt - 0.02   # blind into floor, ~0.2 mm left

    for hw_exact in [h0_exact, h1_exact]:
        try:
            ins_sk = root.sketches.add(floor_cp)
            ins_inv = ins_sk.transform.copy()
            ins_inv.invert()
            p = hw_exact.copy()
            p.transformBy(ins_inv)
            fp_ins = adsk.core.Point3D.create(p.x, p.y, 0)
            ins_sk.sketchCurves.sketchCircles.addByCenterRadius(fp_ins, M2_INSERT_R)
            if ins_sk.profiles.count > 0:
                ci = extrudes.createInput(
                    ins_sk.profiles.item(0),
                    adsk.fusion.FeatureOperations.CutFeatureOperation
                )
                # Negative = against floor_cp normal = through plate_h gap and into floor material
                ci.setDistanceExtent(False, adsk.core.ValueInput.createByReal(-(plate_h + insert_bore_depth)))
                ci.participantBodies = track_bodies   # plain list
                extrudes.add(ci)
            ins_sk.isLightBulbOn = False
        except Exception as e:
            if ui:
                ui.messageBox(f'InsertBore failed (Clip_{joint_num}): {e}')

    try: floor_cp.deleteMe()
    except: pass

    return True


# =============================================================================
# FACE-EDGE HELPERS  (replace pointContainment for shell/sub-component bodies)
# =============================================================================

def _sample_face_edges_2d(face, sk_inv_transform, n_samples=10):
    """Sample points along every edge of `face`, project to sketch 2D.

    Returns a list of (x, y) tuples in sketch-local coordinates.
    Works for solid AND shell/surface bodies because it only reads edge geometry,
    never calls pointContainment.
    """
    pts = []
    try:
        for edge in face.edges:
            try:
                ev = edge.evaluator
                ok, t0, t1 = ev.getParameterExtents()
                if not ok:
                    continue
                for i in range(n_samples + 1):
                    t = t0 + (t1 - t0) * i / n_samples
                    ok2, pt_w = ev.getPointAtParameter(t)
                    if ok2:
                        p = pt_w.copy()
                        p.transformBy(sk_inv_transform)
                        pts.append((p.x, p.y))
            except:
                pass
    except:
        pass
    return pts


def _detect_open_side_from_pts(pts_2d, s_min_x, s_max_x, s_min_y, s_max_y):
    """Detect which side of the U-channel bbox has no spanning edge at its centre.

    A U-channel cross-section face has edges along the floor and walls, but at
    the opening level the ONLY edges are the short wall-cap segments near the
    corners — there is no edge through the centre of the opening side.

    We test each of the four bbox sides: does ANY sample point lie within a
    small perpendicular tolerance of the boundary AND within 40% of the span
    around the centre in the parallel direction?  The side where no such point
    exists is the open side.

    Returns 'min_x', 'max_x', 'min_y', or 'max_y', or None.
    """
    width  = s_max_x - s_min_x
    height = s_max_y - s_min_y
    cx = (s_min_x + s_max_x) / 2.0
    cy = (s_min_y + s_max_y) / 2.0

    # perpendicular tolerance: must be within 15% of the bbox span in that axis
    # parallel tolerance: must be within 40% of the perpendicular span to count as "centre"
    candidates = [
        ('min_y', s_min_y, cx, height, width),
        ('max_y', s_max_y, cx, height, width),
        ('min_x', s_min_x, cy, width,  height),
        ('max_x', s_max_x, cy, width,  height),
    ]

    for side, boundary, centre_par, span_perp, span_par in candidates:
        perp_tol = max(span_perp * 0.15, 0.05)   # at least 0.5 mm
        par_tol  = span_par * 0.40

        if side in ('min_y', 'max_y'):
            near = any(abs(py - boundary) < perp_tol and abs(px - centre_par) < par_tol
                       for px, py in pts_2d)
        else:
            near = any(abs(px - boundary) < perp_tol and abs(py - centre_par) < par_tol
                       for px, py in pts_2d)

        if not near:
            return side

    return None


# =============================================================================
# PIN CONNECTOR (no-hardware alternative to M2 screw plate)
# =============================================================================

def create_pin_connector(root, cut_plane, params, joint_num, ui=None):
    """Approach B: identical socket in BOTH adjacent pieces + one shared H-key.

    All track pieces are identical — no male/female alternation.
    Each junction gets the same socket cut into both adjacent bodies.
    One Connector_Key_N body is created per junction, placed at that junction's
    cut plane with a collar slab.  Print one key per junction; press-fit into sockets.

    Socket profile = key profile + HOLE_CL clearance on all faces.
    Key profile = exact 10-vertex cross (no clearance — it IS the key).

    No combineFeatures anywhere.  Only extrudeFeatures + CutFeatureOperation
    + participantBodies (proven working approach, no component ownership issues).

    Assembly: slide H-key into socket on piece A until centred, then slide
    piece B onto the protruding half.  Key is fully hidden inside floor material
    + tiny rise into channel; invisible from viewer-facing and wall-facing sides.
    """
    PIN_DEPTH  = 1.0    # 10 mm engagement per side (20 mm total key length)
    HOLE_CL    = 0.01   # 0.1 mm clearance on each face of socket
    PIN_EXTRA  = 0.05   # extra socket depth so key never bottoms out

    wt       = params['WALL_THICKNESS']
    inner_hw = (params['TRACK_WIDTH'] - 2.0 * wt) / 2.0   # inner channel half-width

    # ── Cross/dovetail profile dimensions ────────────────────────────────────
    NECK_HW      = wt * 0.50           # half-width at neck (1.5 mm for wt=3 mm)
    EAR_HW       = inner_hw * 0.70     # cross-arm half-width (≈3.15 mm)
    EAR_TOP      = wt * 0.35           # depth to arm top (≈1.05 mm)
    EAR_BOT      = wt * 0.70           # depth to arm bottom (≈2.10 mm)
    FLOOR_DIP    = wt                  # stem flush with outer floor face
    CHANNEL_RISE = 0.05                # 0.5 mm above inner floor (hidden in channel)

    # ── Collar boss dimensions (sits on inner floor face, into channel) ───────
    # Acts as assembly stop + covers junction gap.  Protrudes into channel
    # (wall-hidden side) so invisible when track is mounted.
    # ── Locking style ─────────────────────────────────────────────────────────
    # 'stud' : half-cylinder boss on collar top + M4 thread (current approach)
    # 'bore' : M4 clearance hole through collar along track axis, bolt + nut
    LOCK_STYLE = 'bore'

    COLLAR_HW  = inner_hw - 0.03      # slightly narrower than inner channel
    # bore needs taller collar: 4.2 mm bore + 0.5 mm min wall each side = 5.2 mm min → 6.5 mm
    COLLAR_H   = 0.40 if LOCK_STYLE == 'stud' else 0.85  # stud: 4 mm / bore: 8.5 mm (flat-top M4 hex AF=7.1mm + 0.7mm walls)
    COLLAR_LEN = 1.10                 # 11 mm per piece — wall at hex trap = COLLAR_HALF−CB_DEPTH = 5.5−3.5 = 2.0 mm (4 perimeters, reliably printed)
    POST_R     = 0.175                # 1.75 mm radius — M4 nominal 2.0 mm, −0.25 mm for FDM tolerance
    POST_H     = 0.50                 # 5 mm above collar top (enough for M4x0.7 nut engagement)

    # ── Orientation ──────────────────────────────────────────────────────────
    detect_sk = root.sketches.add(cut_plane)
    detect_tr = detect_sk.transform.copy()
    detect_sk.isLightBulbOn = False
    _ays = 1.0 if detect_tr.getCell(2, 1) >= 0.0 else -1.0

    # ── Find adjacent bodies ──────────────────────────────────────────────────
    adjacent   = find_bodies_at_cut(root, cut_plane)
    cut_geom   = cut_plane.geometry
    cut_origin = cut_geom.origin

    # Keep face alongside body — used for junction-face collar sketching below
    track_pairs  = [(b, f) for b, f in adjacent if b.name.startswith('Track_')]
    track_bodies = [b for b, f in track_pairs]
    if not track_bodies:
        return False

    # ── Guard: skip if sockets already created at this junction ──────────────
    try:
        for i in range(root.sketches.count):
            if root.sketches.item(i).name == f'Socket_{joint_num}_0':
                return True
    except:
        pass

    # ── Inner floor world position ────────────────────────────────────────────
    # The track path is drawn on the OUTER floor face (viewer-facing side).
    # setByDistanceOnPath places cut_origin at the outer floor face.
    # Inner floor = outer floor + wall_thickness inward toward channel.
    # Using cut_origin + wt*_iyw is robust: cut_origin is always exact, and
    # _iyw is the inward direction from detect_sk — no bbox dependency.
    _iyw = adsk.core.Vector3D.create(
        _ays * detect_tr.getCell(0, 1),
        _ays * detect_tr.getCell(1, 1),
        _ays * detect_tr.getCell(2, 1),
    )
    _iyw.normalize()

    floor_w = adsk.core.Point3D.create(
        cut_origin.x + _iyw.x * wt,
        cut_origin.y + _iyw.y * wt,
        cut_origin.z + _iyw.z * wt,
    )

    # ── Shared profile builder ────────────────────────────────────────────────
    def _key_profile(sk_name, neck, ear, ear_top, ear_bot, floor_d,
                     channel_rise=0.0):
        """Build 8-vertex H profile on cut_plane; return (sketch, profile).

        The centre stem (floor_d) is intentionally omitted — the profile stops
        at ear_bot depth so no hole is punched through the outer floor face.
        """
        sk = root.sketches.add(cut_plane)
        sk.name = sk_name
        sk_inv = sk.transform.copy()
        sk_inv.invert()

        fp = floor_w.copy()
        fp.transformBy(sk_inv)
        fx, fy = fp.x, fp.y

        _ch = adsk.core.Point3D.create(
            floor_w.x + 0.5 * _iyw.x,
            floor_w.y + 0.5 * _iyw.y,
            floor_w.z + 0.5 * _iyw.z,
        )
        _ch.transformBy(sk_inv)
        inward = 1.0 if (_ch.y - fy) >= 0.0 else -1.0

        def _fld(d):
            return fy - inward * d

        top_y = fy + inward * channel_rise

        # 8-vertex H/I-beam: neck above floor, two ears into floor, no centre
        # stem — outer floor face stays solid.
        verts = [
            (-neck,  top_y),
            ( neck,  top_y),
            ( ear,   _fld(ear_top)),
            ( ear,   _fld(ear_bot)),
            ( neck,  _fld(ear_bot)),   # inner-right of ear (was stem top-right)
            (-neck,  _fld(ear_bot)),   # inner-left of ear  (was stem top-left)
            (-ear,   _fld(ear_bot)),
            (-ear,   _fld(ear_top)),
        ]

        L = sk.sketchCurves.sketchLines
        for i in range(len(verts)):
            ax, ay = verts[i]
            bx, by = verts[(i + 1) % len(verts)]
            L.addByTwoPoints(adsk.core.Point3D.create(ax, ay, 0),
                             adsk.core.Point3D.create(bx, by, 0))

        # Pick profile nearest centre of cross-arm zone
        tgt_x = fx
        tgt_y = _fld((ear_top + ear_bot) / 2.0)
        best_prof, best_d2 = None, 1e18
        for i in range(sk.profiles.count):
            p  = sk.profiles.item(i)
            bb = p.boundingBox
            mx = (bb.minPoint.x + bb.maxPoint.x) / 2.0
            my = (bb.minPoint.y + bb.maxPoint.y) / 2.0
            d2 = (mx - tgt_x) ** 2 + (my - tgt_y) ** 2
            if d2 < best_d2:
                best_d2   = d2
                best_prof = p
        sk.isLightBulbOn = False
        return sk, best_prof

    success = False
    extrudes = root.features.extrudeFeatures
    cut_normal_v = cut_geom.normal
    cut_normal_v.normalize()

    # ── Step 1: Symmetric collar boss (unsplit) ───────────────────────────────
    # Build ONE body straddling the cut plane.  Do NOT split yet — the full
    # cylinder will be joined in before we split, so splitBodyFeatures sees a
    # slab (guaranteed non-degenerate intersection) rather than a bare cylinder
    # whose axis lies in the cut plane (which causes SPLIT_TARGET_TOOL_NOT_INTERSECT).
    cut_normal = cut_geom.normal.copy()
    cut_normal.normalize()

    iy = _iyw
    cn = cut_normal
    CHAMFER_D = 0.05   # 0.5 mm lead-in chamfer on top edge of stud

    boss_sk   = None
    boss_body = None
    boss_halves = []
    try:
        boss_sk = root.sketches.add(cut_plane)
        boss_sk.name = f'RetainBoss_{joint_num}'
        boss_inv = boss_sk.transform.copy()
        boss_inv.invert()

        fp_b = floor_w.copy()
        fp_b.transformBy(boss_inv)
        fy_b = fp_b.y

        _ch_b = adsk.core.Point3D.create(
            floor_w.x + 0.5 * _iyw.x,
            floor_w.y + 0.5 * _iyw.y,
            floor_w.z + 0.5 * _iyw.z,
        )
        _ch_b.transformBy(boss_inv)
        inward_b = 1.0 if (_ch_b.y - fy_b) >= 0.0 else -1.0

        boss_pts = [
            (-COLLAR_HW, fy_b),
            ( COLLAR_HW, fy_b),
            ( COLLAR_HW, fy_b + inward_b * COLLAR_H),
            (-COLLAR_HW, fy_b + inward_b * COLLAR_H),
        ]
        L = boss_sk.sketchCurves.sketchLines
        for i in range(4):
            a, b_pt = boss_pts[i], boss_pts[(i + 1) % 4]
            L.addByTwoPoints(
                adsk.core.Point3D.create(a[0], a[1], 0),
                adsk.core.Point3D.create(b_pt[0], b_pt[1], 0),
            )
        boss_sk.isLightBulbOn = False

        if boss_sk.profiles.count > 0:
            ei = extrudes.createInput(
                boss_sk.profiles.item(0),
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
            )
            ei.setSymmetricExtent(
                adsk.core.ValueInput.createByReal(COLLAR_LEN), True)
            boss_feat = extrudes.add(ei)
            if boss_feat.bodies.count > 0:
                boss_body = boss_feat.bodies.item(0)

    except Exception as e:
        if boss_sk is not None:
            try: boss_sk.isLightBulbOn = False
            except Exception: pass
        if ui:
            ui.messageBox(f'RetainBoss create failed (jct {joint_num}):\n'
                          f'{e}\n{traceback.format_exc()}')

    # ── Step 2: Full cylinder on collar top → thread → chamfer → join into boss ──
    # Only when LOCK_STYLE == 'stud'.  For 'bore', the collar splits as a plain
    # slab and the bore is cut after the halves are joined to track bodies.
    if boss_body is not None and LOCK_STYLE == 'stud':
        try:
            target_h = wt + COLLAR_H
            collar_top_face = None
            best_f, best_e = None, 1e9
            for face in boss_body.faces:
                try:
                    g = face.geometry
                    if not isinstance(g, adsk.core.Plane):
                        continue
                    dot_n = abs(g.normal.x*iy.x + g.normal.y*iy.y + g.normal.z*iy.z)
                    if dot_n < 0.95:
                        continue
                    pt = face.pointOnFace
                    h = ((pt.x - cut_origin.x)*iy.x +
                         (pt.y - cut_origin.y)*iy.y +
                         (pt.z - cut_origin.z)*iy.z)
                    e = abs(h - target_h)
                    if e < best_e:
                        best_e = e; best_f = face
                except Exception:
                    continue
            if best_f is not None and best_e < 0.05:
                collar_top_face = best_f

            if collar_top_face is None:
                if ui:
                    ui.messageBox(f'HalfStud jct {joint_num}: collar top face not found '
                                  f'(target_h={target_h:.3f} cm) — skipping stud')
            else:
                # Full circle at collar top centre (world → sketch)
                ct_w = adsk.core.Point3D.create(
                    floor_w.x + iy.x * COLLAR_H,
                    floor_w.y + iy.y * COLLAR_H,
                    floor_w.z + iy.z * COLLAR_H,
                )
                stud_sk = root.sketches.add(collar_top_face)
                stud_sk.name = f'HalfStud_{joint_num}'
                stud_sk.isLightBulbOn = False
                sk_inv = stud_sk.transform.copy(); sk_inv.invert()
                ct_pt = ct_w.copy(); ct_pt.transformBy(sk_inv)
                stud_sk.sketchCurves.sketchCircles.addByCenterRadius(
                    adsk.core.Point3D.create(ct_pt.x, ct_pt.y, 0), POST_R)

                if stud_sk.profiles.count == 0:
                    raise ValueError('stud circle sketch: no profile')

                # Pick the disk profile (smallest bounding box = the circle interior).
                # The surrounding ring has a bounding box as large as the whole
                # collar face; the disk is 2*POST_R × 2*POST_R.  Both share the
                # same bbox centre so a centre-proximity test can't distinguish
                # them — compare bbox area instead.
                cir_prof = stud_sk.profiles.item(0)
                best_area = 1e9
                for pi in range(stud_sk.profiles.count):
                    p = stud_sk.profiles.item(pi)
                    bb = p.boundingBox
                    w = bb.maxPoint.x - bb.minPoint.x
                    h = bb.maxPoint.y - bb.minPoint.y
                    area = w * h
                    if area < best_area:
                        best_area = area; cir_prof = p

                # Extrude full cylinder outward (+_iyw direction).
                # Compute is_pos from the actual face normal — don't assume True,
                # because Fusion may orient the face normal downward (into the slab)
                # on some track geometries.
                fn_dot_iy = (collar_top_face.geometry.normal.x * iy.x +
                             collar_top_face.geometry.normal.y * iy.y +
                             collar_top_face.geometry.normal.z * iy.z)
                is_pos_cyl = (fn_dot_iy >= 0)   # True → normal points in +_iyw → extrude outward
                ei_c = extrudes.createInput(
                    cir_prof,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                ei_c.setDistanceExtent(
                    is_pos_cyl, adsk.core.ValueInput.createByReal(POST_H))
                cyl_feat = extrudes.add(ei_c)
                if cyl_feat.bodies.count == 0:
                    raise ValueError('cylinder extrude produced no body')
                cyl_body = cyl_feat.bodies.item(0)

                # Find cylindrical face (clean cylinder — no modifications yet)
                cyl_face = None
                for face in cyl_body.faces:
                    if isinstance(face.geometry, adsk.core.Cylinder):
                        cyl_face = face; break

                base_h_exp = wt + COLLAR_H        # height of cylinder base
                top_h_exp  = wt + COLLAR_H + POST_H  # height of cylinder top

                # ── Fillet at base (before any other ops) ─────────────────────
                # Reduces stress concentration at the break point seen in tests.
                # Applied to the clean cylinder before chamfer/thread/join.
                # FILLET_R = 0.8 mm — large enough to matter, small enough to
                # keep the stud clear of the collar edge.
                FILLET_R = 0.08   # 0.8 mm
                try:
                    base_edges = adsk.core.ObjectCollection.create()
                    for edge in cyl_body.edges:
                        mid = edge.pointOnEdge
                        h = ((mid.x - cut_origin.x)*iy.x +
                             (mid.y - cut_origin.y)*iy.y +
                             (mid.z - cut_origin.z)*iy.z)
                        if abs(h - base_h_exp) < 0.02:
                            base_edges.add(edge)
                    if base_edges.count > 0:
                        fi = root.features.filletFeatures.createInput()
                        fi.addConstantRadiusEdgeSet(
                            base_edges,
                            adsk.core.ValueInput.createByReal(FILLET_R),
                            True)
                        root.features.filletFeatures.add(fi)
                except Exception as e_fi:
                    if ui:
                        ui.messageBox(f'Base fillet failed jct {joint_num}: {e_fi}\n'
                                      f'{traceback.format_exc()}')

                # ── Chamfer at top ─────────────────────────────────────────────
                # Lead-in so nut starts easily.  Search by height on clean body.
                try:
                    top_edges = adsk.core.ObjectCollection.create()
                    for edge in cyl_body.edges:
                        mid = edge.pointOnEdge
                        h = ((mid.x - cut_origin.x)*iy.x +
                             (mid.y - cut_origin.y)*iy.y +
                             (mid.z - cut_origin.z)*iy.z)
                        if abs(h - top_h_exp) < 0.02:
                            top_edges.add(edge)
                    if top_edges.count > 0:
                        ch2 = root.features.chamferFeatures.createInput2()
                        ch2.chamferEdgeSets.addEqualDistanceChamferEdgeSet(
                            top_edges,
                            adsk.core.ValueInput.createByReal(CHAMFER_D),
                            False)
                        root.features.chamferFeatures.add(ch2)
                except Exception as e_ch:
                    if ui:
                        ui.messageBox(f'Chamfer failed jct {joint_num}: {e_ch}\n'
                                      f'{traceback.format_exc()}')

                # ── Modeled thread on FULL cylinder before join/split ──────────
                # isModeled=True works on a full 360° face.  Applied here while
                # cyl_body is still standalone.  The join + split that follow
                # carry the thread geometry onto each D-shape half.
                # Re-find cyl_face after fillet+chamfer (those ops invalidate it).
                cyl_face = None
                for face in cyl_body.faces:
                    if isinstance(face.geometry, adsk.core.Cylinder):
                        cyl_face = face; break
                try:
                    if cyl_face is not None:
                        t_info = adsk.fusion.ThreadInfo.create(
                            False, False,
                            'ISO Metric Profile', 'M4x0.7', '6g', True)
                        t_in = root.features.threadFeatures.createInput(cyl_face, t_info)
                        t_in.isModeled    = True
                        t_in.isFullLength = True
                        root.features.threadFeatures.add(t_in)
                except Exception as e_t:
                    if ui:
                        ui.messageBox(f'Thread failed jct {joint_num}: {e_t}\n'
                                      f'{traceback.format_exc()}')

                # ── Offset thread faces inward for FDM clearance ───────────────
                # Uniformly shrinks all thread surfaces (helix ridges + cylinder)
                # so the nut engages without excessive force after printing.
                # Applied AFTER thread, BEFORE join — cyl_body still standalone.
                THREAD_OFFSET = -0.015   # −0.15 mm inward → ~0.3 mm diameter relief
                try:
                    off_faces = [cyl_body.faces.item(i)
                                 for i in range(cyl_body.faces.count)]
                    off_in = root.features.offsetFacesFeatures.createInput(
                        off_faces,
                        adsk.core.ValueInput.createByReal(THREAD_OFFSET))
                    root.features.offsetFacesFeatures.add(off_in)
                except Exception as e_off:
                    if ui:
                        ui.messageBox(f'Thread offset failed jct {joint_num}: {e_off}\n'
                                      f'{traceback.format_exc()}')

                # Join cylinder into boss_body → composite (root-to-root, always safe)
                tools_oc = adsk.core.ObjectCollection.create()
                tools_oc.add(cyl_body)
                ci = root.features.combineFeatures.createInput(boss_body, tools_oc)
                ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                root.features.combineFeatures.add(ci)
                # boss_body is now the composite: collar slab + threaded full cylinder

        except Exception as e:
            if ui:
                ui.messageBox(f'HalfStud cylinder/join failed (jct {joint_num}):\n'
                              f'{e}\n{traceback.format_exc()}')

    # ── Step 3: Build angled split plane ──────────────────────────────────────
    # The split plane is tilted ~8° from cut_plane around the track-width axis
    # (tw_dir = cut_normal × iy).  Both the collar boss AND each track body are
    # split at this plane so the entire cross-section has the same scarf face.
    # This makes the channel-side edge the first contact point when the bolt is
    # tightened, self-sealing the visible gap regardless of FDM tolerances.
    SPLIT_ANGLE = math.radians(8)
    ang_cp = None
    try:
        # Track-width direction = cut_normal × iy (normalised)
        tw_x = cut_normal.y*iy.z - cut_normal.z*iy.y
        tw_y = cut_normal.z*iy.x - cut_normal.x*iy.z
        tw_z = cut_normal.x*iy.y - cut_normal.y*iy.x
        tw_len = math.sqrt(tw_x*tw_x + tw_y*tw_y + tw_z*tw_z)
        if tw_len > 1e-6:
            tw_x /= tw_len; tw_y /= tw_len; tw_z /= tw_len

        # Sketch on cut_plane with a construction line along tw_dir through the
        # origin.  setByAngle accepts SketchLine; setByThreePoints requires entity
        # objects, not raw Point3D — this avoids "Environment not supported".
        split_sk = root.sketches.add(cut_plane)
        split_sk.isLightBulbOn = False
        sk_tr  = split_sk.transform
        sk_xw  = (sk_tr.getCell(0,0), sk_tr.getCell(1,0), sk_tr.getCell(2,0))
        sk_yw  = (sk_tr.getCell(0,1), sk_tr.getCell(1,1), sk_tr.getCell(2,1))
        u = tw_x*sk_xw[0] + tw_y*sk_xw[1] + tw_z*sk_xw[2]
        v = tw_x*sk_yw[0] + tw_y*sk_yw[1] + tw_z*sk_yw[2]
        SL = 5.0
        sl_a = adsk.core.Point3D.create(-u*SL, -v*SL, 0)
        sl_b = adsk.core.Point3D.create( u*SL,  v*SL, 0)
        split_line = split_sk.sketchCurves.sketchLines.addByTwoPoints(sl_a, sl_b)
        split_line.isConstruction = True

        ang_cp_in = root.constructionPlanes.createInput()
        ang_cp_in.setByAngle(split_line,
                             adsk.core.ValueInput.createByReal(SPLIT_ANGLE),
                             cut_plane)
        ang_cp = root.constructionPlanes.add(ang_cp_in)
        ang_cp.isLightBulbOn = False
    except Exception as e:
        if ui:
            ui.messageBox(f'Angled split plane failed (jct {joint_num}):\n'
                          f'{e}\n{traceback.format_exc()}')

    # (Step 3b removed — bounded patch approach was unreliable; track body trim
    #  now uses ang_cp directly in Step 4, keeping the largest correct-side body.)

    # ── Step 3d: Split collar boss at angled plane ────────────────────────────
    if boss_body is not None and ang_cp is not None:
        try:
            split_feats = root.features.splitBodyFeatures
            split_input = split_feats.createInput(boss_body, ang_cp, True)
            split_feat  = split_feats.add(split_input)
            boss_halves = [split_feat.bodies.item(i)
                           for i in range(split_feat.bodies.count)]
        except Exception as e:
            if ui:
                ui.messageBox(f'Boss split failed (jct {joint_num}):\n'
                              f'{e}\n{traceback.format_exc()}')

    # ── Step 3e: Wedge-transfer scarf trim on track bodies ────────────────────
    # ang_cp (tilted 8° toward -cut_normal at height h) only intersects the
    # -cut_normal track body.  Trim that body; the resulting thin wedge is
    # joined to the +cut_normal body so BOTH bodies end up with the ang_cp
    # junction face — a true full-cross-section scarf joint.
    if ang_cp is not None and len(track_pairs) == 2:
        try:
            idx_pos, idx_neg = None, None
            for idx in range(2):
                com = track_pairs[idx][0].physicalProperties.centerOfMass
                dot = ((com.x - cut_origin.x)*cut_normal.x +
                       (com.y - cut_origin.y)*cut_normal.y +
                       (com.z - cut_origin.z)*cut_normal.z)
                if dot >= 0: idx_pos = idx
                else:        idx_neg = idx

            if idx_pos is not None and idx_neg is not None:
                neg_body, neg_jf = track_pairs[idx_neg]
                pos_body, _      = track_pairs[idx_pos]

                # Split the -cut_normal body
                ts_in = root.features.splitBodyFeatures.createInput(
                            neg_body, ang_cp, True)
                ts_f  = root.features.splitBodyFeatures.add(ts_in)
                parts = [ts_f.bodies.item(i) for i in range(ts_f.bodies.count)]

                # Largest -cut_normal piece = new main body; smallest other piece = wedge
                main_neg = None; main_vol = -1.0
                wedge    = None; wedge_vol = float('inf')
                for p in parts:
                    com_p = p.physicalProperties.centerOfMass
                    dot_p = ((com_p.x - cut_origin.x)*cut_normal.x +
                             (com_p.y - cut_origin.y)*cut_normal.y +
                             (com_p.z - cut_origin.z)*cut_normal.z)
                    vol = p.physicalProperties.volume
                    if dot_p < 0:                          # correct side for neg body
                        if vol > main_vol: main_vol = vol; main_neg = p
                    else:                                  # the wedge to transfer
                        if vol < wedge_vol: wedge_vol = vol; wedge = p
                for p in parts:                            # discard any extras
                    if p is not main_neg and p is not wedge:
                        try: p.deleteMe()
                        except: pass

                if main_neg is not None:
                    track_pairs[idx_neg]  = (main_neg, neg_jf)
                    track_bodies[idx_neg] = main_neg

                # Join wedge → +cut_normal body (gives it the ang_cp face)
                if wedge is not None:
                    woc = adsk.core.ObjectCollection.create()
                    woc.add(wedge)
                    ci_w = root.features.combineFeatures.createInput(pos_body, woc)
                    ci_w.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                    root.features.combineFeatures.add(ci_w)

        except Exception as e_scarf:
            if ui:
                ui.messageBox(f'Track scarf failed (jct {joint_num}):\n'
                              f'{e_scarf}\n{traceback.format_exc()}')

    # ── Step 4: Match each half to its track body and join ────────────────────
    # Boss half CoMs are ±COLLAR_LEN/2 from cut plane → sign unambiguous.
    # Track body side determined from junction face outward normal.
    used_halves = set()
    for tp_idx, (body, jct_face) in enumerate(track_pairs):
        try:
            if not boss_halves or jct_face is None:
                continue

            ok_n, fn = jct_face.evaluator.getNormalAtPoint(jct_face.pointOnFace)
            if not ok_n:
                fn = jct_face.geometry.normal
            # fn is outward from body → body occupies the OPPOSITE side from fn
            fn_dot = (fn.x * cut_normal.x +
                      fn.y * cut_normal.y +
                      fn.z * cut_normal.z)
            track_side = -1 if fn_dot > 0 else +1

            for i, half in enumerate(boss_halves):
                if i in used_halves:
                    continue
                com = half.physicalProperties.centerOfMass
                half_dot = ((com.x - cut_origin.x) * cut_normal.x +
                            (com.y - cut_origin.y) * cut_normal.y +
                            (com.z - cut_origin.z) * cut_normal.z)
                half_side = +1 if half_dot >= 0 else -1
                if half_side == track_side:
                    # Fillet all external collar edges before joining.
                    # Exclude any edge that touches the junction face (d≈0 from
                    # cut_origin along cut_normal) — both edges ON the junction face
                    # and edges whose vertices lie on it.  This prevents fillets from
                    # wrapping around the junction corners and creating gaps at the seam.
                    FILLET_R = 0.08   # 0.8 mm
                    try:
                        fillet_edges = adsk.core.ObjectCollection.create()
                        for ei in range(half.edges.count):
                            edge = half.edges.item(ei)
                            on_jct = False
                            # Check adjacent faces
                            for fi in range(edge.faces.count):
                                f = edge.faces.item(fi)
                                if not isinstance(f.geometry, adsk.core.Plane):
                                    continue
                                fn_e = f.geometry.normal
                                nd_e = abs(fn_e.x*cut_normal.x +
                                           fn_e.y*cut_normal.y +
                                           fn_e.z*cut_normal.z)
                                if nd_e < 0.9:
                                    continue
                                fp_e = f.pointOnFace
                                d_e  = abs((fp_e.x - cut_origin.x)*cut_normal.x +
                                           (fp_e.y - cut_origin.y)*cut_normal.y +
                                           (fp_e.z - cut_origin.z)*cut_normal.z)
                                if d_e < 0.05:
                                    on_jct = True
                                    break
                            if on_jct:
                                continue
                            # Also skip edges whose endpoints touch the junction plane
                            # (prevents fillet propagation to junction-adjacent corners)
                            for vi in range(edge.vertices.count):
                                gv = edge.vertices.item(vi).geometry
                                d_v = abs((gv.x - cut_origin.x)*cut_normal.x +
                                          (gv.y - cut_origin.y)*cut_normal.y +
                                          (gv.z - cut_origin.z)*cut_normal.z)
                                if d_v < 0.05:
                                    on_jct = True
                                    break
                            if not on_jct:
                                fillet_edges.add(edge)
                        if fillet_edges.count > 0:
                            fi_in = root.features.filletFeatures.createInput()
                            fi_in.addConstantRadiusEdgeSet(
                                fillet_edges,
                                adsk.core.ValueInput.createByReal(FILLET_R),
                                True)
                            root.features.filletFeatures.add(fi_in)
                    except Exception as e_fil:
                        pass   # fillet is cosmetic — don't block the join

                    tools_oc = adsk.core.ObjectCollection.create()
                    tools_oc.add(half)
                    ci = root.features.combineFeatures.createInput(body, tools_oc)
                    ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                    root.features.combineFeatures.add(ci)
                    used_halves.add(i)
                    break

        except Exception as e:
            if ui:
                ui.messageBox(f'RetainBoss join failed (jct {joint_num}, {body.name}):\n'
                              f'{e}\n{traceback.format_exc()}')

    # ── Step 4b: Axial bore through collar (LOCK_STYLE == 'bore') ────────────
    # Both track bodies already have their collar halves joined.  One sketch on
    # cut_plane, symmetric extrude → participantBodies cuts both simultaneously,
    # giving each piece an 8 mm blind bore that together form a 16 mm tunnel.
    # Insert M4 bolt + nut from the ends of the assembled collar.
    if LOCK_STYLE == 'bore' and track_bodies:
        BORE_R_AX  = 0.21   # 2.1 mm radius = 4.2 mm (M4 clearance)
        # Hex nut trap — body 0 (nut side)
        # M4 nut AF=7.0 mm + 0.2 mm tolerance → AF_hex=7.2 mm
        # circumradius = (AF/2) / cos(30°)
        HEX_AF_CM  = 0.71                              # 7.1 mm across flats (0.1 mm total AF gap vs M4 nut 7.0 mm)
        HEX_CR     = (HEX_AF_CM / 2.0) / math.cos(math.pi / 6)   # ≈ 0.4157 cm
        CB_DEPTH   = 0.35   # 3.5 mm (M4 nut height 3.2 mm + 0.3 mm)
        try:
            bore_sk = root.sketches.add(cut_plane)
            bore_sk.name  = f'CollarBore_{joint_num}'
            bore_sk.isLightBulbOn = False
            bore_inv = bore_sk.transform.copy()
            bore_inv.invert()
            # Centre at collar mid-height in _iyw direction
            bore_ctr_w = adsk.core.Point3D.create(
                floor_w.x + iy.x * COLLAR_H * 0.5,
                floor_w.y + iy.y * COLLAR_H * 0.5,
                floor_w.z + iy.z * COLLAR_H * 0.5,
            )
            bc = bore_ctr_w.copy()
            bc.transformBy(bore_inv)
            ctr_2d = adsk.core.Point3D.create(bc.x, bc.y, 0)

            # Through bore (M4 clearance) — cuts both track bodies simultaneously
            bore_sk.sketchCurves.sketchCircles.addByCenterRadius(ctr_2d, BORE_R_AX)
            if bore_sk.profiles.count > 0:
                ei_b = extrudes.createInput(
                    bore_sk.profiles.item(0),
                    adsk.fusion.FeatureOperations.CutFeatureOperation)
                ei_b.setSymmetricExtent(
                    adsk.core.ValueInput.createByReal(COLLAR_LEN), True)
                ei_b.participantBodies = list(track_bodies)
                extrudes.add(ei_b)

            # Hex nut trap at each collar OUTER END FACE (captive nut design).
            # setSymmetricExtent(COLLAR_LEN, isFullLength=True) → each half extends
            # COLLAR_LEN/2 from the cut plane, so end face is at COLLAR_LEN/2.
            COLLAR_HALF = COLLAR_LEN / 2.0
            for body_idx2, body in enumerate(track_bodies):
                try:
                    com_b = body.physicalProperties.centerOfMass
                    com_dot_b = ((com_b.x - cut_origin.x)*cut_normal.x +
                                 (com_b.y - cut_origin.y)*cut_normal.y +
                                 (com_b.z - cut_origin.z)*cut_normal.z)
                    body_sign = +1 if com_dot_b >= 0 else -1

                    # Use a construction plane at exactly ±COLLAR_HALF from cut_plane.
                    # No face search needed — we know the collar ends there.
                    cp_in = root.constructionPlanes.createInput()
                    cp_in.setByOffset(
                        cut_plane,
                        adsk.core.ValueInput.createByReal(body_sign * COLLAR_HALF))
                    end_cp = root.constructionPlanes.add(cp_in)
                    end_cp.isLightBulbOn = False

                    trap_sk = root.sketches.add(end_cp)
                    trap_sk.name = f'CollarTrap_{joint_num}_{body_idx2}'
                    trap_sk.isLightBulbOn = False

                    # Transform bore centre into sketch space
                    trap_inv = trap_sk.transform.copy()
                    trap_inv.invert()
                    bc_t = bore_ctr_w.copy()
                    bc_t.transformBy(trap_inv)
                    ctr_t = adsk.core.Point3D.create(bc_t.x, bc_t.y, 0)

                    # Hex nut trap — flat-top (vertex at π/6) so nut cannot rotate
                    hex_pts_t = [
                        adsk.core.Point3D.create(
                            ctr_t.x + HEX_CR * math.cos(i * math.pi / 3),
                            ctr_t.y + HEX_CR * math.sin(i * math.pi / 3),
                            0)
                        for i in range(6)
                    ]
                    sk_lines_t = trap_sk.sketchCurves.sketchLines
                    for i in range(6):
                        sk_lines_t.addByTwoPoints(hex_pts_t[i], hex_pts_t[(i + 1) % 6])

                    # Largest profile = hex interior (construction plane has no face boundary)
                    if trap_sk.profiles.count == 0:
                        if ui:
                            ui.messageBox(f'HexTrap jct {joint_num} body {body_idx2}: no profile')
                        continue
                    trap_prof = trap_sk.profiles.item(0)
                    best_a = 0
                    for pi in range(trap_sk.profiles.count):
                        p  = trap_sk.profiles.item(pi)
                        bb = p.boundingBox
                        a  = (bb.maxPoint.x - bb.minPoint.x) * (bb.maxPoint.y - bb.minPoint.y)
                        if a > best_a:
                            best_a = a; trap_prof = p

                    # Sketch Z (col 2 of transform) vs inward direction → pick correct side
                    trap_tr = trap_sk.transform
                    sz_x = trap_tr.getCell(0, 2)
                    sz_y = trap_tr.getCell(1, 2)
                    sz_z = trap_tr.getCell(2, 2)
                    in_x = -body_sign * cut_normal.x
                    in_y = -body_sign * cut_normal.y
                    in_z = -body_sign * cut_normal.z
                    is_pos_inward = (sz_x*in_x + sz_y*in_y + sz_z*in_z) > 0

                    ei_t = extrudes.createInput(
                        trap_prof,
                        adsk.fusion.FeatureOperations.CutFeatureOperation)
                    ei_t.setDistanceExtent(
                        is_pos_inward, adsk.core.ValueInput.createByReal(CB_DEPTH))
                    ei_t.participantBodies = [body]
                    extrudes.add(ei_t)
                except Exception as e_cb:
                    if ui:
                        ui.messageBox(f'HexTrap failed jct {joint_num} body {body_idx2}: {e_cb}\n'
                                      f'{traceback.format_exc()}')

            # Anti-rotation alignment pin on the junction face.
            # Body 0: round boss protrudes toward body 1.
            # Body 1: matching socket (clearance fit) cut into junction face.
            # Pin placed at lower-right CORNER of the collar, away from the bore.
            # Clearance check: distance from bore centre = sqrt((HW*0.65)²+(H*0.25)²)
            #   ≈ sqrt(2.73²+2.13²) ≈ 3.46 mm > bore_r(2.1)+pin_r(0.75) = 2.85 mm ✓
            PIN_R  = 0.075  # 0.75 mm radius = 1.5 mm diameter
            PIN_CL = 0.025  # 0.25 mm socket radial clearance
            PIN_D  = 0.10   # 1.0 mm depth each side
            # Sketch X axis of bore sketch = track-width direction in world space
            sk_tr_b = bore_sk.transform
            sk_x_w  = adsk.core.Vector3D.create(
                sk_tr_b.getCell(0, 0),
                sk_tr_b.getCell(1, 0),
                sk_tr_b.getCell(2, 0))
            # Lower-right corner: +65 % of half-width laterally, −25 % of collar height
            pin_ofs_w = adsk.core.Point3D.create(
                bore_ctr_w.x + sk_x_w.x * COLLAR_HW * 0.65 - iy.x * COLLAR_H * 0.25,
                bore_ctr_w.y + sk_x_w.y * COLLAR_HW * 0.65 - iy.y * COLLAR_H * 0.25,
                bore_ctr_w.z + sk_x_w.z * COLLAR_HW * 0.65 - iy.z * COLLAR_H * 0.25,
            )
            for pin_idx, body in enumerate(track_bodies):
                try:
                    com_p = body.physicalProperties.centerOfMass
                    com_dot_p = ((com_p.x - cut_origin.x)*cut_normal.x +
                                 (com_p.y - cut_origin.y)*cut_normal.y +
                                 (com_p.z - cut_origin.z)*cut_normal.z)
                    body_sign = +1 if com_dot_p >= 0 else -1

                    # Sketch on ang_cp (the actual junction face after scarf trim).
                    # Using cut_plane would leave a gap equal to the tilt offset at
                    # the pin height; ang_cp projects pin_ofs_w correctly onto the
                    # real junction surface (Z=0 in sketch coords = on-plane).
                    pin_ref = ang_cp if ang_cp is not None else cut_plane
                    pin_sk = root.sketches.add(pin_ref)
                    pin_sk.name = f'CollarPin_{joint_num}_{pin_idx}'
                    pin_sk.isLightBulbOn = False
                    pin_inv = pin_sk.transform.copy()
                    pin_inv.invert()
                    po = pin_ofs_w.copy()
                    po.transformBy(pin_inv)
                    pin_ctr = adsk.core.Point3D.create(po.x, po.y, 0)

                    # Direction toward this body (sketch Z dotted with body direction)
                    pin_tr = pin_sk.transform
                    pz_x = pin_tr.getCell(0, 2)
                    pz_y = pin_tr.getCell(1, 2)
                    pz_z = pin_tr.getCell(2, 2)
                    is_pos_toward = (pz_x*(body_sign*cut_normal.x) +
                                     pz_y*(body_sign*cut_normal.y) +
                                     pz_z*(body_sign*cut_normal.z)) > 0

                    if pin_idx == 0:
                        # Boss: new body then join
                        pin_sk.sketchCurves.sketchCircles.addByCenterRadius(pin_ctr, PIN_R)
                        boss_ei = extrudes.createInput(
                            pin_sk.profiles.item(0),
                            adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                        boss_ei.setDistanceExtent(
                            is_pos_toward, adsk.core.ValueInput.createByReal(PIN_D))
                        boss_feat = extrudes.add(boss_ei)
                        boss_body = boss_feat.bodies.item(0)
                        tools_oc = adsk.core.ObjectCollection.create()
                        tools_oc.add(boss_body)
                        ci = root.features.combineFeatures.createInput(body, tools_oc)
                        ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                        root.features.combineFeatures.add(ci)
                    else:
                        # Socket: cut with clearance into body 1
                        pin_sk.sketchCurves.sketchCircles.addByCenterRadius(pin_ctr, PIN_R + PIN_CL)
                        sock_ei = extrudes.createInput(
                            pin_sk.profiles.item(0),
                            adsk.fusion.FeatureOperations.CutFeatureOperation)
                        sock_ei.setDistanceExtent(
                            is_pos_toward,
                            adsk.core.ValueInput.createByReal(PIN_D + 0.02))  # 0.2 mm extra depth
                        sock_ei.participantBodies = [body]
                        extrudes.add(sock_ei)
                except Exception as e_pin:
                    if ui:
                        ui.messageBox(f'AlignPin failed jct {joint_num} body {pin_idx}: {e_pin}\n'
                                      f'{traceback.format_exc()}')

        except Exception as e_bore:
            if ui:
                ui.messageBox(f'CollarBore failed (jct {joint_num}):\n'
                              f'{e_bore}\n{traceback.format_exc()}')

    # Phase 3: socket cuts + H-key — skipped in bore mode (bolt replaces H-key lock)
    if LOCK_STYLE != 'bore':
        for body_idx, body in enumerate(track_bodies):
            try:
                _, sock_prof = _key_profile(
                    f'Socket_{joint_num}_{body_idx}',
                    NECK_HW + HOLE_CL,
                    EAR_HW  + HOLE_CL,
                    EAR_TOP - HOLE_CL,
                    EAR_BOT + HOLE_CL,
                    FLOOR_DIP + HOLE_CL,
                    channel_rise=CHANNEL_RISE + HOLE_CL,
                )
                if sock_prof is not None:
                    ei = extrudes.createInput(
                        sock_prof,
                        adsk.fusion.FeatureOperations.CutFeatureOperation,
                    )
                    ei.setSymmetricExtent(
                        adsk.core.ValueInput.createByReal(PIN_DEPTH + PIN_EXTRA), True
                    )
                    ei.participantBodies = [body]
                    extrudes.add(ei)
                    success = True
            except Exception as e:
                if ui:
                    ui.messageBox(f'Socket cut failed (jct {joint_num}, body {body.name}):\n'
                                  f'{e}\n{traceback.format_exc()}')

    # ── H-key body — one per junction (stud mode only) ────────────────────────
    key_exists = any(b.name == f'Connector_Key_{joint_num}' for b in root.bRepBodies)
    if not key_exists and LOCK_STYLE != 'bore':
        try:
            _, key_prof = _key_profile(
                f'ConnectorKey_{joint_num}',
                NECK_HW, EAR_HW, EAR_TOP, EAR_BOT, FLOOR_DIP,
                channel_rise=CHANNEL_RISE,
            )
            if key_prof is not None:
                ei = extrudes.createInput(
                    key_prof,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
                )
                ei.setSymmetricExtent(
                    adsk.core.ValueInput.createByReal(PIN_DEPTH), True
                )
                feat = extrudes.add(ei)
                if feat.bodies.count > 0:
                    feat.bodies.item(0).name = f'Connector_Key_{joint_num}'
        except Exception as e:
            if ui:
                ui.messageBox(f'Connector_Key creation failed (jct {joint_num}):\n'
                              f'{e}\n{traceback.format_exc()}')

    return success


# =============================================================================
# EXTERNAL BRACKET
# =============================================================================

def create_ext_bracket(root, cut_plane, params, joint_num, open_side,
                       s_min_x, s_max_x, s_min_y, s_max_y, adjacent):
    """Create two external C-shaped corner clips that hook over the outer
    wall-floor corners at the junction.

    Each clip is a 6-point C-profile that wraps one corner:
      - outer arm  : goes up/down along the outer wall face (arm_h tall, ba thick)
      - base       : runs along the floor outer face (bb deep)
      - inner hook : short lip that hooks past the floor outer edge (hook_h tall)

    Cross-section (max_y — floor at s_min_y, opening at s_max_y):

      left clip                right clip
      p0──────p5               p0──────p5
      │        │               │        │
      │ arm    │p4─p3          p3─p4    │ arm
      │        │    │ hook      │    │  │
      p1──────p2    │          │    p2──p1
         base       ↑ hook_h       base
    """
    try:
        key_depth = params['KEY_DEPTH']
        cl        = params['KEY_CLEARANCE']
        ct        = params.get('CLIP_THICKNESS', DEFAULT_CLIP_THICKNESS)

        ba     = ct    # arm / clip thickness (1 mm)
        arm_h  = 0.40  # outer arm height along wall face (4 mm)
        bb     = 0.25  # base depth along floor outer face (2.5 mm)
        hook_h = 0.15  # inner hook height above/below floor outer face (1.5 mm)
        hook_w = ba    # inner hook width (same as arm, 1 mm)

        ext_sketch = root.sketches.add(cut_plane)
        ext_sketch.name = f'ExtBracket_{joint_num}'

        # Each entry in corner_polys is a list of 6 (x, y) points tracing one C-clip.
        # Clips are placed at the OPENING side wall tips (the free ends of the walls),
        # NOT at the floor corners.  The "C" wraps around the wall tip:
        #   outer arm  → along outer wall face, arm_h deep into the track
        #   base       → past the wall tip (bb into open space)
        #   inner hook → short lip on inner wall face, hook_h into the track
        if open_side == 'max_y':
            # Opening at s_max_y (top); wall tips at (s_min_x, s_max_y) and (s_max_x, s_max_y).
            corner_polys = [
                [  # left — C opens right (toward track interior)
                    (s_min_x - cl - ba,         s_max_y - arm_h),   # p0 outer arm bottom
                    (s_min_x - cl - ba,         s_max_y + bb),      # p1 base top (past tip)
                    (s_min_x - cl + hook_w,     s_max_y + bb),      # p2 base inner top
                    (s_min_x - cl + hook_w,     s_max_y - hook_h),  # p3 hook bottom
                    (s_min_x - cl,              s_max_y - hook_h),  # p4 step
                    (s_min_x - cl,              s_max_y - arm_h),   # p5 arm inner face bottom
                ],
                [  # right — C opens left
                    (s_max_x + cl + ba,         s_max_y - arm_h),
                    (s_max_x + cl + ba,         s_max_y + bb),
                    (s_max_x + cl - hook_w,     s_max_y + bb),
                    (s_max_x + cl - hook_w,     s_max_y - hook_h),
                    (s_max_x + cl,              s_max_y - hook_h),
                    (s_max_x + cl,              s_max_y - arm_h),
                ],
            ]
        elif open_side == 'min_y':
            # Opening at s_min_y (bottom); wall tips at (s_min_x, s_min_y) and (s_max_x, s_min_y).
            corner_polys = [
                [  # left — C opens right
                    (s_min_x - cl - ba,         s_min_y + arm_h),   # p0 outer arm top
                    (s_min_x - cl - ba,         s_min_y - bb),      # p1 base bottom (past tip)
                    (s_min_x - cl + hook_w,     s_min_y - bb),      # p2 base inner bottom
                    (s_min_x - cl + hook_w,     s_min_y + hook_h),  # p3 hook top
                    (s_min_x - cl,              s_min_y + hook_h),  # p4 step
                    (s_min_x - cl,              s_min_y + arm_h),   # p5 arm inner face top
                ],
                [  # right — C opens left
                    (s_max_x + cl + ba,         s_min_y + arm_h),
                    (s_max_x + cl + ba,         s_min_y - bb),
                    (s_max_x + cl - hook_w,     s_min_y - bb),
                    (s_max_x + cl - hook_w,     s_min_y + hook_h),
                    (s_max_x + cl,              s_min_y + hook_h),
                    (s_max_x + cl,              s_min_y + arm_h),
                ],
            ]
        elif open_side == 'max_x':
            # Opening at s_max_x (right); wall tips at (s_max_x, s_min_y) and (s_max_x, s_max_y).
            corner_polys = [
                [  # bottom — C opens upward (toward track)
                    (s_max_x - arm_h,           s_min_y - cl - ba),
                    (s_max_x + bb,              s_min_y - cl - ba),
                    (s_max_x + bb,              s_min_y - cl + hook_w),
                    (s_max_x - hook_h,          s_min_y - cl + hook_w),
                    (s_max_x - hook_h,          s_min_y - cl),
                    (s_max_x - arm_h,           s_min_y - cl),
                ],
                [  # top — C opens downward
                    (s_max_x - arm_h,           s_max_y + cl + ba),
                    (s_max_x + bb,              s_max_y + cl + ba),
                    (s_max_x + bb,              s_max_y + cl - hook_w),
                    (s_max_x - hook_h,          s_max_y + cl - hook_w),
                    (s_max_x - hook_h,          s_max_y + cl),
                    (s_max_x - arm_h,           s_max_y + cl),
                ],
            ]
        elif open_side == 'min_x':
            # Opening at s_min_x (left); wall tips at (s_min_x, s_min_y) and (s_min_x, s_max_y).
            corner_polys = [
                [  # bottom — C opens upward
                    (s_min_x + arm_h,           s_min_y - cl - ba),
                    (s_min_x - bb,              s_min_y - cl - ba),
                    (s_min_x - bb,              s_min_y - cl + hook_w),
                    (s_min_x + hook_h,          s_min_y - cl + hook_w),
                    (s_min_x + hook_h,          s_min_y - cl),
                    (s_min_x + arm_h,           s_min_y - cl),
                ],
                [  # top — C opens downward
                    (s_min_x + arm_h,           s_max_y + cl + ba),
                    (s_min_x - bb,              s_max_y + cl + ba),
                    (s_min_x - bb,              s_max_y + cl - hook_w),
                    (s_min_x + hook_h,          s_max_y + cl - hook_w),
                    (s_min_x + hook_h,          s_max_y + cl),
                    (s_min_x + arm_h,           s_max_y + cl),
                ],
            ]
        else:
            ext_sketch.isLightBulbOn = False
            return None

        lines = ext_sketch.sketchCurves.sketchLines
        for poly in corner_polys:
            n = len(poly)
            for i in range(n):
                a, b = poly[i], poly[(i + 1) % n]
                lines.addByTwoPoints(
                    adsk.core.Point3D.create(a[0], a[1], 0),
                    adsk.core.Point3D.create(b[0], b[1], 0)
                )

        if ext_sketch.profiles.count == 0:
            ext_sketch.isLightBulbOn = False
            return None

        # Collect all profiles (expect 2, one per corner clip).
        profile_col = adsk.core.ObjectCollection.create()
        for pi in range(ext_sketch.profiles.count):
            profile_col.add(ext_sketch.profiles.item(pi))

        extrudes = root.features.extrudeFeatures
        ext_input = extrudes.createInput(
            profile_col,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        ext_input.setSymmetricExtent(
            adsk.core.ValueInput.createByReal(key_depth),
            True
        )
        ext_feat = extrudes.add(ext_input)

        names = [f'ExtClip_{joint_num}_A', f'ExtClip_{joint_num}_B']
        bodies = []
        for i in range(ext_feat.bodies.count):
            b = ext_feat.bodies.item(i)
            b.name = names[i] if i < len(names) else f'ExtClip_{joint_num}_{i}'
            bodies.append(b)

        ext_sketch.isLightBulbOn = False
        return bodies if bodies else None

    except:
        return None


# =============================================================================
# BODY / FACE HELPERS
# =============================================================================

def detect_open_side_from_sketch(sketch, s_min_x, s_max_x, s_min_y, s_max_y, bodies):
    """Detect which side of a cross-section bbox is the channel opening.

    Tests 4 inset points in sketch-local 2-D coordinates against the
    provided track bodies.  Because the sketch transform is used directly,
    the result is always in the same coordinate frame as the bbox — even
    when two sketches on the same construction plane end up with different
    local axes (which can happen on curved paths).

    Returns one of 'min_y', 'max_y', 'min_x', 'max_x', or None.
    """
    try:
        transform = sketch.transform
        normal = adsk.core.Vector3D.create(
            transform.getCell(0, 2),
            transform.getCell(1, 2),
            transform.getCell(2, 2)
        )
        normal.normalize()

        cx = (s_min_x + s_max_x) / 2.0
        cy = (s_min_y + s_max_y) / 2.0
        inset = 0.15

        candidates = [
            ('min_y', cx,            s_min_y + inset),
            ('max_y', cx,            s_max_y - inset),
            ('min_x', s_min_x + inset, cy),
            ('max_x', s_max_x - inset, cy),
        ]

        INSIDE = adsk.fusion.PointContainment.PointInsidePointContainment
        for side_name, tx, ty in candidates:
            pt_base = adsk.core.Point3D.create(tx, ty, 0)
            pt_base.transformBy(transform)

            inside_any = False
            for sign in (1.0, -1.0):
                if inside_any:
                    break
                pt_m = adsk.core.Point3D.create(
                    pt_base.x + sign * normal.x * 0.05,
                    pt_base.y + sign * normal.y * 0.05,
                    pt_base.z + sign * normal.z * 0.05,
                )
                for body in bodies:
                    try:
                        if body.pointContainment(pt_m) == INSIDE:
                            inside_any = True
                            break
                    except:
                        pass

            if not inside_any:
                return side_name

        return None
    except:
        return None


def planes_are_coincident(plane_geom, cut_plane_geom, tol=0.02):
    """Check if a face plane is coincident with the cut plane."""
    n1 = plane_geom.normal
    n2 = cut_plane_geom.normal
    n1.normalize()
    n2.normalize()

    dot = n1.x * n2.x + n1.y * n2.y + n1.z * n2.z
    if abs(abs(dot) - 1.0) > tol:
        return False

    o1 = plane_geom.origin
    o2 = cut_plane_geom.origin
    dx = o1.x - o2.x
    dy = o1.y - o2.y
    dz = o1.z - o2.z
    dist = abs(dx * n2.x + dy * n2.y + dz * n2.z)
    return dist < tol


def find_bodies_at_cut(root, cut_plane, tol=0.05):
    """Find the two Track_ bodies adjacent to a cut plane.

    Primary: coplanar face detection — keeps the 2 LARGEST bodies that have a
    face on the cut plane.  This handles hairpin cuts where a sliver may also
    have a coplanar face: the sliver is always smaller than the real pieces.

    Fallback: closest CoM on each side of the plane (volume-preferred).
    Slivers (volume < 0.5 cm³ = 500 mm³) are excluded.

    Returns list of (body, coplanar_face_or_None) tuples.
    """
    MIN_VOL = 0.5   # 500 mm³ — real pieces are >> this; slivers are not

    results = []
    cut_geom = cut_plane.geometry

    for body in _all_bodies(root):
        if not body.name.startswith('Track_'):
            continue
        try:
            vol = body.physicalProperties.volume
            if vol < MIN_VOL:
                continue
        except:
            continue
        for face in body.faces:
            try:
                surf = face.geometry
                if surf.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                    if planes_are_coincident(surf, cut_geom, tol):
                        results.append((vol, body, face))
                        break
            except:
                continue

    if results:
        # Sort by volume descending, keep the 2 largest.
        results.sort(key=lambda x: x[0], reverse=True)
        best = results[:2]
        if len(best) == 2:
            return [(b, f) for _, b, f in best]

    plane_origin = cut_geom.origin
    plane_normal = cut_geom.normal
    plane_normal.normalize()

    pos_candidates = []
    neg_candidates = []

    for body in _all_bodies(root):
        if not body.name.startswith('Track_'):
            continue
        try:
            vol = body.physicalProperties.volume
            if vol < MIN_VOL:
                continue
            # Filter: body bbox must straddle or touch the cut plane.
            bb = body.boundingBox
            bb_pts = [
                (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z),
                (bb.maxPoint.x, bb.minPoint.y, bb.minPoint.z),
                (bb.minPoint.x, bb.maxPoint.y, bb.minPoint.z),
                (bb.maxPoint.x, bb.maxPoint.y, bb.minPoint.z),
                (bb.minPoint.x, bb.minPoint.y, bb.maxPoint.z),
                (bb.maxPoint.x, bb.minPoint.y, bb.maxPoint.z),
                (bb.minPoint.x, bb.maxPoint.y, bb.maxPoint.z),
                (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z),
            ]
            bb_dots = [((p[0] - plane_origin.x) * plane_normal.x +
                        (p[1] - plane_origin.y) * plane_normal.y +
                        (p[2] - plane_origin.z) * plane_normal.z) for p in bb_pts]
            bbox_tol = 0.05
            if not (min(bb_dots) <= bbox_tol and max(bb_dots) >= -bbox_tol):
                continue
            com = body.physicalProperties.centerOfMass
            dot = ((com.x - plane_origin.x) * plane_normal.x +
                   (com.y - plane_origin.y) * plane_normal.y +
                   (com.z - plane_origin.z) * plane_normal.z)
            if dot >= 0:
                pos_candidates.append((vol, body))
            else:
                neg_candidates.append((vol, body))
        except:
            pass

    # Prefer the LARGEST body on each side (not the closest to the plane).
    # Slivers have small CoM distance but also small volume — sorting by volume
    # descending ensures we pick the real track piece over a sliver.
    result = []
    if pos_candidates:
        pos_candidates.sort(key=lambda x: x[0], reverse=True)
        result.append((pos_candidates[0][1], None))
    if neg_candidates:
        neg_candidates.sort(key=lambda x: x[0], reverse=True)
        result.append((neg_candidates[0][1], None))

    return result


def get_face_bbox_in_sketch(face, sketch):
    """Get bounding box of a face's vertices in sketch 2-D coordinates.

    Returns (min_x, max_x, min_y, max_y) in sketch space, or None on failure.
    """
    try:
        transform = sketch.transform
        inv = transform.copy()
        inv.invert()

        xs = []
        ys = []
        for vertex in face.vertices:
            pt = vertex.geometry.copy()
            pt.transformBy(inv)
            xs.append(pt.x)
            ys.append(pt.y)

        if not xs:
            return None
        return (min(xs), max(xs), min(ys), max(ys))
    except:
        return None


# =============================================================================
# SPLITTING SURFACE CREATION
# =============================================================================

def create_local_split_surface(root, cut_plane, params, section, surface_num, ui=None):
    """Create a thin solid disk at the cut plane for local body splitting."""
    surface_sketch = None
    try:
        cx, cy = 0, 0
        track_w = params['TRACK_WIDTH']
        track_h = params['TRACK_HEIGHT']
        diagonal = math.sqrt(track_w**2 + track_h**2)
        radius = diagonal + 1.0

        surface_sketch = root.sketches.add(cut_plane)
        surface_sketch.name = f'SplitSurface_{surface_num}'

        circles = surface_sketch.sketchCurves.sketchCircles
        center_pt = adsk.core.Point3D.create(cx, cy, 0)
        circles.addByCenterRadius(center_pt, radius)

        if surface_sketch.profiles.count == 0:
            surface_sketch.isLightBulbOn = False
            return None

        profile = surface_sketch.profiles.item(0)

        try:
            patches = root.features.patchFeatures
            patch_input = patches.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            patch_feature = patches.add(patch_input)

            if patch_feature and patch_feature.bodies.count > 0:
                surface_body = patch_feature.bodies.item(0)

                thicken_feats = root.features.thickenFeatures
                surface_faces = adsk.core.ObjectCollection.create()
                for face in surface_body.faces:
                    surface_faces.add(face)

                thicken_input = thicken_feats.createInput(
                    surface_faces,
                    adsk.core.ValueInput.createByReal(0.01),
                    False,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation
                )
                thicken_feature = thicken_feats.add(thicken_input)

                surface_sketch.isLightBulbOn = False

                if thicken_feature and thicken_feature.bodies.count > 0:
                    solid_disk = thicken_feature.bodies.item(0)
                    solid_disk.name = f'SplitSurface_{surface_num}'
                    try:
                        surface_body.deleteMe()
                    except:
                        pass
                    return solid_disk
        except:
            pass

        extrudes = root.features.extrudeFeatures
        extrude_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        extrude_input.setSymmetricExtent(adsk.core.ValueInput.createByReal(0.005), True)
        extrude_feature = extrudes.add(extrude_input)

        surface_sketch.isLightBulbOn = False

        if extrude_feature.bodies.count == 0:
            return None

        surface_body = extrude_feature.bodies.item(0)
        surface_body.name = f'SplitSurface_{surface_num}'
        return surface_body

    except Exception as e:
        if ui:
            ui.messageBox(f'SplitSurface_{surface_num} failed: {str(e)}')
        return None


# =============================================================================
# PATH / SORT HELPERS
# =============================================================================

def sort_bodies_along_path(bodies, curves):
    """Sort bodies by their position along the path."""
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
    assembly_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    assembly_comp = assembly_occ.component
    assembly_comp.name = 'Track_Assembly'

    for idx, body in enumerate(piece_bodies):
        piece_occ = assembly_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        piece_comp = piece_occ.component
        piece_comp.name = f'Piece_{idx + 1}'
        try:
            body.moveToComponent(piece_occ)
        except:
            try:
                body.copyToComponent(piece_occ)
            except:
                pass


def stop(context):
    pass
