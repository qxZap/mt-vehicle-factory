"""Street Racer motorbike preset -> Motor Town bike pieces, laid out the way vanilla Zero is:

  body       everything that does not steer or spin (frame, fairing, screen, tank, seat, swing-arm,
             exhausts) -> SM_<name>_Body
  handlebar  handlebars + front fork, IN BODY SPACE (Zero's Handlebar mesh is body-space too); the game
             turns it about the body's SteeringWheel socket, whose X axis runs down the steering head
  info.json  wheel hubs and radii, steering pivot + pitch, grip ends (Handle_L/R), seat, lamps, bounds

blender --background --python bike.py -- <manifest> <preset name> <factory dir> <out name>
"""
import bpy, bmesh, sys, json, re, math, os
from mathutils import Vector

manifest_path, car_name, FD, OUTNAME = sys.argv[-4:]
car_info = next(c for c in json.load(open(manifest_path)) if c["name"] == car_name)
OUT = f"{FD}/bike/{OUTNAME}"; os.makedirs(OUT, exist_ok=True)
# Zero's own paint names (its ColorSlots: Body_01, Body_02, Seat_01, Window), so a Zero clone paints
SLOTS = ["Trim", "Window", "LeftTailLight", "RightTailLight", "HeadLight", "LeftSignalLight",
         "RightSignalLight", "Body_01", "Body_02", "ReverseLight", "Seat_01"]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=f"{FD}/fbx/{car_name}.fbx")
car = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
for o in [o for o in bpy.data.objects if o is not car]: bpy.data.objects.remove(o)
car.parent = None
bpy.context.view_layer.objects.active = car; car.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
groups = {g.index: g.name.lower() for g in car.vertex_groups}
bm = bmesh.new(); bm.from_mesh(car.data)
unit = 0.01 if max(v.co.length for v in bm.verts) > 20 else 1.0     # cm FBX -> metres
for v in bm.verts: v.co *= unit
deform = bm.verts.layers.deform.active; uvl = bm.loops.layers.uv.active


def bone(f):
    votes = {}
    for v in f.verts:
        if v[deform]:
            g = max(v[deform].items(), key=lambda kv: kv[1])[0]; votes[g] = votes.get(g, 0) + 1
    return groups.get(max(votes, key=votes.get), "") if votes else ""


fb = {f: bone(f) for f in bm.faces}
def has(f, *keys): return any(k in fb[f] for k in keys)
wheel_f = [f for f in bm.faces if has(f, "wheel_front")]
wheel_r = [f for f in bm.faces if has(f, "wheel_rear")]
steer = [f for f in bm.faces if has(f, "handlebar", "front_shock")]
drop = set(wheel_f + wheel_r + [f for f in bm.faces if has(f, "kickstand", "number_plate")])


def hub(faces):
    P = [v.co for f in faces for v in f.verts]
    lo = Vector(map(min, *P)); hi = Vector(map(max, *P)); c = (lo + hi) / 2
    return c, max(hi.x - lo.x, hi.z - lo.z) / 2, hi.y - lo.y


# orientation: +X forward (front wheel ahead of the rear)
cf, rf, wf = hub(wheel_f); cr, rr_, wr = hub(wheel_r)
if cf.x < cr.x:
    for v in bm.verts: v.co.x, v.co.y = -v.co.x, -v.co.y
    cf, rf, wf = hub(wheel_f); cr, rr_, wr = hub(wheel_r)
# steering axis: from the front axle up to the bars' centre line (the pack's Front_Shock is no clean
# tube, so a principal-axis fit came out vertical); Zero's socket pitch is -64
bars = [v.co.copy() for f in bm.faces if has(f, "handlebar") for v in f.verts]
bc = sum(bars, Vector()) / len(bars); bc.y = 0
axis = (cf - bc).normalized()                 # down the steering head, toward the axle
pivot = bc
pitch = math.degrees(math.atan2(axis.z, axis.x))
def grip(s):   # the middle of the grip (6 cm in from the bar end), not the bar-end tip
    tip = max(s * p.y for p in bars); end = [p for p in bars if s * p.y > tip - 0.10]
    g = sum(end, Vector()) / len(end); g.y = s * (tip - 0.06); return g
grip_l, grip_r = grip(1), grip(-1)

atl = bpy.data.images.load(f"{FD}/tex/T_PolygonStreetRacer_01_A.png"); W, H = atl.size; AP = list(atl.pixels)
emi_path = f"{FD}/tex/T_PolygonStreetRacer_Emissive_01.png"
EP = list(bpy.data.images.load(emi_path).pixels) if os.path.exists(emi_path) else None
def px(P, uv):
    x = min(W - 1, max(0, int((uv.x % 1) * W))); y = min(H - 1, max(0, int((uv.y % 1) * H))); i = (y * W + x) * 4
    return P[i], P[i + 1], P[i + 2]
# roles by SLOT INDEX (the manifest lists the slots in mesh order): the livery slot is the paint
slots = car_info["materials"]
def role(f):
    m = slots[f.material_index] if f.material_index < len(slots) else {"slot": "", "mat": ""}
    if "glass" in (m["slot"] + (m["mat"] or "")).lower(): return "glass"
    return "paint" if "livery" in m["slot"].lower() else "atlas"
ATLASES = {}
def atlas_for(f):
    m = slots[f.material_index] if f.material_index < len(slots) else {"mat": ""}
    name = "T_PolygonStreetRacer_02_B" if "02_B" in (m["mat"] or "") else "T_PolygonStreetRacer_01_A"
    if name not in ATLASES:
        img = bpy.data.images.load(f"{FD}/tex/{name}.png"); ATLASES[name] = (img.size[0], img.size[1], list(img.pixels))
    return ATLASES[name]
