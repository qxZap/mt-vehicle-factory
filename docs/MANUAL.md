# Manual: from a pack car to driving it

This takes one car through the whole process. Once one works, the same steps run in bulk with the batch scripts.

## 0. One-time setup

1. **Get the game's layout files.** Motor Town ships unversioned, so every tool needs the `.usmap` mappings for your game build. Dump them with UE4SS, or use the version.dll mappings exporter from the Capitalist Economy plugin. Keep them next to the repo and point the tools at them (`--mappings`).
2. **Build the injector:** `cd tools/MTBPInjector && dotnet build -c Release`. UAssetAPI is a git submodule, so clone with `--recursive`.
3. **Make a UE 5.5 project** for importing and cooking. Plugins: *Python Editor Script Plugin*. Project settings: *Python → Enable Remote Execution*. The scripts talk to the open editor through `editor/ue_exec.py`.
4. **Make game material stand-ins.** In your project, create empty materials at the game's own paths, for example `/Game/Cars/Materials/Body/M_Body` and `/Game/Cars/Materials/M_HeadLight`. `editor/import_kitcars.py` does this for you. They're never shipped: the cooked mesh only references the path, and the game resolves it to its real material.
5. **Set the working folder:** `MTVF_WORK=work` (or anywhere). The scripts create `fbx/`, `kit/`, `tex/` and logs there.

## 1. Identify the car

Every model gets an entry in `data/kit_cars_refs.json`; see `kit_cars_refs.example.json`.

```json
"LP_Veh_Hatchback_03": {"ref": "2017 Volkswagen Golf GTI (Mk7)", "curb": 1300, "front": 0.61,
                        "engine": "I4_150HP", "awd": false, "display": "Kestrel Hatch", "length_mm": 4268}
```

- **ref**: the real car it depicts. Everything physical follows from this.
- **length_mm**: the real length. Packs build cars at arbitrary sizes; this one built everything 5.0–5.6 m long, a Mini included. The model is scaled to this. The game itself is close to real scale (its E30 and M2 are within 1%).
- **curb, front**: the real weight and how much of it sits on the front axle. They drive mass and spring rates.
- **engine_pos**: `front`, `mid` or `rear`. It moves the engine, which is where crash damage lands and where the sound comes from.
- **offroad: true**: fits the game's Offroad tyres and rims.
- **popup: true**: pop-up headlights.
- **dropped**: the car already exists in the game, so it's not shipped. Its id stays reserved, so no other car renumbers.

Write a display name that isn't a trademark.

## 2. Prepare and kit (Blender, about 5 s per car)

```
factory/lpr_batch.sh LP_Veh_Hatchback_03 "<pack>/Models/Hatchback/LP_Veh_Hatchback_03.fbx"
```

**lpr_prep.py** (step 1 → 2 in the README screenshots):
- merges the pack's separate objects into one mesh;
- turns the car to face +X and scales it to `length_mm`;
- tags every piece: `Body`, `Wheel_FL/FR/RL/RR`, `Wheel_M1L/R` (middle axles), `Steering`, `part:<Slot>_P<n>` (tuning parts), `part:PopupOn/Off_P1`.

Alternative pieces the pack stacks in place (Stock/Tuning kits, Spoiler_001/002, Hood_00N) become alternatives of one tuning slot. P1 is the one fitted when the car is sold.

**kit.py** (step 2 → 3, 4):
- assigns the game's material slots;
- finds the paint colour and the second paint colour;
- picks out the lamps. An outer lamp face with the lamp housing just behind it becomes clear glass, and the housing lights up;
- splits out the parts;
- writes the collision hulls and `info.json` (wheels, lamps, steering wheel, seat, sockets).

Check `kit/<car>/info.json` and render it: `factory/lpr_look.py <body.fbx> <atlas.png> <out>`, or `factory/shots.py` for the four-panel view.

**Pop-ups:** run `factory/popup.py <kit/car> <out.fbx>` after the kit. It rigs the closed lids and raised lamps into one skeletal mesh with a `LightOn` animation. Check it with `factory/popup_look.py`.

## 3. Import into the editor

```
python generator/kit_cars.py ue-job          # writes work/kitcars_job.json
python editor/ue_exec.py -f editor/import_kitcars.py
python generator/kit_cars.py popup-job
python editor/ue_exec.py -f editor/import_popup.py
```

**Always import with the classic FBX importer.** UE 5.5's Interchange importer silently drops the `UCX_` collision hulls. You get 8 automatic hulls instead of 24 and never notice. The import scripts switch the importer for you (`Interchange.FeatureFlags.Import.FBX false`). To check, compare `get_convex_collision_count()` with `ucx_hulls` in `info.json`.

## 4. Generate the vehicle

```
python generator/kit_cars.py vehicles        # writes the per-car blueprint edits into the mod config
bash generator/build_dc.sh                   # cook, blueprints, tables, parts, bays, pak, deploy
bash generator/build_dc.sh --skip-cook       # when no mesh changed
```

Each car is a vanilla blueprint (the Stinger for cars, Zero for bikes) cloned and edited by `MTBPInjector`:
- body mesh;
- wheel positions, scale and springs;
- lamp positions;
- mirrors, cockpit and seat;
- engine position;
- extra axles.

It also gets a row cloned into your mod's own Vehicles table, a row per tuning part in your own VehicleParts table, and a dealer bay. [CONCEPTS.md](CONCEPTS.md) explains each of these.

## 5. Test in game

The pak deploys only when the game is closed. Test one change at a time and keep a checklist.

- **Size:** park it next to a vanilla car of the same class.
- **Wheels:** do they fill the arches? Does the car sit at its real ride height? SUVs shouldn't be on their bump stops.
- **Collision:** walk onto the hood and roof. Walk through antennas and mirrors.
- **Lights:** headlights, high beam, tails, brakes, signals, reverse, and pop-ups going up and down.
- **Paint:** recolour it in the garage. No factory-colour patches should stay.
- **Parts:** every body kit, spoiler and hood fits in place. Mandatory slots (whole front ends) can be swapped but never left empty.
- **Seat:** the driver's hands are on the wheel or bars, the camera sits right, and the steering wheel turns.

## Bikes

`factory/moto.py` (Assetsville bikes) and `factory/bike.py` (Street Racer bikes) split a bike into body and handlebar. The handlebar is the bike's `SteeringWheel` and turns with steering. It carries `Handle_L`/`Handle_R` sockets at the middle of each grip, 6 cm in from the bar end, the way the game's Zero has them. The rider's pose is the seat's `SeatPositionType`: `BikeDriverSport` (leaning forward), `BikeDriverUpright` for choppers and cruisers, `ScooterDriver`.
