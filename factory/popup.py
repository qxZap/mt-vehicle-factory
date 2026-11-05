"""Pop-up headlights -> the game's pop-up part (vanilla Panther: Headlight_01_Skel + Headlight_Popup).

kit.py writes the two states lpr_prep.py found, in body space with the car's slots:
    kit/<car>/popup/SM_<car>_PopupOff_P1.fbx   lids closed, flush with the bonnet
    kit/<car>/popup/SM_<car>_PopupOn_P1.fbx    lamps raised
A pop-up is one rigid pod turning about a hinge line across the car (Y), like the Panther's. Per side
the hinge and angle are SOLVED: the raised pod rotated back by the angle about the hinge must land on
the closed lid. The rig carries only the pod, bound in its CLOSED pose (the raised geometry rotated
back), and LightOn turns it up about the hinge to exactly the raised geometry. The closed lid piece
stays only if the rotated-back pod does not cover it.

The first version scaled the lid away and the lamp in; the user saw "the lid drops and something
pushes the lamp up" (5 Nov 2026). This is the Panther's motion.

Also writes popup.json: lit lamp centres (Unreal cm, open pose) and the solved hinges.

blender --background --python popup.py -- <kit car dir> <out fbx>
"""
import bpy, bmesh, sys, json, os, math
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree

KD, OUTF = sys.argv[-2:]
car = os.path.basename(KD.rstrip("/\\"))
bpy.ops.wm.read_factory_settings(use_empty=True)


def load(st):
    bpy.ops.import_scene.fbx(filepath=f"{KD}/popup/SM_{car}_Popup{st}_P1.fbx")
    o = [x for x in bpy.context.selected_objects if x.type == "MESH"][0]
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new(); bm.from_mesh(o.data)
    # a kit part is the car's mesh with every other face deleted: its loose verts span the whole car
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(o.data); bm.free()
    return o


objs = {"Off": load("Off"), "On": load("On")}


def slot_index(o, name):
    for i, m in enumerate(o.data.materials):
        if m and m.name.split(".")[0] == name: return i
    o.data.materials.append(bpy.data.materials.get(name) or bpy.data.materials.new(name))
    return len(o.data.materials) - 1


# slots: the pod's forward faces are the lit lens. Glass faces become lens or paint (kit.py's
# lamp-cover rule turns a pod's outer faces into clear glass: the "see-through" pods).
on, off = objs["On"], objs["Off"]
hl, paint = slot_index(on, "HeadLight"), slot_index(on, "Body_0")
glass_on = {i for i, m in enumerate(on.data.materials) if m and m.name.split(".")[0] == "Windows"}
for p in on.data.polygons:
    if p.normal.x > 0.6: p.material_index = hl
    elif p.material_index in glass_on: p.material_index = paint
glass_off = {i for i, m in enumerate(off.data.materials) if m and m.name.split(".")[0] == "Windows"}
pa_off = slot_index(off, "Body_0")
for p in off.data.polygons:
    if p.material_index in glass_off: p.material_index = pa_off


def rot_about(h, a):
    return Matrix.Translation(h) @ Matrix.Rotation(a, 4, "Y") @ Matrix.Translation(-h)


hinges, lamps, keep_off = {}, {}, {}
raised = [v.co.copy() for v in on.data.vertices]          # the open pose, for the self-check
for side, sgn in (("L", 1), ("R", -1)):
    pv = [v for v in on.data.vertices if sgn * v.co.y >= 0]
    ov = [v for v in off.data.vertices if sgn * v.co.y >= 0]
    if not pv or not ov: continue
    O = [v.co.copy() for v in ov]
    kd = KDTree(len(O))
    for i, c in enumerate(O): kd.insert(c, i)
    kd.balance()
    lo = Vector(map(min, *O)); hi = Vector(map(max, *O))
    P = [v.co.copy() for v in pv]
    # the pod's lid (its uppermost third) is what must land on the closed lid
    ztop = sorted(p.z for p in P)[int(len(P) * 0.66)]
    top = [p for p in P if p.z >= ztop]
    best = None
    for hx in [lo.x + (hi.x - lo.x) * t for t in (-0.15, 0.0, 0.15, 0.3)]:
        for hz in [lo.z + (hi.z - lo.z) * t for t in (0.0, 0.5, 1.0)]:
            h = Vector((hx, (lo.y + hi.y) / 2, hz))
            for deg in range(-100, 101, 2):
                R = rot_about(h, math.radians(deg))
                err = sum(kd.find(R @ p)[2] for p in top) / len(top)
                if best is None or err < best[0]: best = (err, h, deg)
    err, h, deg = best
    for d2 in [deg + x * 0.25 for x in range(-8, 9)]:          # refine the angle
        R = rot_about(h, math.radians(d2))
        e2 = sum(kd.find(R @ p)[2] for p in top) / len(top)
        if e2 < err: err, deg = e2, d2
    back = rot_about(h, math.radians(deg))                       # raised -> closed
    hinges[side] = {"hinge": [round(c, 4) for c in h], "close_deg": deg, "fit_cm": round(err * 100, 2)}
    g = on.vertex_groups.new(name=f"Pod{side}"); g.add([v.index for v in pv], 1.0, "REPLACE")
    fs = [f for f in on.data.polygons if f.material_index == hl and sgn * f.center.y >= 0] or \
         [f for f in on.data.polygons if sgn * f.center.y >= 0]
    lamps[side] = sum((f.center for f in fs), Vector()) / len(fs)     # open pose: where the beam shines from
    for v in pv: v.co = back @ v.co                                    # bind closed
    # the closed lid stays only if the closed pod does not cover it (fit worse than 2 cm)
    keep_off[side] = err > 0.02
    if keep_off[side]:
        go = off.vertex_groups.new(name=f"Pod{side}"); go.add([v.index for v in ov], 1.0, "REPLACE")

