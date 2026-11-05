import bpy, sys
from mathutils import Vector
body, rigf, out = sys.argv[-3:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=body); bpy.ops.import_scene.fbx(filepath=rigf)
for o in [o for o in bpy.data.objects if o.name.startswith("UCX")]: bpy.data.objects.remove(o)
sk = [o for o in bpy.data.objects if o.type == "MESH" and "Popup" in o.name][0]
for m in sk.data.materials:
    if m: m.diffuse_color = (1, 0.85, 0.1, 1) if m.name.startswith("HeadLight") else (0.9, 0.2, 0.2, 1)
sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"; sc.display.shading.color_type = "MATERIAL"
sc.render.resolution_x, sc.render.resolution_y = 600, 380
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
P = [sk.matrix_world @ v.co for v in sk.data.vertices]; c = sum(P, Vector()) / len(P)
cam.location = c + Vector((1.6, -1.4, 0.9)); cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
for f in (0, 6, 12):
    sc.frame_set(f); sc.render.filepath = f"{out}_{f:02d}.png"; bpy.ops.render.render(write_still=True)
