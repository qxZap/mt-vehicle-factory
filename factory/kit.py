"""Car factory: a rigged pack car -> Motor Town-ready static body.

blender --background --python factory.py -- <manifest.json> <car name> <factory dir>

Writes <factory>/out/<car>/: SM_<car>_Body.fbx, info.json, body.blend.
Slots follow Stinger's order so a Stinger-based clone keeps every slot index:
Trim, Windows, LeftTailLight, RightTailLight, HeadLight, LeftSignalLight,
RightSignalLight, Body_0, Body_1, ReverseLight.
"""
import bpy, bmesh, sys, json, re, math
from mathutils import Vector, Matrix

manifest_path, car_name, FD = sys.argv[-3], sys.argv[-2], sys.argv[-1]
car_info = next(c for c in json.load(open(manifest_path)) if c["name"] == car_name)
pack = car_info["pack"]
OUT = f"{FD}/kit/{car_name}"
import os; os.makedirs(OUT, exist_ok=True)

SLOTS = ["Trim", "Windows", "LeftTailLight", "RightTailLight", "HeadLight", "LeftSignalLight",
         "RightSignalLight", "Body_0", "Body_1", "ReverseLight",
         # paintable seats, appended so Stinger's indices above never move: vanilla's own names
         # (85 vehicles carry Seat_01; Brutus adds Seat_02 for a second seat colour)
         "Seat_01", "Seat_02",
         "SoftTop",   # a convertible's folded top: its own paint channel, declared by the roof part
         "Dashboard_01",  # the dash top and fascia, its own interior colour
         "RollCage_01",   # the roll cage part's own colour
         "WindowTrim_01", # the chrome frames around the glass
         "EmergencyRed", "EmergencyBlue"]  # police light lenses: vanilla Zydro_Police's slots, flashed by MTPoliceVehicle
TEX = {"streetracer": ("T_PolygonStreetRacer_01_A", "T_PolygonStreetRacer_Emissive_01"),
       "polycity": ("T_PolygonCity_Texture_01_A", "T_PolygonCity_Emissive_01"),
       "assetsville": ("T_colorPalette2048", None),
       "polytown": ("T_PolygonTown_01_A", "T_PolygonTown_Emissive_01"),
       "lowpolyracing": ("LP_Cars_Texture", None)}

# ---- material roles from the manifest's slot names (FBX material names are the asset names)
roles, paint_n = {}, 0
for s in car_info["materials"]:
    slot, mat = s["slot"].lower(), (s["mat"] or "").split(".")[-1]
    if "glass" in mat.lower() or "glass" in slot: r = "glass"
    elif slot == "lamp": r = "lamp"          # a lamp modelled as its own piece (Low Poly Racing headlights)
    elif "colorpalette" in mat.lower() or mat.startswith("Mat_Polygon") or "logo" in mat.lower(): r = "atlas"
    elif "carbon" in slot or "color_02" in slot: r = "paint2"
    else: r = "paint1"
    roles[mat] = r
if not any(r == "paint1" for r in roles.values()) and any(r == "paint2" for r in roles.values()):
    for k, r in roles.items():
        if r == "paint2": roles[k] = "paint1"; break

bpy.ops.wm.read_factory_settings(use_empty=True)
if os.path.exists(f"{FD}/fbx/{car_name}.blend"):   # unrigged packs: lpr_prep.py merges + groups the pieces
    bpy.ops.wm.open_mainfile(filepath=f"{FD}/fbx/{car_name}.blend")
else:
    bpy.ops.import_scene.fbx(filepath=f"{FD}/fbx/{car_name}.fbx")
car = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
for o in [o for o in bpy.data.objects if o.type == "MESH" and o is not car]:
    bpy.data.objects.remove(o)
mw = car.matrix_world.copy(); car.parent = None; car.matrix_world = mw
for m in list(car.modifiers): car.modifiers.remove(m)
for o in list(bpy.data.objects):
    if o is not car: bpy.data.objects.remove(o)
bpy.context.view_layer.objects.active = car; car.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

groups = {g.index: g.name for g in car.vertex_groups}
# Presets share one body, but an off-road preset is modelled lifted (Muscle_04: +17.5 cm), so its
# parts would float above the base body. Line every preset up with preset 01 on the doors, a panel
# all presets share unchanged. Preset 01 records the anchor; the others move onto it.
def door_anchor():
    pts = [v.co for v in car.data.vertices if v.groups and "door_l" in (n := groups[max(v.groups, key=lambda q: q.weight).group].lower()) and "glass" not in n]
    if not pts: return None
    return [(min(p[i] for p in pts) + max(p[i] for p in pts)) / 2 for i in range(3)]
frame, preset_no = car_name.rsplit("_", 1)
anchor_file = f"{FD}/kit/{frame}_anchor.json"
here = door_anchor()
if here and preset_no == "01":
    json.dump(here, open(anchor_file, "w"))
elif here and os.path.exists(anchor_file):
    base = json.load(open(anchor_file)); d = Vector(base) - Vector(here)
    if d.length > 0.005:
        for v in car.data.vertices: v.co += d
        print("ALIGNED", car_name, [round(x, 3) for x in d])
