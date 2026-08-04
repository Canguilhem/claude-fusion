# Plan: Dovetail Stud + Wall Plaque (replaces screw-through foot)

## Status: IMPLEMENTED in TrackOctaCutter.py (2026-08-04)

Coupon-validated first (`API/Scripts/TrackTestCoupon`): the rail/slide and dovetail were
confirmed on a print 2026-07-31; the connector numbers were settled by the v5 coupon and
variant **A** (0.08 mm/face tongue clearance) on 2026-08-03. What went in:

| | was | now |
|---|---|---|
| `SNAP_LAP_LEN` | 0.80 | **1.20** |
| `SNAP_TONGUE_T` | 0.13 (wt·0.5−0.02) | **0.10** |
| `SNAP_BARB_X` | 0.10 | **0.07** |
| `SNAP_BARB_LEN` | 0.18 | **0.30** (full-depth ramp) |
| `SNAP_BARB_H` | — (full tongue) | **0.80**, centred |
| window | through, leaking | **blind**, floor derived, 1.05 mm skin |
| `SNAP_CL` | 0.008 | **0.008** (unchanged — variant A) |
| foot | bored, 1 mm embed | **dovetail stud**, 3 mm embed, no holes |
| `CONN_CLEAR` | 1.00 | **1.50** |
| mating part | `create_wall_standoff_part` | **`create_wall_plaque_part`** |

Dead `_foot_station`/`_build_foot` loft code deleted (181 lines), bores and `bores_ok`
removed, `rec['screws']` now records the plaque's single central M3.

**Not yet run in Fusion** — the geometry is verified arithmetically only.

---

## Original spec (2026-07-31)

Supersedes the screw-through foot in `create_wall_bracket` and the mating part in
`create_wall_standoff_part`. All dims in **cm** (Fusion internal unit).

---

## PREREQUISITE — fix the design parameters first (blocks everything below)

**The script has been building against the wrong track profile.** `load_parameters`
(line 65-67) reads `TRACK_WIDTH` / `TRACK_HEIGHT` / `WALL_THICKNESS` from the design's
**user parameters**, falling back to 15 / 10 / 3 mm. `wall_bracket_validation.json` records
`th_param: 1.0` against `th_measured: 1.7`, so no such user parameters exist and the
defaults are in force. Measured 2026-07-31: the track is **20 mm wide × 17 mm tall,
3 mm walls, 14 mm channel**.

**Fix: add three user parameters to the Fusion design** — `TRACK_WIDTH = 20 mm`,
`TRACK_HEIGHT = 17 mm`, `WALL_THICKNESS = 3 mm`. The startup dialog (line 146-148) echoes
what the run is actually using; confirm there before generating anything.

Corrected working values used throughout this spec:

```
outer_hw = 1.00    (was 0.75)     inner_hw = 0.70    (was 0.45)
th       = 1.70 (measured globally as wall_top_z − cut_origin.z)
```

**This is not a feet-only problem — check the wallsnap connector.** It places the tongue
and pocket at `x_in = inner_hw` (0.45) and `x_out = inner_hw + wt` (0.75), lines 2599-2600,
i.e. **entirely inside the real 14 mm channel** — tongues in mid-air, pockets cutting
nothing — and `ch_h = th − wt` (line 2214) gives 7 mm of engagement on a 14 mm-tall wall.
The 2026-07-28 circuit printed and clicked together, so the model was presumably 15 mm wide
then and rebuilt at 20 mm afterwards. Section a junction and verify before the next print.

---

## Why the change

The current foot is broken as built, and the screw was doing a job a plaque does better.
Numbers below are the **real** geometry (walls at \|x\| 0.70→1.00, `th` 1.7) vs what the
param-driven code actually built:

