#!/usr/bin/env python3
"""Kit cars beyond Biceps: from kit output to a drivable car in the Biceps mod, the Biceps way.

    python kit_cars.py ue-job      write the editor import job (then run import_kitcars.py in UE)
    python kit_cars.py vehicles    add/refresh the cars' entries in vehicles_biceps.json
    python kit_cars.py bays        write biceps_bays.json and rebuild the Heavy Duty cell
    python kit_cars.py demo        self-check of the placement maths

Every placement comes from the kit's info.json (wheels, lamps, steering centre, driver cushion),
turned into the base class's (Stinger) components with the offsets that were tuned by hand on
Biceps -- which these formulas reproduce exactly (wheel z 29.76/32.36, track 98, seat 10/49.85).
Parts rows come from biceps_parts.CARS; the mod's tables, pak and cell are Biceps'.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.environ.get("MTVF_WORK", "work")   # holds factory/ (kits) and the editor job files
KIT = os.path.join(SCRATCH, "factory", "kit")
JOB = os.path.join(os.environ.get("MTVF_WORK", "work"), "kitcars_job.json")
CONFIG = os.path.join(HERE, "vehicles_biceps.json")
BAYS = os.path.join(HERE, "biceps_bays.json")
CELL = "MotorTown/Content/Maps/Jeju/Jeju_World/_Generated_/2FDNMCAFPUS3ZKEERFVDNPYA7.umap"

# The new cars (Biceps itself keeps its hand-tuned entry). Base "2" = Stinger: every component name
# the placement uses is Stinger's, proven on Biceps; per-car driving feel is a later pass.
CARS = {
    "Exotic": {"new_id": "C0101_Exotic", "display": "Exotic", "cost": 65000, "spot": "between"},
    "Sedan": {"new_id": "C0102_Sedan", "display": "Sedan", "cost": 26000, "spot": "front1"},
    # the pack's police preset on vanilla Zydro_Police: same component names as Stinger, plus
    # MTPoliceVehicle, which flashes the EmergencyRed/Blue slots. Zydro paints Body_01, so the kit's
    # Body_0/Body_1 get their own entries cloned from it.
    "SedanPolice": {"new_id": "C0104_SedanPolice", "display": "Sedan Police", "cost": 30000, "spot": "front2",
                    "base": "Zydro_Police", "folder": "Zydro", "slot_from": "Body_01",
                    "colors": "Body_0=Body=240:240:242;Body_1=Hood=16:16:18",
                    # Zydro's Mesh carries 16 OverrideMaterials: by slot index they repainted our body as a
                    # Zydro (user: "just a Zydro body"). Its row's FD_10.65 is electric gearing.
                    "pre_ops": [["set-component-props", "--export", "Mesh", "--drop", "OverrideMaterials"]],
                    "row": {"FinalDriveRatio": "105"}},
}
# Real-world references (user, 4 Nov 2026): curb weight, front share of the weight, drivetrain from
# the game's own parts. Root mass = curb - default parts (drivetrain, wheels, tyres, preset-1 kit).
PHYSICS = {
    "C0100_Biceps":   {"ref": "1968-70 Dodge Charger R/T", "curb": 1700, "front": 0.55, "kit": "Muscle",
                       "engine": "SmallBlock_320HP", "transmission": "301", "parts_kg": 493 + 105},
    "C0101_Exotic":   {"ref": "mid-engine V12 supercar (Murcielago class)", "curb": 1650, "front": 0.42, "kit": "Exotic",
                       "engine": "V12_400HP", "transmission": "6SpeedSportsLP670", "parts_kg": 563 + 111},
    "C0102_Sedan":    {"ref": "mid-size sedan (Camry/Accord class)", "curb": 1450, "front": 0.60, "kit": "Sedan",
                       "engine": "SmallBlock_180HP", "transmission": "302", "parts_kg": 433 + 80},
    "C0104_SedanPolice": {"ref": "police-package mid-size sedan (+120 kg of gear)", "curb": 1570, "front": 0.58,
                          "kit": "SedanPolice", "engine": "SmallBlock_240HP", "transmission": "302", "parts_kg": 463 + 110},
}
def _register_singles():
    sys.path.insert(0, HERE)
    import biceps_parts
    free = iter([k for k in SPOTS if k.startswith("g")])
    lpr = iter(k for k in SPOTS if k.startswith("lpr"))
    for key, c in biceps_parts.SINGLES.items():
        spot = next(lpr) if c["source"].startswith("LP_Veh_") else next(free)
        r = c["ref"]
        CARS[key] = {"new_id": c["vehicle"], "display": r["display"], "spot": spot, "awd": r["awd"], "offroad": r.get("offroad", False), "engine_pos": r.get("engine_pos"),
                     "cost": int(round((r["curb"] * 8 + ENGINE_KG[r["engine"]] * 60) / 1000.0)) * 1000}
        PHYSICS[c["vehicle"]] = {"ref": r["ref"], "curb": r["curb"], "front": r["front"], "kit": key,
                                 "engine": r["engine"], "transmission": "302",
                                 "parts_kg": ENGINE_KG[r["engine"]] + 100 + 13 + 100}


COM_DROP_CM = -15     # a real car's centre of gravity sits lower than its collision hull's centroid


def physics_ops(new_id):
    """[injector op] pinning root mass + centre of mass, and the {slot: part} drivetrain."""
    p = PHYSICS[new_id]
    i = info(p["kit"]) if p["kit"] in CARS else info("Biceps")
    fx, rx = i["wheels"]["wheel_fl"][0], i["wheels"]["wheel_rl"][0]
    com_x = rx + p["front"] * (fx - rx)                       # where the real split puts the CoM
    hull_x = (i["body_min"][0] + i["body_max"][0]) / 2         # the collision centroid, roughly
    op = ["set-body-mass", "--export", "Body", "--mass", f"{p['curb'] - p['parts_kg']:g}",
          "--com", v(round(com_x - hull_x, 1), 0, COM_DROP_CM)]
    return op, {"Engine": p["engine"], "Transmission": p["transmission"]}


SPOTS = {"between": (227789.6, -183958.1), "front1": (228538.6, -184381.2),
         "front2": (228834.5, -185015.6), "front3": (229130.3, -185650.0)}
# More bays on the same platform, laid out the way the user described it (4 Nov 2026): cars face
# yaw -65; columns step 5 m sideways (+ away from the Stinger truck bay, - toward and past it), rows
# step 7 m forward. Right side: two columns + one bay; the Biceps and Exotic columns get a 5th row;
# the left, past the Stinger, takes a row of six. The old bike column stood in the street.
_B, _S, _F = (228242.8, -183746.8), (0.906308, 0.422618), (0.422618, -0.906308)
def _spot(col, row):
    return (round(_B[0] + col * _S[0] + row * 700 * _F[0], 1), round(_B[1] + col * _S[1] + row * 700 * _F[1], 1))
GRID = [(-500, 1), (-500, 2), (-500, 3), (-500, 4), (0, 4),
        (500, 0), (500, 1), (500, 2), (500, 3), (1000, 0), (1000, 1), (1000, 2), (1000, 3), (1500, 0),
        (-1500, 0), (-2000, 0), (-2500, 0), (-3000, 0), (-3500, 0), (-4000, 0)]
for _col, _row in GRID:
    SPOTS[f"g{_col}r{_row}"] = _spot(_col, _row)
# Low Poly Racing cars (user, 4 Nov 2026): the street the ZapBike stands in, running west-northwest
# (-S) from the platform. Row 3 is its right lane, row 4 the left lane; bays 3.5 m apart, alternating
# lanes, from just past the cars already on rows 3/4 (column -500).
for _i in range(120):
    SPOTS[f"lpr{_i}"] = _spot(-1000 - 350 * (_i // 2), 3 + _i % 2)
# Assetsville motorcycles (moto.py), all on vanilla Zero with Zero's slot names. Engines from the
# game's own bike parts by type; the Bobbers (one merged mesh) and the Cross (posed front wheel) wait.
MOTOS = {
    "Chopper":    ("Moto_Chopper_01", "C0140_Chopper", "Chopper", "Bike_I2_100HP", "Bike6Speed", 14000),
    "ChopperII":  ("Moto_Chopper_02", "C0141_ChopperII", "Chopper II", "Bike_I2_100HP", "Bike6Speed", 14000),
    "Cruiser":    ("Moto_Cruiser_01", "C0142_Cruiser", "Cruiser", "Bike_I2_100HP", "Bike6Speed", 15000),
    "CruiserII":  ("Moto_Cruiser_02", "C0143_CruiserII", "Cruiser II", "Bike_I2_100HP", "Bike6Speed", 15000),
    "Scooter":    ("Moto_Scooter", "C0144_Scooter", "Scooter", "Scooter_15HP", "Scooter2Speed", 3000),
    "Sportbike":  ("Moto_Sport_01", "C0145_Sportbike", "Sportbike", "Bike_I4_160HP", "Bike6SpeedSport", 22000),
    "SportbikeII": ("Moto_Sport_02", "C0146_SportbikeII", "Sportbike II", "Bike_I4_100HP", "Bike6SpeedSport", 17000),
}
BIKE = os.path.join(SCRATCH, "factory", "bike")


def moto_info(key):
    return json.load(open(os.path.join(BIKE, MOTOS[key][0], "info.json")))


def moto_job():
    out = []
    for key, (src, *_rest) in MOTOS.items():
        i = moto_info(key)
        bmin = i["body_min"]
        out.append({"car": key, "pack": "assetsville", "dest": f"/Game/DC/Vehicles/{key}", "body_name": f"SM_{key}_Body",
                    "body_fbx": os.path.join(BIKE, src, f"SM_{src}_Body.fbx"),
                    "sockets": {"SteeringWheel": (i["steering"]["pivot"], [i["steering"]["pitch"], 0, 0]),
                                "Exhaust_Right": ([bmin[0] + 8, 12, 40], [20, 175, 0])},
                    "parts": [], "extra": [{"fbx": os.path.join(BIKE, src, f"SM_{src}_Handlebar.fbx"), "name": f"SM_{key}_Handlebar",
                                            "sockets": {"Handle_L": (i["grip_l"], [0, 0, -90]), "Handle_R": (i["grip_r"], [0, 0, -90])}}]})
    return out


SEAT_POSE = {"Chopper": "BikeDriverUpright", "ChopperII": "BikeDriverUpright", "Cruiser": "BikeDriverUpright",
             "CruiserII": "BikeDriverUpright", "Scooter": "ScooterDriver"}


def moto_entries():
    hide = lambda e: ["set-component-props", "--export", e, "--bool", "bHiddenInGame=1,bVisible=0"]
    vec = lambda e, x, y, z: ["set-component-props", "--export", e, "--vec", f"RelativeLocation={x:g}:{y:g}:{z:g}"]
    zw = lambda w: round(34.3 + (w[2] - w[3] / 2), 1)          # Zero's hub height + the model's ground offset
    out = []
    for key, (src, new_id, display, engine, trans, cost) in MOTOS.items():
        i = moto_info(key); wf, wr = i["wheel_front"], i["wheel_rear"]; sx, sy, sz = i["seat"]
        ops = [["set-component-props", "--export", "Mesh", "--object", f"StaticMesh=/Game/DC/Vehicles/{key}/SM_{key}_Body"],
               ["set-component-props", "--export", "SteeringWheel", "--object", f"StaticMesh=/Game/DC/Vehicles/{key}/SM_{key}_Handlebar"],
               hide("FrontArmStaticMesh_GEN_VARIABLE"), hide("Suspension_GEN_VARIABLE"),
               hide("LeftSideMirror_GEN_VARIABLE"), hide("RightSideMirror_GEN_VARIABLE"),
               vec("Wheel0", wf[0], 0, zw(wf)), vec("Wheel1", wr[0], 0, zw(wr)),
               vec("DriverSeat_GEN_VARIABLE", round(sx - 8, 1), 0, round(sz - 12, 1)),
               # the rider's pose by bike type: Zero's sport lean put chopper and cruiser riders
               # too far forward (user, 5 Nov 2026)
               ["set-component-props", "--export", "DriverSeat_GEN_VARIABLE", "--enum", "SeatPositionType=" + SEAT_POSE.get(key, "BikeDriverSport")]]
        if i["lights"].get("HeadLight"):
            hx, hy, hz = i["lights"]["HeadLight"]
            ops += [vec("HeadLight_GEN_VARIABLE", hx, 8, hz), vec("HeadLight1_GEN_VARIABLE", hx, -8, hz)]
        out.append({"base": "Zero", "new_id": new_id, "display_name": display, "table": "/Game/DataAsset/Vehicles/Vehicles_ZapBikes",
                    "_": f"Assetsville motorcycle {src} (moto.py) on vanilla Zero",
                    "modifications": [{"type": "row_field", "field": "Cost", "value": cost},
                                      {"type": "ship_assets", "assets": [f"/Game/DC/Vehicles/{key}/SM_{key}_Body",
                                                                         f"/Game/DC/Vehicles/{key}/SM_{key}_Handlebar"]},
                                      {"type": "injector_ops", "ops": ops},
                                      {"type": "row_parts", "parts": {"Engine": engine, "Transmission": trans}, "remove": ["RearBumper"]}]})
    return out


ENGINE_KG = {"SmallBlock_90HP": 150, "SmallBlock_140HP": 200, "I4_150HP": 180, "SmallBlock_180HP": 220,
             "I6Sport_200HP": 215, "V6Sport_200HP": 215, "SmallBlock_240HP": 250, "SmallBlock_320HP": 280,
             "V6Sport_400HP": 310, "V12_400HP": 320, "I4_50HP": 110}
BAY_Z, BAY_YAW = -21929.7, -65.0

# Stinger values and the Biceps-tuned offsets (Unreal cm)
STINGER_TYRE_R = (30.46, 33.06)             # front, rear: Stinger radius at scale 0.72 / 0.78
WHEEL_MESH_R = 42.35                        # a wheel's radius at scale 1 (STINGER_TYRE_R / scale)
SEAT_FROM_CUSHION = (-4.2, -1.95)           # Stinger seat minus the Muscle driver cushion (x, z)
CAMERA_FROM_SEAT = (-10.0, 75.15)           # Stinger camera minus Stinger seat (x, z)
WHEEL_FROM_STEER = (3.55, -9.15)            # Biceps' tuned SteeringWheel socket minus the pack wheel (x, z)
DASHBOARD = "4:0:8"                         # Biceps' tuned DashboardMeshLocation


def frame_of(car):
    sys.path.insert(0, HERE)
    import biceps_parts
    return biceps_parts.CARS[car]["frame"]


def preset_of(car):
    import biceps_parts
    return biceps_parts.CARS[car]["presets"][0]


def info(car):
    i = json.load(open(os.path.join(KIT, f"{frame_of(car)}_{preset_of(car)}", "info.json")))
    # Simple models (Assetsville, Polygon City) carry no seat pieces and often no steering wheel:
    # place both from body proportions, fitted on Biceps (steering 59/102.5 vs its 52.5/103.1).
    bmin, bmax = i["body_min"], i["body_max"]
    H = bmax[2] - bmin[2]
    fx, rx = i["wheels"]["wheel_fl"][0], i["wheels"]["wheel_rl"][0]
    if not i.get("steering"):
        i["steering"] = {"centre": [round(fx - 0.36 * (fx - rx), 1), -46.0, round(bmin[2] + 0.64 * H, 1)], "tilt_deg": -20.0}
    pj = os.path.join(KIT, f"{frame_of(car)}_{preset_of(car)}", "popup", "popup.json")
    if os.path.exists(pj):     # pop-up headlights: the beams come from the raised lamps, not the bumper
        i["lights"] = {**i["lights"], **{k: v for k, v in json.load(open(pj)).items() if k.startswith("HeadLight") and v}}
        i["popup"] = True
    if not i.get("seat_driver"):
        sc = i["steering"]["centre"]
        i["seat_driver"] = [round(sc[0] - 38, 1), sc[1], round(bmin[2] + 0.265 * H, 1)]
    return i


def v(*a):
    return ":".join(f"{x:g}" for x in a)


# Stinger's springs on Biceps (1700 kg, 55% front), which the user signed off: the per-corner reference
STINGER_SPRING = {0: {"SpringK": 35000, "SpringBoundDamping": 500, "SpringReboundDamping": 4000},
                  1: {"SpringK": 20000, "SpringBoundDamping": 400, "SpringReboundDamping": 3000}}
REF_CORNER_KG = (1700 * 0.55 / 2, 1700 * 0.45 / 2)


def wheel_ops(i, phys=None):
    """Wheels at the model's own size, on springs for the car's own weight.

    Size: the visible wheel is a 1 m mesh, so scale = tyre diameter / 100 cm; the physics radius is
    42.35 cm x scale (Stinger 0.72/0.78 = STINGER_TYRE_R), so the wheel sits that high. Scaling the
    PHYSICS radius to the tyre drew every wheel 18% oversized (user, 5 Nov 2026).
    Springs: Stinger's rates scaled by corner load, so a 2.6 t SUV is not on its bump stops."""
    out = []
    def place(comp, x, y, z, d, w, axle):
        k = round(d / 100, 3)
        props = ["RelativeLocation=" + v(x, round(y, 1), round(z - d / 2 + WHEEL_MESH_R * k, 2)), "RelativeScale3D=" + v(k, k, k)]
        out.append(["set-component-props", "--export", comp, "--vec", ",".join(props)])
        if phys:
            corner = phys["curb"] * (phys["front"] if axle == 0 else 1 - phys["front"]) / 2
            r = corner / REF_CORNER_KG[axle]
            out.append(["set-component-props", "--export", comp, "--float",
                        ",".join(f"{n}={round(val * r)}" for n, val in STINGER_SPRING[axle].items())])
    for comp, key, sign, axle in (("Wheel0", "wheel_fl", 1, 0), ("Wheel1", "wheel_fl", -1, 0),
                                  ("Wheel2", "wheel_rl", 1, 1), ("Wheel3", "wheel_rl", -1, 1)):
        x, y, z, d, w = i["wheels"][key]
        place(comp, x, sign * (abs(y) + w / 2 - 3), z, d, w, axle)
    # a middle axle (the G63 6x6) becomes Wheel4.. as vanilla CheetahMk1 does it, a copy of the rear
    # wheel (made after the rear wheel is placed, so it inherits its scale and springs)
    _, _, _, d, w = i["wheels"]["wheel_rl"]
    for n, (x, y, z) in enumerate(sorted(i.get("wheels_extra", []), key=lambda c: (-c[0], -c[1])), 4):
        out.append(["vehicle-add-wheel", "--from", "Wheel2" if y > 0 else "Wheel3", "--name", f"Wheel{n}", "--slot", str(n),
                    "--loc", ",".join(f"{c:g}" for c in (x, round((abs(y) + w / 2 - 3) * (1 if y > 0 else -1), 1),
                                                         round(z - d / 2 + WHEEL_MESH_R * d / 100, 2)))])
    return out