def kind(bone):
    b = bone.lower()
    m = re.search(r"wheel_?(f|r)(l|r)(_0?1)?$", b)
    if m: return "wheel_" + m.group(1) + m.group(2)
    if "wheel" in b and "steer" not in b: return "wheelnum:" + bone    # middle axles, duals, numbered
    if "steer" in b: return "steer"
    if "plate" in b: return "plate"
    if re.search(r"speedo|gauge|tacho|needle|dial", b): return "gauge"   # the game draws its own dashboard
    return "body"

bm = bmesh.new(); bm.from_mesh(car.data)
plyr = bm.faces.layers.int.new("part")   # before any face is held: a new layer invalidates BMFace refs
deform = bm.verts.layers.deform.active
def face_kind(f):
    if deform is None: return "body"
    votes = {}
    for v in f.verts:
        if v[deform]:
            g = max(v[deform].items(), key=lambda kv: kv[1])[0]
            k = kind(groups.get(g, "")); votes[k] = votes.get(k, 0) + 1
    return max(votes, key=votes.get) if votes else "body"
fk = {f: face_kind(f) for f in bm.faces}

def bbox(faces):
    pts = [v.co for f in faces for v in f.verts]
    lo = Vector(map(min, *pts)); hi = Vector(map(max, *pts)); return lo, hi

# Numbered wheel bones (Wheel_33..36) carry no corner: when the named corners are missing,
# give each numbered wheel the corner its position says. A numbered wheel left over when the
# corners exist (Exotic_03's bonnet spare) stays part of the body.
if not any(k == "wheel_fl" for k in fk.values()):
    nums = {}
    for f, k in fk.items():
        if k.startswith("wheelnum:"): nums.setdefault(k, []).append(f)
    if len(nums) == 4:
        cen = {k: sum((v.co for f in fs for v in f.verts), Vector()) / sum(len(f.verts) for f in fs) for k, fs in nums.items()}
        mx = sum(c.x for c in cen.values()) / 4
        for k, c in cen.items():
            corner = "wheel_" + ("f" if c.x > mx else "r") + ("l" if c.y > 0 else "r")
            for f in nums[k]: fk[f] = corner
# Remaining wheel groups (middle axles, dual rears) are wheels too: drop them, but record them.
extra_wheels = {}
for f, k in list(fk.items()):
    if k.startswith("wheelnum:"):
        bone = k.split(":", 1)[1].lower()
        if "spare" in bone or (any(fk[x] == "wheel_fl" for x in fk) and re.search(r"wheel_?\d+$", bone) and not re.search(r"_(f|r|m)(l|r)", bone)):
            fk[f] = "body"              # a numbered wheel beside named corners is a decorative spare
        else:
            extra_wheels.setdefault(k, []).append(f); fk[f] = "wheel_extra"
# ---- scale: Assetsville ships at 2x. Normalise on the wheel diameter.
wheel_faces = {k: [f for f in bm.faces if fk[f] == k] for k in ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr")}
have_wheels = all(wheel_faces.values())
scale = 1.0
if have_wheels:
    lo, hi = bbox(wheel_faces["wheel_fl"]); diam = max(hi.x - lo.x, hi.z - lo.z)
    if diam > 2.0: scale = 0.5          # only an absurd wheel means a 2x export; truck wheels are ~1.1 m
if scale != 1.0:
    bmesh.ops.scale(bm, vec=(scale, scale, scale), verts=bm.verts)

# ---- orientation: +X forward, front axle nearest the steering wheel.
def centre(faces):
    lo, hi = bbox(faces); return (lo + hi) / 2
steer_faces = [f for f in bm.faces if fk[f] == "steer"]
rot = 0
if have_wheels:
    fx = (centre(wheel_faces["wheel_fl"]).x + centre(wheel_faces["wheel_fr"]).x) / 2
    rx = (centre(wheel_faces["wheel_rl"]).x + centre(wheel_faces["wheel_rr"]).x) / 2
    front_neg = fx < rx
    if steer_faces:
        sx = centre(steer_faces).x
        front_neg = abs(sx - min(fx, rx)) < abs(sx - max(fx, rx)) if fx < rx else False
    def face_bone(f):
        votes = {}
        for v in f.verts:
            if v[deform]:
                g = max(v[deform].items(), key=lambda kv: kv[1])[0]; votes[g] = votes.get(g, 0) + 1
        return groups.get(max(votes, key=votes.get), "") if votes else ""
    leg = [f for f in bm.faces if "supportleg" in face_bone(f).lower()] if (deform is not None and not steer_faces) else []
    if leg:
        fx, rx = (centre(leg).x, 0.0)
    if fx < rx:   # the bone labelled "front" sits on -X: turn the car around
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi, 3, "Z")); rot = 180
# ground the car: lowest wheel point at z=0 would put the hubs at the radius
info = {"car": car_name, "pack": pack, "scale": scale, "rotated": rot}
def _islands_kit(faces):
    S, seen = set(faces), set()
    for f in faces:
        if f in seen: continue
        isl, st = [], [f]; seen.add(f)
        while st:
            x = st.pop(); isl.append(x)
            for e in x.edges:
                for y in e.link_faces:
                    if y in S and y not in seen: seen.add(y); st.append(y)
        yield isl
