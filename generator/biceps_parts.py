#!/usr/bin/env python3
"""Tuning parts for the kit cars (Biceps, Exotic, Sedan): one row per kit part, all in the mod's
own VehicleParts_Biceps table (the mod keeps its first car's name for now).

    python biceps_parts.py            build the table into Biceps_P
    python biceps_parts.py demo       self-check of the row naming

The kit (scratchpad factory/kit.py) splits the four Street Racer Muscle presets into one shared
body and per-preset parts, all modelled in body space. Each row is cloned from a vanilla part of
the same slot (the Vista's, a Panther roof), locked to C0100_Biceps by VehicleKeys, and points
Aero.Mesh at /Game/DC/Vehicles/Biceps/Parts/SM_Biceps_<Slot>_P<n>. The table is registered with
DataTableFramework (adopted VehicleParts); the mod never ships AeroParts or the composite.
"""
import copy
import glob
import json
import os
import sys

sys.path.insert(0, os.environ.get("MORETUNING_REBASE", r"D:\MT\MoreTuning\Rebase"))
sys.path.insert(0, os.environ.get("MORETUNING_DTF", r"D:\MT\MoreTuning\DataTableFramework"))

KIT = os.path.join(os.environ.get("MTVF_WORK", "work"), "factory", "kit")
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Biceps_P", "MotorTown", "Content")
PACKAGE = "/Game/DataAsset/VehicleParts/VehicleParts_Biceps"
# Every kit car of the mod: its kit frame, the vehicle row its parts lock to, where its meshes live.
CARS = {
    "Biceps": {"frame": "SK_Veh_Preset_Muscle", "vehicle": "C0100_Biceps", "presets": ["01", "02", "03", "04"],
               "names": {"Roof_P1": "Biceps Convertible Top", "Roof_P2": "Biceps Hardtop",
                         "Louvers_P3": "Biceps Rear Window Louvers", "Bullbar_P4": "Biceps Nudge Bar",
                         "RollCage_P2": "Biceps Roll Cage"},
               "colors": {"Roof_P1": [("SoftTop", "Soft Top", (24, 24, 26))]}},
    "Exotic": {"frame": "SK_Veh_Preset_Exotic", "vehicle": "C0101_Exotic", "presets": ["01", "02", "03", "04"]},
    "Sedan": {"frame": "SK_Veh_Preset_Sedan", "vehicle": "C0102_Sedan", "presets": ["01", "02", "03", "04"]},
    "SedanPolice": {"frame": "SK_Veh_Preset_Sedan", "vehicle": "C0104_SedanPolice", "presets": ["05"]},
}
# Single cars (one preset each), registered from kit_cars_refs.json: real-world reference per model.
_REFS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kit_cars_refs.json")
SINGLES = {}
DROPPED = set()     # vehicle ids of cars dropped from the refs (already in the game): removed from the config
if os.path.exists(_REFS):
    # row ids are pinned to the original order: removing a car (City Hatch, vanilla) must not
    # renumber the rest, whose rows saves already key by name
    _ORDER = ["SK_Veh_Car_Small_01", "SK_Veh_Car_Van_01", "SK_Cabrio_01", "SK_Muscle_01", "SK_Muscle_02",
              "SK_Offroad_01", "SK_Offroad_02", "SK_Pickup_01", "SK_SUV_01", "SK_Sport_01", "SK_Sport_02",
              "SK_Van_01", "SK_Wagon_01"]
    _lpr = 0
    for _name, _r in json.load(open(_REFS)).items():
        _key = _r["display"].replace(" ", "")
        if _name.startswith("LP_Veh_"):   # Low Poly Racing: its own id range, clear of the bikes' C0140+
            _id = 300 + _lpr; _lpr += 1   # a dropped car keeps its number, so nobody after it moves
            if _r.get("dropped"): DROPPED.add(f"C{_id:04d}_{_key}"); continue
        else:
            _id = 120 + (_ORDER.index(_name) if _name in _ORDER else len(_ORDER) + len(SINGLES))
        SINGLES[_key] = {"frame": _name.rsplit("_", 1)[0], "vehicle": f"C{_id:04d}_{_key}",
                         "presets": [_name.rsplit("_", 1)[1]], "source": _name, "ref": _r}
CARS.update(SINGLES)
VEHICLE = CARS["Biceps"]["vehicle"]
TEMPLATE = {"FrontBumper": "Vista_FrontBumper_01", "RearBumper": "Vista_RearBumper_01", "Bonnet": "Vista_Bonnet_01",
            "SideSkirt": "Vista_SideSkirt_01", "Fender": "Vista_Fender_02", "RearWing": "Vista_RearWing_01",
            "Roof": "Panther_Roof_01", "Louvers": "Essam_RearWindowLouvers_01",
            "Bullbar": "Vista_FrontBumper_01", "RollCage": "Vista_FrontBumper_01"}