def engine_ops(i, pos):
    """The engine component where the real car has its engine, so crash damage and engine sound come from
    there (user, 5 Nov 2026): over the front axle, ahead of the rear axle (mid), or behind it (rear)."""
    fx, rx = i["wheels"]["wheel_fl"][0], i["wheels"]["wheel_rl"][0]
    z = i["wheels"]["wheel_fl"][2] + 25
    x = {"front": fx - 15, "mid": rx + 0.3 * (fx - rx), "rear": rx - 25}[pos or "front"]
    return [["set-component-props", "--export", "Engine", "--vec", "RelativeLocation=" + v(round(x, 1), 0, round(z, 1))]]


def extra_wheel_parts(i, offroad=False):
    """Tyre/rim/brake row parts: the extra wheels' slots (Wheel4.. on a 6x6) get the rear axle's, and an
    off-roader (refs "offroad") runs the game's Offroad tyre on OffroadWheel_01 rims on every wheel."""
    n = 4 + len(i.get("wheels_extra", []))
    tyre, rim = ("Offroad", "OffroadWheel_01") if offroad else ("BasicTire_45", "StingerR")
    return {f"{s}{k}": p for k in range(0 if offroad else 4, n)
            for s, p in (("Tire", tyre), ("Wheel", rim), ("BrakePad", "BrakePad_Small_01"))}


