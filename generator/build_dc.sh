#!/bin/bash
# The Biceps mod (later "DC"), end to end after the editor imports:
#   cook every mesh the mod ships -> restage -> vehicles + unlock -> parts, wheels, characters ->
#   one table per composite (dc_tables.py) -> dealer bays -> Biceps_P.pak
# Editor side first: import_biceps_kit.py and import_kitcars.py (scratchpad) via ue_exec.py.
#   bash build_dc.sh            build + pack (deploys only if the game is closed)
# no set -e: a grep finding nothing (exit 1) silently ended the build after the vehicle step
cd "$(dirname "$0")"
export MTMI_MOD_NAME=Biceps_P MSYS_NO_PATHCONV=1
UE="${UE_CMD:-/c/Program Files/Epic Games/UE_5.5/Engine/Binaries/Win64/UnrealEditor-Cmd.exe}"
PROJ="${UE_PROJECT:?set UE_PROJECT to your .uproject}"
COOKED="$(dirname "$PROJ")/Saved/Cooked/Windows/$(basename "$PROJ" .uproject)/Content"
SCRATCH="${MTVF_WORK:-work}"
OUT="$SCRATCH/cook_dc"
M="$(python -c 'import mt_paths;print(mt_paths.MAPPINGS)' 2>/dev/null | tail -1)"
INJ=MTBPInjector/bin/Release/net8.0/MTBPInjector.exe

if [ "$1" != "--skip-cook" ]; then        # --skip-cook: meshes unchanged since the last cook
echo "== cook"
L=$(python -c "
import json
c = json.load(open('vehicles_biceps.json'))
a = [x for e in c['vehicles'] for m in e['modifications'] if m['type'] == 'ship_assets' for x in m['assets']]
print('+'.join(dict.fromkeys(a)))")
"$UE" "$PROJ" -run=cook -targetplatform=Windows -unversioned "-OutputDir=$OUT" -cooksinglepackagenorefs "-MAP=$L" -unattended > "$OUT.log" 2>&1 || true
grep -oE 'Cooked packages [0-9]+ Packages Remain 0 Total [0-9]+' "$OUT.log" | tail -1
cp -r "$OUT/MTMapAddon/Content/DC/." "$COOKED/DC/"
fi

echo "== restage (only what the config ships survives)"
STALE="$SCRATCH/dc_stale_$(date +%H%M%S)"; mkdir -p "$STALE"
[ -d Biceps_P/MotorTown/Content/DC/Vehicles ] && mv Biceps_P/MotorTown/Content/DC/Vehicles "$STALE/"

echo "== vehicles"
python build_vehicles.py --config vehicles_biceps.json > "$SCRATCH/build_dc_vehicles.log" 2>&1
grep -E 'missing|unset|rror|no export|not found|refusing' "$SCRATCH/build_dc_vehicles.log" | grep -v Mirror || true
for T in Biceps_P/MotorTown/Content/DataAsset/Vehicles/Vehicles_*.uasset; do
  "$INJ" unlock-vehicles --uasset "$T" --output "$T" --mappings "$M" --ai-mult 1 --ai-mult-offroad 1 --include-police | tail -1   # our police car is ours to sell
done

echo "== parts, wheels, characters, merge"
python biceps_parts.py 2>&1 | grep -E 'rows ->|Traceback|FAIL'
python pack_wheels.py 2>&1 | tail -1
python pack_characters.py 2>&1 | tail -1
python dc_tables.py

# a pak without its parts table strips every car's kits in game: never ship one
[ -f Biceps_P/MotorTown/Content/DataAsset/VehicleParts/VehicleParts_Biceps.uasset ] || { echo "STOP: no VehicleParts_Biceps, nothing packed"; exit 1; }
echo "== bays + pack"
python kit_cars.py bays 2>&1 | tail -1
tools/repak.exe pack ./Biceps_P 2>&1 | tail -1
if tasklist | grep -qi motortown; then echo "GAME RUNNING - staged only: Biceps_P.pak"
else cp Biceps_P.pak "${MT_PAKS:?set MT_PAKS to Motor Town/MotorTown/Content/Paks}/" && echo "DEPLOYED Biceps_P.pak"; fi
