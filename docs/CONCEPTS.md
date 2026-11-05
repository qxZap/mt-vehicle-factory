# How a Motor Town vehicle is built

Everything here was read from the cooked game, with `MTBPInjector inspect-export / dump-schema / dump-table`, and confirmed in game.

## The three pieces

1. **The blueprint** (`/Game/Cars/Models/<Folder>/<Class>`): the actor, with its components. A new car is a vanilla blueprint cloned under a new class name and edited.
2. **The Vehicles row**, in a DataTable: name, price, class, default parts (`Parts`: slot → part row) and `NotOptionalPartSlots`. Ship rows in **your own table**, registered as an adopted parent with the DataTableFramework, never in the vanilla tables. Saves record vehicles and parts **by row name**, so never rename a row.
3. **Part rows**, in a VehicleParts table: one per tuning part, keyed by slot, with `VehicleKeys` = the vehicle rows allowed to fit it.

## Wheels

- Wheels are `MHWheelComponent`s, `Wheel0..3`, inherited from the parent class. Each has `TirePhysicsData`, `SpringK`, `SpringLength`, `SpringBoundDamping`, `SpringReboundDamping`, `BrakeRatio`, `DifferentialComponentName` and `WheelSlotIndex`.
- **Size:** the visible wheel is the fitted Wheel part's mesh, a **1 m circle** scaled by the component's `RelativeScale3D`. The physics radius is **42.35 cm × scale** (Stinger's 0.72/0.78 → 30.46/33.06 cm), so the visible wheel is about 18% larger than the physics one, in vanilla too. Set scale = tyre diameter / 100 cm, and place the hub at `hub - d/2 + 42.35 × scale`.
- **Extra axles:** add SCS `WheelN_GEN_VARIABLE` components (class `MHWheelComponent`, archetype `Default__MHWheelComponent`, outer = the class export, parent `Body`) with `WheelSlotIndex = N`, exactly as vanilla CheetahMk1 does. The row needs `TireN`, `WheelN` and `BrakePadN` parts. Use `MTBPInjector vehicle-add-wheel`.
- **Springs:** scale Stinger's rates by corner load: `k = k_stinger × (curb × axle share / 2) / reference corner`. On Stinger springs, a 2.6 t SUV sits slammed.
- **Tyres:** `Offroad` with `OffroadWheel_01..05` exist in vanilla for Small and Pickup types.

## Material slots (paint, glass, lamps)

The body mesh's material **slot names** are what the game uses: `Body_0`/`Body_1` (paint channels), `Trim`, `Windows`, `HeadLight`, `LeftTailLight`, `RightTailLight`, `LeftSignalLight`, `RightSignalLight`, `ReverseLight`, `Seat_01/02`, `Dashboard_01`, `WindowTrim_01`, `SoftTop`, `RollCage_01`. Keep them in Stinger's order, and keep every slot present even if empty (put a 1-face filler in it), so blueprint indices never shift. Vehicle colour slots come from `add-color-slot` on the blueprint.

## Tuning parts

- A part is a mesh **modelled in body space**: its pivot is its offset, and it attaches at the body origin (`bUseCustomSocket=true`, no socket). Only `RearWing` uses a socket.
- Template rows come from vanilla Aero parts. Copy `VehicleRowGameplayTagQuery` from Vista's, or tag-locked templates (Panther's roof) won't fit.
- A slot whose stock part is a large share of the car (a whole front clip) goes in `NotOptionalPartSlots`: it can be swapped, never removed.
- **Parts need collision**, as vanilla's do: Panther's `Roof_01` has convex hulls. A part without collision is walk-through.
- **Never clone parts into or ship `VehicleParts0`/`UtilityParts`/`Wheels`.** That overwrote 278 rows of another mod once. Make your own table.

## Collision

The body ships its own `UCX_` hulls: 12 slices along the car, each split left and right, from body pieces only. Pieces smaller than about a shoebox (antennas, mirrors) are left out, so they're walk-through. One hull across the whole width bridges fender peaks and buttresses, and you end up standing on air. **Import with the classic FBX importer**; Interchange drops UCX silently.

## Lamps

- `HeadLight_Left/Right_GEN_VARIABLE`, `BlinkerLight_01/02`, `TaliLight_01/02` (sic) and `ReverseLight` are positioned components. Move them onto the model's lamps.
- European cars with their own amber signals: set the tail lights' `TailLightType=None`, or the tails also flash.
- **Pop-up headlights** are a **Headlight part** (slot `Headlight`), not a component. Each one has:
  - a skeletal mesh (`Aero.SkelealMesh`, sic);
  - an animation (`Headlight.LightOnAnim`) the game plays when the lights come on.

  Vanilla: Panther's `Headlight_01_Skel` + `Headlight_Popup`. Ours: bind pose = lids closed, raised lamps scaled to 1% about their hinge; the animation scales the lamps ×100 and the lids to 1%.

## Mirrors

`MTMirrorComponent` (a StaticMeshComponent) has:
- `MirrorType` (side or `Room`), `MirrorSize`, `MirrorCurvature`, `ViewDistance`, `Resolution`, `SideMirrorRotation`;
- sockets `SideMirrorSocketName` / `SideMirrorSurfaceSocketName` on its mesh;
- its own scene capture and render target. The glass uses `/Game/Cars/Materials/M_Mirror`.

Simplest: keep the base car's mirror components and move them to where the model's mirrors are, hiding the model's own. Better: give the model's mirror glass `M_Mirror` and the two sockets.

## Seat, cockpit, engine

- `DriverSeat_GEN_VARIABLE`: position, `SeatPositionType` (`Sedan`, `BikeDriverSport`, `BikeDriverUpright`, `ScooterDriver`, …).
- `SteeringWheel` (a StaticMeshComponent) turns with steering. On bikes it's the handlebar, with `Handle_L/R` sockets for the hands.
- `Dashboard` (`MTDashboard`): its own mesh and gauges.
- `Engine` (`MTEngineComponent`) is a scene component. Its position is where the engine lives for damage and sound.

## Pak rules

- Priority goes by the patch index before `_P` first (`Foo_2_P` beats `Foo_P`), then by name. Subfolders of `Paks/` mount too; disable a pak by moving it **outside** `Paks/`.
- A mod table must be a plain DataTable registered with the DataTableFramework. Never ship the vanilla composites.

## Failure modes that look like success

| Symptom | Cause |
|---|---|
| A car ships as the plain vanilla base | one injector op in its chain failed (e.g. an export the base doesn't have), so the whole chain was dropped. Grep the build log for `no export`, `not found`, `refusing` |
| The parts table is missing, so kits vanish in game | UAssetGUI refused the table: a name (e.g. a class like `SkeletalMesh`) wasn't registered in the name map |
| Collision has 8 hulls, not 24 | Interchange importer |
| An edit "applies" but nothing changes | the blueprint parsed as RawExports (read it beside its vanilla neighbours), or a non-idempotent op ran on last build's output |
| A car sits on oversized wheels | physics radius scaled to the tyre instead of the 1 m visible mesh |