def light_ops(i):
    L = i["lights"]
    pairs = [("HeadLight_Left_GEN_VARIABLE", "HeadLight_Left"), ("HeadLight_Right_GEN_VARIABLE", "HeadLight_Right"),
             ("BlinkerLight_01_GEN_VARIABLE", "Blinker_FrontRight"), ("BlinkerLight_02_GEN_VARIABLE", "Blinker_FrontLeft"),
             ("TaliLight_01_GEN_VARIABLE", "Tail_Left"), ("TaliLight_02_GEN_VARIABLE", "Tail_Right")]
    ops = [["set-component-props", "--export", comp, "--vec", "RelativeLocation=" + v(*L[key])]
           for comp, key in pairs if L.get(key)]   # a lamp the pack lacks keeps the base position
    # European cars have their own amber blinkers, so the tail lamps stop flashing (Stinger's tail
    # lights are TailLightType Left/RightBlinker: the American way, kept where the pack has no amber)
    c = i.get("counts", {})
    if min(c.get("LeftSignalLight", 0), c.get("RightSignalLight", 0)) >= 8:
        ops += [["set-component-props", "--export", t, "--enum", "TailLightType=None"]
                for t in ("TaliLight_01_GEN_VARIABLE", "TaliLight_02_GEN_VARIABLE")]
    return ops


