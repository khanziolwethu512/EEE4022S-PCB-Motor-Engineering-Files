"""
REV1_ICEPAK_BUILD.py  -  v1 (2026-10-08)
========================================
Rev1 thermal build in AEDT Icepak, same method and housing as REV0_ICEPAK_BUILD.py
(build + Validation Check + frozen copy, no solve).

Usage:   python REV1_ICEPAK_BUILD.py Rev1D      (or Rev1S)

Layouts (mm, S1 bottom placed 20 mm from the stator-side plate, as Rev0):
  Rev1D  S1 | 1 mm | R1: 16 PM | 2 mm shared steel | 16 PM | 1 mm | S2 | 1 mm | R2: 16 PM | 2 mm steel
         (axial levels identical to REV1D_FINAL_G100_T20, shifted by +24.591 mm)
  Rev1S  S1 | 1 mm | R1: 16 PM | 2 mm steel | 1 mm [Assump clearance] | S2 | 1 mm | R2: 16 PM | 2 mm steel
v2: each stator = ONE merged 5-board body + ONE winding annulus carrying the stator's
copper loss (P_S1, P_S2); per-board temperatures from point monitors T_S1B1..T_S2B5
(B1 = board nearest R1). The build generates the mesh and refuses to freeze if any object
is left without mesh. Rotors are still (no stirring), as in Rev0.
"""
import os, sys, json, math, time, shutil

# ------------------------------------------------------------------ USER SETTINGS
def _pick_work_dir():
    # Local run folder, never OneDrive (sync locks corrupt AEDT projects).
    # Uses D:/New folder on PCs that have it, otherwise C:/Users/Student/Rev0_work.
    if os.path.isdir(r"D:\New folder"):
        return r"D:\New folder\Motor run\thermal"
    return os.path.join(os.path.expanduser("~"), "Rev0_work", "thermal")
WORK_DIR      = _pick_work_dir()
OUT_DIR       = r"C:\Users\Student\OneDrive - University of Cape Town\EEE4022S Ansys files\Thermal\results"  # copies of logs/CSV/frozen build
DESIGN = (sys.argv[1] if len(sys.argv) > 1 else "Rev1D").replace("-", "")
if DESIGN not in ("Rev1D", "Rev1S", "Rev2S", "RSR"):
    raise SystemExit("Usage: python REV1_ICEPAK_BUILD.py Rev1D|Rev1S|Rev2S|RSR")
PROJECT_NAME  = DESIGN.upper() + "_ICEPAK_BUILD_V2"
FROZEN_NAME   = DESIGN.upper() + "_ICEPAK_FROZEN"
DESIGN_NAME   = DESIGN + "_thermal"
AEDT_VERSION  = "2025.2"
NON_GRAPHICAL = False

T_HOOD   = 30.0      # C   [Assump] measure the air at the motor during tests
V_FAN    = 1.0       # m/s [Assump] approach velocity from the hood fans (0 = off)
P_BOARD0 = 0.42      # W per board initial guess (1 A_pk at ~25 C); run script iterates
RADIATION = False    # S2S radiation off for v1 (lumped model shows ~25 % of external h)

# geometry (mm)
APOTHEM, BORE_D, T_BOARD, N_BOARDS = 46.5, 25.0, 1.02032, 5
WIN_R_IN, WIN_R_OUT = 16.0, 40.0
ROTOR_OD, ROTOR_BORE, T_STEEL, GAP = 86.0, 19.0, 2.0, 1.0
MAG_L, MAG_W, MAG_H, MAG_RC, N_MAG = 20.0, 6.0, 2.0, 28.0, 16
SHAFT_D, SHAFT_OUT = 19.0, 20.0
SHELL_ID, SHELL_T, L_IN = 120.0, 3.0, 60.0
PLATE_W, PLATE_T, BEARING_OD = 140.0, 6.0, 30.0
BASE_T, BASE_W = 6.0, 160.0
ROD_D, ROD_PCD, N_RODS = 3.0, 90.0, 6
Z_STACK_BOTTOM = 20.0            # board 5 bottom, from stator-side plate inner face
PAD = {"+X": 100, "-X": 100, "+Y": 100, "-Y": 0, "+Z": 150, "-Z": 150}   # mm

