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
        connector_bodies = [b for b in root.bRepBodies if b.name == 'Connector_Key']
        connector_label  = (f'{clips_made}/{num_cuts} socket pairs cut + '
                            f'{"1 Connector_Key body created" if connector_bodies else "Connector_Key already exists"}')
        assembly_tip = (
            'Assembly tip: all pieces are identical — each end has the same socket.\n'
            'Print one Connector_Key per junction. Slide key into piece A socket\n'
            'until centred, then push piece B onto the protruding half.\n'
            'Press-fit, no hardware. Key hidden inside floor material.'
        )
        connector_export = '\u2022 Right-click Connector_Key body \u2192 Save As Mesh (print N copies)'
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
    A single Connector_Key body is created once (at junction 1) and reused
    for all junctions.  Print one key per junction; press-fit into sockets.

    Socket profile = key profile + HOLE_CL clearance on all faces.
    Key profile = exact 10-vertex cross (no clearance — it IS the key).

    No combineFeatures anywhere.  Only extrudeFeatures + CutFeatureOperation
    + participantBodies (proven working approach, no component ownership issues).

    Assembly: slide H-key into socket on piece A until centred, then slide
    piece B onto the protruding half.  Key is fully hidden inside floor material
    + tiny rise into channel; invisible from viewer-facing and wall-facing sides.
    """
    PIN_DEPTH  = 1.0    # 10 mm engagement per side (20 mm total key length)
    HOLE_CL    = 0.04   # 0.4 mm clearance on each face of socket
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

    # ── Orientation ──────────────────────────────────────────────────────────
    detect_sk = root.sketches.add(cut_plane)
    detect_tr = detect_sk.transform.copy()
    detect_sk.isLightBulbOn = False
    _ays = 1.0 if detect_tr.getCell(2, 1) >= 0.0 else -1.0

    # ── Find adjacent bodies ──────────────────────────────────────────────────
    adjacent   = find_bodies_at_cut(root, cut_plane)
    cut_geom   = cut_plane.geometry
    cut_origin = cut_geom.origin

    track_bodies = [b for b, _ in adjacent if b.name.startswith('Track_')]
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
    _iyw = adsk.core.Vector3D.create(
        _ays * detect_tr.getCell(0, 1),
        _ays * detect_tr.getCell(1, 1),
        _ays * detect_tr.getCell(2, 1),
    )
    _iyw.normalize()

    _bb      = track_bodies[0].boundingBox
    _outer_z = _bb.minPoint.z if _ays > 0 else _bb.maxPoint.z
    _inner_z = _outer_z + _ays * wt
    floor_w  = adsk.core.Point3D.create(cut_origin.x, cut_origin.y, _inner_z)

    # ── Shared profile builder ────────────────────────────────────────────────
    def _key_profile(sk_name, neck, ear, ear_top, ear_bot, floor_d,
                     channel_rise=0.0):
        """Build 10-vertex cross profile on cut_plane; return (sketch, profile)."""
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

        verts = [
            (-neck,  top_y),
            ( neck,  top_y),
            ( ear,   _fld(ear_top)),
            ( ear,   _fld(ear_bot)),
            ( neck,  _fld(ear_bot)),
            ( neck,  _fld(floor_d)),
            (-neck,  _fld(floor_d)),
            (-neck,  _fld(ear_bot)),
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

    # ── Cut identical socket into each adjacent track body ────────────────────
    for body_idx, body in enumerate(track_bodies):
        try:
            _, sock_prof = _key_profile(
                f'Socket_{joint_num}_{body_idx}',
                NECK_HW + HOLE_CL,
                EAR_HW  + HOLE_CL,
                EAR_TOP - HOLE_CL,          # arm starts sooner → diagonal clearance
                EAR_BOT + HOLE_CL,          # arm ends later
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

    # ── H-key body — created ONCE, shared across all junctions ───────────────
    # Check root bodies for existing Connector_Key.
    key_exists = any(b.name == 'Connector_Key' for b in root.bRepBodies)
    if not key_exists:
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
                    feat.bodies.item(0).name = 'Connector_Key'
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