| defect | numbers |
|---|---|
| foot overhangs the LED aperture | foot spans \|x\| 0.45→1.19 but the wall band is 0.70→1.00 → **2.5 mm per side sits over the open channel**, not on the wall |
| through-bore breaks into the channel | Ø3.6 bore spans \|x\| 0.64→1.00, straddling the real inner wall face (0.70) → **punches through into the channel** = the dominant hole in the screenshots |
| counterbore wider than the foot | Ø6.4 cbore spans 0.50→1.14 in a 7.4 mm-wide foot → **0.5 mm skin** on both sides |
| cbore breaks out through the print chamfer | chamfer (0.75, z1.60)→(1.19, z2.04) vs cbore floor z1.95 → open for \|x\| > 1.10 |
| no flat screw seat | the chamfer removes the flat underside past 0.75, so the head lands half on a 45° ramp |
| shallow weld | `FOOT_EMBED = 0.10` → only 1 mm of a 7 mm-tall foot inside the wall |

The plaque removes all bores from the track, drops the protrusion 6.0 mm → 4.5 mm, and
makes every mount an **identical printed part** (print N, one design).

---

## Concept

Two **dovetail studs** per junction (one per wall tip), welded into the host piece exactly
as today. One **plaque** per junction: a plate + standoff pillar screwed to the wall, with
two inward-hooking rails that capture both studs' outboard dovetails. Engagement =
**axial slide** along the track tangent — the same motion the wallsnap connector already
uses. The two hooks oppose each other, so the pair is captured in pull-off; neither can
rotate out.

Nothing crosses \|x\| < `inner_hw` (0.45) on the track side — the LED aperture stays clear.

---

## Geometry — stud (canonical frame)

Same canonical frame as the current master-copy: **X = along track** (centred ±`STUD_LEN`/2),
**Y = outboard magnitude** \|x\| from the centreline, **Z = height above the outer floor
face** (`cut_origin.z`). Built once as `WBStudMaster_{j}`, copied + transformed per foot.

**Constants (new):**

```
STUD_LEN   = 1.20   # 12 mm along the track  (was FOOT_LEN 0.80)
STUD_EMBED = 0.30   # 3 mm down into the wall crest  (was FOOT_EMBED 0.10)
NECK_H     = 0.25   # 2.5 mm of neck above the wall tip — the rail's throat
FLARE      = 0.20   # dovetail rise = run → exactly 45°, printable, self-centring
CONN_CLEAR = 1.00   # unchanged — clears the wallsnap ±SNAP_LAP_LEN 0.80
```

**Cross-section (5 points, per side; `m` = \|x\|, `z` = height; values for the REAL
profile — 20 mm wide, 3 mm walls, th=1.7):**

| # | m | z | |
|---|---|---|---|
| 1 | `inner_hw + 0.05` 0.75 | `th − STUD_EMBED` 1.40 | 0.5 mm clear of the channel edge — see drift note below |
| 2 | `outer_hw` 1.00 | `th − STUD_EMBED` 1.40 | 2.5 mm of the 3 mm wall band = weld footprint |
| 3 | `outer_hw` 1.00 | `th + NECK_H` 1.95 | neck, rail slides in below this |
| 4 | `outer_hw + FLARE` 1.20 | `th + NECK_H + FLARE` 2.15 | 45° dovetail flare, outboard only |
| 5 | `inner_hw` 0.70 | 2.15 | flat top = bearing face against the plaque |

Total protrusion above the wall tip: **4.5 mm** (was 6.0). Below z1.95 nothing exists
outboard of `outer_hw`, so the track's own silhouette is unchanged.

Load path: the flat top (point 4→5) takes compression against the plaque; the 45° flare
takes pull-off only. Weld: the stud straddles the full wall crest, 3 mm deep.

**Print orientation** (floor on the bed, opening/studs up): the flare is a 45° overhang —
self-supporting. No horizontal overhang anywhere, so the old `_foot_corners` chamfer hack
is no longer needed and is deleted.

---

## Geometry — plaque (one part, printed N times)

**Constants:**

