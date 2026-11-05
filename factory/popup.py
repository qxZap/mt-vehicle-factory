"""Pop-up headlights -> the game's pop-up part (vanilla Panther: Headlight_01_Skel + Headlight_Popup).

kit.py writes the two states lpr_prep.py found, in body space with the car's slots:
    kit/<car>/popup/SM_<car>_PopupOff_P1.fbx   lids closed, flush with the bonnet
    kit/<car>/popup/SM_<car>_PopupOn_P1.fbx    lamps raised
One skeletal mesh carries both. Bind pose = lights off: the closed lids as modelled, the raised lamps
shrunk to 1% about their hinge (rear-bottom of each side). LightOn (0.4 s): each raised lamp's bone
scales x100 (back to as modelled) while each lid's bone scales to 1%, so a lid drops away as its lamp
rises. Left and right have their own bones and hinges.

Also writes popup.json: the lit lamp centres (Unreal cm), for the car's HeadLight components.

blender --background --python popup.py -- <kit car dir> <out fbx>
"""
import bpy, sys, json, os
from mathutils import Vector

KD, OUTF = sys.argv[-2:]
car = os.path.basename(KD.rstrip("/\\"))
bpy.ops.wm.read_factory_settings(use_empty=True)
objs = {}
for st in ("Off", "On"):
    bpy.ops.import_scene.fbx(filepath=f"{KD}/popup/SM_{car}_Popup{st}_P1.fbx")
    o = [x for x in bpy.context.selected_objects if x.type == "MESH"][0]
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    import bmesh
    bm = bmesh.new(); bm.from_mesh(o.data)
    # a kit part is the car's mesh with every other face deleted: its loose verts span the whole car
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    if st == "On":
        # the lens is whatever faces forward; palette lenses are not white, so no HeadLight slot came over
        hi = next((i for i, m in enumerate(o.data.materials) if m and m.name.split(".")[0] == "HeadLight"), None)
        if hi is None:
            o.data.materials.append(bpy.data.materials.get("HeadLight") or bpy.data.materials.new("HeadLight"))
            hi = len(o.data.materials) - 1
        for f in bm.faces:
            if f.normal.x > 0.6: f.material_index = hi
    bm.to_mesh(o.data); bm.free()
    objs[st] = o

SHRINK = 0.01
pivots, lamps = {}, {}
for st, o in objs.items():
    for side, sgn in (("L", 1), ("R", -1)):
        vs = [v for v in o.data.vertices if sgn * v.co.y >= 0]
        if not vs: continue
        P = [v.co.copy() for v in vs]
        lo = Vector(map(min, *P)); hi = Vector(map(max, *P))
        name = f"{st}{side}"
        # a lamp hinges at its rear-bottom edge; a lid simply collapses about its own centre
        piv = Vector((lo.x, (lo.y + hi.y) / 2, lo.z)) if st == "On" else (lo + hi) / 2
        pivots[name] = piv
        g = o.vertex_groups.new(name=name); g.add([v.index for v in vs], 1.0, "REPLACE")
        if st == "On":
            for v in vs: v.co = piv + (v.co - piv) * SHRINK
            # the lit lens: faces on the HeadLight slot, else the lamp's front half
            hs = [i for i, m in enumerate(o.data.materials) if m and m.name.split(".")[0] == "HeadLight"]
            fs = [f for f in o.data.polygons if f.material_index in hs and sgn * f.center.y >= 0] or \
                 [f for f in o.data.polygons if sgn * f.center.y >= 0]
            c = sum((piv + (f.center - piv) / SHRINK for f in fs), Vector()) / len(fs)
            lamps[side] = c

bpy.ops.object.select_all(action="DESELECT")
for o in objs.values(): o.select_set(True)
bpy.context.view_layer.objects.active = objs["Off"]
bpy.ops.object.join()
mesh = bpy.context.view_layer.objects.active
mesh.name = mesh.data.name = f"SK_{car}_Popup"

arm = bpy.data.armatures.new("PopupRig"); rig = bpy.data.objects.new("PopupRig", arm)
bpy.context.collection.objects.link(rig); bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
root = arm.edit_bones.new("Root"); root.head = (0, 0, 0); root.tail = (0, 0, 0.1)
for n, p in pivots.items():
    b = arm.edit_bones.new(n); b.head = p; b.tail = p + Vector((0, 0, 0.05)); b.parent = root
bpy.ops.object.mode_set(mode="OBJECT")
mesh.parent = rig
mod = mesh.modifiers.new("Armature", "ARMATURE"); mod.object = rig

sc = bpy.context.scene; sc.render.fps = 30; sc.frame_start, sc.frame_end = 0, 12
rig.animation_data_create(); act = bpy.data.actions.new("LightOn"); rig.animation_data.action = act
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="POSE")
for n in pivots:
    pb = rig.pose.bones[n]
    for f, k in ((0, 1.0), (12, 1 / SHRINK)) if n.startswith("On") else ((0, 1.0), (6, SHRINK), (12, SHRINK)):
        pb.scale = (k, k, k); pb.keyframe_insert("scale", frame=f)
bpy.ops.object.mode_set(mode="OBJECT")
for fc in act.fcurves:
    for kp in fc.keyframe_points: kp.interpolation = "LINEAR"

bpy.ops.object.select_all(action="DESELECT"); rig.select_set(True); mesh.select_set(True)
bpy.ops.export_scene.fbx(filepath=OUTF, use_selection=True, object_types={"ARMATURE", "MESH"},
                         apply_scale_options="FBX_SCALE_UNITS", mesh_smooth_type="FACE", add_leaf_bones=False,
                         bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                         bake_anim_force_startend_keying=True, armature_nodetype="NULL")
ue = lambda c: [round(c.x * 100, 1), round(-c.y * 100, 1), round(c.z * 100, 1)]
json.dump({"HeadLight_Left": ue(lamps["L"]) if "L" in lamps else None,
           "HeadLight_Right": ue(lamps["R"]) if "R" in lamps else None,
           "bones": sorted(pivots)}, open(f"{KD}/popup/popup.json", "w"), indent=1)
print("POPUP", car, sorted(pivots), {k: ue(v) for k, v in lamps.items()})