# Slots the template's own PartType does not give. The game has no roll-cage slot; the cage goes in
# the spare interior one (FrontWindowSunVisor) so it can be fitted and removed on its own.
PART_TYPE = {"Bullbar": "Bullbar", "RollCage": "FrontWindowSunVisor"}
LABEL = {"FrontBumper": "Front Bumper", "RearBumper": "Rear Bumper", "SideSkirt": "Side Skirt",
         "RearWing": "Rear Wing", "Bonnet": "Bonnet", "Fender": "Fenders", "Roof": "Roof",
         "Louvers": "Rear Window Louvers", "Bullbar": "Nudge Bar", "RollCage": "Roll Cage"}
# Part-level paint channels every car gets for a slot (a roll cage is always its own colour).
SLOT_COLORS = {"RollCage": [("RollCage_01", "Roll Cage", (30, 30, 32))]}
# The factory build: preset 1 is the car as sold (its stripped body carries none of these).
DEFAULTS = ["FrontBumper_P1", "RearBumper_P1", "Bonnet_P1", "Roof_P1"]
# a car whose kit is a single later preset (the police Sedan is preset 05) fits that preset's set


# Presets reuse pieces: Muscle_02 and _04 carry the very same roof. partsig.py (scratchpad factory/)
# fingerprints every part's vertices; a part identical to an earlier preset's is left out.
SIGS = os.path.join(os.path.dirname(KIT), "partsig.json")
# Display names where "Roof 2" says nothing about what you are buying.


def kit_parts(sigs=None, car="Biceps"):
    """[(slot, 'P<n>')] for every distinct part the kit wrote for this car."""
    if sigs is None:
        sigs = {k: (v[2] if len(v) > 2 else v[0]) for k, v in json.load(open(SIGS)).items()} if os.path.exists(SIGS) else {}
    c = CARS[car]
    out, seen = [], set()
    for pre in c["presets"]:
        for f in sorted(glob.glob(os.path.join(KIT, f"{c['frame']}_{pre}", "parts", "*.fbx"))):
            name = os.path.basename(f)[:-4]
            slot, preset = name.rsplit("_", 2)[-2:]
            key = (slot, sigs.get(name, name))
            if key in seen:
                print(f"    {car} {slot}_{preset}: identical to an earlier preset's, left out")
                continue
            seen.add(key)
            out.append((slot, preset))
    return out


def part_file(car, slot, preset):
    """The kit FBX of one part: whichever of the car's preset folders wrote it."""
    c = CARS[car]
    for pre in c["presets"]:
        hit = glob.glob(os.path.join(KIT, f"{c['frame']}_{pre}", "parts", f"*_{slot}_{preset}.fbx"))
        if hit: return hit[0]


def lpr_info(car):
    """Low Poly Racing pieces split by lpr_prep.py: {"labels": {tag: name}, "areas": {tag: share of body}}."""
    c = CARS[car]
    if not c.get("source", "").startswith("LP_Veh_"): return {"labels": {}, "areas": {}}
    pj = os.path.join(os.path.dirname(KIT), "fbx", c["source"] + "_parts.json")
    aj = os.path.join(KIT, c["source"], "parts", "areas.json")
    return {"labels": json.load(open(pj))["labels"] if os.path.exists(pj) else {},
            "areas": json.load(open(aj)) if os.path.exists(aj) else {}}


def row_name(slot, preset, car="Biceps"):
    return f"{car}_{slot}_{preset}"


def mesh_dir(car):
    return f"/Game/DC/Vehicles/{car}/Parts"


def text(name):
    return {"$type": "UAssetAPI.PropertyTypes.Objects.TextPropertyData, UAssetAPI", "Flags": "CultureInvariant",
            "HistoryType": "None", "Namespace": None, "CultureInvariantString": name, "SourceFmt": None,
            "Arguments": None, "ArgumentsData": None, "TransformType": "ToLower", "SourceValue": None,
            "FormatOptions": None, "TargetCulture": None, "Name": "Name", "ArrayIndex": 0, "IsZero": False,
            "PropertyTagFlags": "None", "PropertyTagExtensions": "NoExtension", "Value": None}


def prop(row, name):
    return next(p for p in row["Value"] if p["Name"] == name)