def tex(T, uv):
    w, h, P = T; x = min(w - 1, max(0, int((uv.x % 1) * w))); y = min(h - 1, max(0, int((uv.y % 1) * h))); i = (y * w + x) * 4
    return P[i], P[i + 1], P[i + 2]
assign = {}
for f in bm.faces:
    if f in drop: continue
    c = f.calc_center_median(); uv = sum((l[uvl].uv for l in f.loops), Vector((0, 0))) / len(f.loops)
    r = role(f)
    if has(f, "light_spot"): s = "HeadLight"     # the pack's headlight is a spotlight attachment
    elif r == "glass": s = "Window"
    elif has(f, "seat"): s = "Seat_01"
    elif r == "paint": s = "Body_01"
    else:
        s = "Trim"
        rr, gg, bb = tex(atlas_for(f), uv)
        glow = (EP and max(px(EP, uv)) > 0.25) or min(rr, gg, bb) > 0.85
        front = c.x > cf.x - 0.35; rear = c.x < cr.x - 0.05
        # atlas B has no emissive and its tail lamp is a magenta-red texel
        tail_texel = rear and rr > 0.45 and gg < 0.3 and c.z > 0.55   # low purple = exhaust tips
        if glow or tail_texel:
            orange = rr > 0.6 and 0.25 < gg < 0.7 and bb < 0.35
            left = c.y > 0
            if orange: s = "LeftSignalLight" if left else "RightSignalLight"
            elif front and min(rr, gg, bb) > 0.6: s = "HeadLight"
            elif rear and rr > 0.45 and gg < 0.3: s = "LeftTailLight" if left else "RightTailLight"
    assign[f] = s


def export(faces, name):
    dup = bmesh.new()
    vmap = {}
    uvd = dup.loops.layers.uv.new("UVMap")
    for f in faces:
        vs = []
        for v in f.verts:
            if v not in vmap: vmap[v] = dup.verts.new(v.co)
            vs.append(vmap[v])
        try: nf = dup.faces.new(vs)
        except ValueError: continue
        nf.material_index = SLOTS.index(assign[f])
        for l_new, l_old in zip(nf.loops, f.loops): l_new[uvd].uv = l_old[uvl].uv
    # never ship an empty slot: it shifts every later index. Each filler is a DIFFERENT small face.
    spare = sorted(dup.faces, key=lambda ff: ff.calc_area())
    used = {f.material_index for f in dup.faces}
    for i, s in enumerate(SLOTS):
        if i not in used and spare:
            spare.pop(0).material_index = i
    me = bpy.data.meshes.new(name); dup.to_mesh(me); dup.free()
    for s in SLOTS: me.materials.append(bpy.data.materials.get(s) or bpy.data.materials.new(s))   # no ".001" names
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    # Blender +Y is Unreal -Y: the FBX exporter keeps that convention, as the cars do
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(20), keep_sharp_edges=False)
    bpy.ops.export_scene.fbx(filepath=f"{OUT}/{name}.fbx", use_selection=True, object_types={"MESH"},
                             apply_scale_options="FBX_SCALE_UNITS", mesh_smooth_type="FACE", add_leaf_bones=False)
    return len(faces)


steer_set = set(steer)
nb = export([f for f in assign if f not in steer_set], f"SM_{OUTNAME}_Body")
nh = export([f for f in assign if f in steer_set], f"SM_{OUTNAME}_Handlebar")
def ue(p): return [round(p.x * 100, 1), round(-p.y * 100, 1), round(p.z * 100, 1)]
P = [v.co for f in assign if f not in steer_set for v in f.verts]
lo = Vector(map(min, *P)); hi = Vector(map(max, *P))
seat = [f.calc_center_median() for f, s in assign.items() if s == "Seat_01"]
lamp = lambda s: (lambda fs: ue(sum((f.calc_center_median() for f in fs), Vector()) / len(fs)) if fs else None)([f for f, x in assign.items() if x == s])
info = {"car": car_name, "wheel_front": ue(cf) + [round(rf * 200, 1), round(wf * 100, 1)],
        "wheel_rear": ue(cr) + [round(rr_ * 200, 1), round(wr * 100, 1)],
        "steering": {"pivot": ue(pivot), "pitch": round(pitch, 2)}, "grip_l": ue(grip_l), "grip_r": ue(grip_r),
        "seat": ue(sum(seat, Vector()) / len(seat)) if seat else None,
        "lights": {s: lamp(s) for s in ("HeadLight", "LeftTailLight", "RightTailLight", "LeftSignalLight", "RightSignalLight")},
        "body_min": ue(Vector((lo.x, hi.y, lo.z))), "body_max": ue(Vector((hi.x, lo.y, hi.z))), "faces": [nb, nh]}
json.dump(info, open(f"{OUT}/info.json", "w"), indent=1)
print("BIKE", json.dumps(info))
from collections import Counter
dbg = Counter()
for f in assign:
    c = f.calc_center_median(); uv = sum((l[uvl].uv for l in f.loops), Vector((0, 0))) / len(f.loops)
    zone = "front" if c.x > cf.x - 0.35 else "rear" if c.x < cr.x - 0.05 else None
    if zone: dbg[(zone, tuple(round(x, 1) for x in tex(atlas_for(f), uv)), round(max(px(EP, uv)), 1) if EP else -1)] += 1
print("DBG", sorted(dbg.items(), key=lambda kv: -kv[1])[:24])
from collections import Counter
print("SLOTS", dict(Counter(assign.values())), "EMI", EP is not None)
