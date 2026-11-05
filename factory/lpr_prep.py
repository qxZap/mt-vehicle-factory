"""Low Poly Racing Pack car -> the shape kit.py reads (one mesh, wheel/steer vertex groups, +X forward).

The pack is unrigged: body, Glass_*, Steering wheel, Wheel_00N, Brake disk_00N are separate objects and
the car faces -Y. kit.py finds wheels and the steering wheel by vertex-group name, so each object
becomes a group (Wheel_FL.., Steering) on one merged mesh, turned +90 deg about Z so the front is +X.
Saved as a .blend because an FBX keeps vertex groups only on a skinned mesh.

blender --background --python lpr_prep.py -- <car fbx> <out .blend>
"""
import bpy, bmesh, sys, math
from mathutils import Vector, Matrix

FBX, OUT = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX)
src = [o for o in bpy.data.objects if o.type == "MESH"]
R = Matrix.Rotation(math.pi / 2, 4, "Z")          # -Y forward -> +X forward; +X (left) -> +Y (left)


def role(name):
    n = name.lower()
    if "glass" in n: return "glass"
    if "headlight" in n or n.endswith("lamp") or "_lamp" in n: return "lamp"
    if "steering" in n: return "steer"
    if "wheel" in n or "brake" in n: return "wheel"
    return "body"


me = bpy.data.meshes.new("car"); car = bpy.data.objects.new("car", me)
bpy.context.collection.objects.link(car)
bm = bmesh.new(); uv = bm.loops.layers.uv.new("UVMap"); dl = bm.verts.layers.deform.verify()
groups = ["Body", "Steering", "Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR"]
for g in groups: car.vertex_groups.new(name=g)
pieces = []
for o in src:
    P = [R @ o.matrix_world @ v.co for v in o.data.vertices]
    pieces.append((o, P, role(o.name)))
# The pack builds nearly every car 5.0-5.6 m long (a Mini at 4.5 m). Scale to the real car it was
# identified as (kit_cars_refs.json length_mm), about the origin, which sits on the ground.
import os as _os, json as _json
_car = _os.path.splitext(_os.path.basename(OUT))[0]
_real = _json.load(open(_os.environ.get("MTVF_REFS", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "data", "kit_cars_refs.json")), encoding="utf-8")).get(_car, {}).get("length_mm")
if _real:
    _xs = [p.x for t in pieces if t[2] != "wheel" for p in t[1]]   # a wheel can carry stray verts (Suv_04)
    _k = _real / 1000 / (max(_xs) - min(_xs))
    pieces = [(o, [p * _k for p in P], r) for o, P, r in pieces]
    print("SCALE", _car, round(_k, 4), "->", _real, "mm")
# Parts: the pack stacks alternatives in place (Stock/Tuning kits, Spoiler_001/002, Hood_00N) and
# enables them all. Each detachable piece becomes a tuning part of its slot; pieces of one slot are
# alternatives (P1 = first by name, fitted as sold). A left/right pair, or a piece split as X / X.001
# that does not overlap its twin, is ONE part. Glass that overlaps other glass is a duplicate
# window and is set aside; the root object is the shell and never moves.
import os, json, re
def box(P): return Vector(map(min, *P)), Vector(map(max, *P))
def iou(a, b):
    (l1, h1), (l2, h2) = a, b
    inter = 1.0
    for i in range(3): inter *= max(0.0, min(h1[i], h2[i]) - max(l1[i], l2[i]))
    vol = lambda l, h: max(1e-9, (h.x - l.x) * (h.y - l.y) * (h.z - l.z))
    return inter / (vol(l1, h1) + vol(l2, h2) - inter)
def mirror(bx):
    l, h = bx; return Vector((l.x, -h.y, l.z)), Vector((h.x, -l.y, h.z))
root = max(pieces, key=lambda t: len(t[0].data.polygons) if t[0].parent is None else -1)[0]
boxes = {t[0].name: box(t[1]) for t in pieces}
allx = [p.x for t in pieces for p in t[1]]; midx = (min(allx) + max(allx)) / 2
def slot_of(name):
    n = name.lower()
    if re.search(r"stock|tuning", n): return "SideSkirt"
    if "spoiler" in n: return "RearWing"
    if "hood" in n: return "Bonnet"
    if "front bumper" in n: return "FrontBumper"
    if "rear bumper" in n: return "RearBumper"
    if re.search(r"bumper", n) and "lip" not in n:
        l, h = boxes[name]; return "FrontBumper" if (l.x + h.x) / 2 > midx else "RearBumper"
    if re.search(r"lower lip|splitter|underlip", n): return "lip:FrontBumper"
    if "diffuser" in n: return "lip:RearBumper"
    return None
by_slot = {}
for o, P, r in pieces:
    if o is root or r != "body": continue
    s = slot_of(o.name)
    if s: by_slot.setdefault(s, []).append(o.name)
for lip in [s for s in by_slot if s.startswith("lip:")]:   # a lip is its own part only where no bumper is
    real = lip[4:]
    if real not in by_slot: by_slot[real] = by_slot.pop(lip)
    else: del by_slot[lip]
LABEL = {"SideSkirt": "Body Kit", "RearWing": "Spoiler", "Bonnet": "Hood", "FrontBumper": "Front Bumper",
         "RearBumper": "Rear Bumper"}