def mirror_ops(i):
    """The game's mirrors reflect, the pack's do not: kit.py cut the pack's and recorded where they
    were. A side mirror the pack keeps on its door stays hidden (no double housing)."""
    out = []
    if i.get("mirror_room"):
        out.append(["set-component-props", "--export", "RoomMirror_GEN_VARIABLE", "--vec", "RelativeLocation=" + v(*i["mirror_room"])])
    for side, comp in (("l", "LeftSideMirror_GEN_VARIABLE"), ("r", "RightSideMirror_GEN_VARIABLE")):
        if i.get("mirror_" + side):
            out += [["set-component-props", "--export", comp, "--bool", "bHiddenInGame=0,bVisible=1"],
                    ["set-component-props", "--export", comp, "--vec", "RelativeLocation=" + v(*i["mirror_" + side])]]
        else:
            out.append(["set-component-props", "--export", comp, "--bool", "bHiddenInGame=1,bVisible=0"])
    return out


def cockpit_ops(i):
    sx, sy, sz = i["seat_driver"]
    seat = (round(sx + SEAT_FROM_CUSHION[0], 1), sy, round(sz + SEAT_FROM_CUSHION[1], 1))
    cam = (round(seat[0] + CAMERA_FROM_SEAT[0], 1), sy, round(seat[2] + CAMERA_FROM_SEAT[1], 1))
    front_x = i["wheels"]["wheel_fl"][0]
    return [["set-component-props", "--export", "DriverSeat_GEN_VARIABLE", "--vec", "RelativeLocation=" + v(*seat)],
            ["set-component-props", "--export", "PassengerSeat1_GEN_VARIABLE", "--vec",
             "RelativeLocation=" + v(seat[0], -sy, seat[2])],
            ["set-component-props", "--export", "CockpitCamera", "--vec", "RelativeLocation=" + v(*cam)],
            ["set-component-props", "--export", "Engine", "--vec", "RelativeLocation=" + v(round(front_x + 33, 1), 0, 70)],
            ["set-component-props", "--export", "SteeringWheel", "--vec", "RelativeLocation=0:0:0"],
            ["set-component-props", "--export", "Dashboard", "--vec", "DashboardMeshLocation=" + DASHBOARD]]


