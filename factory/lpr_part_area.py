"""Area of every kit part vs its body -> <kit>/parts/areas.json. blender -b -P lpr_part_area.py -- <kit dir>..."""
import bpy, sys, glob, os, json
def area(p):
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=p)
    return sum(f.area for o in bpy.data.objects if o.type == "MESH" for f in o.data.polygons) * 1e4
for kd in sys.argv[sys.argv.index("--") + 1:]:
    n = os.path.basename(kd); b = area(f"{kd}/SM_{n}_Body.fbx")
    out = {os.path.basename(p)[:-4].split(n + "_")[1]: round(area(p) / b, 3) for p in sorted(glob.glob(f"{kd}/parts/*.fbx"))}
    json.dump(out, open(f"{kd}/parts/areas.json", "w"), indent=1); print("AREA", n, out)