# effective materials
CU_FRAC = 6 * 0.035 * 0.5 / T_BOARD
K_XY = CU_FRAC * 385 + (1 - CU_FRAC) * 0.8
K_Z = 1 / (CU_FRAC / 385 + (1 - CU_FRAC) / 0.30)
MATERIALS = {   # name: (k (scalar or [kx,ky,kz]), rho, cp)
    "PCB_eff":       ([K_XY, K_XY, K_Z], 2600.0, 900.0),
    "Steel1010_th":  (52.0, 7870.0, 460.0),
    "NdFeB_th":      (9.0, 7500.0, 420.0),
    "Acrylic_th":    (0.19, 1190.0, 1470.0),
    "Al6061_th":     (167.0, 2700.0, 900.0),
    "Bearing_eff":   (3.6, 7800.0, 460.0),
}
# ------------------------------------------------------------------------------

LOG = os.path.join(WORK_DIR, DESIGN.lower() + "_icepak_build_log.txt")
def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line)
    with open(LOG, "a") as f: f.write(line + "\n")

def copy_out(paths):
    """Back up small outputs to OneDrive. AEDT never runs inside OneDrive (sync locks)."""
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        for p in paths:
            if os.path.isfile(p): shutil.copy2(p, OUT_DIR)
    except Exception as e:
        print("WARN copy to OneDrive failed: %r" % e)

def try_calls(label, *fns):
    """PyAEDT renamed many arguments between releases; try each form in turn."""
    err = None
    for fn in fns:
        try:
            r = fn()
            if r is False or r is None:
                err = "returned %r" % r; continue
            return r
        except Exception as e:
            err = repr(e)
    raise RuntimeError("%s failed in every form: %s" % (label, err))

