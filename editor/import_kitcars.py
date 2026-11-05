"""Kit cars into the editor from a job file (written by generator/kit_cars.py ue-job).
Each car: its shared body at /Game/DC/Vehicles/<Car>/SM_<Car>_Body with convex collision and sockets,
and its distinct parts under .../Parts. Slots get the game's own materials (stand-ins, never shipped)."""
import unreal, json
import os
JOB = os.path.join(os.environ.get("MTVF_WORK", "work"), "kitcars_job.json")   # MTVF_WORK: the working folder (README)
lib = unreal.EditorAssetLibrary; at = unreal.AssetToolsHelpers.get_asset_tools()
# the classic FBX importer: UE 5.5 Interchange drops UCX_ hull meshes silently (5 Nov 2026)
unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX false")
sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
BODY = "/Game/Cars/Materials/Body/M_Body"
SLOT_MAT = {"Trim": "/Game/Cars/Materials/Body/MI_TexturedBody_PolygonStreetRacer", "Windows": "/Game/Cars/Materials/Windows/M_Glass_Base",
            "LeftTailLight": "/Game/Cars/Materials/M_TailLight", "RightTailLight": "/Game/Cars/Materials/M_TailLight",
            "HeadLight": "/Game/Cars/Materials/M_HeadLight", "LeftSignalLight": "/Game/Cars/Materials/M_TurnSignalLight",
            "RightSignalLight": "/Game/Cars/Materials/M_TurnSignalLight", "ReverseLight": "/Game/Cars/Materials/M_ReverseLight"}
for s in ("Body_0", "Body_1", "Body_01", "Body_02", "Seat_01", "Seat_02", "SoftTop", "Dashboard_01", "RollCage_01", "WindowTrim_01"): SLOT_MAT[s] = BODY
SLOT_MAT["Window"] = SLOT_MAT["Windows"]
SLOT_MAT["EmergencyRed"] = "/Game/Cars/Materials/M_EmergencyLight_Red"     # vanilla police slots
SLOT_MAT["EmergencyBlue"] = "/Game/Cars/Materials/M_EmergencyLight_Blue"
def stub(path):
    """A stand-in at the game's own path (never shipped: the cooked mesh imports the real one)."""
    if lib.does_asset_exist(path): return unreal.load_asset(path)
    folder, name = path.rsplit("/", 1)
    if name.startswith("MI_"):   # the cooked reference carries the class: an MI must stay an MI
        m = at.create_asset(name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        m.set_editor_property("parent", stub(BODY))
    else:
        m = at.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
    lib.save_loaded_asset(m); return m
def imp(fbx, folder, name, collision):
    t = unreal.AssetImportTask(); t.filename = fbx; t.destination_path = folder; t.destination_name = name
    t.automated = True; t.replace_existing = True; t.save = False
    ui = unreal.FbxImportUI(); ui.import_mesh = True; ui.import_as_skeletal = False
    ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH; ui.import_materials = False; ui.import_textures = False
    sd = ui.static_mesh_import_data; sd.combine_meshes = True; sd.auto_generate_collision = False; sd.one_convex_hull_per_ucx = True; sd.generate_lightmap_u_vs = False
    sd.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    t.options = ui; at.import_asset_tasks([t])
    m = unreal.load_asset(f"{folder}/{name}")
    sm = list(m.get_editor_property("static_materials"))
    for s in sm:
        p = SLOT_MAT.get(str(s.material_slot_name))
        if p: s.material_interface = stub(p)
    m.set_editor_property("static_materials", sm)
    if collision and sub.get_convex_collision_count(m) == 0:   # UCX hulls from kit.py (LPR) win
        sub.set_convex_decomposition_collisions(m, 8, 24, 200000)
    lib.save_loaded_asset(m)
    return m
# each pack's own textured palette for Trim, so its atlas UVs keep their colours (as import_factory)
TRIM_BY_PACK = {"streetracer": "/Game/Cars/Materials/Body/MI_TexturedBody_PolygonStreetRacer",
                "polycity": "/Game/Cars/Materials/Palette/MI_Palette_PolygonCity",
                "assetsville": "/Game/AssetsvilleTown/Materials/MI_ColorPalette",
                "polytown": "/Game/Cars/Materials/Palette/MI_Palette_PolygonTown",
                "lowpolyracing": "/Game/Cars/Materials/Body/MI_TexturedBody_Sketchfab_LPCars"}   # vanilla: Zino/Cora/Magis
for car in json.load(open(JOB)):
    SLOT_MAT["Trim"] = TRIM_BY_PACK.get(car.get("pack", "streetracer"), TRIM_BY_PACK["streetracer"])
    if lib.does_asset_exist(f"{car['dest']}/MI_{car['car']}_Livery"):   # a livery car (import_livery.py) keeps its own
        SLOT_MAT["Trim"] = f"{car['dest']}/MI_{car['car']}_Livery"
    body = imp(car["body_fbx"], car["dest"], car["body_name"], True)
    for n, (loc, rot) in car["sockets"].items():
        old = body.find_socket(n)
        if old: body.remove_socket(old)
        so = unreal.StaticMeshSocket(outer=body); so.set_editor_property("socket_name", n)
        so.set_editor_property("relative_location", unreal.Vector(*loc))
        so.set_editor_property("relative_rotation", unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2])); body.add_socket(so)
    lib.save_loaded_asset(body)
    for fbx, name in car["parts"]:
        imp(fbx, car["dest"] + "/Parts", name, True)    # parts are solid, as vanilla parts are
    for x in car.get("extra", []):          # extra meshes with their own sockets (a bike's handlebar)
        m = imp(x["fbx"], car["dest"], x["name"], False)
        for n, (loc, rot) in x.get("sockets", {}).items():
            old = m.find_socket(n)
            if old: m.remove_socket(old)
            so = unreal.StaticMeshSocket(outer=m); so.set_editor_property("socket_name", n)
            so.set_editor_property("relative_location", unreal.Vector(*loc))
            so.set_editor_property("relative_rotation", unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2])); m.add_socket(so)
        lib.save_loaded_asset(m)
    print("CAR", car["car"], "parts", len(car["parts"]), "slots", len(body.get_editor_property("static_materials")))