```
RAIL_OUT   = 1.40   # plaque half-width  (= S_MAG_HI + 0.20)
RAIL_IN    = 1.06   # rail inner vertical face — 0.6 mm off the wall, see drift note
RAIL_DEPTH = 0.40   # rail leg reaches down to z 1.75 (0.5 mm above the wall tip)
RAIL_LEN   = 1.20   # = PLAQUE_LEN = STUD_LEN — see print orientation below
PLATE_T    = 0.30
PLAQUE_LEN = 1.20
FIT_CLR    = 0.020  # 0.21 mm perpendicular on the 45° faces; ZERO on the flat top
WALL_HOLE_R = 0.17  # ONE central M3 (see below)
```

**Print orientation drove two of these numbers (2026-07-31).** Plate, rails and pillar are
all the same length, making the plaque a **constant cross-section prism**, and it prints
**standing on its end face** (track axis vertical; 28 × 14.5 mm footprint, 12 mm tall).
Nothing overhangs, the plate underside — the bearing datum against the stud tops — stays
flat, and the hooks carry pull-off *in-plane* with the layers rather than across them.
Laid flat it is bad either way: pillar-down cantilevers the plate 9 mm per side over air,
plate-down bridges 21 mm directly under the datum face.

**One central M3, not two.** A 12 mm plate has no room for a pair without breaking out its
ends, and the second screw only ever provided anti-rotation — which the two rails supply
once the studs are engaged. The plaque can spin on its screw *before* the track is fitted;
that is an install annoyance, not a failure.

Rail cross-section (y, z), mirrored per side — mating face is the stud's flare line
`z = y + 0.95` offset down 0.03 to `z = y + 0.92`:

```
(1.40, 2.15) (1.40, 1.75) (1.06, 1.75) (1.06, 1.98) (1.23, 2.15)
```

Hook catches the flare over y 1.06 → 1.20 = **1.4 mm of engagement per side**.

- Plate underside sits at the stud top (z 2.15) — that flat contact is the standoff datum.
- Rails hang from the plate at \|x\| 1.20→1.40 with an inward 45° lip whose tip reaches
  `RAIL_TIP` 1.05. **Plaque half-width 1.40 → 28 mm total** against a 20 mm track, i.e.
  4 mm proud per side. Chamfer the plaque's outer edges 45° so it recedes at grazing angles.
- Pillar on the wall side: `PILLAR_H = WALL_STANDOFF_GAP − (stud_top − th) − PLATE_T`
  = 1.5 − 0.45 − 0.30 = **0.75**. Compute it, and hard-error if ≤ 0.20.
- 2 × M3 wall screws on the centreline (Ø6.4 head recess spans ±0.32, well clear of the
  studs at \|x\| ≥ 0.70), counterbored into the plate's track-facing side so the heads
  can't foul the stud tops.

---

## Install flow

1. Clip all plaques onto their studs **off the wall** (each self-locates on its own junction).
2. Offer the whole loop up, mark through the plaque holes, drill, anchor.
3. Unclip, screw all plaques to the wall, slide the pieces back on.

Step 1–2 is what `WallMount_DrillTemplate` does on paper today — doing it physically means
**zero cumulative error**, which was the original reason screw-through beat keyhole/cleat.
Each plaque still locates independently, so N mounts on a rigid closed loop stay
un-over-constrained.

**Closing piece:** the last piece of a closed loop has no axial travel. The 45° flare
doubles as a press-on lead-in — with a 1.5–2 mm rail leg over a 12 mm free length the rails
flex enough to click on. If bench testing says otherwise, fall back to leaving that one
junction's plaque unscrewed and fitting it with the piece.

---

## Code changes (`TrackOctaCutter.py`)