# Cabin boxes (dash, gauge hood, rear bench) were measured by hand on the Muscle. Other frames get
# the same boxes placed relative to THEIR steering-wheel centre: the Synty cabins share a layout.
SC = centre(steer_faces) if steer_faces else None
MUSCLE_SC = Vector((0.5245, 0.4613, 1.0315))
def cabin_box(table, frame_key, keep_y=True):
    if frame_key in table: return table[frame_key]
    if SC is None or "SK_Veh_Preset_Muscle" not in table: return None
    lo_m, hi_m = table["SK_Veh_Preset_Muscle"]
    d = SC - MUSCLE_SC
    if keep_y:   # full-width boxes keep their absolute y
        return ((lo_m[0] + d.x, lo_m[1], lo_m[2] + d.z), (hi_m[0] + d.x, hi_m[1], hi_m[2] + d.z))
    return ((lo_m[0] + d.x, lo_m[1] + d.y, lo_m[2] + d.z), (hi_m[0] + d.x, hi_m[1] + d.y, hi_m[2] + d.z))

uvl = bm.loops.layers.uv.active
mats = [m.name for m in car.data.materials]
def role(f):
    n = mats[f.material_index] if f.material_index < len(mats) else ""
    base = re.sub(r"\.\d+$", "", n)
    return roles.get(base, "glass" if "glass" in base.lower() else "atlas")

atlas_name, emi_name = TEX[pack]
atlas_name = car_info.get("atlas", atlas_name)    # a livery car carries its own copy of the atlas
def load(n):
    if not n: return None
    img = bpy.data.images.load(f"{FD}/tex/{n}.png"); return (img.size[0], img.size[1], list(img.pixels))
ATL, EMI = load(atlas_name), load(emi_name)
def px(T, uv):
    w, h, P = T
    if not (math.isfinite(uv.x) and math.isfinite(uv.y)): uv = Vector((0, 0))   # NaN/inf UVs (Sports_14 ships some)
    x = min(w - 1, max(0, int((uv.x % 1.0) * w))); y = min(h - 1, max(0, int((uv.y % 1.0) * h)))
    i = (y * w + x) * 4; return P[i], P[i + 1], P[i + 2]
def face_uv(f): return sum((l[uvl].uv for l in f.loops), Vector((0, 0))) / len(f.loops)

