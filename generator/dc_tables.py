#!/usr/bin/env python3
"""One table per composite for the Biceps mod (later "DC, Director's Cut"; the user keeps Biceps).

    python dc_tables.py          merge into Biceps_P after the individual builds
    python dc_tables.py demo     self-check

Run after build_vehicles.py (+ unlock), biceps_parts.py, pack_wheels.py and pack_characters.py:
  Vehicles      Vehicles_Biceps  <- Vehicles_Biceps + Vehicles_ZapBikes (bike rows come from Zero's table)
  VehicleParts  VehicleParts_Biceps <- VehicleParts_Biceps + PackWheels_P's VehicleParts_PackWheels
  meshes        PackWheels_P DC/Wheels -> Biceps_P
CharacterBodyParts_Biceps is written straight into Biceps_P by pack_characters.py.
Row names never change: saves key vehicles and parts by row name. MoreTuning's combine() grafts each
source's imports into the first, so rows from different vanilla tables share one asset.
"""
import os
import shutil
import sys

sys.path.insert(0, os.environ.get("MORETUNING_REBASE", os.environ.get("MORETUNING_REBASE", r"D:\MT\MoreTuning\Rebase")))
HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "Biceps_P", "MotorTown", "Content")
WHEELS_MOD = os.path.join(HERE, "PackWheels_P", "MotorTown", "Content")
MERGES = [
    ("/Game/DataAsset/Vehicles/Vehicles_Biceps",
     [os.path.join(MOD, "DataAsset", "Vehicles", "Vehicles_Biceps.uasset"),
      os.path.join(MOD, "DataAsset", "Vehicles", "Vehicles_ZapBikes.uasset")]),
    ("/Game/DataAsset/VehicleParts/VehicleParts_Biceps",
     [os.path.join(MOD, "DataAsset", "VehicleParts", "VehicleParts_Biceps.uasset"),
      os.path.join(WHEELS_MOD, "DataAsset", "VehicleParts", "VehicleParts_PackWheels.uasset")]),
]
RETIRED = [os.path.join(MOD, "DataAsset", "Vehicles", "Vehicles_ZapBikes")]   # folded in, never shipped


def merge(package, sources):
    import channels
    from pipeline import WORK, register_names, to_json
    fw = channels.framework
    parts = []
    for src in sources:
        if not os.path.isfile(src):
            sys.exit(f"FAIL: {src} is missing: build it first")
        t = fw.load(to_json(src, os.path.join(WORK, "dc_" + os.path.basename(src)[:-7] + ".json")))
        parts.append((t, channels.rows_of(t)))
    table, rows = channels.combine(parts)
    register_names(table, [n for r in rows for n in channels.fnames_in(r)] + [r["Name"] for r in rows])
    fw.write_table(fw.make_table(table, package, rows), package, MOD)
    print(f"  {package}: {len(rows)} rows from {len(sources)} tables")


def main():
    for package, sources in MERGES:
        merge(package, sources)
    for stem in RETIRED:
        for ext in (".uasset", ".uexp"):
            if os.path.exists(stem + ext): os.remove(stem + ext)
    src = os.path.join(WHEELS_MOD, "DC", "Wheels")
    dst = os.path.join(MOD, "DC", "Wheels")
    shutil.copytree(src, dst, dirs_exist_ok=True)
    print(f"  wheel meshes -> {dst}: {sum(len(f) for _, _, f in os.walk(dst))} files")


def demo():
    assert all(len(s) == 2 for _, s in MERGES)
    assert all(p.rsplit("/", 1)[1].endswith("_Biceps") for p, _ in MERGES)
    print("ok")


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else main()
