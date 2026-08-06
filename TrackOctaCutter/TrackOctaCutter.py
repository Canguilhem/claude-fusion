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
                'Phase 2, or a wall-mount test part?\n\n'
                'YES = Phase 2 (cut track at all CutPlane_* planes)\n'
                'NO = Generate the screw COVER CAP (one per junction)\n'
                'CANCEL = Show help and current parameters',
                'Track Octa Cutter',
                adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType
            )
            if result2 == adsk.core.DialogResults.DialogYes:
                cut_at_planes(root, ui, design, params)
            elif result2 == adsk.core.DialogResults.DialogNo:
                create_wall_cap_part(root, params, ui)
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
        '  3. Choose connector: wall-snap (recommended) or M2 plate\n'
        '  4. All CutPlane_* planes are processed\n\n'
        'Assembly (wall-snap, approach B):\n'
        '  Hardware per junction: NONE \u2014 integrated snap-fit joints\n'
        '  1. Each piece has a male end (wall tongues) + a female end (pockets)\n'
        '  2. Push two ends together until the side-wall barbs click in\n'
        '  3. To separate: press the barb in through the wall-facing window\n'
        '  Floor + channel stay clear for a continuous LED strip\n\n'
        '--- Current Parameters ---\n'
        f'TRACK_HEIGHT:   {params["TRACK_HEIGHT"]*10:.1f} mm\n'
        f'TRACK_WIDTH:    {params["TRACK_WIDTH"]*10:.1f} mm\n'
        f'WALL_THICKNESS: {params["WALL_THICKNESS"]*10:.1f} mm\n'
        f'KEY_DEPTH:      {params["KEY_DEPTH"]*10:.1f} mm\n\n'
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

    # Clear any CutPlane_* from a previous Phase 1 run — otherwise re-running
    # ACCUMULATES planes (old + new), so Phase 2 splits into far more pieces than
    # intended (the "way more pieces" bug).  Only script-created CutPlane_* are
    # removed; user planes are untouched.
    _removed_old = 0
    for _i in range(root.constructionPlanes.count - 1, -1, -1):
        _cp = root.constructionPlanes.item(_i)
        if _cp.name.startswith('CutPlane_'):
            try:
                _cp.deleteMe(); _removed_old += 1
            except Exception:
                pass

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
        + (f'Removed {_removed_old} old CutPlane_* from a previous run\n'
           if _removed_old else '')
        + f'{planes_created} cut planes created\n'
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
        f'  YES  = M2 screw plate\n'
        f'         Flat plate inside channel + 2\u00d7 M2 screws\n'
        f'         Requires: heat-set inserts + M2 screws\n'
        f'         Fully hidden inside channel (wall-facing side)\n\n'
        f'  NO   = Wall-snap joint (wallsnap, approach B)\n'
        f'         Cantilever snap-fit built into the side walls\n'
        f'         No hardware, no glue — push pieces together until they click\n'
        f'         Floor + channel stay clear for a continuous LED strip\n\n'
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
            for b in _all_bodies(root):
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

            for target_body in track_bodies:
                try:
                    _tb_comp = target_body.parentComponent
                    split_feats = _tb_comp.features.splitBodyFeatures
                    split_input = split_feats.createInput(target_body, split_surface, False)
                    split_result = split_feats.add(split_input)
                    for new_body in split_result.bodies:
                        new_body.name = 'Track_Piece'
                    cuts_made += 1
                    break
                except Exception as _e_split:
                    if ui:
                        ui.messageBox(f'Split {idx+1} body failed: {_e_split}')

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
        degenerate = []
        # Use _all_bodies so subcomponent Track_ bodies are included —
        # when the user chose "separate components", root.bRepBodies is empty.
        for body in _all_bodies(root):
            if not body.name.startswith('Track_'):
                continue
            try:
                vol = body.physicalProperties.volume
                if vol < min_volume:
                    slivers.append(body)
                else:
                    tracks.append(body)
            except:
                # physicalProperties.volume THROWS on a degenerate ~0.1 mm
                # disk-thickness wafer left by the splitter.  The old code did
                # `pass` here, so the wafer landed in neither list and survived
                # to be numbered as a bogus piece (the Track_Piece_5 sleeve that
                # made the joint loose).  Don't try to combine it — a corrupt tool
                # body can damage a good piece — just remove it outright.
                degenerate.append(body)

        for _d in degenerate:
            try:
                _d.deleteMe()
                slivers_removed += 1
            except:
                try:
                    _d.name = 'Sliver_residual'
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
                        # Use track's own component to avoid cross-component combine failure.
                        combines = track.parentComponent.features.combineFeatures
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
                        combines = best_track.parentComponent.features.combineFeatures
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

    # === Build the sweep path (for path-following wall-snap geometry) ===
    # Rebuild the Path object + total length from the selected path sketch so the
    # connector code can place geometry at true path stations (curve-following),
    # not on straight prisms that drift off the wall on bends.  num_pieces matches
    # Phase 1 (planes were placed at ratio i/num_pieces), so junction j sits at
    # path ratio j/num_pieces.
    _sweep_path = None
    _path_len   = 0.0
    _num_pieces = num_cuts + 1
    if path_sketch_ref is not None:
        try:
            _pc = adsk.core.ObjectCollection.create()
            for _curve in path_sketch_ref.sketchCurves:
                _pc.add(_curve)
                if hasattr(_curve, 'geometry'):
                    _ev = _curve.geometry.evaluator
                    _ok, _sp, _ep = _ev.getParameterExtents()
                    if _ok:
                        _ok2, _ln = _ev.getLengthAtParameter(_sp, _ep)
                        if _ok2:
                            _path_len += _ln
            if _pc.count > 0:
                _sweep_path = root.features.createPath(_pc, True)
        except Exception as _e_path:
            _sweep_path = None
            if ui:
                ui.messageBox(f'Path build for wall-snap failed (straight fallback):\n{_e_path}')

    # === STEP 2: Create connectors at each junction ===
    clips_made = 0
    clip_errors = []
    _val_records = []
    for idx, cut_plane in enumerate(cut_planes):
        adsk.doEvents()
        try:
            if use_pin_connector:
                _rec = create_pin_connector(root, cut_plane, params, idx + 1, ui,
                                            path=_sweep_path, path_len=_path_len,
                                            num_pieces=_num_pieces)
                ok = bool(_rec.get('success', False)) if isinstance(_rec, dict) else bool(_rec)
                if isinstance(_rec, dict):
                    _val_records.append(_rec)
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

    # Write validation JSON so geometry can be verified without screenshots.
    if _val_records:
        import json as _json, os as _os, datetime as _dt
        _val_path = _os.path.join(_os.path.dirname(__file__), 'connector_validation.json')
        try:
            with open(_val_path, 'w') as _vf:
                _json.dump({
                    'written': _dt.datetime.now().isoformat(),
                    'junctions': _val_records
                }, _vf, indent=2)
        except Exception as _ve:
            if ui:
                ui.messageBox(f'Validation write failed: {_ve}')

    # === STEP 2.6: Wall-mount standoff feet (integrated, two per junction) ===
    # Optional.  Built while bodies are still in ROOT (before any 'Create
    # components' step) so the feet weld into the piece with no cross-component
    # ownership issue.  Each foot is combined INTO a track piece (no standalone
    # body); the host is temporarily renamed WBHost_N then restored to
    # 'Track_Piece' so STEP 3's rename still catches it.  Orientation-free +
    # self-locating (see create_wall_bracket) — works for any track/orientation.
    wb_choice = ui.messageBox(
        'Add wall-mount dovetail studs at each junction?\n\n'
        'Two studs (one per wall) are grown on the wall-tip faces and welded\n'
        'INTO the track piece — they print as part of it.  They sit on the\n'
        'opaque walls (in shadow) and flare only OUTBOARD, so the LED channel\n'
        'stays fully clear (no blocking, no shadow).\n\n'
        'Each bracket reaches the wall by itself and carries its own M3 on an\n'
        'ear OUTBOARD of the track, so you can drive the screw with the loop\n'
        'already hanging — no separate mount part, and the mounts do NOT have\n'
        'to engage simultaneously.  Generate the screw cover cap from the main\n'
        'menu (Phase 1? NO -> Phase 2? NO); print one per junction.\n\n'
        'A 1:1 drilling template sketch is generated for the wall, but the\n'
        'reliable install is: assemble the loop, clip the plaques on, THEN\n'
        'mark and drill through them so no error accumulates.\n'
        'v1 assumes a flat-XY track.',
        'Wall Mounts',
        adsk.core.MessageBoxButtonTypes.YesNoButtonType
    )
    if wb_choice == adsk.core.DialogResults.DialogYes:
        _wb_records = []
        _wb_made = 0
        # Measure the wall-tip Z ONCE, before ANY foot exists — the max Z over all
        # track pieces on this flat track is the (shared) wall tip.  Feet are
        # welded junction-by-junction, so a per-junction host bbox gets
        # CONTAMINATED by feet already welded in from neighbours (its top reads
        # foot-top, not wall-tip) → later junctions build their feet higher and
        # the heights diverge.  A single pre-measured constant keeps every foot
        # at the same Z.
        _wall_top_z = None
        try:
            _tops = [b.boundingBox.maxPoint.z for b in _all_bodies(root)
                     if b.name.startswith('Track_')]
            if _tops:
                _wall_top_z = max(_tops)
        except Exception:
            _wall_top_z = None
        for idx, cut_plane in enumerate(cut_planes):
            adsk.doEvents()
            try:
                _wbr = create_wall_bracket(root, cut_plane, params, idx + 1, ui,
                                           path=_sweep_path, path_len=_path_len,
                                           num_pieces=_num_pieces,
                                           wall_top_z=_wall_top_z)
                if isinstance(_wbr, dict):
                    _wb_records.append(_wbr)
                    if _wbr.get('success'):
                        _wb_made += 1
            except Exception as _ewb:
                _wb_records.append({'joint': idx + 1, 'success': False,
                                    'error': str(_ewb)})
        # Collect every screw XY (world) for the drilling template + JSON.
        _wb_screws = []
        for _r in _wb_records:
            for _s in (_r.get('screws') or []):
                _wb_screws.append(_s)

        # Build a 1:1 drilling template sketch on xY: a circle at each screw
        # position (the constellation the customer transfers to the wall in
        # whatever orientation they choose).  Export it as DXF/PDF at 1:1.
        _tpl_ok = False
        try:
            if _wb_screws:
                _tpl = root.sketches.add(root.xYConstructionPlane)
                _tpl.name = 'WallMount_DrillTemplate'
                _tinv = _tpl.transform.copy(); _tinv.invert()
                _circ = _tpl.sketchCurves.sketchCircles
                _line = _tpl.sketchCurves.sketchLines
                for _sx, _sy in _wb_screws:
                    _c = adsk.core.Point3D.create(_sx, _sy, 0.0)
                    _c.transformBy(_tinv)
                    _cp = adsk.core.Point3D.create(_c.x, _c.y, 0)
                    _circ.addByCenterRadius(_cp, 0.20)   # 4 mm drill-mark ring
                    # small cross-hair for precise centre-punching
                    _line.addByTwoPoints(
                        adsk.core.Point3D.create(_c.x - 0.30, _c.y, 0),
                        adsk.core.Point3D.create(_c.x + 0.30, _c.y, 0))
                    _line.addByTwoPoints(
                        adsk.core.Point3D.create(_c.x, _c.y - 0.30, 0),
                        adsk.core.Point3D.create(_c.x, _c.y + 0.30, 0))
                _tpl_ok = True
        except Exception:
            pass

        # ── Mount census: does EVERY piece carry a pair of studs? ────────────
        # A junction mounts its downstream piece, so on a closed loop the map
        # should be 1:1.  When it isn't, one piece ends up with two pairs and
        # another with NONE — and a piece with no mount hangs on its snap joints
        # alone.  A bracketed piece reaches the WALL plane; a bare
        # one still reads the wall tip.  This is measured, so it catches a
        # mis-placed pair no matter which code path put it there.
        _wb_census = {'pieces': [], 'unmounted': 0}
        try:
            # A bracketed piece reaches the WALL plane (wall tip + the standoff
            # gap); a bare one still stops at the wall tip.  Half the gap is a
            # threshold nothing else can reach.
            _stud_top = ((_wall_top_z + WALL_STANDOFF_GAP * 0.5)
                         if _wall_top_z is not None else None)
            for _b in _all_bodies(root):
                if not _b.name.startswith('Track_'):
                    continue
                try:
                    _v = _b.physicalProperties.volume
                    if _v < 0.05:
                        continue
                    _zt = _b.boundingBox.maxPoint.z
                except Exception:
                    continue
                _has = (_stud_top is not None and _zt >= _stud_top)
                _wb_census['pieces'].append(
                    {'vol': round(_v, 3), 'zmax': round(_zt, 3),
                     'studs': bool(_has)})
                if not _has:
                    _wb_census['unmounted'] += 1
        except Exception:
            pass
        if _wb_census['unmounted'] and ui:
            ui.messageBox(
                f"{_wb_census['unmounted']} track piece(s) ended up with NO "
                f"wall studs — they would hang on their snap joints alone.\n\n"
                f"Another piece will have received two pairs.  See "
                f"mount_census in wall_bracket_validation.json; the usual cause "
                f"is a junction placing its studs on the wrong side of the seam.")

        # Write bracket validation + screw coordinates JSON.
        try:
            import json as _json2, os as _os2, datetime as _dt2
            _wb_path = _os2.path.join(_os2.path.dirname(__file__),
                                      'wall_bracket_validation.json')
            with open(_wb_path, 'w') as _wf:
                _json2.dump({'written': _dt2.datetime.now().isoformat(),
                             'units': 'cm (world XY; screw axis = +Z into wall)',
                             'screw_positions': _wb_screws,
                             'mount_census': _wb_census,
                             'brackets': _wb_records}, _wf, indent=2)
        except Exception:
            pass
        if ui:
            _tpl_msg = ('A 1:1 drilling template sketch "WallMount_DrillTemplate" '
                        'was created — export it as DXF/PDF at 1:1, tape it to the '
                        'wall in whatever orientation you like, and mark the holes.'
                        if _tpl_ok else
                        'Screw positions are in wall_bracket_validation.json.')
            ui.messageBox(
                f'{_wb_made}/{len(cut_planes)} junctions got dovetail studs '
                f'(2 per junction, {len(_wb_screws)} plaque screws).\n\n'
                'Each stud is part of a track piece (wall-facing side, in the '
                'wall\'s shadow — hidden from the viewer, clear of the LED).\n'
                'Mount: hold the loop up, mark through each bracket ear, '
                'drill, hang it back and drive the screws, then press in a '
                'cover cap.  The gap is printed into the bracket '
                '(WALL_STANDOFF_GAP).\n\n'
                f'{_tpl_msg}'
            )

    # === STEP 3: Rename pieces ===
    # Safety net: never number a sub-threshold body as a piece.  Any Track_ body
    # still under min-volume here is a splitter wafer that escaped the sliver
    # merge — remove it (or de-namespace it) so it can't become a bogus Piece_N.
    # Reclaim any real piece left tagged WBHost_*/WBOther_* because its name
    # restore was missed (e.g. a same-named orphan from a prior run shadowed it
    # in _by_name).  These are full track pieces above sliver volume — rename
    # them back so STEP 3 numbers them into the assembly instead of stranding
    # them loose in root.  Sub-sliver WB* leftovers (stray unwelded nubs) fall
    # through to the sliver filter below and are removed.
    # A REAL piece is >> 1 cm³ (the 20x17 mm profile alone is 1.44 cm² of
    # section, so even a 2 cm stub is ~2.9 cm³); a foot is ~0.3 cm³.  Anything
    # tagged but foot-sized is NOT a piece — numbering it produced the phantom
    # Piece_10/Piece_11 bodies.  Park those under WBOrphan_ and report them.
    _WB_PIECE_MIN_VOL = 1.0
    _wb_reclaimed = 0
    _wb_orphans = []
    for b in _all_bodies(root):
        if b.name.startswith('WBHost_') or b.name.startswith('WBOther_'):
            try:
                _v = b.physicalProperties.volume
            except Exception:
                continue
            if _v >= _WB_PIECE_MIN_VOL:
                b.name = 'Track_Piece'
                _wb_reclaimed += 1
            elif _v >= 0.05:
                _wb_orphans.append((b.name, round(_v, 4)))
                try:
                    b.name = 'WBOrphan_' + b.name
                except Exception:
                    pass
    if _wb_reclaimed and ui:
        ui.messageBox(
            f'Reclaimed {_wb_reclaimed} track piece(s) left tagged WBHost_/WBOther_ '
            f'(name-restore miss) back into the numbered assembly.')
    if _wb_orphans and ui:
        ui.messageBox(
            'Found {} tagged body/bodies too small to be a track piece — NOT '
            'numbered as pieces (renamed WBOrphan_*):\n\n{}\n\n'
            'These are almost certainly wall-mount feet that never welded into '
            'a piece.  Delete them, or fix the junction and re-run.'.format(
                len(_wb_orphans),
                '\n'.join(f'  {n}  {v} cm³' for n, v in _wb_orphans)))

    piece_bodies = []
    _sliver_leftovers = 0
    for b in _all_bodies(root):
        if not b.name.startswith('Track_'):
            continue
        try:
            _bv = b.physicalProperties.volume
        except:
            _bv = 0.0
        if _bv < 0.05:
            _sliver_leftovers += 1
            try:
                b.deleteMe()
            except:
                try:
                    b.name = 'Sliver_residual'
                except:
                    pass
            continue
        piece_bodies.append(b)
    if _sliver_leftovers and ui:
        ui.messageBox(
            f'Removed {_sliver_leftovers} leftover splitter wafer(s) before '
            f'numbering pieces (would have become bogus thin Piece_N bodies).')

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
        connector_label  = f'{clips_made}/{num_cuts} wall-snap joints created'
        bom_line         = 'Hardware needed: NONE \u2014 snap-fit joints, no screws or glue'
        assembly_tip = (
            'Assembly tip: each piece has one male end (wall tongues) and one\n'
            'female end (wall pockets), alternating along the track.\n'
            'Push two ends together until the side-wall barbs click into place.\n'
            'Floor + channel stay clear for a continuous LED strip.\n'
            'To separate: press the barb in through the window on the wall-facing\n'
            'wall face and pull apart.'
        )
        connector_export = '(no separate body to export — joints are integral)'
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
    bom_line   = bom_line if use_pin_connector else ''
    create_comps = ui.messageBox(
        f'Done!\n\n'
        f'{len(piece_bodies)} track pieces created{sliver_msg}\n'
        f'{cuts_made} cuts made\n'
        f'{connector_label}\n'
        + (f'{bom_line}\n' if bom_line else '') +
        '\nCreate separate components for each piece?\n'
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

def create_pin_connector(root, cut_plane, params, joint_num, ui=None,
                         path=None, path_len=0.0, num_pieces=None):
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
    # 'stud'    : half-cylinder boss on collar top + M4 thread
    # 'vscrew'  : vertical M3 bolt through a channel collar + floor nut trap.
    #             Blocks a floor-mounted LED strip at 9 mm channel width — retired.
    # 'wallsnap': integrated cantilever snap-fit lap joint built INTO the two side
    #             walls (3 mm × 10 mm of hidden material).  No hardware, no glue,
    #             reversible.  Floor + channel stay 100 % clear for a continuous
    #             full-width LED strip.  Snap (not slide) so the closed F1 loop's
    #             last piece can click into place between two fixed neighbours.
    LOCK_STYLE = 'wallsnap'

    COLLAR_HW  = inner_hw - 0.03      # slightly narrower than inner channel
    # vscrew: 5 mm collar height gives full M3 self-tap engagement (2.5 mm pilot)
    COLLAR_H   = 0.40   # 4 mm collar → 3 mm bolt-access gap in 7 mm inner channel
    COLLAR_LEN = 0.80                 # 8 mm per piece (4 mm each side); bore at x=0 leaves 4−1.7=2.3 mm wall
    POST_R     = 0.175                # unused for vscrew; kept for stud mode
    POST_H     = 0.50                 # unused for vscrew; kept for stud mode

    # ── Wall-snap lock (LOCK_STYLE == 'wallsnap') ─────────────────────────────
    # All in cm.  Built in the local cut-plane frame: X = across width,
    # Y = floor→wall depth, Z = along track axis (pieces split at Z=0).
    # One end is male (tongue per wall), the mating end female (pocket + window).
    # ── Geometry below was VALIDATED ON A PRINT COUPON, 2026-08-03 ───────────
    # (API/Scripts/TrackTestCoupon, variant A).  The joint had never physically
    # engaged before that — the wrong TRACK_WIDTH param put the tongue in mid
    # air — so every number here was previously untested.  What the coupon
    # showed: the tongue is the SPRING, and a 1.3 mm × 8 mm one is not a spring
    # at all.  Stiffness goes as t³/L³:
    #     t=1.3 L=8  w=15 → k 56 N/mm → 35 N to deflect, ~22 N to insert
    #     t=1.0 L=12 w=15 → k 7.6     →  5 N,            ~3 N
    # The old joint could not be pushed home by hand; it stalled short with the
    # barb riding compressed on the land and the window sitting empty.
    SNAP_LAP_LEN   = 1.20            # 12 mm lap (was 8) — the flex length that
                                     # makes the tongue an actual cantilever
    SNAP_TONGUE_T  = 0.10            # 1.0 mm tongue (was wt*0.5-0.02 = 1.3).
                                     # Thinner = softer spring AND more window
                                     # skin left in the outer slab.  No longer
                                     # tied to wt: the wall budget below is what
                                     # matters, not "half the wall".
    SNAP_CL        = 0.008           # 0.08 mm print clearance — tightened from 0.12
                                     # to cut the vertical rattle that lets the joint
                                     # roll about the track axis (print-tune this knob)
    SNAP_Y0_INSET  = 0.10            # tongue starts 1 mm above outer floor
    SNAP_Y1_INSET  = 0.10            # tongue ends 1 mm below channel top
    SNAP_BARB_X    = 0.07            # 0.7 mm catch.  1.0 mm was tried and is
                                     # impossible with a BLIND window: the wall
                                     # budget is tongue + barb + clearance +
                                     # skin = 3.0 mm, and 1.0 mm of barb leaves
                                     # 0.45 mm of skin — under one extrusion
                                     # width, so the slicer DROPS it and prints
                                     # a through hole (seen 2026-08-03).
    SNAP_BARB_LEN  = 0.30            # 3.0 mm (was 1.8).  The whole length is
                                     # the lead-in ramp: the loft runs from the
                                     # full step at the catch face to FLUSH at
                                     # the tip, so it must be long enough to
                                     # take all of SNAP_BARB_X gradually.  At
                                     # 1.8 mm it ramped only a third of the
                                     # deflection and the rest happened at the
                                     # blunt leading corner.
    SNAP_BARB_H    = 0.80            # 8 mm barb, CENTRED on the ~15 mm tongue.
                                     # A full-height barb had to drop into a
                                     # window only 0.16 mm taller than itself —
                                     # 0.08 mm across 15 mm, which no FDM print
                                     # holds, so it never entered.  Shorter barb
                                     # = real clearance, and costs no stiffness
                                     # (the spring is the tongue, not the bump).
    # ── Floor half-lap ───────────────────────────────────────────────────────
    # The joint used to be walls-only, so nothing keyed the floor: the pieces
    # hinge about the seam and lever the barbs out — that is why the first full
    # circuit popped apart when handled.  This buries a half-lap INSIDE the
    # floor's own thickness: the male keeps the bottom SNAP_FLOOR_TT, the female
    # is relieved to match.  Both visible faces stay flush, so the LED still
    # lies on a flat floor and the outer (viewer) face is unbroken, and nothing
    # enters the channel — the gap above the strip is the LIGHT PATH, not free
    # space, so a boss there would shadow the halo at every junction.
    # The male half is the BOTTOM so it prints flat on the bed; the female's
    # void then bridges the channel WIDTH, anchored at both walls.
    SNAP_FLOOR_TT  = 0.12            # 1.2 mm of 3.0 → 1.8 mm of ceiling left
    SNAP_BARB_CLR  = 0.025           # room past the barb tip inside the window
    SNAP_BARB_ZCL  = 0.04            # window clearance above/below the barb
    SNAP_BARB_OVL  = 0.02            # barb overlap back into tongue (combine bond)
    # Straight-fallback taper must match the loft's full-depth ramp exactly.
    SNAP_BARB_RAMP = math.degrees(math.atan(SNAP_BARB_X / SNAP_BARB_LEN))
    # ── Blind barb window: DERIVED, not dialled in ───────────────────────────
    # The window used to cut 0.5 mm PAST the outer face — 18 through-slots
    # leaking the LED sideways at every junction.  Blind is opaque and a
    # stronger catch (closed pocket; the barb can't be knocked in).  Its depth
    # is fixed by the barb, and whatever skin is left MUST beat one extrusion
    # width or the slicer silently drops it and prints a hole anyway.
    #   wall 3.0 = tongue 1.0 + barb 0.7 + clearance 0.25 + SKIN 1.05 mm ✓
    SNAP_WIN_FLOOR = SNAP_TONGUE_T + SNAP_BARB_X + SNAP_BARB_CLR
    SNAP_WINDOW_SKIN = wt - SNAP_WIN_FLOOR
    SNAP_MIN_SKIN  = 0.045           # ~1 extrusion width on a 0.4 mm nozzle
    if SNAP_WINDOW_SKIN < SNAP_MIN_SKIN and ui:
        ui.messageBox(
            f'WallSnap: blind window would leave only '
            f'{SNAP_WINDOW_SKIN*10:.2f} mm of outer-wall skin '
            f'(need {SNAP_MIN_SKIN*10:.2f} mm — one extrusion width).\n\n'
            f'The slicer will DROP it and print a through hole that leaks '
            f'light.  Reduce SNAP_BARB_X or SNAP_TONGUE_T.')
    # Cost of a blind window: no pressing the barb from outside to separate —
    # pull-and-flex, or slit the skin.  Set SNAP_BARB_CLR high (or edit
    # SNAP_WIN_FLOOR to wt + 0.05) to go back to a through window.

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
    _val_rec = {
        'joint_num': joint_num,
        'is_lower_pos': None,  # filled after is_lower_pos is computed below
        'bore_cx': None, 'bore_cy': None,
        'collar':  {'success': False, 'bodies_created': 0, 'error': None},
        'vbore':   {'success': False, 'profile_found': False, 'error': None},
        'nuttrap': {'success': False, 'profile_found': False, 'error': None},
        'wallsnap': None,
        'volumes': {
            'collar_vol': None,
            'boss_before': None, 'boss_after': None, 'bore_removed': None,
            'bore_expected': round(3.14159265 * 0.17**2 * (0.30 + 0.001), 4),
            'nut_before': None,  'nut_after': None,  'trap_removed': None,
            'trap_expected': round(3*1.73205081/2 * 0.328**2 * 0.24, 4),
        },
    }
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

    boss_sk         = None
    boss_body       = None   # kept for LOCK_STYLE == 'stud' code path; not used by vscrew
    boss_halves     = []
    lower_boss_body = None   # collar half at [wt, wt+COLLAR_H/2] — sits on inner floor
    upper_boss_body = None   # collar half at [wt+COLLAR_H/2, wt+COLLAR_H] — rides on top
    # Coord vars set by Step 1; Step 4 uses them.  Defaults prevent NameError if
    # Step 1 raises (Step 4 will bail on missing profile anyway).
    fy_b   = None; fy_mid = None; fy_top = None
    P3     = adsk.core.Point3D.create
    # Alternating assignment: even joint_num → +cut_normal body gets upper collar.
    # Ensures each physical piece is consistently upper-type or lower-type on both
    # its junctions (A-B-A-B arrangement along the track).
    is_lower_pos    = (joint_num % 2 == 1)  # True: +cut_normal body = lower collar
    _val_rec['is_lower_pos'] = is_lower_pos
    try:
        # Compute sketch-space coordinates once using a temporary sketch.
        # We need fy_b (inner floor Y), fy_mid (mid-collar Y), fy_top (top Y)
        # in the cut_plane sketch's local coordinate system.
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

        fy_mid = fy_b + inward_b * (COLLAR_H / 2)
        fy_top = fy_b + inward_b * COLLAR_H

        # Boss bodies are NOT created here.  Creating them in root when
        # track bodies live in a Track_Assembly subcomponent causes a
        # cross-component combineFeatures failure even when using
        # subcomp.features.combineFeatures.  Instead, Step 4 creates each
        # boss directly in body.parentComponent right before it combines.
        P3 = adsk.core.Point3D.create

        # The coord-detection sketch is no longer needed.
        try: boss_sk.deleteMe()
        except Exception: pass
        boss_sk = None

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
    # DISABLED: the scarf was producing a far-steeper-than-expected cut
    # (~13 mm wedge on a 17 mm track instead of the ~2 mm expected for 8°).
    # With ang_cp = None the track bodies keep a clean perpendicular junction
    # face, the collar boss join reliably finds the inner floor, and
    # _find_iy_face can locate the collar faces.
    # TODO: re-enable and fix the angle calculation once bore/nut is validated.
    ang_cp = None

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
                # Do NOT call deleteMe() on extras here.
                # Deleting a splitBodyFeature result body can invalidate the
                # entire split feature in Fusion's kernel, voiding the references
                # to main_neg and wedge and causing "deleted object" on the
                # subsequent combineFeatures.add.  Leave orphan slivers as-is;
                # they can be deleted manually if they appear in the browser.
                for p in parts:
                    if p is not main_neg and p is not wedge:
                        try: p.name = f'ScarfExtra_{joint_num}'
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

    # ── Step 4: Join each collar boss to its track body ──────────────────────
    # is_lower_pos (set in Step 1): True → +cut_normal body gets the lower boss.
    # The lower boss sits on the inner floor; the upper boss rides on top of it
    # when two pieces are assembled.  Alternating joint_num ensures each physical
    # piece is consistently lower-type or upper-type on both its junctions.
    #
    # lower_track_idx / upper_track_idx record which track_bodies entry received
    # each boss, so Step 4b can identify bodies reliably without re-doing CoM
    # arithmetic (which fails at hairpins where both CoMs land on the same side).
    lower_track_idx = None
    upper_track_idx = None
    # _NUT_INSET: bore + nut-trap centre from junction into nut piece.
    #   Must be ≥ M3_NUT_CR so the full hex pocket clears the junction edge.
    # BOSS_OWN: how far the boss extends INTO its own piece (overlap for combine
    #   reliability and structural strength).
    # Boss total = COLLAR_LEN (into nut piece) + BOSS_OWN (into own piece).
    BOSS_OWN   = 0.30           # 3.0 mm overlap into boss piece

    # Bore / nut-trap constants (vscrew; flat XY track assumed).
    VBORE_R   = 0.17    # 1.7 mm radius = 3.4 mm dia M3 clearance
    M3_NUT_CR = 0.328   # M3 hex circumradius (AF 5.5 mm + 0.1 mm tol)
    M3_NUT_D  = 0.24    # M3 nut height 2.4 mm
    # Bore/trap centre offset from junction INTO nut piece — hex far edge clears junction by 0.5 mm.
    _NUT_INSET = M3_NUT_CR + 0.05   # 3.78 mm
    _nut_sign = 1.0 if is_lower_pos else -1.0
    bore_cx   = cut_origin.x + _nut_sign * _NUT_INSET * cut_normal.x
    bore_cy   = cut_origin.y + _nut_sign * _NUT_INSET * cut_normal.y

    def _bore_plane_at(height):
        """XY-offset plane at cut_origin.z + height (flat track only)."""
        _cp_in = root.constructionPlanes.createInput()
        _cp_in.setByOffset(root.xYConstructionPlane,
                           adsk.core.ValueInput.createByReal(cut_origin.z + height))
        _cp = root.constructionPlanes.add(_cp_in)
        _cp.isLightBulbOn = False
        return _cp

    # Pre-loop: determine lower_tp_idx via RELATIVE CoM comparison so that
    # exactly one body is lower and one is upper even at hairpins where both
    # CoMs land on the same side of cut_plane.
    # The body whose CoM dot product is most in the is_lower_pos direction → lower.
    _lower_tp_idx = 0   # fallback: first body is lower
    if len(track_pairs) >= 2:
        _dots = []
        for _b, _ in track_pairs[:2]:
            _c = _b.physicalProperties.centerOfMass
            _dots.append(
                (_c.x - cut_origin.x)*cut_normal.x +
                (_c.y - cut_origin.y)*cut_normal.y +
                (_c.z - cut_origin.z)*cut_normal.z)
        # is_lower_pos=True → nut piece at +cut_normal: pick body with larger dot
        # is_lower_pos=False → nut piece at -cut_normal: pick body with smaller dot
        if is_lower_pos:
            _lower_tp_idx = 0 if _dots[0] >= _dots[1] else 1
        else:
            _lower_tp_idx = 0 if _dots[0] < _dots[1] else 1

    for tp_idx, (body, _jct_face) in (
            enumerate(track_pairs) if LOCK_STYLE == 'vscrew' else []):
        try:
            if fy_b is None:
                if ui: ui.messageBox(f'RetainBoss jct {joint_num}: coord detection failed, skipping boss')
                continue
            body_is_lower = (tp_idx == _lower_tp_idx)

            # Boss piece (body_is_lower=False): collar insert + VBore through collar.
            # Nut piece  (body_is_lower=True):  hex nut trap in floor.
            if not body_is_lower:
                comp          = body.parentComponent
                comp_extrudes = comp.features.extrudeFeatures

                # Determine which sketch-Z direction is toward nut piece.
                _sk_dir = comp.sketches.add(cut_plane)
                _sk_dir.isLightBulbOn = False
                _sl_tr  = _sk_dir.transform
                _skz_cn = (_sl_tr.getCell(0,2)*cut_normal.x +
                           _sl_tr.getCell(1,2)*cut_normal.y +
                           _sl_tr.getCell(2,2)*cut_normal.z)
                _toward_nut = (is_lower_pos == (_skz_cn > 0))

                # ── Collar insert: NewBodyFeatureOperation, no combine ────────
                # Rectangle from fy_b (inner floor) to fy_top (fy_b + COLLAR_H).
                # Extends BOSS_OWN into boss channel + COLLAR_LEN into nut channel.
                # Stays as separate body — prints as a connector insert piece.
                _collar     = None
                _collar_err = None
                _collar_vol = None
                try:
                    _sk_c = comp.sketches.add(cut_plane)
                    _sk_c.name = f'Collar_{joint_num}'
                    _sk_c.isLightBulbOn = False
                    _Lc = _sk_c.sketchCurves.sketchLines
                    _Lc.addByTwoPoints(P3(-COLLAR_HW, fy_b,   0), P3( COLLAR_HW, fy_b,   0))
                    _Lc.addByTwoPoints(P3( COLLAR_HW, fy_b,   0), P3( COLLAR_HW, fy_top, 0))
                    _Lc.addByTwoPoints(P3( COLLAR_HW, fy_top, 0), P3(-COLLAR_HW, fy_top, 0))
                    _Lc.addByTwoPoints(P3(-COLLAR_HW, fy_top, 0), P3(-COLLAR_HW, fy_b,   0))
                    if _sk_c.profiles.count > 0:
                        _pc = min(
                            [_sk_c.profiles.item(_i) for _i in range(_sk_c.profiles.count)],
                            key=lambda p: (
                                (p.boundingBox.maxPoint.x - p.boundingBox.minPoint.x) *
                                (p.boundingBox.maxPoint.y - p.boundingBox.minPoint.y)))
                        _ei_c = comp_extrudes.createInput(
                            _pc, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                        # setTwoSidesExtent needs DistanceExtentDefinition, not bare ValueInput
                        _d_nut  = adsk.fusion.DistanceExtentDefinition.create(
                            adsk.core.ValueInput.createByReal(COLLAR_LEN))
                        _d_boss = adsk.fusion.DistanceExtentDefinition.create(
                            adsk.core.ValueInput.createByReal(BOSS_OWN))
                        if _toward_nut:
                            _ei_c.setTwoSidesExtent(_d_nut, _d_boss)
                        else:
                            _ei_c.setTwoSidesExtent(_d_boss, _d_nut)
                        _fc = comp_extrudes.add(_ei_c)
                        if _fc.bodies.count > 0:
                            _collar = _fc.bodies.item(0)
                            _collar.name = f'Collar_{joint_num}'
                            try:
                                _collar_vol = _collar.physicalProperties.volume
                            except Exception:
                                pass
                    else:
                        _collar_err = 'no profile on cut_plane'
                        if ui:
                            ui.messageBox(f'Collar_{joint_num}: no profile')
                except Exception as _e_c:
                    _collar_err = str(_e_c)
                    if ui:
                        ui.messageBox(f'Collar failed (jct {joint_num}):\n'
                                      f'{_e_c}\n{traceback.format_exc()}')

                # ── VBore through collar only ─────────────────────────────────
                # Plane at wt+COLLAR_H-0.001 (inside collar top, avoids on-face bug).
                # participantBodies=[_collar] — bore_cx is 3.78mm into nut piece,
                # which is within the collar body (collar extends COLLAR_LEN=8mm). ✓
                _vbore_ok  = False
                _vbore_err = None
                if _collar is not None:
                    try:
                        _bb_cp = _bore_plane_at(wt + COLLAR_H + 0.001)  # free air above collar — avoids Z-flip inside body
                        _bb_sk = root.sketches.add(_bb_cp)
                        _bb_sk.name = f'VBore_{joint_num}'
                        _bb_sk.isLightBulbOn = False
                        _bb_sk.sketchCurves.sketchCircles.addByCenterRadius(
                            adsk.core.Point3D.create(bore_cx, bore_cy, 0), VBORE_R)
                        if _bb_sk.profiles.count > 0:
                            _bb_prof = min(
                                [_bb_sk.profiles.item(_i)
                                 for _i in range(_bb_sk.profiles.count)],
                                key=lambda p: (
                                    (p.boundingBox.maxPoint.x - p.boundingBox.minPoint.x) *
                                    (p.boundingBox.maxPoint.y - p.boundingBox.minPoint.y)))
                            _bb_tr  = _bb_sk.transform
                            _bb_skz = (_bb_tr.getCell(0,2)*iy.x +
                                       _bb_tr.getCell(1,2)*iy.y +
                                       _bb_tr.getCell(2,2)*iy.z)
                            _ei_bb = extrudes.createInput(
                                _bb_prof,
                                adsk.fusion.FeatureOperations.CutFeatureOperation)
                            _ei_bb.setDistanceExtent(
                                _bb_skz < 0,
                                adsk.core.ValueInput.createByReal(COLLAR_H + 0.002))
                            _ei_bb.participantBodies = [_collar]
                            extrudes.add(_ei_bb)
                            _vbore_ok = True
                            success = True
                            try:
                                _collar_vol_after = _collar.physicalProperties.volume
                            except Exception:
                                _collar_vol_after = None
                        else:
                            _vbore_err = 'no profile'
                            _collar_vol_after = None
                            if ui:
                                ui.messageBox(f'VBore_{joint_num}: no profile')
                    except Exception as _e_bb:
                        _vbore_err = str(_e_bb)
                        _collar_vol_after = None
                        if ui:
                            ui.messageBox(f'VBore failed (jct {joint_num}):\n'
                                          f'{_e_bb}\n{traceback.format_exc()}')

                # Capture state into validation record.
                _boss_vol_before = None
                try:
                    _boss_vol_before = body.physicalProperties.volume
                except Exception:
                    pass
                _bore_removed = None
                if _collar_vol is not None and _collar_vol_after is not None:
                    _bore_removed = round(_collar_vol - _collar_vol_after, 6)
                _val_rec['bore_cx'] = bore_cx
                _val_rec['bore_cy'] = bore_cy
                _val_rec['collar']['success'] = _collar is not None
                _val_rec['collar']['bodies_created'] = 1 if _collar is not None else 0
                _val_rec['collar']['error'] = _collar_err
                _val_rec['vbore']['success'] = _vbore_ok
                _val_rec['vbore']['profile_found'] = _vbore_ok or (_vbore_err != 'no profile')
                _val_rec['vbore']['error'] = _vbore_err
                _val_rec['volumes']['collar_vol'] = _collar_vol
                _val_rec['volumes']['collar_vol_after'] = _collar_vol_after
                _val_rec['volumes']['bore_removed'] = _bore_removed
                _val_rec['volumes']['boss_before'] = _boss_vol_before

            if body_is_lower:
                lower_track_idx = tp_idx
                # Nut piece: hex nut trap in floor.
                # Sketch at wt-0.001 (0.01 mm inside inner floor face).
                _nt_err = None
                _nt_profile_found = False
                _nut_vol_before = None
                _nut_vol_after  = None
                try:
                    _nt_name = body.name
                    for _rb in _all_bodies(root):
                        if _rb.name == _nt_name:
                            body = _rb
                            break
                    try:
                        _nut_vol_before = body.physicalProperties.volume
                    except Exception:
                        pass
                    _nt_cp = _bore_plane_at(wt + COLLAR_H + 0.001)  # free air above collar — avoids Z-flip inside body
                    _nt_sk = root.sketches.add(_nt_cp)
                    _nt_sk.name  = f'NutTrap_{joint_num}'
                    _nt_sk.isLightBulbOn = False
                    _nt_ln = _nt_sk.sketchCurves.sketchLines
                    for _i in range(6):
                        _na = adsk.core.Point3D.create(
                            bore_cx + M3_NUT_CR * math.cos(
                                _i * math.pi / 3 + math.pi / 6),
                            bore_cy + M3_NUT_CR * math.sin(
                                _i * math.pi / 3 + math.pi / 6), 0)
                        _nb = adsk.core.Point3D.create(
                            bore_cx + M3_NUT_CR * math.cos(
                                (_i+1) * math.pi / 3 + math.pi / 6),
                            bore_cy + M3_NUT_CR * math.sin(
                                (_i+1) * math.pi / 3 + math.pi / 6), 0)
                        _nt_ln.addByTwoPoints(_na, _nb)
                    if _nt_sk.profiles.count > 0:
                        _nt_profile_found = True
                        _nt_prof = min(
                            [_nt_sk.profiles.item(_i)
                             for _i in range(_nt_sk.profiles.count)],
                            key=lambda p: (
                                (p.boundingBox.maxPoint.x - p.boundingBox.minPoint.x) *
                                (p.boundingBox.maxPoint.y - p.boundingBox.minPoint.y)))
                        _nt_tr  = _nt_sk.transform
                        _nt_skz = (_nt_tr.getCell(0,2)*iy.x +
                                   _nt_tr.getCell(1,2)*iy.y +
                                   _nt_tr.getCell(2,2)*iy.z)
                        _ei_nt = extrudes.createInput(
                            _nt_prof,
                            adsk.fusion.FeatureOperations.CutFeatureOperation)
                        _ei_nt.setDistanceExtent(
                            _nt_skz < 0,
                            adsk.core.ValueInput.createByReal(COLLAR_H + M3_NUT_D + 0.001))
                        _ei_nt.participantBodies = [body]
                        extrudes.add(_ei_nt)
                        success = True
                        try:
                            _nut_vol_after = body.physicalProperties.volume
                        except Exception:
                            pass
                    else:
                        _nt_err = 'no profile'
                        if ui:
                            ui.messageBox(f'NutTrap_{joint_num}: no profile')
                except Exception as _e_trap:
                    _nt_err = str(_e_trap)
                    if ui:
                        ui.messageBox(f'NutTrap failed (jct {joint_num}):\n'
                                      f'{_e_trap}\n{traceback.format_exc()}')
                _trap_removed = (
                    round(_nut_vol_before - _nut_vol_after, 5)
                    if _nut_vol_before is not None and _nut_vol_after is not None
                    else None)
                _val_rec['nuttrap']['success'] = success and _nt_profile_found
                _val_rec['nuttrap']['profile_found'] = _nt_profile_found
                _val_rec['nuttrap']['error'] = _nt_err
                _val_rec['volumes']['nut_before']   = _nut_vol_before
                _val_rec['volumes']['nut_after']    = _nut_vol_after
                _val_rec['volumes']['trap_removed'] = _trap_removed
            else:
                upper_track_idx = tp_idx

        except Exception as e:
            if ui:
                ui.messageBox(f'RetainBoss join failed (jct {joint_num}, body {tp_idx}):\n'
                              f'{e}\n{traceback.format_exc()}')

    # ── Step 4 (wallsnap): cantilever snap-fit lap joint in the side walls ────
    # Male end = tongue per wall (Join); female end = pocket + window (Cut).
    # Floor + channel stay fully clear for the LED strip.  Geometry is direction-
    # independent (symmetric tongue/pocket); only the far-slab window/barb need a
    # side, taken from the male junction-face normal (robust at hairpins, unlike
    # CoM which degenerates there — see MEMORY.md).
    if LOCK_STYLE == 'wallsnap':
        th   = params['TRACK_HEIGHT']
        ch_h = th - wt                      # channel height (0.7 cm)
        # ── Male/female assignment — CONSISTENT, not parity-flipped ───────────
        # cut_normal is the path tangent (consistently oriented along the path),
        # so the body further along +cut_normal is the DOWNSTREAM piece and the
        # other is UPSTREAM.  Rule: downstream = male, upstream = female, at every
        # junction.  Then each piece is the downstream body at its leading
        # junction (male end) and the upstream body at its trailing junction
        # (female end) → exactly one male + one female end per piece.
        #
        # The previous `_lower_tp_idx` used a joint_num-parity flip, which made
        # the rule alternate each junction and produced male-male / female-female
        # pieces (tongues on both ends).  Use a RELATIVE CoM-dot comparison so the
        # pick stays valid even at hairpins where both CoMs land on the same side.
        if len(track_pairs) >= 2:
            _md = []
            for _b, _ in track_pairs[:2]:
                _c = _b.physicalProperties.centerOfMass
                _md.append((_c.x - cut_origin.x) * cut_normal.x +
                           (_c.y - cut_origin.y) * cut_normal.y +
                           (_c.z - cut_origin.z) * cut_normal.z)
            male_idx   = 0 if _md[0] >= _md[1] else 1   # downstream (+cut_normal)
            female_idx = 1 - male_idx
        else:
            male_idx   = 0
            female_idx = None
        ws_rec = {'male_idx': male_idx, 'female_idx': female_idx, 'walls': []}
        _val_rec['wallsnap'] = ws_rec

        if female_idx is None or fy_b is None:
            if ui:
                ui.messageBox(f'WallSnap jct {joint_num}: need 2 bodies + coords, skipping')
        else:
            male_body   = track_pairs[male_idx][0]
            female_body = track_pairs[female_idx][0]
            male_face   = track_pairs[male_idx][1]

            # Record male/female CoM so alternation can be verified from the JSON
            # alone: match pieces across junctions by CoM proximity — every piece
            # should appear as male at one junction and female at another.
            try:
                _mc = male_body.physicalProperties.centerOfMass
                ws_rec['male_com'] = [round(_mc.x, 3), round(_mc.y, 3), round(_mc.z, 3)]
            except Exception:
                ws_rec['male_com'] = None
            try:
                _fc2 = female_body.physicalProperties.centerOfMass
                ws_rec['female_com'] = [round(_fc2.x, 3), round(_fc2.y, 3), round(_fc2.z, 3)]
            except Exception:
                ws_rec['female_com'] = None

            # Female side along +cut_normal: prefer the male face's outward normal
            # (points away from male → toward female); fall back to CoM.
            def _female_dir():
                try:
                    if (male_face is not None and male_face.geometry.surfaceType ==
                            adsk.core.SurfaceTypes.PlaneSurfaceType):
                        n = male_face.geometry.normal.copy()
                        if male_face.isParamReversed:
                            n.scaleBy(-1.0)
                        d = (n.x * cut_normal.x + n.y * cut_normal.y +
                             n.z * cut_normal.z)
                        if abs(d) > 0.3:
                            return 1.0 if d > 0 else -1.0
                except Exception:
                    pass
                c = female_body.physicalProperties.centerOfMass
                d = ((c.x - cut_origin.x) * cut_normal.x +
                     (c.y - cut_origin.y) * cut_normal.y +
                     (c.z - cut_origin.z) * cut_normal.z)
                return 1.0 if d >= 0 else -1.0
            z_fem = _female_dir()

            # ── Stage 1: verify path-station math (no geometry change yet) ────
            # The sweep rewrite will place tongue/barb/pocket/window at true path
            # stations.  Before building it, confirm: (a) junction j really sits
            # at path ratio j/num_pieces (path_origin ≈ cut_origin), and (b) which
            # ratio direction (+/-) points toward the female piece — cut_normal
            # can't tell us (its sign alternates), so we sample the path and test
            # proximity to female_com.
            def _path_sample(ratio):
                """Return (origin, normal) of a plane at `ratio` along the path."""
                r = max(0.0, min(1.0, ratio))
                cin = root.constructionPlanes.createInput()
                cin.setByDistanceOnPath(path, adsk.core.ValueInput.createByReal(r))
                pl = root.constructionPlanes.add(cin)
                o = pl.geometry.origin.copy()
                n = pl.geometry.normal.copy()
                try: pl.deleteMe()
                except Exception: pass
                return o, n

            pdiag = {'have_path': path is not None, 'num_pieces': num_pieces,
                     'r_i': None, 'path_origin': None,
                     'origin_err': None, 'female_ratio_sign': None,
                     'dr_lap': None}
            if path is not None and num_pieces:
                try:
                    r_i = float(joint_num) / float(num_pieces)
                    pdiag['r_i'] = round(r_i, 5)
                    o0, _n0 = _path_sample(r_i)
                    pdiag['path_origin'] = [round(o0.x, 3), round(o0.y, 3), round(o0.z, 3)]
                    pdiag['origin_err'] = round(
                        ((o0.x - cut_origin.x) ** 2 + (o0.y - cut_origin.y) ** 2 +
                         (o0.z - cut_origin.z) ** 2) ** 0.5, 4)
                    # ratio span of one lap length, for placing trim planes later
                    if path_len and path_len > 0:
                        pdiag['dr_lap'] = round(SNAP_LAP_LEN / path_len, 6)
                    # which direction in ratio is toward female?  Sample ±a small
                    # step and compare to female_com.
                    fc = female_body.physicalProperties.centerOfMass
                    dr = (SNAP_LAP_LEN / path_len) if (path_len and path_len > 0) else 0.02
                    op, _ = _path_sample(r_i + dr)
                    om, _ = _path_sample(r_i - dr)
                    dp = (op.x - fc.x) ** 2 + (op.y - fc.y) ** 2 + (op.z - fc.z) ** 2
                    dm = (om.x - fc.x) ** 2 + (om.y - fc.y) ** 2 + (om.z - fc.z) ** 2
                    pdiag['female_ratio_sign'] = 1 if dp < dm else -1
                except Exception as _e_pd:
                    pdiag['error'] = str(_e_pd)
            ws_rec['path_diag'] = pdiag

            # Tongue/pocket height band: most of the wall height (compliant finger).
            _ya = fy_b - inward_b * (wt - SNAP_Y0_INSET)        # near outer floor
            _yb = fy_b + inward_b * (ch_h - SNAP_Y1_INSET)      # near channel top
            ylo, yhi = (_ya, _yb) if _ya < _yb else (_yb, _ya)

            def _rect_profile(sk, xa, xb, ya, yb):
                """Draw a rectangle in sketch-local coords; return its profile."""
                xlo, xhi = (xa, xb) if xa < xb else (xb, xa)
                yl,  yh  = (ya, yb) if ya < yb else (yb, ya)
                L = sk.sketchCurves.sketchLines
                L.addByTwoPoints(P3(xlo, yl, 0), P3(xhi, yl, 0))
                L.addByTwoPoints(P3(xhi, yl, 0), P3(xhi, yh, 0))
                L.addByTwoPoints(P3(xhi, yh, 0), P3(xlo, yh, 0))
                L.addByTwoPoints(P3(xlo, yh, 0), P3(xlo, yl, 0))
                best, best_a = None, 1e18
                for i in range(sk.profiles.count):
                    p  = sk.profiles.item(i); bb = p.boundingBox
                    a  = ((bb.maxPoint.x - bb.minPoint.x) *
                          (bb.maxPoint.y - bb.minPoint.y))
                    if a < best_a:
                        best_a, best = a, p
                return best

            def _rect_profile_xf(sk, src_xform, xa, xb, ya, yb):
                """Draw a rectangle whose corners are given in the cut_plane frame
                (src_xform), re-expressed in `sk`'s own frame.  Offset construction
                planes get an arbitrary 2-D origin/axes, so coords must be routed
                through world space — drawing raw (x,y) on them floats the result."""
                inv = sk.transform.copy(); inv.invert()
                def _loc(x, y):
                    p = adsk.core.Point3D.create(x, y, 0)
                    p.transformBy(src_xform)   # cut-plane local → world
                    p.transformBy(inv)         # world → this sketch's local
                    return adsk.core.Point3D.create(p.x, p.y, 0)  # project onto plane
                xlo, xhi = (xa, xb) if xa < xb else (xb, xa)
                yl,  yh  = (ya, yb) if ya < yb else (yb, ya)
                corners = [_loc(xlo, yl), _loc(xhi, yl), _loc(xhi, yh), _loc(xlo, yh)]
                L = sk.sketchCurves.sketchLines
                for i in range(4):
                    L.addByTwoPoints(corners[i], corners[(i + 1) % 4])
                best, best_a = None, 1e18
                for i in range(sk.profiles.count):
                    p  = sk.profiles.item(i); bb = p.boundingBox
                    a  = ((bb.maxPoint.x - bb.minPoint.x) *
                          (bb.maxPoint.y - bb.minPoint.y))
                    if a < best_a:
                        best_a, best = a, p
                return best

            def _toward_female(sk):
                """True if the sketch's +local-Z points toward the female side."""
                t = sk.transform
                zc = (t.getCell(0, 2) * cut_normal.x +
                      t.getCell(1, 2) * cut_normal.y +
                      t.getCell(2, 2) * cut_normal.z)
                return (zc > 0) == (z_fem > 0)

            def _offset_plane(comp, depth):
                """Plane parallel to cut_plane, `depth` toward the female side."""
                cin = comp.constructionPlanes.createInput()
                cin.setByOffset(cut_plane,
                                adsk.core.ValueInput.createByReal(z_fem * depth))
                pl = comp.constructionPlanes.add(cin)
                pl.isLightBulbOn = False
                return pl

            def _refetch(b):
                nm = b.name
                for _b in _all_bodies(root):
                    if _b.name == nm:
                        return _b
                return b

            def _bbw(b):
                """World bounding box of a body as [minx,miny,minz,maxx,maxy,maxz]."""
                try:
                    bb = b.boundingBox
                    return [round(bb.minPoint.x, 4), round(bb.minPoint.y, 4),
                            round(bb.minPoint.z, 4), round(bb.maxPoint.x, 4),
                            round(bb.maxPoint.y, 4), round(bb.maxPoint.z, 4)]
                except Exception:
                    return None

            # ── PATH-FOLLOWING (loft) wall-snap ───────────────────────────────
            # On curves a straight lap drifts off the wall (barb/window miss it).
            # Here every feature is lofted through cross-section profiles placed at
            # TRUE path stations (setByDistanceOnPath), so tongue/pocket/barb/window
            # all follow the curved wall and stay mutually aligned.  Falls back to
            # the straight loop below when the path isn't available.
            _use_sweep = (path is not None and num_pieces and
                          pdiag.get('origin_err') is not None and
                          pdiag['origin_err'] < 0.05 and
                          pdiag.get('r_i') is not None and
                          pdiag.get('female_ratio_sign') is not None and
                          path_len and path_len > 0)
            if _use_sweep:
                r_i = pdiag['r_i']
                sgn = pdiag['female_ratio_sign']   # +/- ratio dir toward female
                Lp  = path_len
                _NB = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
                _JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
                _CUT  = adsk.fusion.FeatureOperations.CutFeatureOperation
                cz1  = detect_tr.getCell(2, 1)                 # local-y → world-z
                Xl0  = (detect_tr.getCell(0, 0), detect_tr.getCell(1, 0))
                Rt0x, Rt0y = cut_normal.y, -cut_normal.x       # path-right at jct
                _r0 = (Rt0x * Rt0x + Rt0y * Rt0y) ** 0.5 or 1.0
                Rt0x /= _r0; Rt0y /= _r0
                s0 = 1.0 if (Xl0[0] * Rt0x + Xl0[1] * Rt0y) >= 0 else -1.0

                def _station_profile(dist, mag_lo, mag_hi, yl, yh, rside, name):
                    """Rect profile on a plane ⟂ the path at along-path `dist` from
                    the junction (dist>0 = toward female).  mag = |offset| from the
                    path centreline in the width direction; rside = which side."""
                    ratio = max(0.0, min(1.0, r_i + sgn * dist / Lp))
                    cin = root.constructionPlanes.createInput()
                    cin.setByDistanceOnPath(
                        path, adsk.core.ValueInput.createByReal(ratio))
                    pl = root.constructionPlanes.add(cin)
                    pl.isLightBulbOn = False
                    sk = root.sketches.add(pl)
                    sk.name = name; sk.isLightBulbOn = False
                    O = pl.geometry.origin; N = pl.geometry.normal
                    rtx, rty = N.y, -N.x
                    _rl = (rtx * rtx + rty * rty) ** 0.5 or 1.0
                    rtx /= _rl; rty /= _rl
                    inv = sk.transform.copy(); inv.invert()
                    def _c(mag, ly):
                        p = adsk.core.Point3D.create(
                            O.x + rtx * rside * mag,
                            O.y + rty * rside * mag,
                            cut_origin.z + cz1 * ly)
                        p.transformBy(inv)
                        return adsk.core.Point3D.create(p.x, p.y, 0)
                    corners = [_c(mag_lo, yl), _c(mag_hi, yl),
                               _c(mag_hi, yh), _c(mag_lo, yh)]
                    Lc = sk.sketchCurves.sketchLines
                    for i in range(4):
                        Lc.addByTwoPoints(corners[i], corners[(i + 1) % 4])
                    best, ba = None, 1e18
                    for i in range(sk.profiles.count):
                        p = sk.profiles.item(i); bb = p.boundingBox
                        a = ((bb.maxPoint.x - bb.minPoint.x) *
                             (bb.maxPoint.y - bb.minPoint.y))
                        if a < ba:
                            ba, best = a, p
                    return best

                def _loft(dists, mag_lo, mag_hi, yl, yh, rside, name):
                    lin = root.features.loftFeatures.createInput(_NB)
                    lin.isSolid = True
                    for k, dist in enumerate(dists):
                        pr = _station_profile(dist, mag_lo, mag_hi, yl, yh,
                                              rside, f'{name}_{k}')
                        if pr is None:
                            return None
                        lin.loftSections.add(pr)
                    lf = root.features.loftFeatures.add(lin)
                    return lf.bodies.item(0) if lf.bodies.count > 0 else None

                def _combine(target, tool, op):
                    tc = adsk.core.ObjectCollection.create()
                    tc.add(tool)
                    ci = root.features.combineFeatures.createInput(target, tc)
                    ci.operation = op
                    root.features.combineFeatures.add(ci)

                LAP  = SNAP_LAP_LEN; TT = SNAP_TONGUE_T; CL = SNAP_CL
                BL   = SNAP_BARB_LEN; BX = SNAP_BARB_X; BOSS_OWN = 0.30
                ih   = inner_hw
                # Extra DEPTH the female pocket/window run PAST the tongue/barb tips
                # (along the track).  FDM prints protrusions a hair long + pockets a
                # hair shallow, so with only CL clearance the tongue tip bottoms in
                # the wall pocket before the flat floor/outer-wall butt faces meet →
                # walls held apart while the floor closes.  0.5 mm of relief here
                # makes the butt faces (not the tongue) the seating stop.  Only the
                # far end grows; the catch face + cross-section fit are unchanged.
                POCKET_CLR = 0.05
                for wsign in (1.0, -1.0):
                    wlab = 'R' if wsign > 0 else 'L'
                    wrec = {'wall': wlab, 'method': 'loft',
                            'pocket_removed': None, 'window_removed': None,
                            'tongue_ok': False, 'barb_ok': False,
                            'error': None, 'diag': {}}
                    try:
                        rside = s0 * wsign
                        # tongue-band mags (|offset| from centreline, width dir)
                        m_ti, m_to = ih, ih + TT            # tongue band
                        # Window floor is DERIVED from the barb (see the constant
                        # block): deep enough for the barb to spring clear, no
                        # deeper, so the outer-wall skin stays printable.
                        m_wo = ih + SNAP_WIN_FLOOR
                        # Barb band — centred on the tongue, SHORTER than it, so
                        # it drops into the window with real clearance.
                        yb0 = (ylo + yhi) * 0.5 - SNAP_BARB_H * 0.5
                        yb1 = (ylo + yhi) * 0.5 + SNAP_BARB_H * 0.5
                        # Shared, DENSE lap stations (dist along path).  Tongue and
                        # pocket MUST loft through the SAME interior stations, or on a
                        # curve their ruled surfaces chord across the arc by DIFFERENT
                        # amounts (tongue starts back at -BOSS_OWN, pocket at -CL) →
                        # the gap opens well past CL → loose joint on bends, even
                        # though straight joints (colinear sections) stay tight.  With
                        # matched stations the two surfaces stay exactly CL apart.
                        _lap_st = [0.0, LAP*0.2, LAP*0.4, LAP*0.6, LAP*0.8, LAP]
                        # ── FEMALE cuts: pocket (inner half) + window (outer slab)
                        female_body = _refetch(female_body)
                        _vf0 = female_body.physicalProperties.volume
                        pk = _loft([-CL] + _lap_st + [LAP + POCKET_CLR],
                                   m_ti - CL, m_to + CL, ylo - CL, yhi + CL,
                                   rside, f'SnapPocket_{joint_num}_{wlab}')
                        if pk is not None:
                            _combine(_refetch(female_body), _refetch(pk), _CUT)
                            female_body = _refetch(female_body)
                            wrec['pocket_removed'] = round(
                                _vf0 - female_body.physicalProperties.volume, 5)
                        _vf1 = female_body.physicalProperties.volume
                        wn = _loft([LAP - BL - CL, LAP + POCKET_CLR],
                                   m_to, m_wo,
                                   yb0 - SNAP_BARB_ZCL, yb1 + SNAP_BARB_ZCL,
                                   rside, f'SnapWindow_{joint_num}_{wlab}')
                        if wn is not None:
                            _combine(_refetch(female_body), _refetch(wn), _CUT)
                            female_body = _refetch(female_body)
                            wrec['window_removed'] = round(
                                _vf1 - female_body.physicalProperties.volume, 5)
                        # ── MALE adds: tongue (inner half) + barb (catch step) ───
                        tongue = _loft([-BOSS_OWN] + _lap_st,
                                       m_ti, m_to, ylo, yhi,
                                       rside, f'SnapTongue_{joint_num}_{wlab}')
                        if tongue is not None:
                            _combine(_refetch(male_body), _refetch(tongue), _JOIN)
                            male_body = _refetch(male_body)
                            wrec['tongue_ok'] = True
                            wrec['diag']['tongue_bbox_world'] = _bbw(male_body)
                        # barb spans inner half (bridges to tongue) + step into slab.
                        # Ramp the OUTER step from full (m_to+BX) at the proximal/
                        # catch station down to flush (m_to) at the insertion tip:
                        # the tip cams the tongue in smoothly on assembly, while the
                        # proximal end-cap stays a square (90°) face that can't slide
                        # back out under pull.  Inner edge (m_ti) and height stay
                        # constant so only the protruding step tapers.
                        barb = None
                        _bl_in = root.features.loftFeatures.createInput(_NB)
                        _bl_in.isSolid = True
                        _pr_prox = _station_profile(
                            LAP - BL, m_ti, m_to + BX, yb0, yb1, rside,
                            f'SnapBarb_{joint_num}_{wlab}_0')   # full step (catch)
                        _pr_tip = _station_profile(
                            LAP, m_ti, m_to, yb0, yb1, rside,
                            f'SnapBarb_{joint_num}_{wlab}_1')    # flush (lead-in)
                        if _pr_prox is not None and _pr_tip is not None:
                            _bl_in.loftSections.add(_pr_prox)
                            _bl_in.loftSections.add(_pr_tip)
                            _bf = root.features.loftFeatures.add(_bl_in)
                            barb = _bf.bodies.item(0) if _bf.bodies.count > 0 else None
                        if barb is not None:
                            _combine(_refetch(male_body), _refetch(barb), _JOIN)
                            male_body = _refetch(male_body)
                            wrec['barb_ok'] = True
                        success = True
                    except Exception as _e_ws:
                        wrec['error'] = str(_e_ws)
                        if ui:
                            ui.messageBox(
                                f'WallSnap(loft) failed (jct {joint_num}, {wlab}):\n'
                                f'{_e_ws}\n{traceback.format_exc()}')
                    ws_rec['walls'].append(wrec)

                # ── Floor half-lap (one per junction, spans the channel) ─────
                # Not per-wall, so it sits outside the wall loop.  Heights come
                # from the MEASURED floor faces (fy_b / inward_b), the same
                # source the wall band uses, so the arbitrary per-junction sign
                # of the sketch frame can't flip it.
                frec = {'tongue_ok': False, 'pocket_removed': None,
                        'error': None}
                try:
                    _fa = fy_b - inward_b * wt              # outer floor face
                    _fb = _fa + inward_b * SNAP_FLOOR_TT    # top of the tongue
                    flo, fhi = (_fa, _fb) if _fa < _fb else (_fb, _fa)
                    _fst = [0.0, LAP * 0.25, LAP * 0.5, LAP * 0.75, LAP]
                    # Relieve the female first, then grow the male's tongue.
                    female_body = _refetch(female_body)
                    _vf0 = female_body.physicalProperties.volume
                    fpk = _loft([-CL] + _fst + [LAP + POCKET_CLR],
                                -(ih + CL), ih + CL, flo - CL, fhi + CL,
                                1.0, f'SnapFloorPocket_{joint_num}')
                    if fpk is not None:
                        _combine(_refetch(female_body), _refetch(fpk), _CUT)
                        female_body = _refetch(female_body)
                        frec['pocket_removed'] = round(
                            _vf0 - female_body.physicalProperties.volume, 5)
                    # Starts BOSS_OWN inside its own piece so the JOIN has
                    # overlap to bond to, exactly like the wall tongue.
                    ftg = _loft([-BOSS_OWN] + _fst, -ih, ih, flo, fhi, 1.0,
                                f'SnapFloorTongue_{joint_num}')
                    if ftg is not None:
                        _combine(_refetch(male_body), _refetch(ftg), _JOIN)
                        male_body = _refetch(male_body)
                        frec['tongue_ok'] = True
                except Exception as _e_fl:
                    frec['error'] = str(_e_fl)
                ws_rec['floor'] = frec

            if not _use_sweep:
                # The straight fallback builds walls only.  Say so rather than
                # letting a junction quietly come out without a floor key.
                ws_rec['floor'] = {'skipped': 'straight fallback (no path)'}
            for wsign in (1.0, -1.0) if not _use_sweep else []:
                wlab = 'R' if wsign > 0 else 'L'
                wrec = {'wall': wlab, 'pocket_removed': None,
                        'window_removed': None, 'tongue_ok': False,
                        'barb_ok': False, 'error': None, 'diag': {}}
                try:
                    x_in  = wsign * inner_hw                 # channel-side wall face
                    x_out = wsign * (inner_hw + wt)          # outer wall face
                    x_tng = x_in + wsign * SNAP_TONGUE_T     # tongue/backing split
                    # Window floor derived from the barb — see the loft path above.
                    x_win = x_in + wsign * SNAP_WIN_FLOOR
                    # Barb band: centred on the tongue, shorter than it.
                    yb0 = (ylo + yhi) * 0.5 - SNAP_BARB_H * 0.5
                    yb1 = (ylo + yhi) * 0.5 + SNAP_BARB_H * 0.5

                    # ── FEMALE: pocket (clear inner half over the lap) ────────
                    fcomp = female_body.parentComponent
                    fex   = fcomp.features.extrudeFeatures
                    female_body = _refetch(female_body)
                    sk_p = fcomp.sketches.add(cut_plane)
                    sk_p.name = f'SnapPocket_{joint_num}_{wlab}'
                    sk_p.isLightBulbOn = False
                    cxf_f = sk_p.transform.copy()    # cut_plane frame (female comp)
                    pr_p = _rect_profile(sk_p,
                                         x_in - wsign * SNAP_CL,
                                         x_tng + wsign * SNAP_CL,
                                         ylo - SNAP_CL, yhi + SNAP_CL)

                    # ── Diagnostics: pin down why a wall removes 0 ────────────
                    # cxf_f maps cut-plane local (x,y,0) → world.  We log the
                    # local-X world axis (flip check), z_fem, the rectangle's
                    # world corners, the female-body world bbox, and the profile
                    # count/centre — enough to tell a frame-flip from a curvature
                    # miss from a min-area mis-pick without a screenshot.
                    try:
                        def _w(x, y):
                            p = adsk.core.Point3D.create(x, y, 0)
                            p.transformBy(cxf_f)
                            return [round(p.x, 4), round(p.y, 4), round(p.z, 4)]
                        _xlo = x_in - wsign * SNAP_CL
                        _xhi = x_tng + wsign * SNAP_CL
                        _corners = [_w(_xlo, ylo - SNAP_CL), _w(_xhi, ylo - SNAP_CL),
                                    _w(_xhi, yhi + SNAP_CL), _w(_xlo, yhi + SNAP_CL)]
                        _pc = None
                        if pr_p is not None:
                            try:
                                _pbb = pr_p.boundingBox
                                _pc = [round((_pbb.minPoint.x + _pbb.maxPoint.x) / 2, 4),
                                       round((_pbb.minPoint.y + _pbb.maxPoint.y) / 2, 4),
                                       round((_pbb.minPoint.z + _pbb.maxPoint.z) / 2, 4)]
                            except Exception:
                                pass
                        wrec['diag'] = {
                            'wsign': wsign,
                            'x_in': round(x_in, 4), 'x_tng': round(x_tng, 4),
                            'z_fem': z_fem,
                            'local_x_world': [round(cxf_f.getCell(0, 0), 4),
                                              round(cxf_f.getCell(1, 0), 4),
                                              round(cxf_f.getCell(2, 0), 4)],
                            'cut_normal': [round(cut_normal.x, 4),
                                           round(cut_normal.y, 4),
                                           round(cut_normal.z, 4)],
                            'pocket_rect_world': _corners,
                            'pocket_profiles_count': sk_p.profiles.count,
                            'pocket_profile_found': pr_p is not None,
                            'pocket_profile_centre_world': _pc,
                            'female_bbox_world': _bbw(female_body),
                            'female_com_world': None,
                        }
                        try:
                            _fc = female_body.physicalProperties.centerOfMass
                            wrec['diag']['female_com_world'] = [
                                round(_fc.x, 4), round(_fc.y, 4), round(_fc.z, 4)]
                        except Exception:
                            pass
                    except Exception as _e_diag:
                        wrec['diag']['diag_error'] = str(_e_diag)

                    vb = female_body.physicalProperties.volume
                    ei = fex.createInput(
                        pr_p, adsk.fusion.FeatureOperations.CutFeatureOperation)
                    ei.setSymmetricExtent(
                        adsk.core.ValueInput.createByReal(SNAP_LAP_LEN + SNAP_CL),
                        False)
                    ei.participantBodies = [female_body]
                    fex.add(ei)
                    female_body = _refetch(female_body)
                    wrec['pocket_removed'] = round(
                        vb - female_body.physicalProperties.volume, 5)

                    # ── FEMALE: window (open backing at far slab for the barb) ─
                    pw = _offset_plane(
                        fcomp, SNAP_LAP_LEN - SNAP_BARB_LEN - SNAP_CL)
                    sk_w = fcomp.sketches.add(pw)
                    sk_w.name = f'SnapWindow_{joint_num}_{wlab}'
                    sk_w.isLightBulbOn = False
                    pr_w = _rect_profile_xf(sk_w, cxf_f, x_tng, x_win,
                                            yb0 - SNAP_BARB_ZCL,
                                            yb1 + SNAP_BARB_ZCL)
                    vb = female_body.physicalProperties.volume
                    eiw = fex.createInput(
                        pr_w, adsk.fusion.FeatureOperations.CutFeatureOperation)
                    eiw.setDistanceExtent(
                        _toward_female(sk_w),
                        adsk.core.ValueInput.createByReal(
                            SNAP_BARB_LEN + 2 * SNAP_CL))
                    eiw.participantBodies = [female_body]
                    fex.add(eiw)
                    female_body = _refetch(female_body)
                    wrec['window_removed'] = round(
                        vb - female_body.physicalProperties.volume, 5)

                    # ── MALE: tongue + barb ───────────────────────────────────
                    # Built as NEW BODIES, then merged into the male body ONLY via
                    # an explicit combineFeatures.  A plain JoinFeatureOperation
                    # extrude welds to EVERY body it touches (can't be restricted),
                    # which fused adjacent pieces — combine with an explicit target
                    # guarantees the female piece is never consumed.
                    mcomp = male_body.parentComponent
                    mex   = mcomp.features.extrudeFeatures
                    combs = mcomp.features.combineFeatures
                    male_body = _refetch(male_body)
                    sk_t = mcomp.sketches.add(cut_plane)
                    sk_t.name = f'SnapTongue_{joint_num}_{wlab}'
                    sk_t.isLightBulbOn = False
                    cxf_m = sk_t.transform.copy()    # cut_plane frame (male comp)
                    pr_t = _rect_profile(sk_t, x_in, x_tng, ylo, yhi)
                    d_lap_a = adsk.fusion.DistanceExtentDefinition.create(
                        adsk.core.ValueInput.createByReal(SNAP_LAP_LEN))
                    d_lap_b = adsk.fusion.DistanceExtentDefinition.create(
                        adsk.core.ValueInput.createByReal(SNAP_LAP_LEN))
                    eit = mex.createInput(
                        pr_t, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                    eit.setTwoSidesExtent(d_lap_a, d_lap_b)
                    ft = mex.add(eit)
                    t_body = ft.bodies.item(0)
                    t_body.name = f'SnapTBody_{joint_num}_{wlab}'
                    wrec['tongue_ok'] = True

                    # barb: bump on tongue tip → springs into the window.
                    pb = _offset_plane(mcomp, SNAP_LAP_LEN - SNAP_BARB_LEN)
                    sk_b = mcomp.sketches.add(pb)
                    sk_b.name = f'SnapBarb_{joint_num}_{wlab}'
                    sk_b.isLightBulbOn = False
                    pr_b = _rect_profile_xf(
                        sk_b, cxf_m, x_tng - wsign * SNAP_BARB_OVL,
                        x_tng + wsign * SNAP_BARB_X, yb0, yb1)
                    eib = mex.createInput(
                        pr_b, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                    # Sketch is on the offset plane = barb's PROXIMAL (catch) face.
                    # Extrude toward the tip with a negative taper so the catch face
                    # stays full-size (square, grips the window) while the insertion
                    # tip ramps in — flexes the tongue smoothly on assembly.
                    _barb_dir = (adsk.fusion.ExtentDirections.PositiveExtentDirection
                                 if _toward_female(sk_b)
                                 else adsk.fusion.ExtentDirections.NegativeExtentDirection)
                    eib.setOneSideExtent(
                        adsk.fusion.DistanceExtentDefinition.create(
                            adsk.core.ValueInput.createByReal(SNAP_BARB_LEN)),
                        _barb_dir,
                        adsk.core.ValueInput.createByString(f'-{SNAP_BARB_RAMP} deg'))
                    fb = mex.add(eib)
                    b_body = fb.bodies.item(0)
                    b_body.name = f'SnapBBody_{joint_num}_{wlab}'
                    wrec['barb_ok'] = True

                    # ── Diagnostics: does the barb actually land in the window? ──
                    # Project CoMs onto cut_normal (along-path distance from the
                    # junction).  Barb and window should both centre at
                    # z_fem*(LAP - BARB_LEN/2); the tongue is symmetric so ~0.
                    try:
                        def _along(pt):
                            return round((pt.x - cut_origin.x) * cut_normal.x +
                                         (pt.y - cut_origin.y) * cut_normal.y +
                                         (pt.z - cut_origin.z) * cut_normal.z, 4)
                        _tc = t_body.physicalProperties.centerOfMass
                        _bc = b_body.physicalProperties.centerOfMass
                        wrec['diag']['tongue_com_along'] = _along(_tc)
                        wrec['diag']['barb_com_along']   = _along(_bc)
                        wrec['diag']['barb_window_along_expected'] = round(
                            z_fem * (SNAP_LAP_LEN - SNAP_BARB_LEN / 2), 4)
                        wrec['diag']['window_depth_range'] = [
                            round(z_fem * (SNAP_LAP_LEN - SNAP_BARB_LEN - SNAP_CL), 4),
                            round(z_fem * (SNAP_LAP_LEN + SNAP_CL), 4)]
                        wrec['diag']['tongue_bbox_world'] = _bbw(t_body)
                        wrec['diag']['barb_bbox_world']   = _bbw(b_body)
                    except Exception as _e_bd:
                        wrec['diag']['barb_diag_error'] = str(_e_bd)

                    # Merge barb into tongue, then tongue(+barb) into male ONLY.
                    # Re-fetch by name before each createInput — a preceding
                    # NewBody add silently staleness the body pointers (MEMORY.md).
                    t_body = _refetch(t_body)
                    tc1 = adsk.core.ObjectCollection.create()
                    tc1.add(_refetch(b_body))
                    ci1 = combs.createInput(t_body, tc1)
                    ci1.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                    combs.add(ci1)

                    male_body = _refetch(male_body)
                    t_body    = _refetch(t_body)
                    tc2 = adsk.core.ObjectCollection.create()
                    tc2.add(t_body)
                    ci2 = combs.createInput(male_body, tc2)
                    ci2.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                    combs.add(ci2)
                    male_body = _refetch(male_body)

                    success = True
                except Exception as _e_ws:
                    wrec['error'] = str(_e_ws)
                    if ui:
                        ui.messageBox(
                            f'WallSnap failed (jct {joint_num}, wall {wlab}):\n'
                            f'{_e_ws}\n{traceback.format_exc()}')
                ws_rec['walls'].append(wrec)

    # Step 4b: bore and nut trap are now handled inline in Step 4 (boss branch
    # cuts bore into boss_body_new before combine; nut branch cuts trap into
    # combined body after combine).  Nothing to do here.
    if False and LOCK_STYLE == 'vscrew' and track_bodies:
        VBORE_R   = 0.17    # 1.7 mm radius = 3.4 mm dia (M3 clearance)
        M3_NUT_CR = 0.328   # M3 nut circumradius (AF=5.5 mm + 0.1 mm tol)
        M3_NUT_D  = 0.24    # M3 nut height 2.4 mm; trap bites into nut pad → 2.6 mm floor below

        # Use Step 4's recorded indices — avoids CoM re-identification which
        # fails at hairpins where both bodies' CoMs land on the same side.
        upper_body = None; lower_body = None
        if lower_track_idx is not None and lower_track_idx < len(track_bodies):
            lower_body = track_bodies[lower_track_idx]
        if upper_track_idx is not None and upper_track_idx < len(track_bodies):
            upper_body = track_bodies[upper_track_idx]
        # If one assignment is missing (combine was skipped), assign the other body
        if lower_body is None and upper_body is not None and len(track_bodies) == 2:
            lower_body = track_bodies[1 - upper_track_idx]
        if upper_body is None and lower_body is not None and len(track_bodies) == 2:
            upper_body = track_bodies[1 - lower_track_idx]

        if upper_body is None or lower_body is None:
            if ui:
                ui.messageBox(f'VBore jct {joint_num}: cannot identify upper/lower bodies '
                               f'(lower_idx={lower_track_idx}, upper_idx={upper_track_idx})')
        else:
            # Bore/nut centre is at _NUT_INSET (≈3.48mm) into the nut piece —
            # matches the boss midpoint so collar, bore, and nut trap are co-axial.
            _nut_sign   = 1.0 if is_lower_pos else -1.0
            bore_cx = cut_origin.x + _nut_sign * _NUT_INSET * cut_normal.x
            bore_cy = cut_origin.y + _nut_sign * _NUT_INSET * cut_normal.y

            def _bore_plane_at(height):
                """Plane at world Z = cut_origin.z + height via XY-plane offset.
                Track is flat in XY so iy = world +Z; sketch-Z of the resulting
                plane = +iy.  Bore cuts use isPositive=False → -iy = downward."""
                cp_in = root.constructionPlanes.createInput()
                cp_in.setByOffset(
                    root.xYConstructionPlane,
                    adsk.core.ValueInput.createByReal(cut_origin.z + height))
                cp = root.constructionPlanes.add(cp_in)
                cp.isLightBulbOn = False
                return cp

            def _bore_cut_at(body, height, bore_depth, bore_name):
                """Circle bore at junction centre (cut_origin.x/y), cutting in -iy."""
                cp = _bore_plane_at(height)
                sk = root.sketches.add(cp)
                sk.name = bore_name
                sk.isLightBulbOn = False
                sk.sketchCurves.sketchCircles.addByCenterRadius(
                    adsk.core.Point3D.create(bore_cx, bore_cy, 0), VBORE_R)
                if sk.profiles.count == 0:
                    if ui: ui.messageBox(f'{bore_name}: bore profile empty')
                    return False
                best_bp = min(
                    [sk.profiles.item(i) for i in range(sk.profiles.count)],
                    key=lambda p: ((p.boundingBox.maxPoint.x-p.boundingBox.minPoint.x)*
                                   (p.boundingBox.maxPoint.y-p.boundingBox.minPoint.y)))
                # Determine direction dynamically: cut in -iy (downward toward outer floor).
                # skz_iy > 0 → sketch-Z = +iy → isPositive=False cuts in -iy ✓
                # skz_iy < 0 → sketch-Z = -iy → isPositive=True  cuts in -iy ✓
                sk_tr  = sk.transform
                skz_iy = (sk_tr.getCell(0,2)*iy.x +
                          sk_tr.getCell(1,2)*iy.y +
                          sk_tr.getCell(2,2)*iy.z)
                ei = extrudes.createInput(
                    best_bp, adsk.fusion.FeatureOperations.CutFeatureOperation)
                ei.setDistanceExtent(skz_iy < 0,
                                     adsk.core.ValueInput.createByReal(bore_depth))
                ei.participantBodies = [body]
                extrudes.add(ei)
                return True

            # ── Bore: boss body only ──────────────────────────────────────────
            # Bore from collar top downward through boss material only.
            # Boss spans [fy_boss_b, fy_top]; depth = COLLAR_H - NUT_PAD_H - PAD_CLR.
            # The bolt falls freely across the PAD_CLR gap before entering the nut trap.
            try:
                _boss_bore_depth = COLLAR_H - NUT_PAD_H - PAD_CLR
                if _bore_cut_at(upper_body, wt + COLLAR_H, _boss_bore_depth,
                                f'VBore_{joint_num}_upper'):
                    success = True
            except Exception as e_u:
                if ui:
                    ui.messageBox(f'VBore upper failed (jct {joint_num}):\n'
                                  f'{e_u}\n{traceback.format_exc()}')

            # ── Nut trap: nut pad top face (lower body) ───────────────────────
            # Sketch in free air at wt+COLLAR_H (avoids on-face profile failure).
            # Depth = COLLAR_H - NUT_PAD_H + M3_NUT_D: traverses air gap, enters
            # nut pad at its top, bites M3_NUT_D deep → 2.6 mm solid floor below.
            try:
                nut_cp = _bore_plane_at(wt + COLLAR_H)
                nut_sk = root.sketches.add(nut_cp)
                nut_sk.name = f'NutTrap_{joint_num}'
                nut_sk.isLightBulbOn = False
                sk_ln = nut_sk.sketchCurves.sketchLines
                for i in range(6):
                    a = adsk.core.Point3D.create(
                        bore_cx + M3_NUT_CR*math.cos( i   *math.pi/3 + math.pi/6),
                        bore_cy + M3_NUT_CR*math.sin( i   *math.pi/3 + math.pi/6), 0)
                    b = adsk.core.Point3D.create(
                        bore_cx + M3_NUT_CR*math.cos((i+1)*math.pi/3 + math.pi/6),
                        bore_cy + M3_NUT_CR*math.sin((i+1)*math.pi/3 + math.pi/6), 0)
                    sk_ln.addByTwoPoints(a, b)
                if nut_sk.profiles.count > 0:
                    best_np = max(
                        [nut_sk.profiles.item(i) for i in range(nut_sk.profiles.count)],
                        key=lambda p: ((p.boundingBox.maxPoint.x-p.boundingBox.minPoint.x)*
                                       (p.boundingBox.maxPoint.y-p.boundingBox.minPoint.y)))
                    nt_tr    = nut_sk.transform
                    skz_iy_n = (nt_tr.getCell(0,2)*iy.x +
                                nt_tr.getCell(1,2)*iy.y +
                                nt_tr.getCell(2,2)*iy.z)
                    _nut_trap_depth = COLLAR_H - NUT_PAD_H + M3_NUT_D
                    ei_n = extrudes.createInput(
                        best_np, adsk.fusion.FeatureOperations.CutFeatureOperation)
                    ei_n.setDistanceExtent(skz_iy_n < 0,   # cut downward (-iy) toward outer floor
                                           adsk.core.ValueInput.createByReal(_nut_trap_depth))
                    ei_n.participantBodies = [lower_body]
                    extrudes.add(ei_n)
                elif ui:
                    ui.messageBox(f'NutTrap jct {joint_num}: nut profile empty')
            except Exception as e_l:
                if ui:
                    ui.messageBox(f'NutTrap failed (jct {joint_num}):\n'
                                   f'{e_l}\n{traceback.format_exc()}')

    # Phase 3: socket cuts + H-key (skipped for vscrew/wallsnap — they replace H-key)
    if LOCK_STYLE not in ('bore', 'vscrew', 'wallsnap'):
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

    # ── H-key body — one per junction (stud mode only) ───────────────────────
    key_exists = any(b.name == f'Connector_Key_{joint_num}' for b in root.bRepBodies)
    if not key_exists and LOCK_STYLE not in ('bore', 'vscrew', 'wallsnap'):
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

    _val_rec['success'] = success
    return _val_rec


# =============================================================================
# WALL-MOUNT BRACKET  (adjustable standoff, one per junction)
# =============================================================================

# Master enable — set False to skip wall brackets entirely.
WALL_BRACKET_ENABLED = True


def create_wall_bracket(root, cut_plane, params, joint_num, ui=None,
                        path=None, path_len=0.0, num_pieces=0, wall_top_z=None):
    """Add TWO integrated wall-mount standoff feet at a junction.

    Not separate parts — a small boss is grown on EACH wall-tip face at the
    junction and welded (combineFeatures JOIN) INTO the adjacent track piece, so
    each foot prints as part of the piece (no standalone body).  Two feet (one
    per wall) give a stable, symmetric mount per junction.

    Why here and not a plate across the channel: the wall-facing side IS the
    LED's exit aperture, so any material spanning the inner-channel opening
    blocks the strip and casts a shadow.  The two 3 mm wall tips are opaque and
    already shadow the wall, so a boss that stays OVER a wall band (bulging only
    OUTBOARD, never toward the opening) adds no new obstruction and no shadow.

    ORIENTATION-FREE by design (so one script serves any F1 track in any hang
    orientation the customer picks): the mount is ISOTROPIC — the screw axis is
    the track normal (_iyw = wall side), needing no in-plane "up".  Each foot is
    independent and self-locating (drill/drive straight through its own bore), so
    a rigid multi-mount loop is never over-constrained.  The bore is OVERSIZED
    (forgiving) with a wall-side counterbore for a captive nut / heat-set insert
    + lock nut → standoff set once and locked; the gap (LED diffusion) is pure
    hardware, no reprint, no geometry encodes it.  cut_at_planes assembles a 1:1
    drilling template from the returned screw positions.

    Feet are offset ~CONN_CLEAR past the seam so they clear the wallsnap
    connector (which lives within ±SNAP_LAP_LEN of the seam) — no collision.

    PATH-FOLLOWING: each foot is LOFTED through stations that ride the true path
    (setByDistanceOnPath), so it hugs the curved wall instead of chording across
    it as a straight prism did (same fix as the wallsnap loft).  Falls back to a
    straight extrude when the path isn't available.

    Assumes a flat-XY track (screw axis = world Z); returns a dict record
    including rec['screws'] = [[x, y], ...] world positions for the template.
    """
    rec = {'joint': joint_num, 'success': False, 'screws': []}
    if not WALL_BRACKET_ENABLED:
        rec['skipped'] = 'disabled'
        return rec

    # ── Tunable constants (cm) ────────────────────────────────────────────────
    wt        = params['WALL_THICKNESS']
    th        = params['TRACK_HEIGHT']
    outer_hw  = params['TRACK_WIDTH'] / 2.0                 # outer wall face |x|
    inner_hw  = (params['TRACK_WIDTH'] - 2.0 * wt) / 2.0    # inner wall face |x|

    # ── Integrated single-ear bracket (2026-08-05) ───────────────────────────
    # Supersedes BOTH the bored foot and the dovetail-stud + separate-plaque
    # design.  ONE bracket per junction, welded into the piece, reaching all the
    # way to the wall and carrying its screw on an ear OUTBOARD of the track.
    # What that removes, versus stud + plaque:
    #   • every fit tolerance between track and mount (no rails, no dovetail);
    #   • the simultaneous-engagement problem — the mount IS the piece;
    #   • the R≈3 cm curve limit imposed by a straight rail on a curved wall;
    #   • 18 separate printed parts;
    #   • the plaque plate that spanned the channel and shadowed the halo at
    #     every junction — a bracket on one wall tip never crosses the channel.
    # The cost is that the standoff gap is now PRINTED GEOMETRY: changing the
    # LED gap means reprinting pieces, not small parts.
    FOOT_LEN   = 1.20    # 12 mm along the track
    FOOT_EMBED = 0.30    # 3 mm INTO the wall crest — this overlap IS the weld:
                         # 0.25 × 0.30 × 1.20 = 0.090 cm³, vs 0.020 for the old
                         # 1 mm lap, which left joint 4 with just 0.0011 cm³
                         # once the straight foot chorded off the arc.
    EAR_T      = 0.40    # ear plate: 2 mm of counterbore + 2 mm above it
    RIB_T      = 0.25    # gusset rib thickness — TWO ribs, at the ENDS of the
                         # length, NOT a solid 45° wedge across it.  A wedge
                         # would put the screw's counterbore mouth on a sloped
                         # face, which is exactly what made the original foot's
                         # screw seat unusable.  Ribs leave the middle of the
                         # ear's underside flat and horizontal for the head and
                         # the cap, and the gap between them bridges.
    IN_MARGIN  = 0.05    # hold the bracket 0.5 mm clear of the channel edge so
                         # curve drift can never push it over the LED aperture
    EAR_SIDE   = 1.0     # +1 = path-right.  Keep it CONSTANT: the path is
                         # consistently oriented, so one local side means all
                         # ears land on the same side of the loop, which reads
                         # deliberate.  Flip to -1.0 to put them all inboard.
    BORE_R     = 0.17    # M3 clearance through the ear
    CBORE_R    = 0.32    # head recess, on the VIEWER side; the cap plugs it
    CBORE_D    = 0.20
    CONN_CLEAR = 1.50    # 15 mm past the seam (SNAP_LAP_LEN 1.20 + the 0.5 mm
                         # pocket relief + margin) so the feet clear the
                         # wallsnap zone.  Raised from 1.00 when the lap grew
                         # 8 → 12 mm.  A piece now needs CONN_CLEAR + FOOT_LEN
                         # of length past each seam to host its feet.

    # No bores in the track any more — the M3 lives in the plaque.  (The old
    # BORE_R 0.18 / CBORE_R 0.32 / CBORE_D 0.35 are deliberately gone: the
    # Ø6.4 counterbore was wider than the foot it sat in and broke out through
    # both the chamfer and the LED channel.)

    # ── Orientation frame ─────────────────────────────────────────────────────
    detect_sk = root.sketches.add(cut_plane)
    detect_tr = detect_sk.transform.copy()
    detect_sk.isLightBulbOn = False
    try: detect_sk.deleteMe()
    except Exception: pass
    cz1  = detect_tr.getCell(2, 1)                    # local-y (floor->wall) -> world-z
    _ays = 1.0 if cz1 >= 0.0 else -1.0
    _iyw = adsk.core.Vector3D.create(
        _ays * detect_tr.getCell(0, 1),
        _ays * detect_tr.getCell(1, 1),
        _ays * detect_tr.getCell(2, 1))
    _iyw.normalize()
    # v1 assumes a flat-XY track so the floor->wall axis (screw axis) is world Z
    # — the bores are cut on the permanent xY plane.  _ays makes _iyw always
    # point +Z here, so the wall side is +Z and the screw goes +Z.
    if abs(_iyw.z) < 0.9:
        rec['skipped'] = 'non-flat track (v1 needs flat XY)'
        return rec

    cut_geom   = cut_plane.geometry
    cut_origin = cut_geom.origin
    cut_normal = cut_geom.normal.copy(); cut_normal.normalize()

    def _by_name(name):
        for b in _all_bodies(root):
            if b.name == name:
                return b
        return None

    # ── Guard: already built here (the master profile sketch persists) ────────
    try:
        if root.sketches.itemByName(f'WBMasterProf_{joint_num}') is not None:
            rec['skipped'] = 'exists'; rec['success'] = True
            return rec
    except Exception:
        pass

    # ── Adjacent track bodies; pick the downstream (+cut_normal) host piece ────
    # Both feet weld into the SAME piece (offset past the connector on one side
    # of the seam) — the connector already ties the two pieces together.
    adjacent    = find_bodies_at_cut(root, cut_plane)
    track_pairs = [(b, f) for b, f in adjacent if b.name.startswith('Track_')]
    if not track_pairs:
        rec['skipped'] = 'no track bodies at cut'
        return rec
    rec['track_bodies'] = len(track_pairs)

    host = other = None
    if len(track_pairs) >= 2:
        try:
            d = []
            for b, _ in track_pairs[:2]:
                c = b.physicalProperties.centerOfMass
                d.append((c.x - cut_origin.x) * cut_normal.x +
                         (c.y - cut_origin.y) * cut_normal.y +
                         (c.z - cut_origin.z) * cut_normal.z)
            if d[0] >= d[1]:
                host, other = track_pairs[0][0], track_pairs[1][0]
            else:
                host, other = track_pairs[1][0], track_pairs[0][0]
        except Exception:
            host, other = track_pairs[0][0], track_pairs[1][0]
    else:
        host = track_pairs[0][0]

    # Reference the MEASURED wall height, not the TRACK_HEIGHT param.  The foot's
    # embed/protrusion (y_lo/y_hi below) are built off `th`; if the modeled track
    # is taller than the param, a param-based foot top lands at/under the real
    # wall tip and the wall pokes through the foot's top face.
    #   th = wall_tip_z − cut_origin.z (outer floor face).
    # Prefer the GLOBAL wall_top_z measured once before any foot existed: a
    # per-host bbox is contaminated by feet already welded in from neighbouring
    # junctions (its max-Z reads foot-top, not wall-tip), which made later feet
    # climb and the heights diverge.  Fall back to this host's bbox, then param.
    rec['th_param'] = round(th, 3)
    try:
        if wall_top_z is not None:
            _th_meas = wall_top_z - cut_origin.z
            rec['th_src'] = 'global'
        else:
            _th_meas = host.boundingBox.maxPoint.z - cut_origin.z
            rec['th_src'] = 'host_bbox'
        rec['th_measured'] = round(_th_meas, 3)
        if 0.5 <= _th_meas <= 3.0:
            th = _th_meas
    except Exception:
        pass

    NB   = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    CUT  = adsk.fusion.FeatureOperations.CutFeatureOperation
    JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
    ex   = root.features.extrudeFeatures

    # Uniquely rename BOTH adjacent pieces so a foot can be re-fetched + welded
    # into whichever it overlaps (all pieces share 'Track_Piece' here, and each
    # NewBody foot extrude stales the pointers).  Welding to EITHER piece (not
    # just the pre-guessed host) makes a wrong host/direction guess harmless — a
    # foot can never end up standalone as long as it overlaps some track body.
    host_tag   = f'WBHost_{joint_num}'
    other_tag  = f'WBOther_{joint_num}'
    orig_host  = host.name
    host.name  = host_tag
    orig_other = None
    if other is not None:
        orig_other = other.name
        other.name = other_tag

    # ── Consistent WORLD cross-section frame (see wallsnap / MEMORY.md) ───────
    # world(xp, yp) = cut_origin + Rt*xp + _iyw*yp ; xp = across width (0 =
    # centreline), yp = floor(0)->wall(th).  Map corners into each sketch's own
    # inverse so a per-junction local frame flip can't rotate the geometry.
    Rt = adsk.core.Vector3D.create(cut_normal.y, -cut_normal.x, 0.0)
    if Rt.length < 1e-9:
        Rt = adsk.core.Vector3D.create(1.0, 0.0, 0.0)
    Rt.normalize()

    def _wpt(xp, yp):
        return adsk.core.Point3D.create(
            cut_origin.x + Rt.x * xp + _iyw.x * yp,
            cut_origin.y + Rt.y * xp + _iyw.y * yp,
            cut_origin.z + Rt.z * xp + _iyw.z * yp)

    # ── Path-following setup ─────────────────────────────────────────────────
    # The straight prism drifts off the curved wall (chords across the arc), so
    # follow the path: loft the foot cross-section through several stations that
    # ride the true path (setByDistanceOnPath), exactly like the wallsnap loft.
    # r_i = the path ratio of THIS junction; host_sign = the ratio direction
    # toward the host piece.
    _use_path = False
    r_i = host_sign = None
    Lp  = path_len

    def _frame_at(ratio):
        """(origin, right_x, right_y) of a plane ⟂ the path at absolute `ratio`."""
        r = max(0.0, min(1.0, ratio))
        cin = root.constructionPlanes.createInput()
        cin.setByDistanceOnPath(path, adsk.core.ValueInput.createByReal(r))
        pl = root.constructionPlanes.add(cin); pl.isLightBulbOn = False
        O = pl.geometry.origin.copy(); N = pl.geometry.normal.copy()
        try: pl.deleteMe()
        except Exception: pass
        rtx, rty = N.y, -N.x
        rl = (rtx * rtx + rty * rty) ** 0.5 or 1.0
        return O, rtx / rl, rty / rl

    def _path_frame(dist):
        """Frame at along-path `dist` from the junction toward the host."""
        return _frame_at(r_i + host_sign * dist / Lp)

    if path is not None and num_pieces and Lp and Lp > 0:
        try:
            # r_i is TOPOLOGICAL, not spatial: junction j was placed at ratio
            # j/num_pieces in Phase 1 (setByDistanceOnPath), and Phase 2 rebuilds
            # the Path the same way (same sketch curves), so this is exact — no
            # search needed.  A spatial "nearest path point to cut_origin" search
            # is WRONG on a loop that passes near itself (hairpins / parallel
            # straights): it locks onto the wrong section, placing the foot off in
            # space so it never overlaps the wall (the floating, unwelded feet) —
            # AND it created ~140 construction planes per junction (the slowness).
            r_i = float(joint_num) / float(num_pieces)
            # ALWAYS place the studs in the +ratio direction.  This is
            # topological, not geometric: junction j sits at ratio j/num_pieces,
            # so the piece spanning (r_i, r_i + 1/num_pieces) is by construction
            # the one you enter by moving +ratio.  Two consequences:
            #   • every junction mounts its DOWNSTREAM piece, so on a closed loop
            #     each piece is downstream of exactly one junction and therefore
            #     gets exactly one pair of studs;
            #   • no sampling, so it cannot degenerate.
            # The previous version compared the host's CENTRE OF MASS against
            # path points at ±dr.  On a hairpin the piece is folded back on
            # itself, so its CoM sits nearer the WRONG sample and the sign
            # flipped — at joint 6 (the loop's right-tip hairpin) that put both
            # studs in the neighbouring piece: it ended up with 4 studs while
            # its neighbour got none and hung on its snap joints alone.  Same
            # degeneracy the wallsnap code already avoids for male/female
            # assignment.  (weld-to-either still covers a wrong host GUESS; what
            # it cannot fix is placing the studs on the wrong piece entirely.)
            host_sign = 1.0
            # Sanity only (not a gate): how close r_i lands to the junction.
            try:
                O0, _, _ = _frame_at(r_i)
                rec['origin_err'] = round(
                    ((O0.x-cut_origin.x)**2 + (O0.y-cut_origin.y)**2 +
                     (O0.z-cut_origin.z)**2) ** 0.5, 4)
            except Exception:
                pass
            _use_path = True                 # always loft when a path exists
        except Exception as _ep:
            rec['path_err'] = str(_ep); _use_path = False
    rec['method'] = 'loft' if _use_path else 'straight'

    feet_ok = 0
    nonlocal_welds = [0]      # feet whose tool body was consumed by the JOIN

    def _foot_corners(mag_lo, mag_hi, yl, yh):
        """Bracket cross-section as (mag, y) pairs — post + ear, 6 points:

           (mag_lo, yh) ─────────────────── (mag_hi, yh)   wall face; the screw
                │                                │          goes through here
                │      (outer_hw, yh-EAR_T) ─── (mag_hi, yh-EAR_T)
                │                │                          ↑ flat underside =
                │   post         │                            screw seat + cap
           (mag_lo, yl) ── (outer_hw, yl)                   3 mm into the crest

        The ear reaches OUTBOARD only — inboard is the LED aperture.  Its
        underside is deliberately flat and horizontal: the head bears there and
        the cap plugs it, so it must not be sloped.  The 9 mm overhang is
        carried by two 45° ribs at the ENDS of the length (see `_rib_corners`),
        leaving the middle open to bridge.
        `yl` sits FOOT_EMBED below the wall tip: that overlap is the weld."""
        return [(mag_lo, yl), (outer_hw, yl), (outer_hw, yh - EAR_T),
                (mag_hi, yh - EAR_T), (mag_hi, yh), (mag_lo, yh)]

    def _rib_corners(yh):
        """45° gusset rib under the ear: rise = run, so it self-supports when
        printed floor-on-bed.  Right triangle from the post's outer face up to
        the ear's outboard edge."""
        _run = ear_out - outer_hw
        return [(outer_hw, yh - EAR_T - _run), (ear_out, yh - EAR_T),
                (outer_hw, yh - EAR_T)]

    # ══ Master-copy strategy.  Build ONE dovetail stud, then COPY and TRANSFORM
    #    it into place at each wall tip and merge.  A rigid copy oriented by the
    #    LOCAL wall tangent at its own centre drifts only by the sagitta of the
    #    arc it spans — 0.18 mm at R=10 cm, 0.36 mm at R=5 cm over 12 mm — versus
    #    metres of chord error if it were built off the junction tangent.  The
    #    3 mm embed swallows that drift; the old 1 mm one did not.
    #    KEEP THE STUD STRAIGHT: the plaque that hooks it is a rigid straight
    #    part, so a curve-following stud could not slide into its rails. ═══════
    # Screw sits WALL_EAR_Y outboard of the centreline — far enough that
    # its head clears the track edge, so it can be driven with the loop already
    # hanging.  Same constant the drill template marks with.
    ear_out     = WALL_EAR_Y + CBORE_R + 0.18   # 1.90 ear edge
    mag_lo      = inner_hw + IN_MARGIN          # 0.5 mm clear of the aperture
    mag_hi      = ear_out
    y_lo        = th - FOOT_EMBED               # 3 mm into the wall crest
    y_hi        = th + WALL_STANDOFF_GAP        # ear face lies ON the wall
    center_dist = CONN_CLEAR + FOOT_LEN * 0.5
    master_name = f'WBFootMaster_{joint_num}'

    def _yz_prism(corners, length, name):
        """Extrude a (mag, y) polygon along X, SYMMETRICALLY about x=0 — that
        way the yZ plane's normal direction never has to be guessed.  Returns
        the new body."""
        sk = root.sketches.add(root.yZConstructionPlane)
        sk.name = name; sk.isLightBulbOn = False
        inv = sk.transform.copy(); inv.invert()
        pts = []
        for v, w in corners:
            p = adsk.core.Point3D.create(0.0, v, w); p.transformBy(inv)
            pts.append(adsk.core.Point3D.create(p.x, p.y, 0))
        Lm = sk.sketchCurves.sketchLines
        for i in range(len(pts)):
            Lm.addByTwoPoints(pts[i], pts[(i + 1) % len(pts)])
        prof, ba = None, 1e18
        for i in range(sk.profiles.count):
            pp = sk.profiles.item(i); bb = pp.boundingBox
            a = ((bb.maxPoint.x-bb.minPoint.x) * (bb.maxPoint.y-bb.minPoint.y))
            if a < ba:
                ba, prof = a, pp
        if prof is None:
            return None
        ei = ex.createInput(prof, NB)
        ei.setSymmetricExtent(adsk.core.ValueInput.createByReal(length), True)
        ff = ex.add(ei)
        return ff.bodies.item(0) if ff.bodies.count else None

    def _shift(body, dx):
        mtx = adsk.core.Matrix3D.create()
        mtx.translation = adsk.core.Vector3D.create(dx, 0.0, 0.0)
        col = adsk.core.ObjectCollection.create(); col.add(body)
        mi = root.features.moveFeatures.createInput2(col)
        mi.defineAsFreeMove(mtx)
        root.features.moveFeatures.add(mi)

    def _build_master():
        """One bracket in the CANONICAL frame: X = length (centred ±FOOT_LEN/2),
        Y = outboard, Z = toward wall.  Post + ear extruded the full length,
        then a 45° gusset rib added at EACH END so the middle of the ear's
        underside stays flat for the screw head and the cap.  Finally the M3
        bore + counterbore, both along +Z at Y = the ear offset."""
        body = _yz_prism(_foot_corners(mag_lo, mag_hi, y_lo, y_hi), FOOT_LEN,
                         f'WBMasterProf_{joint_num}')
        if body is None:
            return None
        body.name = master_name
        # Ribs: built symmetric about x=0, then shifted out to the ends.
        _off = (FOOT_LEN - RIB_T) * 0.5
        for _k, _dx in ((0, -_off), (1, _off)):
            rb = _yz_prism(_rib_corners(y_hi), RIB_T,
                           f'WBMasterRib_{joint_num}_{_k}')
            if rb is None:
                continue
            rb.name = f'WBtmpRib_{joint_num}_{_k}'
            _shift(_by_name(f'WBtmpRib_{joint_num}_{_k}'), _dx)
            t = _by_name(master_name); f = _by_name(f'WBtmpRib_{joint_num}_{_k}')
            if t is not None and f is not None:
                c = adsk.core.ObjectCollection.create(); c.add(f)
                ci = root.features.combineFeatures.createInput(t, c)
                ci.operation = JOIN
                ci.isNewComponent = False
                ci.isKeepToolBodies = False
                root.features.combineFeatures.add(ci)

        def _mcirc(nm, r):
            s = root.sketches.add(root.xYConstructionPlane)
            s.name = nm; s.isLightBulbOn = False
            iv = s.transform.copy(); iv.invert()
            c = adsk.core.Point3D.create(0.0, WALL_EAR_Y, 0.0)
            c.transformBy(iv)
            s.sketchCurves.sketchCircles.addByCenterRadius(
                adsk.core.Point3D.create(c.x, c.y, 0), r)
            return s.profiles.item(0) if s.profiles.count else None

        def _mcut(prof2, z0, depth):
            """Cut UP from z0 (the ear's flat underside) toward the wall.  With
            isSymmetric=False a POSITIVE distance runs along +normal = +Z, i.e.
            into the ear — the opposite convention to the old downward bores."""
            ei2 = ex.createInput(prof2, CUT)
            ei2.startExtent = adsk.fusion.OffsetStartDefinition.create(
                adsk.core.ValueInput.createByReal(z0))
            ei2.setDistanceExtent(False, adsk.core.ValueInput.createByReal(depth))
            mm = _by_name(master_name)
            if mm is not None:
                ei2.participantBodies = [mm]
            ex.add(ei2)

        _ear_u = y_hi - EAR_T
        try:
            _v0 = _by_name(master_name).physicalProperties.volume
        except Exception:
            _v0 = None
        c1 = _mcirc(f'WBMBore_{joint_num}', BORE_R)
        if c1 is not None:
            _mcut(c1, _ear_u - 0.05, EAR_T + 0.10)      # clean through the ear
        c2 = _mcirc(f'WBMCbore_{joint_num}', CBORE_R)
        if c2 is not None:
            _mcut(c2, _ear_u - 0.05, CBORE_D + 0.05)    # head recess + the cap
        try:
            _v1 = _by_name(master_name).physicalProperties.volume
            rec['master_vol'] = round(_v1, 4)
            if _v0 is not None:
                rec['master_bored'] = (_v0 - _v1) > 1e-4
        except Exception:
            pass
        return _by_name(master_name)

    def _place_foot(side, tag):
        nonlocal feet_ok
        # Position + LOCAL tangent at the foot centre (curve-following without a loft).
        O = T = None
        if _use_path:
            try:
                ratio = max(0.0, min(1.0, r_i + host_sign * center_dist / Lp))
                cin = root.constructionPlanes.createInput()
                cin.setByDistanceOnPath(path, adsk.core.ValueInput.createByReal(ratio))
                pl = root.constructionPlanes.add(cin); pl.isLightBulbOn = False
                O = pl.geometry.origin.copy(); N = pl.geometry.normal.copy()
                try: pl.deleteMe()
                except Exception: pass
                T = adsk.core.Vector3D.create(N.x, N.y, 0.0)
            except Exception:
                O = T = None
        if O is None or T is None or T.length < 1e-9:
            O = adsk.core.Point3D.create(
                cut_origin.x + cut_normal.x * center_dist,
                cut_origin.y + cut_normal.y * center_dist, cut_origin.z)
            T = adsk.core.Vector3D.create(cut_normal.x, cut_normal.y, 0.0)
        T.normalize()
        # The path sketch drives only the in-plane (XY) curve-following; its
        # origin sits on the Phase-2 centreline plane (z≈0), NOT the floor face.
        # The master's height (y_lo/y_hi) is built off the floor face cut_origin.z
        # (via the measured th = host_ztop − cut_origin.z), so the vertical BASE
        # must be cut_origin.z — otherwise the foot drops by the plane offset and
        # its top lands at the wall tip instead of the full standoff gap.
        O = adsk.core.Point3D.create(O.x, O.y, cut_origin.z)
        # Canonical→world frame: v = side·path-right(T); w = _iyw; u ⟂ (right-handed).
        v = adsk.core.Vector3D.create(side * T.y, side * (-T.x), 0.0); v.normalize()
        w = adsk.core.Vector3D.create(_iyw.x, _iyw.y, _iyw.z); w.normalize()
        u = adsk.core.Vector3D.create(T.x, T.y, T.z)
        cxp = u.y*v.z - u.z*v.y; cyp = u.z*v.x - u.x*v.z; czp = u.x*v.y - u.y*v.x
        if cxp*w.x + cyp*w.y + czp*w.z < 0.0:
            u.scaleBy(-1.0)
        mtx = adsk.core.Matrix3D.create()
        mtx.setWithCoordinateSystem(O, u, v, w)

        master = _by_name(master_name)
        if master is None:
            return False
        foot = master.copyToComponent(root)
        foot_body_name = f'WBFootBody_{joint_num}_{tag}'
        foot.name = foot_body_name
        col = adsk.core.ObjectCollection.create(); col.add(_by_name(foot_body_name))
        mf = root.features.moveFeatures
        mi = mf.createInput2(col); mi.defineAsFreeMove(mtx)
        mf.add(mi)
        # Diagnostic: where did the foot actually land in Z vs the wall tip?
        # (bracket top should be WALL_STANDOFF_GAP above the wall rim; if lower
        # the wall pokes through the foot's top face.)
        try:
            _fbb = _by_name(foot_body_name).boundingBox
            rec.setdefault('foot_z', []).append(
                [round(_fbb.minPoint.z, 3), round(_fbb.maxPoint.z, 3)])
        except Exception:
            pass
        feet_ok += 1

        # Weld into whichever adjacent piece it overlaps (host then other).
        # A JOIN between bodies that DON'T touch still consumes the tool and
        # leaves the foot as a disjoint lump, so "the tool vanished" proves
        # nothing.  Measure the target's volume across the combine instead: a
        # real weld ADDS LESS than the foot's own volume (the embedded part is
        # already inside the wall); a disjoint lump adds exactly the foot.
        _fvol = None
        try:
            _fvol = _by_name(foot_body_name).physicalProperties.volume
        except Exception:
            pass
        def _recover_stray(tags):
            """A JOIN between bodies that never touch consumes the tool and re-emits
            it as a NEW body named '<target> (n)' (Fusion behaviour — this is how
            joint 6's feet became WBHost_6 (1)/(2) and then bogus Piece_N).  Find
            that body and give it the foot's name back so the next tag can be tried."""
            if not _fvol:
                return None
            for b in _all_bodies(root):
                for _tg in tags:
                    if not b.name.startswith(_tg + ' ('):
                        continue
                    try:
                        if abs(b.physicalProperties.volume - _fvol) < _fvol * 0.10:
                            b.name = foot_body_name
                            return b
                    except Exception:
                        pass
            return None

        _welded_into = None
        _tried = []
        for _tag_try in (host_tag, other_tag):
            f = _by_name(foot_body_name)
            if f is None and _tried:
                # Previous attempt consumed the foot without absorbing it.
                f = _recover_stray(_tried)
            _tried.append(_tag_try)
            t = _by_name(_tag_try)
            if t is None or f is None:
                continue
            try:
                _tv0 = t.physicalProperties.volume
            except Exception:
                _tv0 = None
            try:
                c = adsk.core.ObjectCollection.create(); c.add(f)
                ci = root.features.combineFeatures.createInput(t, c)
                ci.operation = JOIN
                ci.isNewComponent = False
                ci.isKeepToolBodies = False
                root.features.combineFeatures.add(ci)
            except Exception:
                continue
            try:
                _tv1 = _by_name(_tag_try).physicalProperties.volume
                if _tv0 is not None and _fvol:
                    _dv = _tv1 - _tv0
                    rec.setdefault('weld_dv', []).append(
                        [tag, _tag_try, round(_dv, 4), round(_fvol, 4)])
                    # Three outcomes, all of which used to report success:
                    #   dv ≈ 0          → target untouched, foot re-emitted as
                    #                     '<target> (n)' → try the other piece
                    #   dv ≈ foot vol   → absorbed but not overlapping (lump)
                    #   0 < dv < 0.95·f → real weld (the embedded part is already
                    #                     inside the wall, so it adds less)
                    if _dv > 1e-4 and _dv < _fvol * 0.95:
                        _welded_into = _tag_try
                        break
            except Exception:
                pass
        if _welded_into is not None:
            nonlocal_welds[0] += 1
            rec.setdefault('welded_into', []).append([tag, _welded_into])
        else:
            # Consumed but never touching (disjoint lump), or never consumed.
            # If it survives as a '<tag> (n)' stray, give it the foot name back so
            # leftover_bodies reports it honestly instead of it drifting into
            # STEP 3 as a bogus piece.
            if _by_name(foot_body_name) is None:
                _recover_stray([host_tag, other_tag])
            rec.setdefault('unwelded', []).append(tag)

        # Wall-screw XY (world) for the drilling template: the bracket's single
        # M3, WALL_EAR_Y outboard of the centreline.  `v` is this side's
        # outboard unit vector, so this lands on the real hole — marking the
        # centreline instead would put every hole 14 mm out.
        rec['screws'].append(
            [round(O.x + v.x * WALL_EAR_Y, 4),
             round(O.y + v.y * WALL_EAR_Y, 4)])
        return True

    if _build_master() is not None:
        # ONE bracket per junction now, on EAR_SIDE.  It reaches the wall by
        # itself, so there is nothing for a second one to pair with — and a
        # single-sided mount leaves the piece a little twist freedom about the
        # track axis, which the floor lap and ~20 cm mount spacing cover.
        for side, tag in ((EAR_SIDE, 'R' if EAR_SIDE > 0 else 'L'),):
            try:
                _place_foot(side, tag)
            except Exception as _ef:
                rec.setdefault('foot_err', str(_ef))
        _m = _by_name(master_name)
        if _m is not None:
            try: _m.deleteMe()
            except Exception: pass
        # The master's bore/counterbore sketches live at the world ORIGIN (the
        # master is built there before being copied+moved onto each wall).  Once
        # the bore is baked into the moved feet these are just clutter that reads
        # as "bores stuck at the origin" — remove them.  Keep WBMasterProf_{j};
        # it's the re-run guard.
        for _snm in (f'WBMBore_{joint_num}', f'WBMCbore_{joint_num}'):
            try:
                _sk = root.sketches.itemByName(_snm)
                if _sk is not None:
                    _sk.deleteMe()
            except Exception:
                pass
    else:
        rec.setdefault('foot_err', 'master build failed')

    rec['feet_ok']  = feet_ok
    rec['welds_ok'] = nonlocal_welds[0]

    # Diagnostic: wall-tip Z of the host piece (foot_z[*][1] should sit
    # ~WALL_STANDOFF_GAP
    # above this), and any foot/master bodies that survived (true standalone
    # count, independent of the weld bookkeeping above).
    try:
        _hb = _by_name(host_tag)
        if _hb is not None:
            rec['host_ztop'] = round(_hb.boundingBox.maxPoint.z, 3)
    except Exception:
        pass
    try:
        rec['leftover_bodies'] = [
            b.name for b in _all_bodies(root)
            if b.name.startswith(f'WBFootBody_{joint_num}_')
            or b.name.startswith(f'WBFootMaster_{joint_num}')]
    except Exception:
        pass

    # ── Restore both shared piece names so STEP 3 renames them to Piece_N ─────
    h = _by_name(host_tag)
    if h is not None:
        h.name = orig_host
    if orig_other is not None:
        o = _by_name(other_tag)
        if o is not None:
            o.name = orig_other
    rec['host_restored'] = h is not None

    try:
        rec['cut_origin'] = [round(cut_origin.x, 2), round(cut_origin.y, 2),
                             round(cut_origin.z, 2)]
        rec['iyw'] = [round(_iyw.x, 2), round(_iyw.y, 2), round(_iyw.z, 2)]
    except Exception:
        pass

    rec['success'] = feet_ok > 0
    return rec


# Standoff gap (pillar height) of the wall bracket = the adjustable track-to-wall
# distance that tunes the LED halo diffusion.  Tune here (cm).
WALL_STANDOFF_GAP = 1.5      # 15 mm

# Offset of the bracket's screw ear from the track centreline.  SHARED: the
# bracket bores its hole here AND the drill template marks here.  If the two
# ever disagree, every wall hole is drilled in the wrong place.
WALL_EAR_Y = 1.40            # 14 mm — head clears the 10 mm track edge


def create_wall_cap_part(root, params, ui=None):
    """Standalone printable COVER CAP that plugs a bracket's counterbore, so the
    screw head disappears once the loop is on the wall.

    The bracket itself is printed as part of its track piece (see
    create_wall_bracket) — it reaches the wall and carries its own M3 on an ear
    outboard of the track, so there is no separate mount part any more.  This
    is all that is left to print separately: one cap per junction.

    Supersedes create_wall_plaque_part (dovetail studs + a hooking plaque),
    which is gone: the integrated bracket removed every fit tolerance between
    track and mount, the simultaneous-engagement problem, the R~3 cm curve
    limit a straight rail imposed, and the plate that spanned the channel and
    shadowed the halo at every junction.
    """
    try:
        CBORE_R  = 0.32         # * must match create_wall_bracket's counterbore
        CBORE_D  = 0.20         # *
        CAP_R    = CBORE_R - 0.005      # 0.1 mm total — snug in FDM
        CAP_LEAD = 0.03                 # stepped lead-in on the back edge
        NAME     = 'WallScrewCap'

        NB = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
        ex = root.features.extrudeFeatures

        for b in list(root.bRepBodies):
            if b.name.startswith(NAME) or b.name.startswith('WCtmp_'):
                try: b.deleteMe()
                except Exception: pass
        for s in list(root.sketches):
            if s.name.startswith('WC_'):
                try: s.deleteMe()
                except Exception: pass

        def _by(nm):
            for b in root.bRepBodies:
                if b.name == nm:
                    return b
            return None

        def _disc(r, z0, z1, name):
            sk = root.sketches.add(root.xYConstructionPlane)
            sk.name = 'WC_' + name; sk.isLightBulbOn = False
            inv = sk.transform.copy(); inv.invert()
            c = adsk.core.Point3D.create(0.0, 0.0, 0.0); c.transformBy(inv)
            sk.sketchCurves.sketchCircles.addByCenterRadius(
                adsk.core.Point3D.create(c.x, c.y, 0), r)
            ei = ex.createInput(sk.profiles.item(0), NB)
            ei.startExtent = adsk.fusion.OffsetStartDefinition.create(
                adsk.core.ValueInput.createByReal(z0))
            ei.setDistanceExtent(
                False, adsk.core.ValueInput.createByReal(z1 - z0))
            f = ex.add(ei)
            return f.bodies.item(0) if f.bodies.count else None

        body = _disc(CAP_R, 0.0, CBORE_D - CAP_LEAD, 'CapBody')
        if body is None:
            return False
        body.name = NAME
        lead = _disc(CAP_R - CAP_LEAD, CBORE_D - CAP_LEAD, CBORE_D, 'CapLead')
        if lead is not None:
            lead.name = 'WCtmp_lead'
            t = _by(NAME); f = _by('WCtmp_lead')
            if t is not None and f is not None:
                col = adsk.core.ObjectCollection.create(); col.add(f)
                ci = root.features.combineFeatures.createInput(t, col)
                ci.operation = JOIN
                ci.isNewComponent = False
                ci.isKeepToolBodies = False
                root.features.combineFeatures.add(ci)

        # Park it clear of the track, below everything at min-Y.
        miny = 1e18; minx = 1e18
        for b in _all_bodies(root):
            if b.name.startswith(NAME):
                continue
            try:
                bb = b.boundingBox
                miny = min(miny, bb.minPoint.y); minx = min(minx, bb.minPoint.x)
            except Exception:
                pass
        if miny < 1e17 and _by(NAME) is not None:
            mtx = adsk.core.Matrix3D.create()
            mtx.translation = adsk.core.Vector3D.create(minx, miny - 3.0, 0.0)
            col = adsk.core.ObjectCollection.create(); col.add(_by(NAME))
            mi = root.features.moveFeatures.createInput2(col)
            mi.defineAsFreeMove(mtx)
            root.features.moveFeatures.add(mi)

        if ui:
            ui.messageBox(
                'Body "{}" created, parked below the track.\n\n'
                '  {:.1f} mm dia x {:.1f} mm, into a {:.1f} mm counterbore\n'
                '  ({:.2f} mm total clearance — press fit)\n\n'
                'Print one per junction; they print flat, face down.\n\n'
                'Install:\n'
                '  1. Hold the assembled loop against the wall and mark\n'
                '     through each bracket ear.\n'
                '  2. Drill and anchor.\n'
                '  3. Hang it back up and drive the screws — the ears are\n'
                '     outboard of the track, so nothing is in the way and the\n'
                '     mounts do NOT have to engage simultaneously.\n'
                '  4. Press a cap into each counterbore to hide the head.'.format(
                    NAME, CAP_R * 20, CBORE_D * 10, CBORE_R * 20,
                    (CBORE_R - CAP_R) * 20))
        return True
    except:
        if ui:
            ui.messageBox('Wall cap part failed:\n' + traceback.format_exc())
        return False


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