drop = [f for f in bm.faces if fk[f] in ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr", "wheel_extra", "steer", "plate", "gauge")]
keep = [f for f in bm.faces if f not in set(drop)]
lo, hi = bbox(keep); L = hi.x - lo.x
info["body_min"] = [round(c * 100, 1) for c in lo]; info["body_max"] = [round(c * 100, 1) for c in hi]

# Polygon City has no paint slot: its paint is the dominant HUE over the outward-facing
# exterior panels (the atlas shades one colour across several tones, so exact colour fails).
import colorsys
paint_rgb = paint2_rgb = None
def hue_bin(rgb):
    if pack == "lowpolyracing":       # a palette of flat 25 px cells: the exact cell is the colour
        return ("c", tuple(round(x * 255) for x in rgb))
    return _hue_bin(rgb)
def _hue_bin(rgb):
    h, sat, val = colorsys.rgb_to_hsv(*rgb)
    if sat < 0.25 or val < 0.15: return ("v", round(val * 4))     # greys: bucket by brightness
    return ("h", int(h * 12) % 12)
if pack in ("polycity", "polytown", "lowpolyracing"):
    from mathutils.bvhtree import BVHTree
    _bvh = BVHTree.FromBMesh(bm)
    hist = {}
    for f in keep:
        if role(f) != "atlas": continue
        n = f.normal
        if not (abs(n.y) > 0.55 or n.z > 0.6): continue          # side panels, roof, bonnet
        key = hue_bin(px(ATL, face_uv(f)))
        if pack == "lowpolyracing":   # only panels seen from outside vote: a floor's ray hits the roof
            if _bvh.ray_cast(f.calc_center_median() + n * 0.003, n, 20.0)[0] is not None: continue
        hist[key] = hist.get(key, 0) + f.calc_area()
    info["paint_hist"] = sorted(([str(k), round(v, 2)] for k, v in hist.items()), key=lambda kv: -kv[1])[:6]
    if hist:
        paint_rgb = max(hist, key=hist.get)
        hue = {k: v for k, v in hist.items() if k[0] == "h"}
        if hue and pack != "lowpolyracing" and max(hue.values()) >= 0.35 * sum(hist.values()):
            paint_rgb = max(hue, key=hue.get)       # a coloured car: its colour, not the dark trim
    info["paint_bin"] = list(paint_rgb) if paint_rgb else None
    # A second colour nearly as big as the first (two-tone roof, racing stripes) is the second paint
    # channel, Body_1. Dark trim greys never qualify.
    paint2_rgb = None
    if pack == "lowpolyracing" and paint_rgb:
        rest = sorted(((v, k) for k, v in hist.items() if k != paint_rgb and max(k[1]) >= 60), reverse=True)
        if rest and rest[0][0] >= 0.2 * hist[paint_rgb]: paint2_rgb = rest[0][1]
    info["paint2_bin"] = list(paint2_rgb) if paint2_rgb else None
def same_bin(rgb, b):
    """A livery texture is not flat cells: its base varies by a shade or two, which exact matching
    missed (Kaiju Turbo's grey panels stayed unpainted). LPR matches within 8 of 255."""
    k = hue_bin(rgb)
    if pack != "lowpolyracing" or k[0] != "c" or b[0] != "c": return k == b
    return max(abs(x - y) for x, y in zip(k[1], b[1])) <= 8
assign = {}
for f in keep:
    r = role(f); c = f.calc_center_median()
    if r == "glass": s = "Windows"
    elif r == "lamp":
        s = ("HeadLight" if c.x > (lo.x + hi.x) / 2 else ("LeftTailLight" if c.y > 0 else "RightTailLight"))
    elif r == "paint1": s = "Body_0"
    elif r == "paint2": s = "Body_1"
    else:
        uv = face_uv(f); rr, gg, bb = px(ATL, uv)
        # Low Poly Racing: an exact palette cell IS the paint, whichever way the panel faces. The facing
        # rule left nose and tail panels in the pack's colour, patches on the paint (user, 5 Nov 2026).
        # A livery car is clean: everything mapped outside the palette corner (u, v < 0.16) is paint.
        faces_out = pack == "lowpolyracing" or abs(f.normal.y) + max(f.normal.z, 0) > 0.3
        livery_panel = bool(car_info.get("atlas")) and not (uv.x % 1.0 < 0.16 and uv.y % 1.0 < 0.16)
        if livery_panel or (paint_rgb and same_bin((rr, gg, bb), paint_rgb) and faces_out): s = "Body_0"
        elif paint2_rgb and same_bin((rr, gg, bb), paint2_rgb) and faces_out: s = "Body_1"
        else:
            front = c.x > hi.x - 0.35 * 1.0 and c.x > lo.x + L * 0.75
            rear = c.x < lo.x + 0.35 and c.x < lo.x + L * 0.25
            redish = rr > 0.3 and rr > 2 * gg and rr > 2 * bb
            glow = (max(px(EMI, uv)) > 0.25) if EMI else (min(rr, gg, bb) > 0.8 or redish or (rr > 0.75 and 0.3 < gg < 0.7 and bb < 0.3))
            s = "Trim"
            if glow and (front or rear):
                left = c.y > 0
                orange = rr > 0.6 and 0.25 < gg < 0.7 and bb < 0.35
                red = (rr > 0.45 and gg < 0.3) or redish
                if front: s = ("LeftSignalLight" if left else "RightSignalLight") if orange else ("Trim" if red else "HeadLight")
                else:
                    if orange: s = "LeftSignalLight" if left else "RightSignalLight"
                    elif red: s = "LeftTailLight" if left else "RightTailLight"
                    elif EMI: s = "ReverseLight"          # palette packs: white at the rear is chrome
                    else: s = "Trim"
    assign[f] = s
# Low Poly Racing lamps are often the glass lens itself (no white texel under it): glass in the
# front/rear quarter below the beltline (15 cm under the steering wheel) is a lamp, not a window.
if pack == "lowpolyracing" and SC is not None:
    for f, s_ in list(assign.items()):
        c = f.calc_center_median()
        if s_ == "Windows" and c.z < SC.z - 0.15:
            if c.x > hi.x - 0.25 * L: assign[f] = "HeadLight"
            elif c.x < lo.x + 0.25 * L: assign[f] = "LeftTailLight" if c.y > 0 else "RightTailLight"
# ...unless the lamp has insides. A lamp face with open air in front of it and the lamp's own housing
# within 25 cm behind it is the COVER: clear glass, so the bulb and reflector behind it show and light
# up. Lit opaque covers were the "white patches" (Flare Rotary, Azure Edge, Glacier GT; user 5 Nov).
if pack == "lowpolyracing":
    LAMPS = ("HeadLight", "LeftTailLight", "RightTailLight", "LeftSignalLight", "RightSignalLight", "ReverseLight")
    bm.faces.ensure_lookup_table()
    covers = 0
    for f, s_ in list(assign.items()):
        if s_ not in LAMPS: continue
        c = f.calc_center_median(); n = f.normal
        if n.length < 0.5: continue
        if _bvh.ray_cast(c + n * 0.003, n, 3.0)[0] is not None: continue        # something in front: not the outermost
        hit = _bvh.ray_cast(c - n * 0.003, -n, 0.10)
        if hit[0] is None: continue                                              # a lens with nothing behind IS the lamp
        bf = bm.faces[hit[2]]
        if assign.get(bf) is None or bf.calc_area() > 3 * f.calc_area() + 0.002: continue   # a body panel, not a housing
        assign[f] = "Windows"
        if assign[bf] not in LAMPS: assign[bf] = s_                              # the housing behind lights instead
        covers += 1
    info["lamp_covers"] = covers
# Rear clusters keep their own colours. Carving strips out of a solid red cluster (inner quarter
# reverse, outer quarter blink) ran on whichever side came first and left the car lopsided; the
# user preferred the solid red side.
# No reverse lamp of its own (a solid red cluster): the rear badge becomes it -- the Muscle's boot
# logo is white-grey and sits between the clusters, which is where a reverse lamp would be.
if deform is not None and not any(s == "ReverseLight" for s in assign.values()):
    def _bone(f):
        votes = {}
        for v in f.verts:
            if v[deform]:
                g = max(v[deform].items(), key=lambda kv: kv[1])[0]; votes[g] = votes.get(g, 0) + 1
        return groups.get(max(votes, key=votes.get), "").lower() if votes else ""
    badge = [f for f in assign if "badge" in _bone(f) and f.calc_center_median().x < lo.x + 0.35]
    for f in badge: assign[f] = "ReverseLight"
    if badge: info_badge_reverse = len(badge)
# Seats: the pack's seat pieces (front seats) -> Seat_01, the rear bench area -> Seat_02.
if deform is not None:
    def _sbone(f):
        votes = {}
        for v in f.verts:
            if v[deform]:
                g = max(v[deform].items(), key=lambda kv: kv[1])[0]; votes[g] = votes.get(g, 0) + 1
        return groups.get(max(votes, key=votes.get), "").lower() if votes else ""
    for f in list(assign):
        if "seat" in _sbone(f) and assign[f] == "Trim":
            rr, gg, bb = px(ATL, face_uv(f))
            # seat pieces are the front seats, unless they sit well behind the wheel (a sedan's rear
            # seats are seat pieces too): Muscle front backrests end 0.81 m behind its wheel centre
            behind = SC is not None and f.calc_center_median().x < SC.x - 0.85
            assign[f] = "Seat_02" if behind else "Seat_01"
    # The rear bench is not a seat piece in the pack but interior trim behind the front seats.
    BENCH = {"SK_Veh_Preset_Muscle": ((-1.15, -0.78, 0.3), (-0.33, 0.78, 0.95))}
    bx = cabin_box(BENCH, frame)
    if bx:
        lo_b, hi_b = bx
        if pack == "lowpolyracing":   # its cabins are narrower: full width caught the rear wheel wells
            lo_b, hi_b = (lo_b[0], -0.6, lo_b[2]), (hi_b[0], 0.6, hi_b[2])
        for f in list(assign):
            c = f.calc_center_median()
            if assign[f] == "Trim" and all(lo_b[i] <= c[i] <= hi_b[i] for i in range(3)):
                assign[f] = "Seat_02"
        if pack == "lowpolyracing":      # no seat pieces: the front seats are the box 0.8 m ahead of the bench
            for f in list(assign):
                c = f.calc_center_median()
                if assign[f] == "Trim" and hi_b[0] < c.x <= hi_b[0] + 0.95 and 0.15 < abs(c.y) < 0.75 and lo_b[2] <= c.z <= SC.z + 0.15:
                    assign[f] = "Seat_01"
    # Window chrome: light Trim faces within 1.5 cm of the glass (the glass is a separate island,
    # so "touching" is distance, not shared edges).
    from mathutils import kdtree
    glass = [v.co.copy() for f, s_ in assign.items() if s_ == "Windows" for v in f.verts]
    if glass:
        kd = kdtree.KDTree(len(glass))
        for i, co in enumerate(glass): kd.insert(co, i)
        kd.balance()
        for f in list(assign):
            # 4 cm / lum 0.38: at 1.5 cm / 0.45 the outer frame strips were missed (user screenshot)
            if assign[f] == "Trim" and any(kd.find(v.co)[2] < 0.04 for v in f.verts):
                rr, gg, bb = px(ATL, face_uv(f))
                if (rr + gg + bb) / 3 > 0.38: assign[f] = "WindowTrim_01"
    # Two-tone frames: the bonnet's paint is the second colour (Body_1, "Racing Stripe" in the
    # paint menu), as the pack shows it. Without this Body_1 holds a single filler face.
    if frame in ("SK_Veh_Preset_Muscle",):
        for f in list(assign):
            if assign[f] == "Body_0" and "bonnet" in _sbone(f): assign[f] = "Body_1"
    # Dashboard: Trim of the body between the windscreen and the seats, minus the bits that are
    # separate pieces in the pack (stereo, gear stick, handbrake, pedals, steering).
    DASH = {"SK_Veh_Preset_Muscle": ((0.5, -0.85, 0.8), (1.05, 0.85, 1.13))}
    dx = cabin_box(DASH, frame)
    if dx:
        lo_d, hi_d = dx
        for f in list(assign):
            c = f.calc_center_median()
            if assign[f] == "Trim" and all(lo_d[i] <= c[i] <= hi_d[i] for i in range(3)) and                     not any(k in _sbone(f) for k in ("headunit", "gear", "handbrake", "pedal", "steer", "wiper", "mirror")):
                assign[f] = "Dashboard_01"

# ---- measurements, Unreal space (cm, Y flipped)
def ue(v): return [round(v.x * 100, 1), round(-v.y * 100, 1), round(v.z * 100, 1)]
def side_centre(pred):
    pts = [(f.calc_center_median(), f.calc_area()) for f, s in assign.items() if pred(f, s)]
    if not pts or sum(a for _, a in pts) == 0: return None
    return ue(sum((c * a for c, a in pts), Vector()) / sum(a for _, a in pts))
info["lights"] = {
    "HeadLight_Left": side_centre(lambda f, s: s == "HeadLight" and f.calc_center_median().y > 0),
    "HeadLight_Right": side_centre(lambda f, s: s == "HeadLight" and f.calc_center_median().y < 0),
    "Blinker_FrontLeft": side_centre(lambda f, s: s == "LeftSignalLight" and f.calc_center_median().x > 0),
    "Blinker_FrontRight": side_centre(lambda f, s: s == "RightSignalLight" and f.calc_center_median().x > 0),
    "Tail_Left": side_centre(lambda f, s: s == "LeftTailLight"),
    "Tail_Right": side_centre(lambda f, s: s == "RightTailLight"),
    "Reverse": side_centre(lambda f, s: s == "ReverseLight"),
}
info["wheels_extra"] = [ue(centre(fs)) for fs in extra_wheels.values()] if "extra_wheels" in dir() else []
if have_wheels:
    info["wheels"] = {}
    for k, fs in wheel_faces.items():
        wlo, whi = bbox(fs); c = (wlo + whi) / 2
        info["wheels"][k] = ue(c) + [round(max(whi.x - wlo.x, whi.z - wlo.z) * 100, 1), round((whi.y - wlo.y) * 100, 1)]
if steer_faces:
    P = [v.co.copy() for f in steer_faces for v in f.verts]
    import numpy as np
    A = np.array([p[:] for p in P]); A -= A.mean(0)
    w, vecs = np.linalg.eigh(A.T @ A); n = vecs[:, 0]
    if n[0] < 0: n = -n
    info["steering"] = {"centre": ue(centre(steer_faces)), "tilt_deg": round(math.degrees(math.atan2(n[2], n[0])), 2)}
xmin = lo.x
roof = [v.co.z for f in keep for v in f.verts if -0.45 < v.co.x < -0.15 and assign.get(f) != "Windows"]
boot = [v.co.z for f in keep for v in f.verts if xmin + 0.05 < v.co.x < xmin + 0.25]
info["sockets"] = {"TaxiRoofSign": [-30.0, 0.0, round(max(roof) * 100, 1) if roof else 140.0],
                   "RearWing": [round((xmin + 0.15) * 100, 1), 0.0, round(max(boot) * 100, 1) if boot else 100.0],
                   "TrailerHitch": [round(xmin * 100, 1), 0.0, 40.0]}
counts = {s: sum(1 for v in assign.values() if v == s) for s in SLOTS}
# Headlight clusters: the emissive map often marks only the small inner lamp, leaving the big lens
# dark (the Exotic). Light-coloured Trim faces in the same loose piece as a lit headlight face join it.
lit = [f for f, s_ in assign.items() if s_ == "HeadLight"]
if lit:
    trimmed = [f for f, s_ in assign.items() if s_ in ("Trim", "HeadLight")]
    for isl in _islands_kit(trimmed):
        if any(assign[f] == "HeadLight" for f in isl):
            for f in isl:
                if assign[f] == "Trim":
                    rr, gg, bb = px(ATL, face_uv(f))
                    if (rr + gg + bb) / 3 > 0.55: assign[f] = "HeadLight"
# Police lights: the pack's light bar and police lamps are their own bones; their lenses go to the
# slots vanilla police bodies use (M_EmergencyLight_Red/Blue), housings stay Trim.
if deform is not None:
    for f in list(assign):
        if any(k in _sbone(f) for k in ("lightbar", "light_bar", "light_police")):
            rr, gg, bb = px(ATL, face_uv(f))
            if rr > 0.4 and rr > 1.6 * max(gg, bb): assign[f] = "EmergencyRed"
            elif bb > max(rr, gg) + 0.05: assign[f] = "EmergencyBlue"    # the pack's blue lens is a dark navy (0.2,0.2,0.3)
# Mirrors: the pack's are plain geometry, the game's reflect. The interior mirror is its own bone;
# a side mirror is the outermost loose piece at the front of its door. Both are cut, and their
# centres recorded so the base car's MTMirrorComponents can be put exactly there.
def _islands(faces):
    S, seen = set(faces), set()
    for f in faces:
        if f in seen: continue
        isl, st = [], [f]; seen.add(f)
        while st:
            x = st.pop(); isl.append(x)
            for e in x.edges:
                for y in e.link_faces:
                    if y in S and y not in seen: seen.add(y); st.append(y)
        yield isl
if deform is not None:
    room = [f for f in assign if "mirror" in _sbone(f)]
    if room:
        info["mirror_room"] = ue(sum((f.calc_center_median() for f in room), Vector()) / len(room))
        for f in room: assign.pop(f); drop.append(f)
    for side, key, sgn in (("l", "door_l", 1), ("r", "door_r", -1)):
        door = [f for f in assign if key in _sbone(f) and "glass" not in _sbone(f)]
        if not door: continue
        xs = [v.co.x for f in door for v in f.verts]; midx = (min(xs) + max(xs)) / 2
        tip = max((v.co for f in door for v in f.verts if v.co.x > midx), key=lambda c: sgn * c.y)
        cut = [isl for isl in _islands(door) if all((v.co - tip).length < 0.25 for g in isl for v in g.verts)]
        if cut:
            fs = [f for isl in cut for f in isl]
            info["mirror_" + side] = ue(sum((f.calc_center_median() for f in fs), Vector()) / len(fs))
            for f in fs: assign.pop(f); drop.append(f)
counts = {s: sum(1 for v in assign.values() if v == s) for s in SLOTS}
info["counts"] = counts
# driver cushion centre (Unreal cm): seat and cockpit camera are placed from it, using the offsets
# that put Biceps' driver right (Stinger values vs the Muscle cushion)
cush = [f.calc_center_median() for f, s_ in assign.items() if s_ == "Seat_01" and f.is_valid
        and f.calc_center_median().y > 0.15 and SC is not None and f.calc_center_median().z < SC.z - 0.25]
if cush:
    info["seat_driver"] = ue(sum(cush, Vector()) / len(cush))

PARTS = [("front_bumper", "FrontBumper"), ("rear_bumper", "RearBumper"), ("bonnet", "Bonnet"),
         ("side_skirt", "SideSkirt"), ("fender", "Fender"), ("spoiler", "RearWing"), ("roof_", "Roof"),
         # preset-only extras ride with the part they belong to, so every preset shares one body
         # extras that the game has a slot for become their own parts (user, 4 Nov 2026): the
         # louvers (RearWindowLouvers), the nudge bar (Bullbar) and the roll cage (own weight)
         ("intake", "Bonnet"), ("louver", "Louvers"), ("rollcage", "RollCage"), ("nudge_bar", "Bullbar"),
         ("light_cover", "FrontBumper"), ("mud_flap", "MudFlap")]
def bone_of(f):
    votes = {}
    for v in f.verts:
        if v[deform]:
            g = max(v[deform].items(), key=lambda kv: kv[1])[0]; votes[g] = votes.get(g, 0) + 1
    return groups.get(max(votes, key=votes.get), "") if votes else ""
part_names = ["body"]
for f in keep:
    bo = bone_of(f)
    if bo.startswith("part:"):    # lpr_prep.py names the part itself: part:<Slot>_P<n>, alternatives of one slot
        tag = bo[5:]
        if tag not in part_names: part_names.append(tag)
        f[plyr] = part_names.index(tag); continue
    b = bo.lower()
    if b == "glass": b = "roof_glass"            # a preset's bare "Glass" bone is its roof glass
    for key, slot in PARTS:
        if key in b:
            if slot == "MudFlap": slot = "FrontBumper" if f.calc_center_median().x > 0 else "RearBumper"
            # one variant = everything this preset puts in the slot (a spoiler can be struts + blade)
            tag = slot + "_P" + car_name.rsplit("_", 1)[-1].lstrip("0")
            if tag not in part_names: part_names.append(tag)
            f[plyr] = part_names.index(tag); break
info["parts"] = part_names[1:]
bmesh.ops.delete(bm, geom=drop, context="FACES")
car.data.materials.clear()
for s in SLOTS: car.data.materials.append(bpy.data.materials.new(s))
for f, s in assign.items():
    if f.is_valid: f.material_index = SLOTS.index(s)
# never leave a slot empty: an empty slot vanishes on import and shifts every later index
for s in SLOTS:
    if counts[s] == 0:
        f = min((ff for ff in bm.faces if ff.is_valid and ff.material_index == SLOTS.index("Trim")), key=lambda ff: ff.calc_area())
        f.material_index = SLOTS.index(s); counts[s] = 1; info.setdefault("filler_slots", []).append(s)
bm.to_mesh(car.data); bm.free()

# Hard edges: the packs' crisp panels came from custom split normals, which the mesh edits
# drop -- left alone everything shades smooth and flat panels look bulbous.
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
try: bpy.ops.mesh.customdata_custom_splitnormals_clear()
except Exception: pass
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(20), keep_sharp_edges=False)
# decal UV: a unique unwrap of the painted panels on a second channel
uv2 = car.data.uv_layers.new(name="DecalUV"); car.data.uv_layers.active = uv2
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="DESELECT")
for s in ("Body_0", "Body_1"):
    car.active_material_index = SLOTS.index(s); bpy.ops.object.material_slot_select()
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004)
bpy.ops.object.mode_set(mode="OBJECT"); car.data.uv_layers.active = car.data.uv_layers[0]
car.vertex_groups.clear(); car.name = f"SM_{car_name}_Body"
os.makedirs(f"{OUT}/parts", exist_ok=True)
pattr = car.data.attributes["part"]
for idx, tag in enumerate(part_names):
    if idx == 0: continue
    dup = car.copy(); dup.data = car.data.copy(); bpy.context.collection.objects.link(dup)
    pa = dup.data.attributes["part"]
    bmp = bmesh.new(); bmp.from_mesh(dup.data); lay = bmp.faces.layers.int["part"]
    bmesh.ops.delete(bmp, geom=[f for f in bmp.faces if f[lay] != idx], context="FACES")
    # per-part recolours: (car, part tag) -> Trim faces behind x get the atlas texel at uv. The
    # Muscle convertible's folded top sits on a light blue-grey texel and reads as white paint.
    KIT_RECOLOR = {("SK_Veh_Preset_Muscle_01", "Roof_P1"): (-0.5, (0.0011, 0.0011))}
    if tag.startswith("RollCage"):
        for f in bmp.faces: f.material_index = SLOTS.index("RollCage_01")   # all of it: the cage is body-painted in the pack
    rule = KIT_RECOLOR.get((car_name, tag))
    if rule:
        uvp = bmp.loops.layers.uv[0]
        for f in bmp.faces:
            if f.material_index == SLOTS.index("Trim") and f.calc_center_median().x < rule[0]:
                for l in f.loops: l[uvp].uv = rule[1]
                f.material_index = SLOTS.index("SoftTop")
    bmp.to_mesh(dup.data); bmp.free()
    dup.name = f"SM_{car_name}_{tag}"
    bpy.ops.object.select_all(action="DESELECT"); dup.select_set(True); bpy.context.view_layer.objects.active = dup
    bpy.ops.object.material_slot_remove_unused()
    sub_ = "popup" if tag.startswith("Popup") else "parts"     # pop-up lamp states: popup.py rigs them, they are no tuning part
    os.makedirs(f"{OUT}/{sub_}", exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=f"{OUT}/{sub_}/{dup.name}.fbx", use_selection=True, object_types={"MESH"},
                             apply_scale_options="FBX_SCALE_UNITS", mesh_smooth_type="FACE", add_leaf_bones=False)
    bpy.data.objects.remove(dup)