1. **`create_wall_bracket`** (line ~3000)
   - Constants block (~3046): `FOOT_LEN/FOOT_H/FOOT_EMBED` → `STUD_LEN/NECK_H/FLARE/STUD_EMBED`;
     **delete `BORE_R`, `CBORE_R`, `CBORE_D`**.
   - `_foot_corners` (~3246) → `_stud_corners`: return the 5-point profile above.
     The chamfer branch and its `ramp` guard go away.
   - `_build_master` (~3454): keep the yZ-plane sketch + symmetric extrude; **delete
     `_mcirc`/`_mcut` and both bore cuts**, and the `master_vol_removed`/`master_bored`
     validation with them.
   - `_place_foot` (~3526): unchanged (transform + weld-to-either), except
     `center_dist = CONN_CLEAR + STUD_LEN/2` and `bores_ok` → drop.
   - `rec['screws']`: now the **plaque** screw XY = `O ± 0.60·u` (centreline, u = tangent),
     2 per junction — so `WallMount_DrillTemplate` in STEP 2.6 keeps working unchanged.
   - Dead `_foot_station`/`_build_foot` loft path: delete now (unused since the master-copy
     rev, and it would need the same profile change).
2. **`create_wall_standoff_part`** (~3690) → `create_wall_plaque_part`: plate + 2 rails +
   pillar + 2 wall holes, placed below the track at min-Y as today. Starred dims must mirror
   the stud (`outer_hw`, `NECK_H`, `FLARE`, `FIT_CLR`).
3. **Guard/cleanup names**: `WBFootPad_*`/`WBFootMaster_*`/`WBBore_*`/`WBCbore_*` →
   `WBStudMaster_{j}` + `WBStudProf_{j}`; re-run guard checks `WBStudProf_{j}`.
4. **Validation JSON**: drop `master_bored`/`bores_ok`; add `stud_z`, `flare_top`,
   `plaque_screws`.

---

## Open risks (check before/while implementing)

1. **Params vs model — CONFIRMED WRONG, see the prerequisite section.** Set the three user
   parameters in the design (20 / 17 / 3 mm). Belt-and-braces so this can never silently
   build mid-air geometry again, mirroring the `wall_top_z` hoist: measure the profile
   **once** before the junction loop and pass it in. Method — sketch on a station plane
   inside a piece (`setByDistanceOnPath`, not the seam plane), `sketch.projectCutEdges(body)`
   to get the real cross-section, then in the cut-plane frame take `outer_hw = max |right·(p−O)|`
   over all section points, and `inner_hw = min |right·(p−O)|` restricted to points at
   `z ≈ max z` (the wall-tip faces). Fall back to the params if the projection yields nothing.
   Log both into the validation JSON next to `th_measured`.
2. **Piece length.** A stud needs `CONN_CLEAR + STUD_LEN` = **2.20 cm** of piece past the
   seam, and a piece hosting feet at both ends needs 4.4 cm. Clamp `STUD_LEN` to
   `min(1.20, 0.35 × piece_len)` (the long-standing overrun TODO, now with a bigger foot).
3. **Curve drift — measured, not theoretical.** The stud is a rigid straight copy oriented
   by the tangent at its CENTRE, so it is tangent in the middle and deviates outward at both
   ends by the sagitta: L²/8R ≈ 0.18 mm at R=10 cm, 0.53 mm at R=1.5 cm over 8 mm (worse at
   12 mm). Confirmed visually in section 2026-07-31 — welded feet read as slightly shifted
   against the wall, orphaned ones (which happened to be sectioned mid-foot) read as
   perfectly aligned. This is what left joint 4's left foot with **1.1 mm³** of contact
   (`weld_dv` 0.1961 of a 0.1972 cm³ foot). Two mitigations, both in the spec above:
   `STUD_EMBED 0.30` makes the contact 0.30×0.30×1.20 = **0.108 cm³** (~100× the old
   nominal, drift-insensitive), and `mag_lo = inner_hw + 0.05` keeps drift from pushing the
   stud over the LED channel.
   **Keep the stud STRAIGHT** — do not resurrect the curve-following loft. The plaque is a
   rigid straight part; a stud that hugged the arc could not slide into its rails.
4. **Plaque proud by 4 mm per side** — the one aesthetic cost vs the buried screw. Print it
   dark / wall-coloured, chamfer the outer edges.
5. **Axial retention** is currently only the wallsnap joints + loop closure. Add a detent
   bump on the rail if a bench test shows pieces creeping.