if not any(keep_off.values()):
    bpy.data.objects.remove(off); parts = [on]
else:
    dead = [v for v in off.data.vertices if not any(keep_off.get(s) and sg * v.co.y >= 0 for s, sg in (("L", 1), ("R", -1)))]
    bm = bmesh.new(); bm.from_mesh(off.data); bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[v.index] for v in dead], context="VERTS"); bm.to_mesh(off.data); bm.free()
    parts = [on, off]
bpy.ops.object.select_all(action="DESELECT")
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = on
if len(parts) > 1: bpy.ops.object.join()
mesh = bpy.context.view_layer.objects.active
mesh.name = mesh.data.name = f"SK_{car}_Popup"
# one material per slot NAME (joined objects arrive as Trim / Trim.001): UE matches slots by name
by = {}
for i, m in enumerate(mesh.data.materials):
    base = m.name.split(".")[0] if m else "Trim"
    by.setdefault(base, []).append(i)
remap = {}
for base, idx in by.items():
    keep = idx[0]; mesh.data.materials[keep].name = base
    for i in idx: remap[i] = keep
for p in mesh.data.polygons: p.material_index = remap[p.material_index]
bpy.ops.object.material_slot_remove_unused()

arm = bpy.data.armatures.new("PopupRig"); rig = bpy.data.objects.new("PopupRig", arm)
bpy.context.collection.objects.link(rig); bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
root = arm.edit_bones.new("Root"); root.head = (0, 0, 0); root.tail = (0, 0, 0.1)
for side, hg in hinges.items():
    hp = Vector(hg["hinge"])
    b = arm.edit_bones.new(f"Pod{side}"); b.head = hp; b.tail = hp + Vector((0, 0.05, 0)); b.roll = 0; b.parent = root
bpy.ops.object.mode_set(mode="OBJECT")
mesh.parent = rig
mod = mesh.modifiers.new("Armature", "ARMATURE"); mod.object = rig

sc = bpy.context.scene; sc.render.fps = 30; sc.frame_start, sc.frame_end = 0, 12
rig.animation_data_create(); act = bpy.data.actions.new("LightOn"); rig.animation_data.action = act
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="POSE")
for side, hg in hinges.items():
    pb = rig.pose.bones[f"Pod{side}"]; pb.rotation_mode = "XYZ"
    # the bone's local Y is world Y (head->tail along +Y, roll 0): turning it by -close_deg undoes "back"
    for f, a in ((0, 0.0), (12, -math.radians(hg["close_deg"]))):
        pb.rotation_euler = (0, a, 0); pb.keyframe_insert("rotation_euler", frame=f)
bpy.ops.object.mode_set(mode="OBJECT")
for fc in act.fcurves:
    for kp in fc.keyframe_points: kp.interpolation = "BEZIER"     # ease in and out, like a motor

# self-check: at the last frame the pod must sit where the pack modelled it raised
sc.frame_set(12)
ev = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
open_err = max((rig.matrix_world @ ev.vertices[i].co - raised[i]).length for i in range(len(raised)))
sc.frame_set(0)
assert open_err < 0.005, f"pod at frame 12 is {open_err * 100:.1f} cm off the modelled raised pose"

bpy.ops.object.select_all(action="DESELECT"); rig.select_set(True); mesh.select_set(True)
bpy.ops.export_scene.fbx(filepath=OUTF, use_selection=True, object_types={"ARMATURE", "MESH"},
                         apply_scale_options="FBX_SCALE_UNITS", mesh_smooth_type="FACE", add_leaf_bones=False,
                         bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                         bake_anim_force_startend_keying=True, armature_nodetype="NULL")
ue = lambda c: [round(c.x * 100, 1), round(-c.y * 100, 1), round(c.z * 100, 1)]
json.dump({"HeadLight_Left": ue(lamps["L"]) if "L" in lamps else None,
           "HeadLight_Right": ue(lamps["R"]) if "R" in lamps else None,
           "hinges": hinges, "kept_closed_lid": keep_off}, open(f"{KD}/popup/popup.json", "w"), indent=1)
print("POPUP", car, json.dumps(hinges), "kept lid", keep_off)
