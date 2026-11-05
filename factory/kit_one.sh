#!/bin/bash
# kit one non-LPR car from manifest.json; usage: kit_one.sh <name>
W="$(cd "$(dirname "$0")" && pwd)"               # the factory scripts
WORK="${MTVF_WORK:-$W/../work}"                     # kit/, fbx/, tex/, manifests, logs
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 4.5/blender.exe}"
"$B" --background --python $W/kit.py -- $WORK/manifest.json "$1" $WORKORK > "$WORK/log_kit_$1.txt" 2>&1
grep -q "^KIT" "$WORK/log_kit_$1.txt" && echo "OK $1" || echo "FAIL $1"