tag_of, labels = {}, {}
for slot, names in by_slot.items():
    names.sort()
    sets = []                         # one set = one fittable part
    for n in names:
        stem = re.sub(r"\.\d+$", "", n)
        home = next((S for S in sets if any(
            (iou(mirror(boxes[n]), boxes[m]) > 0.5 and abs(boxes[n][0].y + boxes[n][1].y) > 0.2)
            or (re.sub(r"\.\d+$", "", m) == stem and iou(boxes[n], boxes[m]) < 0.3) for m in S)), None)
        (home.append(n) if home else sets.append([n]))
    for i, S in enumerate(sets, 1):
        kind_ = "Stock" if slot == "SideSkirt" and "stock" in S[0].lower() else None
        lab = LABEL[slot] if len(sets) == 1 else f"{LABEL[slot]} {i}"
        if slot == "SideSkirt":
            lab = "Stock Body Kit" if kind_ else f"Tuning Kit {sum(1 for T in sets[:i] if 'stock' not in T[0].lower())}"
        for n in S: tag_of[n] = f"{slot}_P{i}"
        labels[f"{slot}_P{i}"] = lab
glass = sorted((t for t in pieces if t[0] is not root and t[2] == "glass"), key=lambda t: t[0].name)
variants = set()
for i, a_ in enumerate(glass):
    if a_[0].name in variants: continue
    for b_ in glass[i + 1:]:
        if b_[0].name not in variants and iou(boxes[a_[0].name], boxes[b_[0].name]) > 0.3:
            variants.add(b_[0].name)
# Pop-up headlights (refs "popup"): the pack models both states, lid closed and lamp raised, as two
# headlight pieces, and both were merged into the body and lit -- the glowing patch on the bonnet.
# The raised one (highest top) is PopupOn, the next tallest PopupOff; any other headlight piece is
# a hidden leftover (Muscle_05's 006). popup.py rigs the pair into the game's pop-up part. Both are
# body-role so kit.py paints the lid and lights only the white lens texels.
_ref = _json.load(open(_os.environ.get("MTVF_REFS", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "data", "kit_cars_refs.json")), encoding="utf-8")).get(_car, {})
if _ref.get("popup"):
    hl = [t for t in pieces if "headlight" in t[0].name.lower()]
    top = lambda t: max(p.z for p in t[1])
    on = max(hl, key=top)
    rest = sorted((t for t in hl if t is not on), key=lambda t: -(top(t) - min(p.z for p in t[1])))
    tag_of[on[0].name] = "PopupOn_P1"; tag_of[rest[0][0].name] = "PopupOff_P1"
    variants.update(t[0].name for t in rest[1:])
    pieces = [(o, P, "body" if o.name in (on[0].name, rest[0][0].name) else r) for o, P, r in pieces]
    print("POPUP", on[0].name, rest[0][0].name, [t[0].name for t in rest[1:]])
json.dump({"labels": labels, "pieces": tag_of, "dropped_glass": sorted(variants)},
          open(OUT[:-6] + "_parts.json", "w"), indent=1)
pieces = [t for t in pieces if t[0].name not in variants]
for t in sorted(set(tag_of.values())): car.vertex_groups.new(name="part:" + t); groups.append("part:" + t)
# wheel corners from the hub positions after the turn: front = +X, left = +Y
hubs = [sum(P, Vector()) / len(P) for o, P, r in pieces if r == "wheel"]
# axles: hubs within 0.4 m of X are one axle. Front- and rearmost are the corners; any axle
# between (the G63 6x6's middle one) is Wheel_M<n>, which kit.py records as an extra wheel.
axles = []
for x in sorted(h.x for h in hubs):
    if axles and x - axles[-1][-1] < 0.4: axles[-1].append(x)
    else: axles.append([x])
ax = [sum(a) / len(a) for a in axles]
def axle_of(x):
    i = min(range(len(ax)), key=lambda k: abs(ax[k] - x))
    return "F" if i == len(ax) - 1 else "R" if i == 0 else f"M{i}"
for g in sorted({"Wheel_" + axle_of(a) + s for a in ax[1:-1] for s in "LR"}):
    car.vertex_groups.new(name=g); groups.append(g)
for o, P, r in pieces:
    if r == "wheel":
        c = sum(P, Vector()) / len(P)
        g = "Wheel_" + axle_of(c.x) + ("L" if c.y > 0 else "R")
    else:
        g = "part:" + tag_of[o.name] if o.name in tag_of else {"steer": "Steering"}.get(r, "Body")
    gi = groups.index(g)
    vs = [bm.verts.new(p) for p in P]
    for v in vs: v[dl][gi] = 1.0
    ouv = o.data.uv_layers.active.data if o.data.uv_layers else None
    for poly in o.data.polygons:
        try: f = bm.faces.new([vs[i] for i in poly.vertices])
        except ValueError: continue
        f.material_index = {"glass": 1, "lamp": 2}.get(r, 0)
        if ouv:
            for l, li in zip(f.loops, poly.loop_indices): l[uv].uv = ouv[li].uv
bm.to_mesh(me); bm.free()
for n in ("LP_ColorPalette", "LP_Glass", "LP_Lamp"): me.materials.append(bpy.data.materials.new(n))
for o in src: bpy.data.objects.remove(o)
for o in [o for o in bpy.data.objects if o is not car]: bpy.data.objects.remove(o)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("PREP", OUT, len(me.polygons), "faces", len(hubs), "wheel pieces", labels, len(variants), "glass set aside")