bmb = bmesh.new(); bmb.from_mesh(car.data); lay = bmb.faces.layers.int["part"]
# LPR body collision: 8 convex hulls of the shell cut along X, shipped as UCX_ meshes (the auto
# decomposition left holes). Each part carries its own collision, as vanilla's do (Panther Roof_01),
# so whichever kit is fitted is solid in its own shape.
ucx = []
if True:     # every pack: hulls that skip antennas and mirrors (LPR first, all packs from 5 Nov)
    # small loose pieces stay out of the hulls: antennas and mirrors must be walk-through (user, 5 Nov),
    # and a hull spanning a mirror or roof antenna stood well above and beside the real roof
    def _islands(fs):
        seen = set()
        for f in fs:
            if f in seen: continue
            isl, st = [], [f]; seen.add(f)
            while st:
                x = st.pop(); isl.append(x)
                for e in x.edges:
                    for y in e.link_faces:
                        if y not in seen and y[lay] == 0: seen.add(y); st.append(y)
            yield isl
    pts = []
    for isl in _islands([f for f in bmb.faces if f[lay] == 0]):
        P = [v.co.copy() for f in isl for v in f.verts]
        ext = [max(p[i] for p in P) - min(p[i] for p in P) for i in range(3)]
        if ext[0] * ext[1] * ext[2] < 0.01 and max(ext) < 0.6: continue
        pts += P
    # 12 slices along X, each split left/right (overlapping at the centre line): one hull per whole-width
    # slice bridged fender peaks and buttresses, a flat top above the C3's bonnet and rear glass
    x0 = min(p.x for p in pts); x1 = max(p.x for p in pts); N = 12; step = (x1 - x0) / N
    for k, side in ((k, s) for k in range(N) for s in (1, -1)):
        sl = [p for p in pts if x0 + (k - 0.05) * step <= p.x <= x0 + (k + 1.05) * step and side * p.y >= -0.05]
        if len(sl) < 8: continue
        hb = bmesh.new()
        for p in sl: hb.verts.new(p)
        bmesh.ops.convex_hull(hb, input=hb.verts[:])
        bmesh.ops.delete(hb, geom=[v for v in hb.verts if not v.link_faces], context="VERTS")
        me = bpy.data.meshes.new(f"UCX_{car.name}_{2 * k + (side < 0):02d}"); hb.to_mesh(me); hb.free()
        o = bpy.data.objects.new(me.name, me); bpy.context.collection.objects.link(o); ucx.append(o)
    info["ucx_hulls"] = len(ucx)
