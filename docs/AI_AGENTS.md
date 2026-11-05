# For AI agents

You are converting asset-pack cars into Motor Town vehicles in bulk. This page covers the operating
rules, the checks that catch silent failures, and the mistakes that cost the most. Read
[CONCEPTS.md](CONCEPTS.md) first: it explains every component you'll edit.

## Operating rules

1. **The game's own cars are the ground truth.** Before inventing a mechanism, find the vanilla car that already does it and copy its shape:
   - extra axles: CheetahMk1;
   - pop-ups: the Panther;
   - mirrors: Stinger's `MTMirrorComponent`;
   - weather volume: the graveyard's `MTWeatherOverrideVolume`.

   Use `inspect-export --limit 9999 --array-limit 50`, `dump-schema --class X`, `dump-enum`, and `dump-table --row R --deep --array-limit 99`.
2. **One unknown mechanic, one in-game probe.** Don't put an unproven idea into the bulk pipeline. Build it on one car, have the human test it, and then roll it out.
3. **Never start or kill the game.** Check `tasklist` for `MotorTown-Win64-Shipping`. Deploy only when it's closed, and tell the human when something is testable.
4. **Rows are save keys.** Never rename a vehicle or part row. To drop a car, mark it `dropped` in the refs: its id stays counted, so no other row renumbers.
5. **Only ship your own tables.** Never ship vanilla `VehicleParts0`, `Wheels`, `UtilityParts` or the composites.
6. **Don't edit a config while a build reads it.** The build reads `vehicles_*.json` at its start. Change scripts freely, but regenerate configs between builds.
7. **No asset-pack content in any public repo.**

## Checks after every build

Each check guards against a failure that already happened once without a single visible error.

```bash
# 1. no injector chain dropped (a dropped chain ships the plain vanilla base car)
grep -E 'no export|not found|refusing' build_vehicles.log
# 2. the parts table exists, and so do the rows you added
test -f <Mod>/.../VehicleParts_<Mod>.uasset
MTBPInjector dump-table --uasset <table> --mappings M --list | grep _Headlight_P1
# 3. a car's blueprint really carries your body, not the base's
MTBPInjector inspect-imports --cell <bp>.uasset --mappings M | grep SM_<Car>_Body
# 4. a sample car's row has the parts you expect
MTBPInjector dump-table --uasset Vehicles_<Mod>.uasset --mappings M --row <id> --deep --array-limit 99
# 5. the pak has what the config ships
repak list <Mod>_P.pak | grep -c Popup
```

In the editor, compare `get_convex_collision_count(mesh)` with `ucx_hulls` in `info.json`. A
mismatch means the import went through Interchange, which drops UCX hulls.

## Detection heuristics (factory/kit.py)

- **Paint:** the colour cell covering the most outward-facing panel area. LPR palettes are flat 25 px cells, but livery textures aren't flat, so match within 8/255. Don't require panels to face sideways: that rule left nose and tail panels unpainted.
- **Second paint channel:** another cell at least 20% as large, if it isn't a dark trim grey.
- **Lamps:** a glass or lamp face with open air in front and the lamp's housing within 10 cm behind it is a **cover**. Make it clear glass and light the housing. A lens with nothing behind it is the lamp itself.
- **Pop-ups:** two headlight pieces; the highest top is the raised state.
- **Tuning parts:** pieces stacked in place are alternatives of one slot. P1 (first by name) is fitted when sold. Mirror pairs and non-overlapping `X` / `X.001` splits are one part.
- **Axles:** cluster wheel hubs within 0.4 m of X (pack units are metres). Front- and rearmost are the corners; anything between is `Wheel_M<n>`.
- **Scale:** measure length on non-wheel pieces. A wheel object can carry stray vertices metres away.

## Verifying visually

Render before you ship. `factory/shots.py` gives raw / tagged / slots / collision; `lpr_look.py` gives slot colours; `popup_look.py` gives pop-up frames 0/6/12. The workbench renderer won't show textures unless shading is set to `TEXTURE`. An all-white render means "texture not shown", not "white car". Don't conclude from it.

## Costly mistakes, so you don't repeat them

- Scaling the wheel's *physics* radius to the tyre: every wheel ended up 18% too big.
- Leaving every car on Stinger's springs: SUVs sat slammed.
- One convex hull across the whole width: invisible walls above the bonnet.
- Assuming an op is idempotent: `--drop` failed on the second build because the property was already gone, and the car silently shipped vanilla. Builds re-edit their own last output, so every op must be safe to run twice.
- Rebuilding the table and reapplying every fitting per car: quadratic, 40 minutes at 120 cars. Finalize once.
- Registering a new class in a table without adding its name to the name map: UAssetGUI writes nothing, and a later step packs anyway.

## Handing work to the human

Keep a test checklist (markdown, checkboxes, grouped by build). For each item, say which car to check
and what "right" looks like. Ask concrete questions ("is it the roof light bar or the tail lamps?"),
not open ones.
