"""Documentation screenshots of one car through the pipeline (Blender workbench, 1280x720).

blender --background --python shots.py -- <raw fbx> <prep .blend> <kit dir> <atlas png> <out dir>
  01_raw.png       the pack's FBX as shipped, textured (every alternative piece stacked)
  02_tagged.png    after lpr_prep.py: body / wheels / parts / pop-up states coloured by vertex group
  03_slots.png     after kit.py: the game's material slots (paint, trim, glass, lamps)
  04_collision.png the UCX hulls kit.py ships, over the body
"""
import bpy, sys, os, glob, colorsys
from mathutils import Vector

RAW, PREP, KIT, ATLAS, OUT = sys.argv[-5:]
os.makedirs(OUT, exist_ok=True)


def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"; sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sh = sc.display.shading; sh.light = "STUDIO"; sh.show_cavity = True; sh.show_shadows = True
    w = bpy.data.worlds.new("w"); sc.world = w; w.color = (0.86, 0.87, 0.9)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam


def frame(sc, cam, objs, d=Vector((1.0, -0.85, 0.42)), zoom=1.15):
    P = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    lo = Vector(map(min, *P)); hi = Vector(map(max, *P)); c = (lo + hi) / 2
    cam.location = c + d.normalized() * (hi - lo).length * zoom
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()


def shot(sc, name):
    sc.render.filepath = os.path.join(OUT, name); bpy.ops.render.render(write_still=True)


# 01: raw, textured
bpy.ops.wm.read_factory_settings(use_empty=True); sc, cam = scene_setup()
bpy.ops.import_scene.fbx(filepath=RAW)
img = bpy.data.images.load(ATLAS)
for m in bpy.data.materials:
    m.use_nodes = True; nt = m.node_tree; b = next(x for x in nt.nodes if x.type == "BSDF_PRINCIPLED")
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.interpolation = "Closest"; nt.links.new(t.outputs[0], b.inputs["Base Color"])
sc.display.shading.color_type = "TEXTURE"
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
frame(sc, cam, meshes, d=Vector((0.85, 1.0, 0.42)))      # the pack faces -Y
shot(sc, "01_raw.png")

# 02: tagged vertex groups
bpy.ops.wm.read_factory_settings(use_empty=True); sc, cam = scene_setup()
with bpy.data.libraries.load(PREP) as (src, dst): dst.objects = src.objects
car = next(o for o in dst.objects if o.type == "MESH"); sc.collection.objects.link(car)
groups = [g.name for g in car.vertex_groups]
mats = []
for i, g in enumerate(groups):
    m = bpy.data.materials.new(g)
    m.diffuse_color = (0.78, 0.78, 0.8, 1) if g == "Body" else (*colorsys.hsv_to_rgb((i * 0.137) % 1, 0.75, 0.95), 1)
    mats.append(m)
car.data.materials.clear()
for m in mats: car.data.materials.append(m)
for p in car.data.polygons:
    vs = [car.data.vertices[i] for i in p.vertices]
    votes = {}
    for v in vs:
        for ge in v.groups: votes[ge.group] = votes.get(ge.group, 0) + ge.weight
    p.material_index = max(votes, key=votes.get) if votes else 0
sc.display.shading.color_type = "MATERIAL"
frame(sc, cam, [car]); shot(sc, "02_tagged.png")
print("GROUPS", groups)

# 03: game slots, 04: collision hulls
LOOK = {"Body_0": (0.75, 0.12, 0.12), "Body_1": (0.95, 0.95, 0.92), "Windows": (0.35, 0.6, 0.9), "HeadLight": (1, 0.9, 0.3),
        "LeftTailLight": (1, 0.1, 0.1), "RightTailLight": (1, 0.1, 0.1), "LeftSignalLight": (1, 0.5, 0), "RightSignalLight": (1, 0.5, 0),
        "ReverseLight": (0.9, 1, 1), "Seat_01": (0.2, 0.7, 0.2), "Seat_02": (0.2, 0.4, 0.9), "Dashboard_01": (0.8, 0.3, 0.8),
        "Trim": (0.25, 0.25, 0.27)}
bpy.ops.wm.read_factory_settings(use_empty=True); sc, cam = scene_setup()
body = glob.glob(os.path.join(KIT, "SM_*_Body.fbx"))[0]
bpy.ops.import_scene.fbx(filepath=body)
for f in glob.glob(os.path.join(KIT, "parts", "*_P1.fbx")): bpy.ops.import_scene.fbx(filepath=f)
ucx = [o for o in bpy.data.objects if o.name.startswith("UCX")]
vis = [o for o in bpy.data.objects if o.type == "MESH" and o not in ucx]
for m in bpy.data.materials:
    m.diffuse_color = (*LOOK.get(m.name.split(".")[0], (0.6, 0.6, 0.62)), 1)
for o in ucx: o.hide_render = True
sc.display.shading.color_type = "MATERIAL"
frame(sc, cam, vis); shot(sc, "03_slots.png")
hm = bpy.data.materials.new("hull"); hm.diffuse_color = (0.1, 0.8, 0.5, 0.45)
for o in ucx:
    o.hide_render = False; o.data.materials.clear(); o.data.materials.append(hm)
for o in vis:
    for s in o.material_slots: s.material = bpy.data.materials.get("Trim") or s.material
sc.display.shading.color_type = "MATERIAL"; sc.display.shading.show_xray = True; sc.display.shading.xray_alpha = 0.6
frame(sc, cam, vis); shot(sc, "04_collision.png")
print("SHOTS", sorted(os.listdir(OUT)))