bmesh.ops.delete(bmb, geom=[f for f in bmb.faces if f[lay] != 0], context="FACES")
# Per-frame cuts: loose islands lying wholly inside a box go. The gauge hood over the pack's dials
# doubles up with the game's own dashboard in first person (Blender metres, after alignment).
KIT_CUTS = {"SK_Veh_Preset_Muscle": [((0.63, 0.23, 1.0), (0.94, 0.69, 1.17))]}
def islands(faces):
    seen = set()
    for f in faces:
        if f in seen: continue
        isl, st = [], [f]; seen.add(f)
        while st:
            x = st.pop(); isl.append(x)
            for e in x.edges:
                for y in e.link_faces:
                    if y not in seen: seen.add(y); st.append(y)
        yield isl
cut = []
cuts = KIT_CUTS.get(frame) or ([cabin_box({"SK_Veh_Preset_Muscle": KIT_CUTS["SK_Veh_Preset_Muscle"][0]}, frame, keep_y=False)]
                                if SC is not None else [])
for lo, hi in cuts:
    for isl in islands(list(bmb.faces)):
        if all(lo[i] <= v.co[i] <= hi[i] for g in isl for v in g.verts for i in range(3)): cut += isl
if cut:
    bmesh.ops.delete(bmb, geom=cut, context="FACES"); info["cut_faces"] = len(cut)
# the stripped body must still carry all 10 slots: the parts took some (bumper headlights), and an
# empty slot vanishes on import and shifts every later index the blueprint relies on
for i, s in enumerate(SLOTS):
    if not any(f.material_index == i for f in bmb.faces):
        f = min((ff for ff in bmb.faces if ff.material_index == 0), key=lambda ff: ff.calc_area())
        f.material_index = i; info.setdefault("body_filler_slots", []).append(s)
bmb.to_mesh(car.data); bmb.free()
bpy.ops.object.select_all(action="DESELECT"); car.select_set(True); bpy.context.view_layer.objects.active = car
for o in ucx: o.select_set(True)
bpy.ops.export_scene.fbx(filepath=f"{OUT}/SM_{car_name}_Body.fbx", use_selection=True, object_types={"MESH"},
                         apply_scale_options="FBX_SCALE_UNITS", mesh_smooth_type="FACE", add_leaf_bones=False)
json.dump(info, open(f"{OUT}/info.json", "w"), indent=1)
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/body.blend")
print("KIT", car_name, info["parts"], json.dumps({k: info[k] for k in ("scale", "rotated", "counts")}))
