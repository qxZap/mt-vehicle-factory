#!/usr/bin/env python3
"""
build_vehicles.py — ship the new vehicles declared in vehicles.json.

Each entry clones a base vehicle two ways:

  1. The CLASS asset, byte-renamed into the mod. Byte-rename keeps file
     offsets valid only if the new name is the SAME LENGTH as the old, so the
     shipped class gets a generated same-length name. That name is invisible:
     what you spawn and buy is the ROW name, which is free-form.
  2. The DataTable ROW, with VehicleClass repointed at that class and any
     row_field overrides applied.

Modifications are applied to the cloned class, never the base, so vanilla
vehicles are untouched.
"""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path

from mt_paths import GAME_CONTENT, MAPPINGS, MOD_CONTENT_ROOT, WORK_DIR, effective_asset
from unlock_vehicles import discover_tables, vehicle_class_by_row

INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")
CONFIG   = Path("vehicles.json")


def same_length_name(new_id: str, base_short: str) -> str:
    """A class name the byte-renamer can use: exactly as long as the base's.
    Derived from new_id so it is stable across builds."""
    h = hashlib.sha1(new_id.encode()).hexdigest().upper()
    return (("V" + h)[:len(base_short)])


def run(*args: str) -> bool:
    r = subprocess.run([str(INJECTOR), *args], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.strip(): print(f"    {line}")
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
    return r.returncode == 0


# Rear winch mounts: one tiny mesh per crane slot, each carrying ONLY its own
# socket at the origin. One mesh per slot, not one mesh with all three: the
# game finds CraneN by socket name on any component, so three carriers each
# holding Crane0..2 would all answer to the same name. Built from
# Inventory_Small_01 because it has a BodySetup -- a carrier with no collision
# geometry creates no body, and the winch then fails to weld (see the
# weld-ghost notes in vehicles.json).
WINCH_MOUNT_PKG = "/Game/Arini/WinchMounts"
WINCH_MOUNT_SRC = "Cars/Parts/Utility/Inventory_Small_01.uasset"
_MOUNT_MESHES_BUILT: set[str] = set()

# Blueprint edits queued per class asset during one row's modifications and
# run as a single chain afterwards (see _run_bp_chain).
_BP_STEPS: dict[str, list[list[str]]] = {}


def _ensure_winch_mount_mesh(slot: str) -> bool:
    if slot in _MOUNT_MESHES_BUILT:
        return True
    name = f"SM_WinchMount_{slot}"
    src = Path(effective_asset(WINCH_MOUNT_SRC))
    out_dir = MOD_CONTENT_ROOT / WINCH_MOUNT_PKG[len("/Game/"):]
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in (".uasset", ".uexp", ".ubulk"):
        sp = src.with_suffix(ext)
        if sp.exists():
            (out_dir / f"{name}{ext}").write_bytes(sp.read_bytes())
    out = out_dir / f"{name}.uasset"
    ok = (run("rename-package", "--uasset", str(out), "--mappings", str(MAPPINGS),
              "--name", name, "--package", WINCH_MOUNT_PKG)
          and run("add-mesh-sockets", "--uasset", str(out), "--mappings", str(MAPPINGS),
                  "--add", f"{slot}:0,0,0"))
    if ok:
        _MOUNT_MESHES_BUILT.add(slot)
    return ok


def _run_bp_chain(rel: str, steps: list[list[str]]) -> bool:
    """Apply several injector edits to one vehicle blueprint, in order.

    A blueprint only parses properly when UAssetAPI can resolve its imports off
    NEIGHBOURING files: identical bytes read as 8 RawExports from a bare folder
    and 0 from the vanilla extract, and an edit on a RawExport is a silent
    no-op. So every intermediate is written BESIDE the vanilla asset, never in
    staging, and only the last step writes the staged copy.

    A MOD's copy is extracted outside the content tree and fails the same way
    -- ProxyTechDuallys' Hana and Ranch did, and the refusal aborted the whole
    build before packing. Those bytes are copied beside the vanilla asset
    first: the edit then runs on the mod's blueprint with vanilla neighbours.
    """
    src = Path(effective_asset(rel))
    if not src.is_file():
        print(f"    vehicle class {rel} not found - skipped", file=sys.stderr)
        return False
    home = Path(GAME_CONTENT) / rel
    litter: list[Path] = []
    try:
        if home.is_file() and src.resolve() != home.resolve():
            twin = home.with_name(f"{home.stem}__mtmisrc.uasset")
            for ext in (".uasset", ".uexp", ".ubulk"):
                sp = src.with_suffix(ext)
                if sp.exists():
                    twin.with_suffix(ext).write_bytes(sp.read_bytes())
                    litter.append(twin.with_suffix(ext))
            print(f"    {rel}: editing the installed mod's copy, parsed beside vanilla")
            src = twin
        probe = subprocess.run([str(INJECTOR), "inspect-export", "--cell", str(src),
                                "--mappings", str(MAPPINGS), "--limit", "999"],
                               capture_output=True, text=True).stdout
        if (raw := probe.count("RawExport")):
            print(f"    {rel}: {raw} RawExport(s) at the source -- edits would silently do "
                  f"nothing, refusing", file=sys.stderr)
            return False
        out = MOD_CONTENT_ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        cur = src
        for i, st in enumerate(steps):
            last = i == len(steps) - 1
            dst = out if last else src.with_name(f"{src.stem}__mtmi{i}.uasset")
            if not last:
                litter += [dst.with_suffix(e) for e in (".uasset", ".uexp", ".ubulk")]
            if not run(st[0], "--uasset", str(cur), "--output", str(dst),
                       "--mappings", str(MAPPINGS), *st[1:]):
                return False
            cur = dst
        return True
    finally:
        for t in litter:
            t.unlink(missing_ok=True)


def _tables_with_row(tables, row: str):
    """Tables that carry `row`, matched EXACTLY. A substring test on
    "<row>\t" would let Hana's row -- literally named "1" -- match
    SemiTruck_01."""
    for trel in tables:
        tsrc = effective_asset(trel)
        if not Path(tsrc).is_file():
            continue
        r = subprocess.run([str(INJECTOR), "dump-table", "--uasset", str(tsrc),
                            "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                           capture_output=True, text=True)
        if any(ln.split("\t", 1)[0] == row for ln in r.stdout.splitlines()):
            yield trel, Path(tsrc)


def apply_modifications(entries, row_to_class, tables) -> bool:
    """Modify vehicles the game already ships, in place.

    Different from the `vehicles` list above, which builds a NEW vehicle from
    an existing one. Here the row keeps its name and its class keeps its path,
    so the mod's copy simply overrides vanilla's and every one of these already
    in the world gains the change. That is the point for something like a fuel
    pump on the tanker trailer: nobody wants a second trailer to buy, they want
    the trailer they already own to work.

    The class asset is re-copied from vanilla each build rather than edited in
    place, so the result depends only on vehicles.json and not on what the last
    build happened to leave behind.
    """
    ok = True
    for v in entries:
        row = v.get("row")
        base_path = row_to_class.get(row) if row else None
        if not base_path:
            print(f"    row '{row}' not in any vehicle table - skipped", file=sys.stderr)
            ok = False
            continue
        print(f"  {row} (modified in place)")

        short   = base_path[base_path.rfind("/") + 1:]
        rel_dir = base_path[len("/Game/"):].rsplit("/", 1)[0]
        src     = effective_asset(f"{rel_dir}/{short}.uasset")
        dst_dir = MOD_CONTENT_ROOT / rel_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst     = dst_dir / f"{short}.uasset"
        copied = 0
        for ext in (".uasset", ".uexp", ".ubulk"):
            sp = src.with_suffix(ext)
            if sp.exists():
                (dst_dir / f"{short}{ext}").write_bytes(sp.read_bytes())
                copied += 1
        if not copied:
            print(f"    class asset {short} not found - skipped", file=sys.stderr)
            ok = False
            continue

        row_sets = []
        for m in v.get("modifications") or []:
            t = m.get("type")
            if t == "fuel_pump":
                # Adds MTTankerFuelPumpComponent. bHasFuelPump on the row only
                # advertises the component -- without this the flag does
                # nothing at all, which is the trap worth remembering.
                a = ["vehicle-fuel-pump", "--uasset", str(dst), "--mappings", str(MAPPINGS)]
                fts = m.get("fuel_types") or ["Diesel"]
                a += ["--fuel-types", ",".join(fts)]
                for flag, key in (("--rel-x", "rel_x"), ("--rel-y", "rel_y"), ("--rel-z", "rel_z")):
                    if m.get(key) is not None:
                        a += [flag, str(m[key])]
                if not run(*a):
                    ok = False
            elif t == "cargo_fuel_types":
                # What the tank ACCEPTS, as opposed to what the pump gives out.
                # A hydrant refuses a tanker with "wrong fuel type" until Water
                # is listed here, however the pump is configured.
                a = ["vehicle-cargo-fuels", "--uasset", str(dst), "--mappings", str(MAPPINGS),
                     "--types", ",".join(m.get("types") or ["Water"])]
                if m.get("space_type"):
                    a += ["--space-type", m["space_type"]]
                if not run(*a):
                    ok = False
            elif t == "crane_winch":
                a = ["vehicle-crane-winch", "--uasset", str(dst), "--mappings", str(MAPPINGS)]
                if m.get("name"):  a += ["--name", m["name"]]
                if m.get("crane"): a += ["--crane", m["crane"]]
                if not run(*a):
                    ok = False
            elif t == "all_wheel_drive":
                # Present in the CLONE dispatch but not here, so asking for AWD
                # on an existing vehicle silently hit "unsupported" and the log
                # line that looked like Crany's AWD was actually Vista GTR's,
                # a few lines further down.
                a = ["vehicle-awd", "--uasset", str(dst), "--mappings", str(MAPPINGS)]
                if m.get("each_set_awd"):       a.append("--each-set-awd")
                if m.get("enable_center_diff"): a.append("--center-diff")
                if not run(*a):
                    ok = False
            elif t == "constraint":
                # A hydraulic constraint between two of the vehicle's own
                # components. Crany's boom is driven kinematically and pulls
                # nothing; the wreckers that lift are built from these.
                a = ["vehicle-constraint", "--uasset", str(dst), "--mappings", str(MAPPINGS),
                     "--component1", m["component1"], "--component2", m["component2"]]
                if m.get("name"):           a += ["--name", m["name"]]
                if m.get("angular_speed") is not None:
                    a += ["--angular-speed", str(m["angular_speed"])]
                if not run(*a):
                    ok = False
            elif t == "interactable":
                a = ["vehicle-interactable", "--uasset", str(dst), "--mappings", str(MAPPINGS),
                     "--types", ",".join(m["types"])]
                if m.get("name"):
                    a += ["--name", m["name"]]
                if not run(*a):
                    ok = False
            elif t == "sockets":
                # Motor Town mounts equipment at sockets NAMED AFTER THE SLOT --
                # Winch0, Crane0, Utility0..Utility9. Atlas 8x8 is the reference:
                # its rails mesh carries Winch0 and Utility4, its flanker bed
                # carries Utility2/3/4. The name IS the slot, so a winch socket
                # and a utility socket are genuinely different things.
                #
                # The mesh is another mod's or vanilla's, so it is copied into
                # our staging first and patched there -- we never edit in place.
                rel = m["mesh"].strip("/") + ".uasset"
                src = effective_asset(rel)
                if not src.is_file():
                    print(f"    socket mesh {rel} not found - skipped", file=sys.stderr)
                    ok = False
                    continue
                out = MOD_CONTENT_ROOT / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                for ext in (".uasset", ".uexp", ".ubulk"):
                    sp = src.with_suffix(ext)
                    if sp.exists():
                        out.with_suffix(ext).write_bytes(sp.read_bytes())
                specs = []
                for s in m.get("add") or []:
                    loc = ",".join(str(x) for x in s["loc"])
                    spec = f'{s["name"]}:{loc}'
                    if s.get("rot"):
                        spec += ":" + ",".join(str(x) for x in s["rot"])
                    specs.append(spec)
                if specs and not run("add-mesh-sockets", "--uasset", str(out),
                                     "--mappings", str(MAPPINGS), "--add", ";".join(specs)):
                    ok = False
            elif t == "part_slots":
                # Slots are a SET on the row, and a winch is spawned at runtime
                # from a part fitted to one. Crany declares no slots at all,
                # which is why its crane's Winch is forever null.
                for rel in tables:
                    tbl_src = effective_asset(rel)
                    if not tbl_src.is_file():
                        continue
                    probe = subprocess.run(
                        [str(INJECTOR), "dump-table", "--uasset", str(tbl_src),
                         "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                        capture_output=True, text=True)
                    if f"{row}	" not in probe.stdout:
                        continue
                    out = MOD_CONTENT_ROOT / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if not out.is_file():
                        for ext in (".uasset", ".uexp"):
                            sp = tbl_src.with_suffix(ext)
                            if sp.exists():
                                out.with_suffix(ext).write_bytes(sp.read_bytes())
                    cmd = ["set-row-slots", "--uasset", str(out),
                           "--mappings", str(MAPPINGS), "--row", row,
                           "--field", m.get("field", "NotOptionalPartSlots")]
                    if m.get("clear"):
                        cmd.append("--clear")
                    if m.get("add"):
                        cmd += ["--add", ",".join(m["add"])]
                    if not run(*cmd):
                        ok = False
            elif t == "winch_mounts":
                # Rear winches. Measured 10 Sep on Golima: a CraneN slot needs
                # (a) Parts[CraneN] fitted on the row, as Dory_Wrecker does, and
                # (b) a CraneN socket on a CHILD mesh component -- not on the body
                # mesh, not on a part mesh. That child needs a physics body or
                # the spawned winch cannot weld through it and pushes the truck,
                # hence --weld-ghost; --hidden because nobody should see it.
                rel = m["asset"].strip("/") + ".uasset"
                mounts = m.get("mounts") or []
                for mn in mounts:
                    slot = mn["slot"]
                    if not _ensure_winch_mount_mesh(slot):
                        ok = False
                        continue
                    st = ["vehicle-mesh-component", "--name", f"WinchMount_{slot}",
                          "--mesh", f"{WINCH_MOUNT_PKG}/SM_WinchMount_{slot}",
                          "--parent", m.get("parent", "Mesh"),
                          "--loc", ",".join(str(x) for x in mn["loc"]),
                          "--rot", ",".join(str(x) for x in (mn.get("rot") or [0, 0, 0])),
                          "--weld-ghost", "--hidden"]
                    if m.get("sample"):
                        st += ["--sample", m["sample"]]
                    if m.get("sample_from"):
                        st += ["--sample-from",
                               str(effective_asset(m["sample_from"].strip("/") + ".uasset"))]
                    _BP_STEPS.setdefault(rel, []).append(st)
                if m.get("fit") and mounts:
                    spec = ";".join(f"EMTVehiclePartSlot::{mn['slot']}={m['fit']}" for mn in mounts)
                    fitted = 0
                    for trel, tsrc in _tables_with_row(tables, row):
                        tout = MOD_CONTENT_ROOT / trel
                        tout.parent.mkdir(parents=True, exist_ok=True)
                        if not tout.is_file():
                            for ext in (".uasset", ".uexp"):
                                sp = tsrc.with_suffix(ext)
                                if sp.exists():
                                    tout.with_suffix(ext).write_bytes(sp.read_bytes())
                        if run("edit-row-map", "--uasset", str(tout), "--mappings", str(MAPPINGS),
                               "--row", row, "--field", "Parts", "--set", spec):
                            fitted += 1
                        else:
                            ok = False
                    if not fitted:
                        print(f"    winch_mounts: no table carries row '{row}' to fit {m['fit']}",
                              file=sys.stderr)
                        ok = False
            elif t == "injector_ops":
                # Raw MTBPInjector edits on this vehicle's blueprint, run in order
                # through the blueprint chain (parsed beside vanilla). Written for
                # Crany, whose working crane is eight verbs deep -- remove-scs-node,
                # set-component-props, four vehicle-crane-joint, vehicle-seat-controls
                # -- worked out one probe at a time in vehicle_mod/crany/.
                # "{vanilla}" in an argument is the extracted game content folder,
                # for donor blueprints.
                rel = f"{rel_dir}/{short}.uasset"
                for op in m.get("ops") or []:
                    _BP_STEPS.setdefault(rel, []).append(
                        [str(a).replace("{vanilla}", str(GAME_CONTENT)) for a in op])
            elif t == "utility_slots":
                # THE mechanism. Confirmed in game 9 Sep after every table-side
                # lever failed: a part slot exists because the vehicle
                # BLUEPRINT declares it as an MTVehicleUtilitySlotComponent,
                # not because a mesh has a socket, not because the row carries
                # a SlotSupportedPartsQueries entry, and not because a part
                # names the slot. 26 vanilla blueprints do it this way.
                #
                # The class asset lives outside our staging, so it is copied in
                # first -- but the injector must READ it from a full content
                # tree. UAssetAPI resolves imports off neighbouring files on
                # disk, and the identical bytes parse as eight RawExports in a
                # bare folder and zero in the vanilla extract, which silently
                # turns the edit into a no-op.
                rel = m["asset"].strip("/") + ".uasset"
                src = effective_asset(rel)
                if not src.is_file():
                    print(f"    vehicle class {rel} not found - skipped", file=sys.stderr)
                    ok = False
                    continue
                out = MOD_CONTENT_ROOT / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                spec = ";".join(
                    s["slot"] + ":" + ",".join(str(x) for x in s["loc"])
                    + (":" + ",".join(str(x) for x in s["rot"]) if s.get("rot") else "")
                    for s in m.get("add") or [])
                if spec:
                    _BP_STEPS.setdefault(rel, []).append(
                        ["vehicle-utility-slot", "--parent", m.get("parent", "Body"), "--add", spec])
            elif t == "parts":
                # Clone generic part rows and point them at this vehicle. This
                # is the recipe the Atlas 8x8 mod uses to put utility mounts on
                # a truck that had none: every one of its utility rows carries
                # Slots=[Utility4] and VehicleKeys=[its truck rows], and nothing
                # else on that vehicle declares the slot. Neither a mesh socket
                # nor SlotSupportedPartsQueries produced a slot here -- both
                # were shipped, verified in the winning pak, and the Parts menu
                # still listed no Utility category at all.
                rel = m["table"].strip("/") + ".uasset"
                src = effective_asset(rel)
                if not src.is_file():
                    print(f"    parts table {rel} not found - skipped", file=sys.stderr)
                    ok = False
                    continue
                out = MOD_CONTENT_ROOT / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                if not out.is_file():
                    for ext in (".uasset", ".uexp"):
                        sp = src.with_suffix(ext)
                        if sp.exists():
                            out.with_suffix(ext).write_bytes(sp.read_bytes())
                slots = ",".join(
                    x if "::" in x else f"EMTVehiclePartSlot::{x}"
                    for x in (m.get("slots") or []))
                # An ABSENT vehicle_keys means "this vehicle only". An
                # explicitly EMPTY one means no restriction, which is how the
                # winch parts work: Winch_01 names Slots=[Winch0] and no keys
                # at all, and that is why Golima -- which has no winch of its
                # own and no winch entry anywhere on its row -- still lists
                # "Winch (15)" in the Parts menu. That is the only utility-like
                # pattern OBSERVED WORKING on this install.
                keys = ",".join(m["vehicle_keys"] if "vehicle_keys" in m else [row])
                for c in m.get("clone") or []:
                    new_id = c.get("id") or f'{row}_{c["base"]}'
                    if not run("clone-vehicle-row", "--uasset", str(out),
                               "--mappings", str(MAPPINGS),
                               "--base", c["base"], "--new-id", new_id):
                        ok = False
                        continue
                    if slots and not run("set-row-array", "--uasset", str(out),
                                         "--mappings", str(MAPPINGS), "--row", new_id,
                                         "--field", "Slots", "--kind", "enum",
                                         "--enum-type", "EMTVehiclePartSlot",
                                         "--values", slots):
                        ok = False
                    if keys and not run("set-row-array", "--uasset", str(out),
                                        "--mappings", str(MAPPINGS), "--row", new_id,
                                        "--field", "VehicleKeys", "--kind", "name",
                                        "--values", keys):
                        ok = False
                    # TruckClasses is the other gate, and an EMPTY one is not
                    # provably "no restriction": every generic utility part
                    # ships empty with bTruckClassIncludeNone set, and the
                    # trucks that picked our parts up are LightDuty while the
                    # one that did not is HeavyDuty. Naming all four classes
                    # satisfies either reading.
                    classes = ",".join(m.get("truck_classes") or [])
                    if classes and not run("set-row-array", "--uasset", str(out),
                                           "--mappings", str(MAPPINGS), "--row", new_id,
                                           "--field", "TruckClasses", "--kind", "enum",
                                           "--enum-type", "EMTTruckClass",
                                           "--values", classes):
                        ok = False
            elif t == "slot_queries":
                # What actually DECLARES an optional slot. A mesh socket only
                # says where a part hangs -- Golima got eight correctly shaped
                # Utility sockets and the tuning menu still offered no Utility
                # category. Trailer_Carry, Vulcan, Tavan and EVan have working
                # utility slots with no socket and no slot component at all;
                # their only declaration is this map on the vehicle row.
                for rel in tables:
                    tbl_src = effective_asset(rel)
                    if not tbl_src.is_file():
                        continue
                    probe = subprocess.run(
                        [str(INJECTOR), "dump-table", "--uasset", str(tbl_src),
                         "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                        capture_output=True, text=True)
                    if f"{row}\t" not in probe.stdout:
                        continue
                    out = MOD_CONTENT_ROOT / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if not out.is_file():
                        for ext in (".uasset", ".uexp"):
                            sp = tbl_src.with_suffix(ext)
                            if sp.exists():
                                out.with_suffix(ext).write_bytes(sp.read_bytes())
                    spec = ";".join(
                        f'{q["slot"]}={q.get("expr", "none")}:'
                        f'{q.get("tag", "VehiclePart.VehicleKeySpecific")}'
                        for q in m.get("add") or [])
                    if spec and not run("add-slot-queries", "--uasset", str(out),
                                        "--mappings", str(MAPPINGS), "--row", row,
                                        "--add", spec):
                        ok = False
            elif t == "row_field":
                val = m["value"]
                row_sets.append(f'{m["field"]}={val}')
            else:
                print(f"    unsupported modification '{t}' - skipped", file=sys.stderr)

        for rel_bp, steps in list(_BP_STEPS.items()):
            if not _run_bp_chain(rel_bp, steps):
                ok = False
        _BP_STEPS.clear()

        if not row_sets and not v.get("display_name"):
            continue
        # base == new-id: clone-vehicle-row REPLACES a row that already exists,
        # so naming the row as its own base is an in-place field edit and needs
        # no separate verb. No --class-path: the class keeps its identity.
        placed = 0
        for rel in tables:
            tbl_src = effective_asset(rel)
            if not tbl_src.is_file():
                continue
            probe = subprocess.run(
                [str(INJECTOR), "dump-table", "--uasset", str(tbl_src),
                 "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                capture_output=True, text=True)
            if f"{row}\t" not in probe.stdout:
                continue
            out = MOD_CONTENT_ROOT / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            table_in = out if out.is_file() else tbl_src
            cmd = ["clone-vehicle-row", "--uasset", str(table_in), "--output", str(out),
                   "--mappings", str(MAPPINGS), "--base", row, "--new-id", row]
            if row_sets:
                cmd += ["--set", ",".join(row_sets)]
            if v.get("display_name"):
                cmd += ["--display-name", v["display_name"]]
            if run(*cmd):
                placed += 1
            else:
                ok = False
        if placed == 0:
            print(f"    WARNING: no table carried row '{row}'", file=sys.stderr)
            ok = False
    return ok



# What the LAST run staged, so this run can remove what it no longer builds.
MANIFEST = MOD_CONTENT_ROOT / ".vehicles_staged.json"


def prune_stale(expected: set[str]) -> None:
    """Delete vehicle assets a previous run staged and this one does not.

    Dropping a `modify` entry stops the build TOUCHING that vehicle -- it does
    not remove the copy already sitting in the staging tree, which is packed
    again regardless. Removing the crashing Crany constraint from vehicles.json
    therefore shipped the crashing Crany anyway, and the build log looked clean
    because the step simply never ran.

    Reverting a change has to remove its artifact, or "reverted" is a claim
    about the config rather than about the pak.
    """
    try:
        old = set(json.loads(MANIFEST.read_text(encoding="utf-8")))
    except Exception:
        old = set()
    for rel in sorted(old - expected):
        d = MOD_CONTENT_ROOT / rel
        if not d.exists():
            continue
        for f in sorted(d.glob("*")):
            if f.is_file():
                f.unlink()
        try:
            d.rmdir()
        except OSError:
            pass
        print(f"  pruned {rel} — staged by an earlier run, not built by this one")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(sorted(expected), indent=2), encoding="utf-8")


def main() -> int:
    # --config so the island's vehicles and the shippable tanker work can live
    # in separate files. They ship as different mods, so keeping them in one
    # config meant every standalone pak had to be carved out of it at build
    # time.
    global CONFIG
    for i, a in enumerate(sys.argv):
        if a == "--config" and i + 1 < len(sys.argv):
            CONFIG = Path(sys.argv[i + 1])
        elif a.startswith("--config="):
            CONFIG = Path(a.split("=", 1)[1])
    if not CONFIG.exists():
        print("  vehicles.json absent — no custom vehicles"); return 0
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    # "skip": true leaves an entry declared but unbuilt -- no cloned class, no
    # table row, and import_meshes drops its Spawn_ placeholder too, because
    # the spawner resolves a mod-declared vehicle THROUGH this file. Keeping
    # the entry rather than deleting it preserves the tuning next to the
    # decision to shelve it.
    entries = [v for v in (cfg.get("vehicles") or [])
               if isinstance(v, dict) and v.get("base") and v.get("new_id")
               and not v.get("skip")]
    if skipped := [v["new_id"] for v in (cfg.get("vehicles") or [])
                   if isinstance(v, dict) and v.get("skip") and v.get("new_id")]:
        print(f"  skipped (skip=true): {', '.join(skipped)}")
    # "skip": true on a modify entry too. Leaving it out of `mods` also leaves
    # its class folder out of `expected`, so prune_stale removes whatever an
    # earlier run staged for it -- otherwise a parked vehicle's plain blueprint
    # copy keeps shipping and overriding whichever mod owns that vehicle.
    # "layers": [...] scopes a modify entry to named build layers. Hana and
    # Ranch are overridden by ProxyTechDuallys, so their mounts may only be
    # built in the duallys compat -- in the base they would either overwrite
    # Duallys or make the release depend on it. Same pruning rule as skip:
    # out of `mods` means out of `expected`, so a stale staged copy is removed.
    layer = (__import__("os").environ.get("MTMI_LAYER") or "vanilla").strip() or "vanilla"

    def _wanted(v):
        return not v.get("skip") and (not v.get("layers") or layer in v["layers"])

    mods = [v for v in (cfg.get("modify") or [])
            if isinstance(v, dict) and v.get("row") and _wanted(v)]
    if parked := [v["row"] for v in (cfg.get("modify") or [])
                  if isinstance(v, dict) and v.get("row") and not _wanted(v)]:
        print(f"  modify not built in layer '{layer}': {', '.join(parked)}")
    if not entries and not mods:
        print("  no vehicles declared"); return 0

    row_to_class = vehicle_class_by_row()
    tables = discover_tables()

    # Everything this run intends to stage. Anything a previous run left behind
    # and this one does not rebuild gets removed before we start.
    expected = set()
    for v in mods:
        cp = row_to_class.get(v.get("row"))
        if cp:
            expected.add(cp[len("/Game/"):].rsplit("/", 1)[0])
    for v in entries:
        cp = row_to_class.get(v.get("base"))
        if cp:
            expected.add(cp[len("/Game/"):].rsplit("/", 1)[0])
    if any(m.get("type") == "winch_mounts"
           for v in mods for m in (v.get("modifications") or [])):
        expected.add(WINCH_MOUNT_PKG[len("/Game/"):])
    prune_stale(expected)
    ok = True
    own_rows: dict[str, list[str]] = {}   # mod table -> rows cloned into it this build
    own_fits: dict[str, list[tuple[str, str]]] = {}   # mod table -> (row, edit-row-map --set)
    own_slots: dict[str, list[tuple[str, str, str]]] = {}   # mod table -> (row, field, set-row-slots --add)
    own_final: dict[str, tuple] = {}     # mod table -> (working copy, shipped path, last clone args, package)

    if mods:
        ok = apply_modifications(mods, row_to_class, tables) and ok

    for v in entries:
        base, new_id = v["base"], v["new_id"]
        print(f"  {new_id} (from {base})")
        base_path = row_to_class.get(base)
        if not base_path:
            print(f"    base row '{base}' not in any vehicle table — skipped", file=sys.stderr)
            ok = False; continue

        # --- 1. clone the class asset -----------------------------------
        base_short = base_path[base_path.rfind("/") + 1:]
        new_short  = same_length_name(new_id, base_short)
        rel_dir    = base_path[len("/Game/"):].rsplit("/", 1)[0]
        # /Game-relative for the self-path replace above.
        rel_dir_g  = base_path.rsplit("/", 1)[0]
        src        = effective_asset(f"{rel_dir}/{base_short}.uasset")
        dst_dir    = MOD_CONTENT_ROOT / rel_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst        = dst_dir / f"{new_short}.uasset"
        # Rename ONLY the asset's self-references. A blind replace of the base
        # name is wrong here in two ways, and both produce a car with no body:
        #   /Game/Cars/Models/Vista/Body   the FOLDER is also called Vista
        #   /Game/Cars/Parts/Wheels/Vista_L  the wheels are separate assets
        # Renaming either points the clone at packages that do not exist.
        # Delivery point classes never hit this because their folder is not
        # named after the class.
        pairs = [
            (f"{rel_dir_g}/{base_short}".encode(), f"{rel_dir_g}/{new_short}".encode()),
            (f"Default__{base_short}_C".encode(), f"Default__{new_short}_C".encode()),
            (f"{base_short}_C".encode(),          f"{new_short}_C".encode()),
        ]
        for ext in (".uasset", ".uexp", ".ubulk"):
            sp = src.with_suffix(ext)
            if not sp.exists():
                continue
            b = sp.read_bytes()
            for a, z in pairs:
                b = b.replace(a, z)
            (dst_dir / f"{new_short}{ext}").write_bytes(b)
        print(f"    class {base_short} -> {new_short}")
        new_class_path = f"/Game/{rel_dir}/{new_short}"

        # --- 2. modifications on the CLONE ------------------------------
        row_sets = []
        for m in v.get("modifications") or []:
            t = m.get("type")
            if t == "all_wheel_drive":
                a = ["vehicle-awd", "--uasset", str(dst), "--mappings", str(MAPPINGS)]
                # Default is a spool: one differential, four wheels, no new
                # components. each_set_awd gives front and rear their own;
                # enable_center_diff adds the centre one they both feed, which
                # is the shape vanilla AWD cars actually use.
                if m.get("each_set_awd"):      a.append("--each-set-awd")
                if m.get("enable_center_diff"): a.append("--center-diff")
                if not run(*a):
                    ok = False
            elif t == "row_field":
                row_sets.append(f'{m["field"]}={m["value"]}')
            elif t == "injector_ops":
                # Same verbs as on a modify entry, run on the CLONE. The chain parses a
                # blueprint only beside its vanilla neighbours, so the clone is parked
                # next to the base class for the duration and removed afterwards.
                rel = f"{rel_dir}/{new_short}.uasset"
                home = Path(GAME_CONTENT) / rel
                parked = []
                for ext in (".uasset", ".uexp", ".ubulk"):
                    sp = dst.with_suffix(ext)
                    if sp.exists():
                        home.with_suffix(ext).write_bytes(sp.read_bytes()); parked.append(home.with_suffix(ext))
                try:
                    steps = [[str(a).replace("{vanilla}", str(GAME_CONTENT)) for a in op] for op in m.get("ops") or []]
                    if not _run_bp_chain(rel, steps):
                        ok = False
                finally:
                    for p in parked:
                        p.unlink(missing_ok=True)
            elif t == "ship_assets":
                # Cooked assets the clone now references (a new body mesh...). Their own
                # /Game dependencies -- materials, textures -- follow automatically.
                import import_meshes as im
                for a in m.get("assets") or []:
                    status = im.copy_asset_to_mod(a[len("/Game/"):].split(".")[0], str(Path(__file__).parent))
                    print(f"    asset {a}: {status}")
                    if status in ("missing", "unset"):
                        ok = False
            elif t in ("row_parts", "part_slots"):
                pass                                # applied with the row, step 3
            else:
                print(f"    unsupported modification '{t}' — skipped", file=sys.stderr)

        # --- 3. clone the row into every table that defines the base ----
        # "table": a standalone mod ships its row in its OWN table (registered with
        # DataTableFramework as an adopted Vehicles parent), never in vanilla's or Arini's.
        if v.get("table"):
            own = v["table"]                                   # /Game/DataAsset/Vehicles/Vehicles_X
            src_rel = next((rel for rel in tables if f"{base}\t" in subprocess.run(
                [str(INJECTOR), "dump-table", "--uasset", str(effective_asset(rel)), "--mappings", str(MAPPINGS),
                 "--fields", "VehicleClass"], capture_output=True, text=True).stdout), None)
            if not src_rel:
                print(f"    WARNING: no table carried row '{base}'", file=sys.stderr); ok = False; continue
            out = MOD_CONTENT_ROOT / (own[len("/Game/"):] + ".uasset")
            out.parent.mkdir(parents=True, exist_ok=True)
            # Clone from VANILLA, not whatever mod currently overrides the table: a standalone
            # mod must not carry another mod's copy (VehicleLabs ships Vehicles.uasset).
            vanilla_src = Path(GAME_CONTENT) / src_rel
            # Several cars may share one mod table: each row is cloned into an unfiltered
            # working copy (vanilla rows + every clone so far), then --only keeps just ours.
            full = WORK_DIR / "own_tables" / (own[len("/Game/"):] + ".uasset")
            built = own_rows.setdefault(own, [])
            row_src = full if built else (vanilla_src if vanilla_src.is_file() else effective_asset(src_rel))
            built.append(new_id)
            extra = []
            if v.get("display_name"):
                extra += ["--display-name", v["display_name"]]
            if row_sets:
                extra += ["--set", ",".join(row_sets)]
            full.parent.mkdir(parents=True, exist_ok=True)
            common = ["--mappings", str(MAPPINGS), "--base", base, "--new-id", new_id, "--class-path", new_class_path]
            pkg, name = own.rsplit("/", 1)
            if not run("clone-vehicle-row", "--uasset", str(row_src), "--output", str(full), *common, *extra):
                ok = False
            # The shipped table, its fittings and must-fill slots are written ONCE after every car
            # is in (finalize below). Rebuilding it and reapplying every fitting per car was
            # quadratic: 40 minutes for 120 cars.
            own_final[own] = (full, out, common, extra, pkg, name)
            for m in v.get("modifications") or []:
                if m.get("type") == "row_parts":
                    own_fits.setdefault(own, []).append(
                        (new_id, ";".join(f"EMTVehiclePartSlot::{s}={p}" for s, p in m["parts"].items()),
                         ",".join(f"EMTVehiclePartSlot::{s}" for s in m.get("remove", []))))
                if m.get("type") == "part_slots":
                    own_slots.setdefault(own, []).append(
                        (new_id, m.get("field", "NotOptionalPartSlots"), ",".join(f"EMTVehiclePartSlot::{s}" for s in m["add"])))
            continue
        placed = 0
        for rel in tables:
            tbl_src = effective_asset(rel)
            if not tbl_src.is_file():
                continue
            probe = subprocess.run(
                [str(INJECTOR), "dump-table", "--uasset", str(tbl_src),
                 "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                capture_output=True, text=True)
            if f"{base}\t" not in probe.stdout:
                continue
            out = MOD_CONTENT_ROOT / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            # A table we already rewrote this build (unlock pass) is the input,
            # so the row lands on top of those edits instead of reverting them.
            table_in = out if out.is_file() else tbl_src
            args = ["clone-vehicle-row", "--uasset", str(table_in), "--output", str(out),
                    "--mappings", str(MAPPINGS), "--base", base, "--new-id", new_id,
                    "--class-path", new_class_path]
            if v.get("display_name"):
                args += ["--display-name", v["display_name"]]
            if row_sets:
                args += ["--set", ",".join(row_sets)]
            if run(*args):
                placed += 1
            else:
                ok = False
        if placed == 0:
            print(f"    WARNING: no table carried row '{base}'", file=sys.stderr); ok = False
    for own, (full, out, common, extra, pkg, name) in own_final.items():
        print(f"  finalize {own}: {len(own_rows[own])} row(s)")
        if not (run("clone-vehicle-row", "--uasset", str(full), "--output", str(out), *common, *extra,
                    "--only", ",".join(own_rows[own]))
                and run("rename-package", "--uasset", str(out), "--mappings", str(MAPPINGS), "--name", name, "--package", pkg)):
            ok = False; continue
        for row, sets, drops in own_fits.get(own, []):
            if not run("edit-row-map", "--uasset", str(out), "--mappings", str(MAPPINGS), "--row", row,
                       "--field", "Parts", "--set", sets, *(["--remove", drops] if drops else [])):
                ok = False
        for row, field, add in own_slots.get(own, []):
            if not run("set-row-slots", "--uasset", str(out), "--mappings", str(MAPPINGS), "--row", row,
                       "--field", field, "--add", add):
                ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