def sockets(i):
    sc, tilt = i["steering"]["centre"], i["steering"]["tilt_deg"]
    out = {"SteeringWheel": ([round(sc[0] + WHEEL_FROM_STEER[0], 1), sc[1], round(sc[2] + WHEEL_FROM_STEER[1], 1)], [tilt, 0, 0])}
    for k, loc in i["sockets"].items():
        out[k] = (loc, [0, 0, 0])
    bmin, bmax = i["body_min"], i["body_max"]
    half_w = (bmax[1] - bmin[1]) / 2
    out["Exhaust_Left"] = ([bmin[0] + 4, -round(half_w * 0.45, 1), bmin[2] + 14], [0, 180, 0])
    out["Exhaust_Right"] = ([bmin[0] + 4, round(half_w * 0.45, 1), bmin[2] + 14], [0, 180, 0])
    return out


POPUP_JOB = os.path.join(os.path.dirname(JOB), "popup_job.json")
TRIM_LPR = "/Game/Cars/Materials/Body/MI_TexturedBody_Sketchfab_LPCars"


def popup_assets(car):
    """What a pop-up car ships: the rig's skeletal mesh, skeleton and LightOn animation (factory popup.py)."""
    d = f"/Game/DC/Vehicles/{car}/Popup"
    return [f"{d}/SK_{car}_Popup", f"{d}/SK_{car}_Popup_Skeleton", f"{d}/SK_{car}_Popup_Anim"]


