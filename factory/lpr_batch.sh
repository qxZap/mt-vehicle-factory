#!/bin/bash
# prep + kit one LPR car; usage: lpr_batch.sh <name> <src fbx>
W="$(cd "$(dirname "$0")" && pwd)"               # the factory scripts
WORK="${MTVF_WORK:-$W/../work}"                     # kit/, fbx/, tex/, manifests, logs
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 4.5/blender.exe}"
n=$1; src=$2
"$B" --background --python $W/lpr_prep.py -- "$src" "$WORK/fbx/$n.blend" > "$WORK/log_lprprep_$n.txt" 2>&1
"$B" --background --python $W/kit.py -- $WORK/manifest_lpr.json "$n" $WORK > "$WORK/log_kit_$n.txt" 2>&1
grep -q "^KIT" "$WORK/log_kit_$n.txt" && echo "OK $n" || echo "FAIL $n"
