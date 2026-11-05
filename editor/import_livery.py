"""Livery cars into the editor: per car a texture + MI under /Game/DC/Vehicles/<Car>/, and the car's
body and part meshes take that MI on their Trim slot (the shared LPR palette MI otherwise).
The MI's parent is a stand-in at the game's /Game/Cars/Materials/Body/M_TexturedBody (never shipped)
carrying the one parameter the real one has: "Base Color Texture"."""
import unreal, json
import os
JOB = os.path.join(os.environ.get("MTVF_WORK", "work"), "livery_job.json")   # MTVF_WORK: the working folder (README)
lib = unreal.EditorAssetLibrary; at = unreal.AssetToolsHelpers.get_asset_tools(); mel = unreal.MaterialEditingLibrary
PARENT = "/Game/Cars/Materials/Body/M_TexturedBody"
if lib.does_asset_exist(PARENT):
    parent = unreal.load_asset(PARENT)
else:
    parent = at.create_asset("M_TexturedBody", "/Game/Cars/Materials/Body", unreal.Material, unreal.MaterialFactoryNew())
    t = mel.create_material_expression(parent, unreal.MaterialExpressionTextureSampleParameter2D, -300, 0)
    t.set_editor_property("parameter_name", "Base Color Texture")
    mel.connect_material_property(t, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.recompile_material(parent); lib.save_loaded_asset(parent)
for c in json.load(open(JOB)):
    car = c["car"]; dest = f"/Game/DC/Vehicles/{car}"
    task = unreal.AssetImportTask(); task.filename = c["tex"]; task.destination_path = dest
    task.destination_name = f"T_{car}_Livery"; task.automated = True; task.replace_existing = True; task.save = True
    at.import_asset_tasks([task])
    tex = unreal.load_asset(f"{dest}/T_{car}_Livery")
    tex.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)     # flat palette cells, as the vanilla atlas
    lib.save_loaded_asset(tex)
    mp = f"{dest}/MI_{car}_Livery"
    mi = unreal.load_asset(mp) if lib.does_asset_exist(mp) else at.create_asset(
        f"MI_{car}_Livery", dest, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", parent)
    mel.set_material_instance_texture_parameter_value(mi, "Base Color Texture", tex)
    lib.save_loaded_asset(mi)
    meshes = [f"{dest}/SM_{car}_Body"] + [p for p in lib.list_assets(f"{dest}/Parts", recursive=False) if "/SM_" in p]
    for p in meshes:
        m = unreal.load_asset(p.split(".")[0])
        sm = list(m.get_editor_property("static_materials"))
        for s in sm:
            if str(s.material_slot_name) == "Trim": s.material_interface = mi
        m.set_editor_property("static_materials", sm); lib.save_loaded_asset(m)
    print("LIVERY", car, len(meshes))
