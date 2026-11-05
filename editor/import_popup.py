"""Pop-up headlight parts into the editor (factory/popup.py rigs them): per car a skeletal mesh
/Game/DC/Vehicles/<Car>/Popup/SK_<Car>_Popup with its own skeleton and the LightOn animation, slots
on the game's stand-in materials (never shipped), as import_kitcars.py does for static parts."""
import unreal, json
import os
JOB = os.path.join(os.environ.get("MTVF_WORK", "work"), "popup_job.json")   # MTVF_WORK: the working folder (README)
lib = unreal.EditorAssetLibrary; at = unreal.AssetToolsHelpers.get_asset_tools()
BODY = "/Game/Cars/Materials/Body/M_Body"
SLOT_MAT = {"HeadLight": "/Game/Cars/Materials/M_HeadLight", "Windows": "/Game/Cars/Materials/Windows/M_Glass_Base",
            "Body_0": BODY, "Body_1": BODY, "WindowTrim_01": BODY}
for car in json.load(open(JOB)):
    dest = f"/Game/DC/Vehicles/{car['car']}/Popup"; name = f"SK_{car['car']}_Popup"
    t = unreal.AssetImportTask(); t.filename = car["fbx"]; t.destination_path = dest; t.destination_name = name
    t.automated = True; t.replace_existing = True; t.save = True
    ui = unreal.FbxImportUI(); ui.import_mesh = True; ui.import_as_skeletal = True; ui.import_animations = True
    ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH; ui.import_materials = False; ui.import_textures = False
    ui.create_physics_asset = False
    ui.skeletal_mesh_import_data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    t.options = ui; at.import_asset_tasks([t])
    sk = unreal.load_asset(f"{dest}/{name}")
    mats = list(sk.get_editor_property("materials"))
    trim = car["trim"]
    for m in mats:
        s = str(m.get_editor_property("material_slot_name")).split(".")[0]
        p = SLOT_MAT.get(s, trim)
        if lib.does_asset_exist(p): m.set_editor_property("material_interface", unreal.load_asset(p))
    sk.set_editor_property("materials", mats); lib.save_loaded_asset(sk)
    found = [a for a in lib.list_assets(dest, recursive=False)]
    print("POPUP", car["car"], [a.split("/")[-1] for a in found])
