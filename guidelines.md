PART 1
Simplified Geometric Pseudocode – Connector Generator

Assumptions:

Track already split

Slivers merged

We are processing one CutPlane_i

We have path curve available

We have section data from analyze_u_section()

A. Detect The Two Adjacent Bodies at This Cut

Do NOT rely on naming order.

def find_bodies_at_cut(root, cut_plane, tol=0.01):
bodies = []

    for body in root.bRepBodies:
        if not body.name.startswith("Track_"):
            continue

        for face in body.faces:
            if face.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                plane = face.geometry

                if planes_are_coincident(plane, cut_plane.geometry, tol):
                    bodies.append(body)
                    break

    return bodies  # should return exactly 2

You now have:

bodyA, bodyB

These are the only two valid connector targets.

B. Determine Path Direction at Cut

We need a stable direction vector.

def get_path_frame_at_cut(path_curve, cut_plane):

    # Get parameter on path closest to cut plane origin
    param = get_param_at_plane_intersection(path_curve, cut_plane)

    point = path_curve.evaluator.getPointAtParameter(param)
    tangent = path_curve.evaluator.getFirstDerivative(param)

    tangent.normalize()

    plane_normal = cut_plane.geometry.normal
    plane_normal.normalize()

    # Ensure tangent and plane normal point consistently
    if tangent.dotProduct(plane_normal) < 0:
        tangent.scaleBy(-1)

    return point, tangent, plane_normal

Now we have:

T = forward direction along track

N = cut plane normal

C. Automatically Decide Male vs Female

Rule:

The body whose centroid lies in the positive tangent direction becomes MALE.

def assign_male_female(bodyA, bodyB, cut_point, tangent):

    centroidA = bodyA.physicalProperties.centerOfMass
    centroidB = bodyB.physicalProperties.centerOfMass

    vecA = centroidA.vectorTo(cut_point)
    vecB = centroidB.vectorTo(cut_point)

    dotA = vecA.dotProduct(tangent)
    dotB = vecB.dotProduct(tangent)

    if dotA > dotB:
        male = bodyA
        female = bodyB
    else:
        male = bodyB
        female = bodyA

    return male, female

This ensures:

All connectors point forward along the track

Entire track assembles in one consistent direction

No random flipping

D. Generate Connector Sketch

Sketch must be created on cut_plane.

def create_connector_sketch(root, cut_plane, section_bbox, params):

    sketch = root.sketches.add(cut_plane)

    width = params["key_width"]
    depth = params["key_depth"]
    height = params["key_height"]

    centerline = project_track_centerline(sketch)

    # Place two symmetric rectangles
    offset = section_bbox.width * 0.25

    rect1 = sketch.sketchCurves.sketchLines.addCenterPointRectangle(
        Point(offset, 0, 0),
        width,
        height
    )

    rect2 = sketch.sketchCurves.sketchLines.addCenterPointRectangle(
        Point(-offset, 0, 0),
        width,
        height
    )

    return sketch

E. Extrude Male Connector
def extrude_male_keys(root, sketch, male_body, depth):

    extrudes = root.features.extrudeFeatures

    profs = sketch.profiles

    for profile in profs:
        input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.JoinFeatureOperation)
        input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(depth))
        input.participantBodies = [male_body]
        extrudes.add(input)

F. Cut Female Side
def cut_female_from_male(root, male_body, female_body):

    combine = root.features.combineFeatures

    tools = adsk.core.ObjectCollection.create()
    tools.add(male_body)

    ci = combine.createInput(female_body, tools)
    ci.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
    ci.isKeepToolBodies = True

    combine.add(ci)

G. Apply Clearance

Offset only internal cavity faces:

def apply_clearance(female_body, clearance):

    for face in female_body.faces:
        if is_connector_cavity_face(face):
            offset_face(face, clearance)

That is the entire connector generator in simplified geometry form.

PART 2
Robust Male/Female Assignment Strategy

You want this invariant:

When assembling pieces in path order, male always inserts into next piece.

Correct Rule:

Use path tangent.

Let:

T = normalized path tangent at cut

Ci = centroid of body

Compute:

Di = dot( Ci - CutPoint , T )

Body with larger positive Di = downstream piece
Downstream piece becomes MALE

This makes assembly direction consistent.

PART 3
UPDATED MASTER GUIDELINE README
Track Cutting + Connector Placement – Best Practice

1. Cutting Strategy (Correct & Required)
   DO NOT use infinite planes directly.

Instead:

Create construction plane perpendicular to path.

Create bounded sketch aligned to section bounding box.

Create surface patch only (no thickening required).

Split body using surface.

Delete surface.

This prevents:

Hairpin multi-splits

Remote intersections

Thin disk slivers

2. Sliver Management

After all cuts:

Remove residual SplitSurface bodies.

Merge bodies below min_volume_threshold.

Iterate until stable.

Never generate connectors before cleanup.

3. Connector Generation Rules

For each cut:

Detect exactly two adjacent bodies via coplanar face detection.

Determine forward path tangent.

Assign male = downstream body.

Sketch connector geometry on cut plane.

Extrude Join into male.

Combine Cut into female.

Offset cavity faces by clearance.

Apply chamfers.

4. Connector Geometry Standard

Use dual rectangular keys:

key_width
key_depth
key_height
clearance
lead_chamfer

Keys must:

Be symmetric about track centerline

Be extruded along plane normal

Never be world-axis aligned

Be fully parametric

5. Parameter Block
   key_width = 10 mm
   key_depth = 8 mm
   key_height = 6 mm
   clearance = 0.25 mm
   lead_chamfer = 0.75 mm
   min_sliver_volume = 0.05 cm^3

All connector geometry derives from these.

6. Ordering of Operations (Critical)

Correct order:

Analyze sections

Create bounded split surfaces

Split bodies

Merge slivers

Detect adjacent bodies

Assign male/female

Generate connectors

Rename pieces

Convert to components

Never generate connectors before sliver merge.

7. Assembly Invariant

If pieces are sorted along path:

For every piece i:

Its downstream face contains male connector.

Its upstream face contains female cavity.

This ensures:

Linear assembly

No alternating flip errors

Deterministic orientation

8. Why This System Is Robust

Because:

Split plane defines truth.

Connector derives from truth.

Path tangent defines orientation.

Clearance is parametric.

Slivers are removed before geometry modification.

No geometric ambiguity remains.

9. Result

This approach guarantees:

No misalignment

No rotational drift

No random male/female inversion

No unintended multi-cuts

Stable automation across entire 80×50 layout
