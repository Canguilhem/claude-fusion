# Plan: Clean Half-Stud Restart

## Status: PLANNED (2026-03-24)

---

## Problem

Multiple accumulated functions (`_add_track_bore`, `_UNUSED` variants, full-circle+rectangle
approach) have created confusing geometry. The goal is to revert to a single clean concept:
two D-shaped half-cylinder bosses on each collar top, one per side of the H-key neck.

When two pieces mate, the two halves on each side form one complete cylinder. Thread M2 nuts
onto the assembled cylinders from the open channel.

---

## Goal

`_add_half_studs` produces exactly this per body:

- 2 half-cylinder (D-shape) bosses protruding outward from the collar top face
- Arc face points INTO the piece; flat face sits at the junction line
- When two pieces mate, two halves form one complete cylinder per side
- Thread M2 nuts onto the assembled cylinders from the open channel

---

## Step-by-Step Implementation

### 1. Find `collar_top_face`

- BRepFace with normal ≈ `_iyw`
- Height ≈ `wt + COLLAR_H` from `cut_origin`
- If not found or `best_err > 0.05` → skip with message

### 2. Validate face

- `try: root.sketches.add(collar_top_face)` — if it fails, collar boss is missing, skip with message

### 3. Compute sketch coordinate system

- From `ref_sk` transform (same pattern as existing socket cuts)

### 4. Compute extrude direction

```python
fn_dot = collar_top_face.geometry.normal · _iyw
extrude_outward = (fn_dot > 0)
# fn_dot > 0 → normal points outward (same as _iyw) → isPositiveDirection=True = outward
# fn_dot < 0 → normal points inward → isPositiveDirection=False = also outward
```

### 5. Build BOTH D-shape sketches before any geometry changes

`collar_top_face` goes stale after the first CombineFeatures — all sketches must be created first.

```
For stud_idx in [0, 1], x_sign in [+1, -1]:
  cx = jx + x_sign * stud_x * flat_x
  cy = jy + x_sign * stud_x * flat_y
  stud_sk = root.sketches.add(collar_top_face)   # must happen before any extrude/join
  Draw D-shape: arc (p_s → p_m → p_e) + diameter line (p_s → p_e)
    p_s = (cx - flat * POST_R)
    p_e = (cx + flat * POST_R)
    p_m = (cx + piece_sign * dn * POST_R)   # arc bulges toward piece
  Store (profile, stud_sk) in pending[]
```

### 6. Geometry phase (after all sketches built)

```
For each (profile, stud_sk) in pending:
  Extrude profile as NewBodyFeatureOperation, setDistanceExtent(extrude_outward, POST_H)
  Try: ThreadFeature on cylindrical face of stud_body (M2x0.4, isModeled=True) — best-effort
  CombineFeatures(Join) stud_body into body
```

---

## Constants

```python
POST_R   = 0.10   # 1.0 mm radius = M2
POST_H   = 0.30   # 3.0 mm above collar top
COLLAR_H = 0.20   # must match create_pin_connector
HOLE_CL  = 0.01
```

---

## Guard

Sketch name `f'HalfStud_{joint_num}_0_0'` — skip entire function if already present.

---

## What to Remove / Keep Inactive

- `_add_track_bore` — keep defined but NOT called (already not called)
- All `_UNUSED_*` functions — keep as dead code, do not call

---

## Call Site in `create_pin_connector`

```python
_add_half_studs(root, cut_plane, track_bodies, params, joint_num, ui)
```

Already the call site — no change needed there.

---

## Verification

Run addin → section view at junction should show:

- Two D-shaped profiles on collar top of each piece
- Flat face at junction plane, arc pointing into piece
- Section from above: two semicircles per piece, facing toward their own piece

---

## Implementation Checklist

- [ ] Remove or stub out `_add_track_bore` call site (ensure it is not called)
- [ ] Keep all `_UNUSED_*` functions as dead code
- [ ] Rewrite `_add_half_studs` per the step-by-step above
- [ ] Verify guard sketch name `HalfStud_{joint_num}_0_0`
- [ ] Smoke-test in Fusion on a simple 2-piece straight track
- [ ] Section view: confirm D-shape profiles on each collar top
- [ ] Print one junction pair and test M2 nut fit on assembled cylinders
- [ ] Commit on `approach-b` branch
