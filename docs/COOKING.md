# Unreal Engine as the cooker

Motor Town ships **cooked** assets, so the game can't load a raw FBX or an editor `.uasset`. You need
an Unreal Engine of the **same version** (5.5) to turn your meshes, textures, skeletons and
animations into cooked `.uasset` / `.uexp` / `.ubulk` files. Then you pack those into a pak with
the game's folder layout. You never build the game, and you don't need its source. An empty project
is enough.

## Why it works

A cooked asset refers to everything else **by path**: `/Game/Cars/Materials/Body/M_Body`,
`/Game/DC/Vehicles/MyCar/SM_MyCar_Body`. At runtime the game resolves each path against its own
content and every mounted pak. So:

- your own assets go under your own folder (we use `/Game/DC/...`) and ship in your pak;
- **the game's assets you only reference** (materials, the Stinger blueprint, wheel meshes) get a
  **stand-in**: an empty asset at the exact same path in your project. It's never shipped. The
  cooked mesh just remembers the path, and in game the path resolves to the real one.

A stand-in has to be the **same class** as the real asset. A `MaterialInstanceConstant` path needs
an MI stand-in, not a Material, because the reference records the class. Give it whatever
parameters you need to preview with (`import_livery.py` creates `M_TexturedBody` with its one
texture parameter).

## The project

1. Create a blank C++ or Blueprint project in UE 5.5. The project name doesn't matter.
2. Enable these plugins: **Python Editor Script Plugin** (to import by script) and, optionally,
   **Remote Execution** (Project Settings → Python), so scripts outside the editor can drive it
   (`editor/ue_exec.py`).
3. Put your content under `Content/<YourMod>/...`. That's `/Game/<YourMod>/...` in paths, and
   `MotorTown/Content/<YourMod>/...` in the pak.

## Importing (editor, by script)

`editor/import_kitcars.py` and `import_popup.py` show the settings that matter:

- **Use the classic FBX importer** (`Interchange.FeatureFlags.Import.FBX false`). UE 5.5's
  Interchange importer silently drops `UCX_` collision meshes.
- **Static meshes:** `combine_meshes`, no auto collision, `FBXNIM_IMPORT_NORMALS` (keep the
  normals Blender wrote; recomputed normals make low-poly cars look blobby), no material import.
  Then assign the stand-in materials **by slot name**.
- **Re-importing over an existing mesh keeps its old collision.** Clear it first
  (`remove_collisions`) or new hulls never land.
- **Sockets** (`add_socket`) are part of the mesh: grips, steering wheel, mirror surface.
- **Skeletal mesh + animation** (pop-ups): `import_as_skeletal`, `import_animations`,
  `create_physics_asset=False`. The import creates `<Name>`, `<Name>_Skeleton` and `<Name>_Anim`;
  ship all three.
- Save every asset you touch (`save_loaded_asset`). An editor crash or restore reverts unsaved work.

## Cooking (command line)

```bash
MSYS_NO_PATHCONV=1 "UnrealEditor-Cmd.exe" "<Project>.uproject" -run=cook -targetplatform=Windows \
    -unversioned "-OutputDir=<scratch folder>" -cooksinglepackagenorefs \
    "-MAP=/Game/DC/Vehicles/A/SM_A_Body+/Game/DC/Vehicles/A/Parts/SM_A_Bonnet_P1" -unattended
```

- `-unversioned`: Motor Town's assets are unversioned. Match it.
- `-cooksinglepackagenorefs`: cook exactly the listed packages and none of their references. The
  references are the game's own assets and your stand-ins, which must not be cooked or shipped.
- **List the packages with `-MAP=`, joined by `+`.** `-PACKAGE=` is ignored.
- **Always set `-OutputDir` to a scratch folder.** A cook without `-iterate` is a full cook, and
  it **deletes** `Saved/Cooked/<platform>` first, whatever you listed. Copy the cooked files from
  the scratch folder into place yourself.
- From Git Bash, set `MSYS_NO_PATHCONV=1`, or `/Game/...` gets rewritten into a Windows path and
  the list comes out empty.
- Check the log for `Cooked packages N Packages Remain 0 Total N`, where N is your count.

The cooked files land in `<scratch>/<Project>/Content/<YourMod>/...`. Each asset is a `.uasset` +
`.uexp`, plus a `.ubulk` for meshes and textures with bulk data.

## Packing

Lay the files out as the game does and pack the folder:

```
MyMod_P/
  MotorTown/Content/DC/Vehicles/...        cooked meshes, textures, skeletons, animations
  MotorTown/Content/Cars/Models/...        edited blueprints (MTBPInjector output)
  MotorTown/Content/DataAsset/...          your own Vehicles / VehicleParts tables
```

```bash
repak pack MyMod_P          # -> MyMod_P.pak
```

Copy the pak to `Motor Town/MotorTown/Content/Paks/`. Load order goes by the patch index before
`_P` first, then by name. New paks have to be accepted in game: they're listed in
`%LOCALAPPDATA%\MotorTown\Saved\Config\Windows\CustomPak.ini`, and an unaccepted pak is
silently not mounted.

## What is NOT cooked by Unreal

Blueprints and DataTables are edited **directly in their cooked form** by `tools/MTBPInjector`
(on UAssetAPI, with the game's `.usmap`). You don't recreate the game's car blueprint in the
editor: you clone the cooked Stinger blueprint, edit its components, and point it at your cooked
meshes by path.