def main():
    import channels
    framework = channels.framework
    from pipeline import register_names
    src = channels.vanilla("AeroParts")
    by_name = {r["Name"]: r for r in channels.rows_of(src)}
    vista_query = copy.deepcopy(prop(by_name["Vista_RearWing_01"], "VehicleRowGameplayTagQuery"))
    rows, names, colors = [], [], {}
    for car, c in CARS.items():
        names += [c["vehicle"]] + c.get("also", [])
        lpr = lpr_info(car)["labels"]
        for slot, preset in kit_parts(car=car):
            r = copy.deepcopy(by_name[TEMPLATE[slot]])
            r["Name"] = row_name(slot, preset, car)
            label = c.get("names", {}).get(f"{slot}_{preset}", f"{car} {LABEL[slot]} {preset[1:]}")
            if f"{slot}_{preset}" in lpr: label = f"{c['ref']['display']} {lpr[f'{slot}_{preset}']}"
            r["Value"] = [text(label) if p["Name"] == "Name" else p for p in r["Value"]]
            if slot in PART_TYPE: prop(r, "PartType")["Value"] = PART_TYPE[slot]
            prop(r, "ColorSlots")["Value"] = []      # templates carry their own car's (Panther: Body_02 -> a dead "Body2")
            keys = prop(r, "VehicleKeys")
            keys["Value"] = [dict(keys["Value"][0], Value=k) for k in [c["vehicle"]] + c.get("also", [])]
            q = prop(r, "VehicleRowGameplayTagQuery")
            q["Value"] = copy.deepcopy(vista_query["Value"])                 # Panther's roof is tag-locked
            mesh = f"SM_{car}_{slot}_{preset}"
            pkg = framework.add_import(src, f"{mesh_dir(car)}/{mesh}", 0, "/Script/CoreUObject", "Package")
            obj = framework.add_import(src, mesh, pkg, "/Script/Engine", "StaticMesh")
            names += [f"{mesh_dir(car)}/{mesh}", mesh]
            for a in prop(r, "Aero")["Value"]:
                if a["Name"] == "Mesh": a["Value"] = obj
                # every kit part is modelled in body space: attach at the body origin, wing included
                elif a["Name"] == "bUseCustomSocket": a["Value"] = True
                elif a["Name"] in ("CustomSocketName", "AttachParentComponentName"): a["Value"] = None
            colors[r["Name"]] = c.get("colors", {}).get(f"{slot}_{preset}", []) + SLOT_COLORS.get(slot, [])
            rows.append(r)
    # Pop-up headlights (factory popup.py): one Headlight part per car, Panther's row with our
    # skeletal mesh and its LightOn animation; the game plays it when the lights come on.
    hl_src = {r["Name"]: r for r in channels.rows_of(channels.vanilla("Headlights"))}
    # only cars whose config ships the rig: a row naming an asset the pak lacks is a dead part
    _cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vehicles_biceps.json"), encoding="utf-8"))
    shipped = {x for e in _cfg["vehicles"] for m in e["modifications"] if m["type"] == "ship_assets" for x in m["assets"]}
    for car, c in CARS.items():
        if f"/Game/DC/Vehicles/{car}/Popup/SK_{car}_Popup" not in shipped: continue
        r = copy.deepcopy(hl_src["Panther_Headlight_01"])
        r["Name"] = f"{car}_Headlight_P1"
        r["Value"] = [text(f"{c['ref']['display']} Pop-up Headlights") if p["Name"] == "Name" else p for p in r["Value"]]
        keys = prop(r, "VehicleKeys"); keys["Value"] = [dict(keys["Value"][0], Value=c["vehicle"])]
        prop(r, "VehicleRowGameplayTagQuery")["Value"] = copy.deepcopy(vista_query["Value"])
        prop(r, "ColorSlots")["Value"] = []
        d = f"/Game/DC/Vehicles/{car}/Popup"
        def imp(obj, cls):
            pkg = framework.add_import(src, f"{d}/{obj}", 0, "/Script/CoreUObject", "Package")
            names.extend([f"{d}/{obj}", obj, cls]); return framework.add_import(src, obj, pkg, "/Script/Engine", cls)
        sk, anim = imp(f"SK_{car}_Popup", "SkeletalMesh"), imp(f"SK_{car}_Popup_Anim", "AnimSequence")
        for a in prop(r, "Aero")["Value"]:
            if a["Name"] == "SkelealMesh": a["Value"] = sk
        for a in prop(r, "Headlight")["Value"]:
            if a["Name"] == "LightOnAnim": a["Value"] = anim
        rows.append(r)
    # Part-level paint channels, the way vanilla custom rims declare Wheel_01: the convertible
    # roof's folded top is its own colour (material slot SoftTop on SM_Biceps_Roof_P1).
    wheel_cs = prop(next(r for r in channels.rows_of(channels.vanilla("Wheels")) if r["Name"] == "CustomWheel_05"), "ColorSlots")
    for r in rows:
        for slot, label, rgb in colors.get(r["Name"], []):
            k, v = copy.deepcopy(wheel_cs["Value"][0])
            k["Value"] = slot
            for q in v["Value"]:
                if q["Name"] == "DisplayName":
                    q.update(text(label), Name="DisplayName")
                elif q["Name"] == "DefaultColor":
                    q["Value"][0]["Value"] = f"{rgb[0]}, {rgb[1]}, {rgb[2]}"      # UAssetAPI writes Color as "R, G, B"
            cs = prop(r, "ColorSlots"); cs["Value"] = [x for x in cs["Value"] if x[0]["Value"] != slot] + [[k, v]]
            names.append(slot)
    names += [n for r in rows for n in channels.fnames_in(r)]
    register_names(src, names + [r["Name"] for r in rows])
    table = framework.make_table(src, PACKAGE, rows)
    framework.write_table(table, PACKAGE, DEST)
    print(f"  {PACKAGE}: {len(rows)} rows -> {DEST}")
    for r in rows:
        print("   ", r["Name"])


def demo():
    assert row_name("FrontBumper", "P1") == "Biceps_FrontBumper_P1"
    assert row_name("Roof", "P2", "Exotic") == "Exotic_Roof_P2"
    assert all(d.rsplit("_", 1)[0] in TEMPLATE for d in DEFAULTS)
    print("ok")


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else main()