def popup_job():
    job = []
    for car in CARS:
        k = os.path.join(KIT, f"{frame_of(car)}_{preset_of(car)}", "popup")
        f = os.path.join(k, f"SK_{frame_of(car)}_{preset_of(car)}_Popup.fbx")
        if os.path.exists(f):
            job.append({"car": car, "fbx": f, "trim": f"/Game/DC/Vehicles/{car}/MI_{car}_Livery" if car in LIVERY else TRIM_LPR})
    json.dump(job, open(POPUP_JOB, "w"), indent=1)
    print("  popup job:", [j["car"] for j in job])


def ue_job():
    import biceps_parts
    job = []
    for car in CARS:
        fr = frame_of(car)
        parts = [(biceps_parts.part_file(car, s, p), f"SM_{car}_{s}_{p}") for s, p in biceps_parts.kit_parts(car=car)]
        job.append({"car": car, "pack": info(car)["pack"], "dest": f"/Game/DC/Vehicles/{car}", "body_name": f"SM_{car}_Body",
                    "body_fbx": os.path.join(KIT, f"{fr}_{preset_of(car)}", f"SM_{fr}_{preset_of(car)}_Body.fbx"),
                    "sockets": sockets(info(car)), "parts": parts})
    job += moto_job()
    json.dump(job, open(JOB, "w"), indent=1)
    print("  job:", JOB, [(j["car"], len(j["parts"])) for j in job])


def apply_physics(cfg):
    for e in cfg["vehicles"]:
        if e["new_id"] not in PHYSICS: continue
        op, drive = physics_ops(e["new_id"])
        for m in e["modifications"]:
            if m["type"] == "injector_ops":
                m["ops"] = [o for o in m["ops"] if o[0] != "set-body-mass"] + [op]
            if m["type"] == "row_parts":
                m["parts"] = {**m["parts"], **drive}
        e["_physics"] = PHYSICS[e["new_id"]]["ref"]


