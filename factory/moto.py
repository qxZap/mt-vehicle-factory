"""Assetsville motorcycle FBX -> Motor Town bike pieces (same layout as bike.py / vanilla Zero).

The pack ships each bike as separate objects: motorcycleBody, steeringWheel (bars + fork), wheelFront,
wheelRear, kickStand. Materials: customMat_01 / customMat_02 = the two paints, colorPalette = atlas
(T_colorPalette, emissive T_colorPalette_EMS). Slots use Zero's names so a Zero clone paints.

blender --background --python moto.py -- <fbx> <factory dir> <out name>
"""
import bpy, bmesh, sys, json, math, os
from mathutils import Vector

FBX, FD, OUTNAME = sys.argv[-3:]
OUT = f"{FD}/bike/{OUTNAME}"; os.makedirs(OUT, exist_ok=True)
SLOTS = ["Trim", "Window", "LeftTailLight", "RightTailLight", "HeadLight", "LeftSignalLight",
         "RightSignalLight", "Body_01", "Body_02", "ReverseLight", "Seat_01"]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX)
objs = {o.name.split(".")[0]: o for o in bpy.data.objects if o.type == "MESH"}


def world(o):
    """[(verts in metres, faces, material names, uvs)] for one object, transforms applied."""
    me = o.data; mw = o.matrix_world
    unit = 0.01 if max((mw @ v.co).length for v in me.vertices) > 20 else 1.0
    return [(mw @ v.co) * unit for v in me.vertices], me, unit


def bounds(P):
    lo = Vector(map(min, *P)); hi = Vector(map(max, *P)); return lo, hi


def load(name):
    img = bpy.data.images.load(f"{FD}/tex/{name}.png"); return img.size[0], img.size[1], list(img.pixels)
ATL, EMS = load("Moto_T_colorPalette"), load("Moto_T_colorPalette_EMS")
def tex(T, uv):
    w, h, P = T; x = min(w - 1, max(0, int((uv.x % 1) * w))); y = min(h - 1, max(0, int((uv.y % 1) * h))); i = (y * w + x) * 4
    return P[i], P[i + 1], P[i + 2]


wr_P, _, _ = world(objs["wheelRear"]); wf_P, _, _ = world(objs["wheelFront"])
(lr, hr), (lf, hf) = bounds(wr_P), bounds(wf_P)
cr = (lr + hr) / 2; rr_ = max(hr.x - lr.x, hr.z - lr.z) / 2
cf = (lf + hf) / 2; rf = max(hf.x - lf.x, hf.z - lf.z) / 2
if cf.z < rf * 0.5:          # the front wheel sits on a posed suspension empty: put its hub at its radius
    cf.z = rf
sw_P, _, _ = world(objs["steeringWheel"])
sl, sh = bounds(sw_P)
top = [p for p in sw_P if p.z > sh.z - 0.08]
bc = sum(top, Vector()) / len(top); bc.y = 0           # the bars' centre line
axis = (cf - bc).normalized()
pitch = math.degrees(math.atan2(axis.z, axis.x))
def grips(o):
    """Hand points: the middle of each grip, i.e. the last 10 cm of the BAR, the piece of the steering
    mesh with the widest Y span. Its highest or widest vertex was a mirror stalk on Chopper II and the
    bar-end tip elsewhere, which put the hands beside the bar instead of on it."""
    bm = bmesh.new(); bm.from_mesh(o.data); bm.verts.ensure_lookup_table()
    mw = o.matrix_world; unit = 0.01 if max((mw @ v.co).length for v in o.data.vertices) > 20 else 1.0
    seen, isl = set(), []
    for v in bm.verts:
        if v.index in seen: continue
        st, comp = [v], []; seen.add(v.index)
        while st:
            a = st.pop(); comp.append((mw @ a.co) * unit)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen: seen.add(b.index); st.append(b)
        isl.append(comp)
    out = []
    for s in (1, -1):
        side = [c for c in isl if max(s * p.y for p in c) > 0.05]
        bar = max(side, key=lambda c: max(p.y for p in c) - min(p.y for p in c))
        tip = max(s * p.y for p in bar)
        end = [p for p in bar if s * p.y > tip - 0.10]
        g = sum(end, Vector()) / len(end); g.y = s * (tip - 0.06)   # a grip is ~12 cm: its middle
        out.append(g)
    return out
