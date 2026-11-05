"""Slot-coloured check render of a kit body: front 3/4, rear 3/4, top (roof cut away = interior)."""
import bpy, sys, json
from mathutils import Vector
BODY, ATLAS, OUT = sys.argv[-3:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=BODY)
atlas = bpy.data.images.load(ATLAS)
LOOK = {"Body_0": (0.6, 0.05, 0.05), "Body_1": (0.95, 0.95, 0.9), "Windows": (0.3, 0.5, 0.7), "HeadLight": (1, 1, 0.6),
        "LeftSignalLight": (1, 0.45, 0), "RightSignalLight": (1, 0.45, 0), "LeftTailLight": (1, 0, 0), "RightTailLight": (0.6, 0, 0.3),
        "ReverseLight": (0.8, 1, 1), "Seat_01": (0.1, 0.6, 0.1), "Seat_02": (0.1, 0.3, 0.9), "Dashboard_01": (0.9, 0.2, 0.9),
        "WindowTrim_01": (1, 0.85, 0.1)}
for m in bpy.data.materials:
    m.use_nodes = True; nt = m.node_tree; b = next(x for x in nt.nodes if x.type == "BSDF_PRINCIPLED")
    k = m.name.split(".")[0]
    if k in LOOK:
        b.inputs["Base Color"].default_value = (*LOOK[k], 1)
        if "Light" in k: b.inputs["Emission Color"].default_value = (*LOOK[k], 1); b.inputs["Emission Strength"].default_value = 3
    else:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = atlas; t.interpolation = "Closest"; nt.links.new(t.outputs[0], b.inputs["Base Color"])
ob = next(o for o in bpy.data.objects if o.type == "MESH")
import os, bmesh
if os.environ.get("HIDEGLASS"):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    wi = [i for i, m in enumerate(ob.data.materials) if m.name.startswith("Windows")]
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in wi], context="FACES"); bm.to_mesh(ob.data); bm.free()
P = [ob.matrix_world @ v.co for v in ob.data.vertices]; lo = Vector(map(min, *P)); hi = Vector(map(max, *P)); c = (lo + hi) / 2; size = (hi - lo).length
sc = bpy.context.scene
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.82, 0.86, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 1.2
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN")); sun.data.energy = 3; sun.rotation_euler = (0.7, 0.2, 2.2); sc.collection.objects.link(sun)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_WORKBENCH"
sc.render.resolution_x, sc.render.resolution_y = 640, 420
views = {"front": Vector((0.75, -0.6, 0.35)), "rear": Vector((-0.75, 0.6, 0.35)), "top": Vector((0.01, 0, 1))}
if os.environ.get("VIEWS"): views = {k: views[k] for k in os.environ["VIEWS"].split(",")}
ZOOM = float(os.environ.get("ZOOM", "1.25"))
for name, d in views.items():
    cam.location = c + d.normalized() * size * ZOOM
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    if name == "top":   # cut the roof: clip just under the windscreen top
        cam.data.clip_start = cam.location.z - (lo.z + (hi.z - lo.z) * 0.78)
    sc.render.filepath = f"{OUT}_{name}.png"; bpy.ops.render.render(write_still=True)