# livery cars (factory import_livery.py): their own texture + MI on the Trim slot, shipped with the car
_LJ = os.path.join(os.path.dirname(KIT), "livery_job.json")
LIVERY = {c["car"] for c in json.load(open(_LJ))} if os.path.exists(_LJ) else set()


def vehicles():
    import biceps_parts
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    old = {e["new_id"]: e for e in cfg["vehicles"]}
    keep = [e for e in cfg["vehicles"] if e["new_id"] not in {c["new_id"] for c in CARS.values()} | biceps_parts.DROPPED]
    table = keep[0]["table"]
    for car, c in CARS.items():
        i = info(car)
        parts = biceps_parts.kit_parts(car=car)
        have = {f"{s}_{p}" for s, p in parts}
        lpr = biceps_parts.lpr_info(car)
        ops = (c.get("pre_ops", [])
               + [["set-component-props", "--export", "Mesh", "--object", f"StaticMesh=/Game/DC/Vehicles/{car}/SM_{car}_Body"]]
               + wheel_ops(i, PHYSICS.get(c["new_id"])) + light_ops(i)
               + (engine_ops(i, c.get("engine_pos")) if c.get("base", "2") == "2" else [])
               + [["set-component-props", "--export", e, "--bool", "bHiddenInGame=1,bVisible=0"]
                  for e in ("LeftDoor_GEN_VARIABLE", "RightDoor_GEN_VARIABLE") if c.get("base", "2") == "2"]   # Zydro has no doors: the op failed and the police car shipped as a vanilla Zydro
               + mirror_ops(i)
               + cockpit_ops(i)
               + [o for m in old.get(c["new_id"], {}).get("modifications", []) if m["type"] == "injector_ops"
                  for o in m["ops"] if o[0] == "add-color-slot" and o[o.index("--from") + 1] == "Body_0"]
               + ([["add-color-slot", "--from", c["slot_from"], "--add", c["colors"]]] if c.get("colors") else [])
               + [["add-color-slot", "--from", c.get("slot_from", "Body_1"), "--add",
                   "Seat_01=Front Seats=45:45:48;Seat_02=Rear Seats=45:45:48;Dashboard_01=Dashboard=40:40:42;"
                   "WindowTrim_01=Window Trim=180:182:186"]])
        keep.append({
            "base": c.get("base", "2"), "new_id": c["new_id"], "display_name": c["display"], "table": table,
            "_": f"kit car {car} (kit_cars.py): {frame_of(car)}, placement from the kit",
            "modifications": [
                {"type": "row_field", "field": "Cost", "value": c["cost"]},
                *([{"type": "all_wheel_drive"}] if c.get("awd") else []),
                {"type": "ship_assets", "assets": [f"/Game/DC/Vehicles/{car}/SM_{car}_Body"]
                    + ([f"/Game/DC/Vehicles/{car}/MI_{car}_Livery", f"/Game/DC/Vehicles/{car}/T_{car}_Livery"] if car in LIVERY else [])
                    + [f"/Game/DC/Vehicles/{car}/Parts/SM_{car}_{s}_{p}" for s, p in parts]
                    + (popup_assets(car) if i.get("popup") else [])},
                {"type": "injector_ops", "ops": ops},
                {"type": "row_parts", "parts": ({s_: f"{car}_{s_}_P1" for s_, p in parts if p == "P1"} if lpr["labels"] else
                                                {d.rsplit("_", 1)[0]: f"{car}_{d.rsplit('_', 1)[0]}_P{int(preset_of(car))}"
                                                 for d in biceps_parts.DEFAULTS + ["Bullbar_P1"]
                                                 if f"{d.rsplit('_', 1)[0]}_P{int(preset_of(car))}" in have}) | extra_wheel_parts(i, c.get("offroad", False))
                                  | ({"Headlight": f"{car}_Headlight_P1"} if i.get("popup") else {}) | c.get("row", {})},
                # a kit or bumper that is a real share of the car (its whole front end) can be swapped, never removed
                *([{"type": "part_slots", "add": must}] if (must := sorted({t.rsplit("_", 1)[0] for t, a in lpr["areas"].items()
                    if t.endswith("_P1") and a > 0.05 and not t.startswith(("Bonnet", "RearWing"))})) else []),
            ]})
    keep = [e for e in keep if e["new_id"] not in {m[1] for m in MOTOS.values()}] + moto_entries()
    cfg["vehicles"] = keep
    apply_physics(cfg)
    json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), indent=2)
    print("  vehicles:", [e["new_id"] for e in keep])