grip_l, grip_r = grips(objs["steeringWheel"])


def build(names, outname):
    dup = bmesh.new(); uvd = dup.loops.layers.uv.new("UVMap")
    for n in names:
        if n not in objs: continue
        P, me, unit = world(objs[n])
        uvl = me.uv_layers.active.data if me.uv_layers else None
        vs = [dup.verts.new(p) for p in P]
        for poly in me.polygons:
            try: f = dup.faces.new([vs[i] for i in poly.vertices])
            except ValueError: continue
            mat = me.materials[poly.material_index].name if me.materials else ""
            uv = Vector((0, 0))
            for l_new, li in zip(f.loops, poly.loop_indices):
                if uvl: l_new[uvd].uv = uvl[li].uv; uv += uvl[li].uv
            uv /= max(1, len(poly.loop_indices))
            c = f.calc_center_median()
            if mat.startswith("customMat_01"): s = "Body_01"
            elif mat.startswith("customMat_02"): s = "Body_02"
            else:
                s = "Trim"
                r, g, b = tex(ATL, uv); glow = max(tex(EMS, uv)) > 0.25
                if glow:
                    orange = r > 0.6 and 0.25 < g < 0.7 and b < 0.35
                    if orange: s = "LeftSignalLight" if c.y > 0 else "RightSignalLight"
                    elif c.x > (cf.x + cr.x) / 2: s = "HeadLight"
                    elif r > 0.45 and g < 0.3: s = "LeftTailLight"
                elif b > 0.45 and b > r + 0.1 and (r + g + b) / 3 > 0.35 and c.z > 0.6: s = "Window"
            f.material_index = SLOTS.index(s)
    spare = sorted(dup.faces, key=lambda ff: ff.calc_area()); used = {f.material_index for f in dup.faces}
    for i in range(len(SLOTS)):
        if i not in used and spare: spare.pop(0).material_index = i
    me = bpy.data.meshes.new(outname); dup.to_mesh(me); dup.free()
    for s in SLOTS: me.materials.append(bpy.data.materials.get(s) or bpy.data.materials.new(s))
    ob = bpy.data.objects.new(outname, me); bpy.context.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(20), keep_sharp_edges=False)
    bpy.ops.export_scene.fbx(filepath=f"{OUT}/{outname}.fbx", use_selection=True, object_types={"MESH"},
                             apply_scale_options="FBX_SCALE_UNITS", mesh_smooth_type="FACE", add_leaf_bones=False)
    from collections import Counter
    return dict(Counter(SLOTS[f.material_index] for f in me.polygons)), ob


body_counts, body = build(["motorcycleBody"], f"SM_{OUTNAME}_Body")
bar_counts, _ = build(["steeringWheel"], f"SM_{OUTNAME}_Handlebar")
def ue(p): return [round(p.x * 100, 1), round(-p.y * 100, 1), round(p.z * 100, 1)]
P = [body.matrix_world @ v.co for v in body.data.vertices]; lo, hi = bounds(P)
# seat: the highest body region between the wheels, behind the bars
mid = [p for p in P if cr.x + 0.15 < p.x < bc.x - 0.15]
seat = max(mid, key=lambda p: p.z) if mid else (cr + cf) / 2
lamp = lambda s: (lambda fs: ue(sum((f.center for f in fs), Vector()) / len(fs)) if fs else None)(
    [f for f in body.data.polygons if SLOTS[f.material_index] == s and body_counts.get(s, 0) > 1])
info = {"fbx": os.path.basename(FBX), "wheel_front": ue(cf) + [round(rf * 200, 1)], "wheel_rear": ue(cr) + [round(rr_ * 200, 1)],
        "steering": {"pivot": ue(bc), "pitch": round(pitch, 2)}, "grip_l": ue(grip_l), "grip_r": ue(grip_r),
        "seat": ue(seat), "lights": {"HeadLight": lamp("HeadLight"), "LeftTailLight": lamp("LeftTailLight")},
        "body_min": ue(Vector((lo.x, hi.y, lo.z))), "body_max": ue(Vector((hi.x, lo.y, hi.z))),
        "counts": {"body": body_counts, "bar": bar_counts}}
json.dump(info, open(f"{OUT}/info.json", "w"), indent=1)
print("MOTO", json.dumps(info))