def main():
    os.makedirs(WORK_DIR, exist_ok=True)
    print("Work folder: " + WORK_DIR)
    proj = os.path.join(WORK_DIR, PROJECT_NAME + ".aedt")
    if os.path.exists(proj):
        raise SystemExit("Project exists, refusing to overwrite (use a new PROJECT_NAME): " + proj)
    try:
        from ansys.aedt.core import Icepak
    except ImportError:
        from pyaedt import Icepak
    log("%s Icepak build v1 | k_xy=%.1f k_z=%.3f W/mK" % (DESIGN, K_XY, K_Z))
    ipk = try_calls("open Icepak",
        lambda: Icepak(project=proj, design=DESIGN_NAME, solution_type="SteadyState",
                       version=AEDT_VERSION, non_graphical=NON_GRAPHICAL, new_desktop=True),
        lambda: Icepak(projectname=proj, designname=DESIGN_NAME, solution_type="SteadyState",
                       specified_version=AEDT_VERSION, non_graphical=NON_GRAPHICAL, new_desktop_session=False))
    ipk.modeler.model_units = "mm"
    M = ipk.modeler

    # ---- materials
    for name, (k, rho, cp) in MATERIALS.items():
        m = ipk.materials.add_material(name)
        m.thermal_conductivity = [str(v) for v in k] if isinstance(k, list) else str(k)
        m.mass_density = str(rho)
        m.specific_heat = str(cp)
        try: m.thermal_material_type = "Solid"
        except Exception: pass
    log("materials created")

    # ---- layout
    S = N_BOARDS * T_BOARD
    z = Z_STACK_BOTTOM
    stacks, rotors = [], []                  # stacks: (name, z_bottom, B1_on_top)
    if DESIGN == "RSR":                     # v4 (23 Oct): R1-S1-R2, one stator between two rotors (design study)
        zr = Z_STACK_BOTTOM - GAP - MAG_H     # lower rotor: steel below, magnets facing the stator 1 mm below board 5
        if zr - T_STEEL < 1.0:
            raise SystemExit("RSR: lower rotor does not fit above the stator-side plate")
        rotors.append([("steel", zr - T_STEEL, "R1Steel"), ("mag", zr, "R1")])
        stacks.append(("S1", z, True)); z += S + GAP
        rotors.append([("mag", z, "R2"), ("steel", z + MAG_H, "R2Steel")])
    else:
        stacks.append(("S1", z, True)); z += S + GAP
    if DESIGN == "RSR":
        pass
    elif DESIGN == "Rev1D":
        rotors.append([("mag", z, "R1A"), ("steel", z + MAG_H, "R1Plate"), ("mag", z + MAG_H + T_STEEL, "R1B")])
        z += 2 * MAG_H + T_STEEL + GAP
    else:
        rotors.append([("mag", z, "R1A"), ("steel", z + MAG_H, "R1Steel")])
        z += MAG_H + T_STEEL + GAP          # [Assump] 1 mm clearance from R1's bare steel to S2
    if DESIGN == "Rev2S":                   # v3 (21 Oct): S1-R1-S2-R2-S3-R3, identical single-sided stages
        stacks.append(("S2", z, False)); z += S + GAP
        rotors.append([("mag", z, "R2"), ("steel", z + MAG_H, "R2Steel")])
        z += MAG_H + T_STEEL + GAP          # [Assump] 1 mm clearance from R2's bare steel to S3
        stacks.append(("S3", z, False)); z += S + GAP
        rotors.append([("mag", z, "R3"), ("steel", z + MAG_H, "R3Steel")])
    elif DESIGN != "RSR":
        stacks.append(("S2", z, False)); z += S + GAP
        rotors.append([("mag", z, "R2"), ("steel", z + MAG_H, "R2Steel")])
    z_end = z + MAG_H + T_STEEL
    if z_end > L_IN - 5:
        raise SystemExit("layout does not fit the housing: top at %.2f mm" % z_end)
    log("%s layout: %s, top of the last rotor steel %.3f mm"
        % (DESIGN, ", ".join("%s %.3f" % (n, zb) for n, zb, _ in stacks), z_end))

    # ---- design variables (the run script edits these)
    ipk["T_hood"] = "%gcel" % T_HOOD
    ipk["V_fan"] = "%gm_per_sec" % V_FAN
    # v2: each STATOR is one winding body + one board body (5 boards merged, same
    # anisotropic PCB_eff). With 10 thin stacked boards, the Icepak mesher dropped one
    # board's winding whatever the mesh settings. Per-board temperatures come from the
    # point monitors T_S1B1..T_S2B5 (centre radius, mid-thickness of each board).
    units, board_mon = [], []                # units: (label, z0, height)
    for sname, zb, b1_top in stacks:
        units.append((sname, zb, N_BOARDS * T_BOARD))
        for k in range(1, N_BOARDS + 1):
            z0 = zb + (N_BOARDS - k) * T_BOARD if b1_top else zb + (k - 1) * T_BOARD
            board_mon.append(("%sB%d" % (sname, k), z0))
    for lab, _, _ in units:
        ipk["P_" + lab] = "%gW" % (N_BOARDS * P_BOARD0)

    # ---- stators
    R_vertex = APOTHEM / math.cos(math.pi / 12)
    rod_ang = [math.radians(60 * i) for i in range(N_RODS)]   # [Assump] hole angles
    win_objs = []
    for lab, z0, h in units:
        pts = [[R_vertex * math.cos(math.pi / 6 * i), R_vertex * math.sin(math.pi / 6 * i), z0]
               for i in range(12)]
        pts.append(pts[0])
        poly = M.create_polyline(pts, cover_surface=True, close_surface=True, name="Board_" + lab)
        M.sweep_along_vector(poly, [0, 0, h])
        win = M.create_cylinder("Z", [0, 0, z0], WIN_R_OUT, h, name="Win_" + lab)
        cut_in = M.create_cylinder("Z", [0, 0, z0], WIN_R_IN, h, name="WinIn_" + lab)
        M.subtract(win, [cut_in], keep_originals=False)
        tools = [M.create_cylinder("Z", [0, 0, z0], BORE_D / 2, h, name="Bore_" + lab)]
        for i, a in enumerate(rod_ang):
            tools.append(M.create_cylinder("Z", [ROD_PCD / 2 * math.cos(a), ROD_PCD / 2 * math.sin(a), z0],
                                           ROD_D / 2, h, name="BH_%s_%d" % (lab, i)))
        M.subtract(poly, tools, keep_originals=False)
        M.subtract(poly, [win], keep_originals=True)
        for o in (poly, win): o.material_name = "PCB_eff"
        win_objs.append(win)
    log("%d stators built (5 boards each, merged)" % len(units))

    # ---- rotors (still)
    mag_layers, steel_names, mag_mon = {}, [], []
    for parts in rotors:
        for kind, z0, nm in parts:
            if kind == "steel":
                st = M.create_cylinder("Z", [0, 0, z0], ROTOR_OD / 2, T_STEEL, name=nm)
                sb = M.create_cylinder("Z", [0, 0, z0], ROTOR_BORE / 2, T_STEEL, name=nm + "_bore")
                M.subtract(st, [sb], keep_originals=False)
                st.material_name = "Steel1010_th"; steel_names.append(nm)
            else:
                names = []
                for i in range(N_MAG):
                    m = M.create_box([MAG_RC - MAG_L / 2, -MAG_W / 2, z0], [MAG_L, MAG_W, MAG_H],
                                     name="%s_Mag%02d" % (nm, i))
                    M.rotate(m, "Z", 360.0 / N_MAG * i)
                    m.material_name = "NdFeB_th"; names.append(m.name)
                mag_layers[nm] = names
                mag_mon.append((nm, z0 + MAG_H / 2))
    log("rotors built: %s" % ", ".join(list(mag_layers) + steel_names))

    # ---- shaft, plates, bearings, shell, rods, base
    shaft = M.create_cylinder("Z", [0, 0, -PLATE_T - SHAFT_OUT], SHAFT_D / 2,
                              L_IN + 2 * PLATE_T + 2 * SHAFT_OUT, name="Shaft")
    shaft.material_name = "Steel1010_th"
    for nm, z0 in (("PlateS", -PLATE_T), ("PlateR", L_IN)):
        pl = M.create_box([-PLATE_W / 2, -PLATE_W / 2, z0], [PLATE_W, PLATE_W, PLATE_T], name=nm)
        hole = M.create_cylinder("Z", [0, 0, z0], BEARING_OD / 2, PLATE_T, name=nm + "_hole")
        M.subtract(pl, [hole], keep_originals=False)
        pl.material_name = "Al6061_th"
        br = M.create_cylinder("Z", [0, 0, z0], BEARING_OD / 2, PLATE_T, name="Bearing" + nm[-1])
        bi = M.create_cylinder("Z", [0, 0, z0], SHAFT_D / 2, PLATE_T, name="BearingIn" + nm[-1])
        M.subtract(br, [bi], keep_originals=False)
        br.material_name = "Bearing_eff"
    shell = M.create_cylinder("Z", [0, 0, 0], SHELL_ID / 2 + SHELL_T, L_IN, name="Shell")
    si = M.create_cylinder("Z", [0, 0, 0], SHELL_ID / 2, L_IN, name="ShellIn")
    M.subtract(shell, [si], keep_originals=False)
    shell.material_name = "Acrylic_th"
    for i, a in enumerate(rod_ang):
        r = M.create_cylinder("Z", [ROD_PCD / 2 * math.cos(a), ROD_PCD / 2 * math.sin(a), 0],
                              ROD_D / 2, L_IN, name="Rod%d" % i)
        r.material_name = "Steel1010_th"
    # rods pass through the boards: remove the board-hole overlap already cut above
    base = M.create_box([-BASE_W / 2, -PLATE_W / 2 - BASE_T, -PLATE_T - 20],
                        [BASE_W, BASE_T, L_IN + 2 * PLATE_T + 40], name="BasePlate")
    base.material_name = "Al6061_th"
    log("housing built")

    # ---- region (hood) and boundaries
    # Icepak designs come with a default "Region" (percentage padding); replace it
    # with the absolute-padding hood region.
    if "Region" in M.object_names:
        M.delete("Region")
        log("default Icepak region deleted")
    reg = try_calls("region",
        lambda: M.create_air_region(x_pos=PAD["+X"], y_pos=PAD["+Y"], z_pos=PAD["+Z"],
                                    x_neg=PAD["-X"], y_neg=PAD["-Y"], z_neg=PAD["-Z"], is_percentage=False),
        lambda: M.create_region([PAD["+X"], PAD["+Y"], PAD["+Z"], PAD["-X"], PAD["-Y"], PAD["-Z"]], False))
    faces = {}
    for f in reg.faces:
        c = f.center
        faces[(round(c[0], 3), round(c[1], 3), round(c[2], 3))] = f.id
    def face_at(axis, sign):
        i = "XYZ".index(axis)
        ids = sorted(faces.items(), key=lambda kv: kv[0][i])
        return (ids[-1] if sign > 0 else ids[0])[1]
    inlet = face_at("Z", -1)
    outs = [face_at("Z", +1), face_at("X", +1), face_at("X", -1), face_at("Y", +1)]
    try_calls("fan inlet",
        lambda: ipk.assign_free_opening(assignment=inlet, boundary_name="FanInlet",
                    temperature="T_hood", flow_type="Velocity",
                    velocity=["0m_per_sec", "0m_per_sec", "V_fan"]),
        lambda: ipk.assign_velocity_free_opening(assignment=inlet, boundary_name="FanInlet",
                    temperature="T_hood", velocity=["0m_per_sec", "0m_per_sec", "V_fan"]))
    try_calls("pressure openings",
        lambda: ipk.assign_free_opening(assignment=outs, boundary_name="HoodOpen",
                    temperature="T_hood", flow_type="Pressure"),
        lambda: ipk.assign_pressure_free_opening(assignment=outs, boundary_name="HoodOpen",
                    temperature="T_hood"))
    log("region + openings assigned (inlet face %s)" % inlet)

    # ---- heat sources: copper loss in each winding annulus
    for (lab, _, _), w in zip(units, win_objs):
        try_calls("power " + w.name,
            lambda w=w, lab=lab: ipk.assign_solid_block(w.name, "P_" + lab, boundary_name="Loss_" + lab),
            lambda w=w, lab=lab: ipk.assign_solid_block(object_name=w.name, power_assignment="P_" + lab,
                                                         boundary_name="Loss_" + lab))
    log("losses assigned to %d windings" % len(win_objs))

    # ---- global settings, gravity, mesh
    # gravity_dir: 0/1/2 = -X/-Y/-Z in PyAEDT 1.8 (AEDT < 2027.1); 1 = gravity along -Y
    try_calls("icepak settings",
        lambda: ipk.edit_design_settings(gravity_dir=1, ambient_temperature=T_HOOD, default_fluid="air"),
        lambda: ipk.apply_icepak_settings(ambienttemp=T_HOOD, gravityDir=1, perform_minimal_val=True))
    try:
        mr = ipk.mesh.global_mesh_region
        mr.manual_settings = True
        mr.settings["MaxElementSizeX"] = "8mm"; mr.settings["MaxElementSizeY"] = "8mm"
        mr.settings["MaxElementSizeZ"] = "8mm"; mr.settings["MinGapX"] = "0.25mm"
        mr.settings["MinGapY"] = "0.25mm"; mr.settings["MinGapZ"] = "0.25mm"
        mr.settings["BufferLayers"] = "2"; mr.update()
        stack = [o.name for o in win_objs] + ["Board_" + l for l, _, _ in units] + steel_names
        loc = ipk.mesh.assign_mesh_region(stack, name="StackMesh")
        loc.manual_settings = True
        loc.settings["MaxElementSizeX"] = "2mm"; loc.settings["MaxElementSizeY"] = "2mm"
        loc.settings["MaxElementSizeZ"] = "0.5mm"; loc.update()
        log("mesh regions set")
    except Exception as e:
        log("WARN mesh settings not applied (%r); AEDT defaults used" % e)

    # ---- monitors: board centre radius, mid-thickness; magnet layer centres
    for lab, z0 in board_mon:
        try: ipk.monitor.assign_point_monitor([28.0, 0, z0 + T_BOARD / 2], monitor_quantity="Temperature",
                                              monitor_name="T_" + lab)
        except Exception as e: log("WARN monitor T_%s: %r" % (lab, e))
    for nm, zc in mag_mon:
        try: ipk.monitor.assign_point_monitor([MAG_RC, 0, zc], monitor_quantity="Temperature",
                                              monitor_name="T_" + nm)
        except Exception as e: log("WARN monitor T_%s: %r" % (nm, e))

    # ---- guard: every board must have its winding annulus removed (a failed Boolean
    # leaves Board_X overlapping Win_X, and the Win then gets no mesh and no heat)
    v_exp = (12 * APOTHEM ** 2 * math.tan(math.pi / 12) - math.pi * (WIN_R_OUT ** 2 - WIN_R_IN ** 2)
             - math.pi * (BORE_D / 2) ** 2 - N_RODS * math.pi * (ROD_D / 2) ** 2) * N_BOARDS * T_BOARD
    for lab, _, _ in units:
        b = "Board_" + lab
        try:
            if abs(M[b].volume - v_exp) / v_exp > 0.01:
                log("WARN %s volume %.1f vs %.1f mm3 - re-subtracting Win_%s" % (b, M[b].volume, v_exp, lab))
                M.subtract(b, ["Win_" + lab], keep_originals=True)
        except Exception as e:
            log("WARN volume check %s: %r" % (b, e))
    try:
        ipk.mesh.assign_priorities([["Board_" + l for l, _, _ in units], [w.name for w in win_objs]])
        log("mesh priorities set (boards low, windings high)")
    except Exception as e:
        log("WARN priorities: %r" % e)

    # ---- placeholder steady setup (run script owns the real settings)
    setup = ipk.create_setup("Steady" + DESIGN)
    setup.props["Flow Regime"] = "Laminar"
    setup.props["Include Flow"] = True
    setup.props["Include Gravity"] = True
    setup.props["Convergence Criteria - Max Iterations"] = 400
    if RADIATION: setup.props["Radiation Model"] = "Discrete Ordinates Model"
    setup.update()

    # ---- mesh check: refuse to freeze if any object gets no mesh
    try:
        try: ipk.odesktop.ClearMessages(ipk.project_name, ipk.design_name, 3)
        except Exception: pass
        ipk.mesh.generate_mesh()
        msgs = list(ipk.odesktop.GetMessages(ipk.project_name, ipk.design_name, 0))
        nomesh = sorted({m.split("'")[1] for m in msgs if "does not have mesh" in m and "'" in m})
    except Exception as e:
        nomesh = []; log("WARN mesh check could not run: %r" % e)
    log("mesh check - objects without mesh: %s" % (nomesh or "none"))
    if nomesh:
        log("NOT FROZEN: objects without mesh %s" % nomesh)
        ipk.save_project(); ipk.release_desktop(close_projects=True, close_desktop=True)
        raise SystemExit("mesh check failed - paste this output")
    ok = bool(ipk.validate_simple(os.path.join(WORK_DIR, DESIGN.lower() + "_icepak_validation.log")))
    log("Validation Check: %s" % ok)
    ipk.save_project()
    frozen = os.path.join(WORK_DIR, FROZEN_NAME + ".aedt")
    if ok:
        ipk.save_project(file_name=frozen)
        json.dump(dict(DESIGN=DESIGN, DESIGN_NAME=DESIGN_NAME, SETUP="Steady" + DESIGN,
                       UNITS=[l for l, _, _ in units], WINS=[w.name for w in win_objs],
                       BOARD_MONITORS=["T_" + l for l, _ in board_mon], N_BOARDS=N_BOARDS,
                       MAG_LAYERS=mag_layers, STEELS=steel_names, T_HOOD=T_HOOD, V_FAN=V_FAN,
                       K_XY=K_XY, K_Z=K_Z, built=time.strftime("%Y-%m-%d %H:%M")),
                  open(os.path.join(WORK_DIR, FROZEN_NAME + "_info.json"), "w"), indent=1)
        log("FROZEN: " + frozen)
        copy_out([frozen, LOG, os.path.join(WORK_DIR, FROZEN_NAME + "_info.json")])
    else:
        log("Validation FAILED - frozen copy NOT written; see AEDT message window")
    ipk.release_desktop(close_projects=True, close_desktop=True)

if __name__ == "__main__":
    main()