def bays():
    bays_cfg = {"dealerships": {
        "biceps": [{"vehicle_path": "/Game/Cars/Models/Muscle_01/V519CD4", "vehicle_key": "C0100_Biceps",
                    "X": 228242.8, "Y": -183746.8, "Z": BAY_Z, "Pitch": 0.0, "Yaw": BAY_YAW, "Roll": 0.0}],
        "control": [{"vehicle_path": "/Game/Cars/Models/Muscle_01/Stinger", "vehicle_key": "Stinger",
                     "X": 227336.5, "Y": -184169.4, "Z": BAY_Z, "Pitch": 0.0, "Yaw": BAY_YAW, "Roll": 0.0}]}}
    sys.path.insert(0, HERE)
    from build_vehicles import same_length_name
    extra = {"ZapBike": {"new_id": "C0110_ZapBike", "spot": "front3", "base": "Zero", "folder": "Bike/Zero"}}
    used = {c["spot"] for c in CARS.values()}
    for (key, m), spot in zip(MOTOS.items(), [k for k in SPOTS if k.startswith("g") and k not in used]):
        extra[key] = {"new_id": m[1], "spot": spot, "base": "Zero", "folder": "Bike/Zero"}
    for car, c in {**CARS, **extra}.items():
        if c["spot"] is None: continue          # built and sold, no bay yet
        x, y = SPOTS[c["spot"]]
        base_cls = {"2": "Stinger", "Zydro_Police": "Zydro_Police"}.get(c.get("base", "2"), c.get("base", "Stinger"))
        cls = same_length_name(c["new_id"], base_cls)
        bays_cfg["dealerships"][car.lower()] = [{"vehicle_path": f"/Game/Cars/Models/{c.get('folder', 'Muscle_01')}/{cls}",
                                                  "vehicle_key": c["new_id"], "X": x, "Y": y, "Z": BAY_Z,
                                                  "Pitch": 0.0, "Yaw": BAY_YAW, "Roll": 0.0}]
    json.dump(bays_cfg, open(BAYS, "w"), indent=1)
    import mt_paths
    r = subprocess.run([os.path.join(HERE, "MTBPInjector", "bin", "Release", "net8.0", "MTBPInjector.exe"), "inject-static",
                        "--main", os.path.join(HERE, "vanilla_extract", CELL), "--output", os.path.join(HERE, "Biceps_P", CELL),
                        "--config", BAYS, "--mappings", str(mt_paths.MAPPINGS)], capture_output=True, text=True)
    print("  bays:", [l for l in r.stdout.splitlines() if "Injected" in l or "Done" in l], r.stderr[-300:])


def demo():
    # Biceps' hand-tuned numbers from its own kit data
    i = {"wheels": {"wheel_fl": [177.2, -86.7, 35.0, 71.4, 28.6], "wheel_rl": [-150.9, -86.7, 35.0, 71.4, 28.6]}}
    w = wheel_ops(i)
    # 71.4 cm tyres: visible wheel 0.714 (1 m mesh), physics radius 30.24 cm on the ground
    assert w[0][-1] == "RelativeLocation=177.2:98:29.54,RelativeScale3D=0.714:0.714:0.714", w[0]
    assert w[2][-1] == "RelativeLocation=-150.9:98:29.54,RelativeScale3D=0.714:0.714:0.714", w[2]
    e = wheel_ops({**i, "wheels_extra": [[-60.0, -86.7, 35.0], [-60.0, 86.7, 35.0]]})
    assert [o[4] for o in e[4:]] == ["Wheel4", "Wheel5"] and e[4][-1] == "-60,98,29.54" and e[5][2] == "Wheel3", e[4:]
    # springs follow the corner load: Biceps' own weight gives Stinger's rates, a 2.6 t SUV ~1.5x
    sp = wheel_ops(i, {"curb": 1700, "front": 0.55})
    assert sp[1][-1] == "SpringK=35000,SpringBoundDamping=500,SpringReboundDamping=4000", sp[1]
    assert engine_ops(i, "mid")[0][-1] == "RelativeLocation=-52.5:0:60" and engine_ops(i, None)[0][-1] == "RelativeLocation=162.2:0:60"
    big = wheel_ops(i, {"curb": 2600, "front": 0.52})[1][-1]
    assert big.startswith("SpringK=50610"), big
    assert abs(14.2 + SEAT_FROM_CUSHION[0] - 10) < 0.01 and abs(51.8 + SEAT_FROM_CUSHION[1] - 49.85) < 0.01
    print("ok")


_register_singles()

if __name__ == "__main__":
    {"ue-job": ue_job, "popup-job": popup_job, "vehicles": vehicles, "bays": bays, "demo": demo}[sys.argv[1]]()
