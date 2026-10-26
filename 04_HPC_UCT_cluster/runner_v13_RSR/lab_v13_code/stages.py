# -*- coding: utf-8 -*-
"""Stage pipeline. Each stage is a function; the runner saves the project + state after each one,
stops on the first failure, and can resume from any stage (START_AT)."""
import os
import shutil

import pcb_geometry
import build_pcb
import build_rotor
import setup_model
from aedt_api import StageError
from setup_model import ROT_VAR

STAGES = ["project", "stator", "rotor", "region_band", "excitation", "solver_setup", "validate", "analyze", "export"]


# ------------------------------------------------------------------------------------ stages
def st_project(ctx, geo):
    cfg = ctx.cfg
    if not os.path.isdir(ctx.project_dir()):
        os.makedirs(ctx.project_dir())
    base = os.path.splitext(ctx.project_path())[0]
    old = [p for p in (ctx.project_path(), base + ".aedtresults", ctx.project_path() + ".lock") if os.path.exists(p)]
    if old:
        # Overwriting a same-name project hits file locks (e.g. "Rev0.asol_priv is in use") held by an
        # open project or a leftover solver process. Never overwrite: ask for a fresh name instead.
        raise StageError("A project named %s already exists in %s (%s). Use a new name in main.py, e.g. "
                         "OVERRIDES = {\"PROJECT_NAME\": \"%s_V2\"}, or close it in AEDT and delete/move "
                         "those files first." % (cfg.PROJECT_NAME, ctx.project_dir(),
                                                 ", ".join(os.path.basename(p) for p in old), cfg.PROJECT_NAME))
    ctx.project = ctx.desktop.NewProject()
    ctx.project.SaveAs(ctx.project_path(), True)
    stype = cfg.aedt_solution_type()
    try:
        ctx.project.InsertDesign("Maxwell 3D", cfg.DESIGN_NAME, stype, "")
        ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    except Exception:
        ctx.project.InsertDesign("Maxwell 3D", cfg.DESIGN_NAME, "Transient", "")
        ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
        ctx.design.SetSolutionType(stype)
    try:
        actual = ctx.design.GetSolutionType()
        ctx.log("Design solution type reported by AEDT: %s" % actual)
        if cfg.is_aphi() and "aphi" not in str(actual).replace("-", "").replace(" ", "").lower():
            raise StageError("Requested Transient A-Phi but AEDT reports '%s'" % actual)
    except StageError:
        raise
    except Exception:
        ctx.log("GetSolutionType not available - check the design type in the Project Manager", 1)
    ctx.attach_design()
    ctx.editor.SetModelUnits(["NAME:Units Parameter", "Units:=", "mm", "Rescale:=", False])
    try:
        ctx.desktop.EnableAutoSave(False)
    except Exception:
        pass
    ctx.state = {"stages_done": [], "objects": {}, "profile": cfg.PROFILE}
    if cfg.BUILD_FR4:
        try:
            ctx.project.GetDefinitionManager().AddMaterial(
                ["NAME:" + cfg.MASK_MATERIAL, "CoordinateSystemType:=", "Cartesian", "BulkOrSurfaceType:=", 1,
                 ["NAME:PhysicsTypes", "set:=", ["Electromagnetic"]],
                 "permittivity:=", str(cfg.MASK_EPS_R), "permeability:=", "1", "conductivity:=", "0"])
            ctx.state["mask_material"] = cfg.MASK_MATERIAL
            ctx.log("Material %s created (eps_r %.2f, mu_r 1, non-conductive)" % (cfg.MASK_MATERIAL, cfg.MASK_EPS_R))
        except Exception as e:
            ctx.state["mask_material"] = "FR4_epoxy"
            ctx.log("Could not create %s (%s) - solder mask falls back to FR4_epoxy (magnetically identical)"
                    % (cfg.MASK_MATERIAL, e), 1)
    ctx.log("Project %s / design %s (%s)" % (cfg.PROJECT_NAME, cfg.DESIGN_NAME, stype))
    for a in cfg.assumptions():
        ctx.log("ASSUMPTION: " + a)


def st_stator(ctx, geo):
    cfg = ctx.cfg
    obj = ctx.state["objects"]
    excite = cfg.EXCITE_STATOR and bool(cfg.PHASES) and cfg.N_BOARDS >= 1
    if excite and cfg.N_BOARDS > 1 and not cfg.STACK_SERIES:
        raise StageError("Detailed excitation of %d boards is not supported (RAM). Use N_BOARDS=1 for the "
                         "reference model; the 5-board stator is done by the field-map / equivalent models."
                         % cfg.N_BOARDS)
    # pre-build source checks (pure geometry, no AEDT)
    bad = build_pcb.cross_phase_check(geo)
    if bad:
        raise StageError("%d vias land on copper of a different phase (unintended shortcut)" % bad)
    ctx.log("Check: no via of one phase touches copper of another phase")
    if cfg.SYNC_3PH:
        for net in ("PHASE_B", "PHASE_C"):
            f = build_pcb.rotation_match(geo, net, "PHASE_A", cfg.PHASE_ROT_MECH[net])
            ctx.log("Check %s = PHASE_A rotated %g deg mech: %.2f%% of L1 copper coincides"
                    % (net, cfg.PHASE_ROT_MECH[net], 100 * f))
            if f < 0.99:
                raise StageError("%s is not PHASE_A rotated by %g deg - the superposition prediction would be wrong"
                                 % (net, cfg.PHASE_ROT_MECH[net]))
    for net in cfg.PHASES:
        r = build_pcb.verify_phase(geo, net, cfg.TERMINAL_MAP[net])
        ctx.log("Check %s: %d islands form ONE network; In->Out %d island-hops (farthest island %d)"
                % (net, r["islands"], r["hops_in_out"], r["max_hops"]))
    y_end = max(p[1] for p in geo["outline"]) + cfg.REGION_PADDING
    obj["y_lead_end"] = y_end
    obj.setdefault("boards", [])
    for k in range(1, cfg.N_BOARDS + 1):
        if any(b["k"] == k for b in obj["boards"]):
            ctx.log("PCB%d already built and validated (restored from its board checkpoint) - skipped" % k)
            continue
        b = build_pcb.build_board(ctx, geo, k, excite and not cfg.STACK_SERIES, y_end)
        st = b["stack"]
        obj["boards"].append({"k": k, "phases": b["phases"], "leads": b["leads"], "fr4": b["fr4"], "mask": b.get("mask"),
                              "top_surface": st["top_surface"], "bottom_surface": st["bottom_surface"],
                              "layers": st["layers"]})
        ctx.log("PCB%d built: copper L1 top z=%.5f, top mask surface z=%.5f, bottom surface z=%.5f"
                % (k, st["layers"]["L1"][1], st["top_surface"], st["bottom_surface"]))
        if cfg.STACK_SERIES:
            board_checkpoint(ctx, k)
    if cfg.STACK_SERIES and excite:
        chk = build_pcb.bridge_pad_check(geo, cfg)
        for net, ok in sorted(chk.items()):
            ctx.log("Check %s bridge footprint: %s" % (net, "on own L6 Out / L1 In pad copper only" if ok else "FAIL"))
        if not all(chk.values()):
            raise StageError("A bridge footprint is not fully on its own phase's terminal pads: %s" % chk)
        st = build_pcb.build_stack_series(ctx, geo, obj["boards"], y_end)
        for b in obj["boards"]:
            b["phases"] = {}                    # consumed into the series strings
        obj["stack"] = st
        ctx.log("Stator stack: %d boards at centres z = %s mm (pitch %.5f mm)"
                % (cfg.N_BOARDS, ", ".join("%.5f" % (-(k - 1) * cfg.board_pitch()) for k in range(1, cfg.N_BOARDS + 1)),
                   cfg.board_pitch()))
    # stator top surface even if no copper is built (rotor-only profiles)
    obj["stator_top_surface"] = build_pcb.board_stack(cfg, geo, 1)["top_surface"]


def _board_ckpt_paths(ctx, k):
    base = os.path.join(_ckpt_dir(ctx), "02_stator_board%d" % k)
    return base + ".aedt", base + "_state.json"


EXPECTED_BUILD_ONLY = ("no excitation or value boundary", "no solution setups have been created")


def validate_geometry(ctx, label, allow_no_excitation=False):
    """AEDT Validation Check. In a build-only project the check always reports 'No excitation ... defined'
    (before the windings exist) and 'No solution setups have been created' (by design) - those two are
    expected and accepted; ANY other validation error fails (2026-10-06: PCB1 'failed' on exactly these two)."""
    before = _messages(ctx) or []
    try:
        ok = ctx.design.ValidateDesign()
    except Exception as e:
        ctx.log("%s: ValidateDesign not available (%s)" % (label, e), 1)
        return None
    if ok is False or ok == 0:
        after = _messages(ctx) or []
        new = after[len(before):] if after[:len(before)] == before else [m for m in after if m not in before]
        if not new:      # AEDT may not repeat an identical message - judge on all error messages present
            new = after
        allowed = EXPECTED_BUILD_ONLY if (allow_no_excitation or ctx.cfg.BUILD_ONLY) else ()
        bad = [m.strip() for m in new if not any(p in m.lower() for p in allowed)]
        if bad or not new:
            raise StageError("%s failed the AEDT Validation Check: %s" % (label, " | ".join(bad) or "see Message Manager"))
        ctx.log("%s: Validation Check passed for geometry (only the expected build-only notices: %s)"
                % (label, " / ".join(m.strip()[:60] for m in new)))
        return "geometry OK"
    return ok


def board_checkpoint(ctx, k):
    """Five-board build: after EACH board - AEDT Validation Check, save, checkpoint. A crash then costs at
    most one board; START_AT = "stator" resumes after the last saved board (Olwethu, 2026-10-06)."""
    ok = validate_geometry(ctx, "PCB%d" % k, allow_no_excitation=True)
    ctx.project.Save()
    ctx.save_state()
    aedt, js = _board_ckpt_paths(ctx, k)
    shutil.copyfile(ctx.project_path(), aedt)
    shutil.copyfile(ctx.state_path(), js)
    ctx.log("PCB%d validated (%s) and saved: %s" % (k, ok, aedt))


def st_rotor(ctx, geo):
    if not ctx.cfg.BUILD_ROTOR:
        ctx.log("Rotor disabled for this profile")
        return
    cfg = ctx.cfg
    r = build_rotor.build_rotor(ctx, ctx.state["objects"]["stator_top_surface"])
    ctx.state["objects"]["rotor"] = r
    if cfg.REAR_STEEL_GAP:
        import pcb_geometry as _pg
        bottom = build_pcb.board_stack(cfg, _pg.load(), cfg.N_BOARDS)["bottom_surface"]
        z1 = bottom - cfg.REAR_STEEL_GAP
        rs = ctx.cylinder("RearSteel", 0, 0, z1 - cfg.REAR_STEEL_THICK, cfg.REAR_STEEL_THICK, cfg.BACK_IRON_OD / 2.0,
                          cfg.BACK_IRON_MATERIAL, "(110 110 110)")
        ctx.state["objects"]["rear_steel"] = rs
        ctx.log("Rev1 S2 environment: rear steel plate %s z %.5f..%.5f (%.3f mm below the board bottom surface "
                "z=%.5f), OD %.1f mm" % (rs, z1 - cfg.REAR_STEEL_THICK, z1, cfg.REAR_STEEL_GAP, bottom,
                                         cfg.BACK_IRON_OD))
    if cfg.LOWER_PM_GAP:
        # Rev1-D: R1 seen from S2 = face-B magnets (toward this board) + shared plate + face-A magnets (toward S1)
        import pcb_geometry as _pg
        bottom = build_pcb.board_stack(cfg, _pg.load(), cfg.N_BOARDS)["bottom_surface"]
        zB1 = bottom - cfg.LOWER_PM_GAP
        zB0 = zB1 - cfg.MAG_THICK
        lo = build_rotor.magnet_array(ctx, zB0, "LoB_", flip=(cfg.LOWER_POLARITY == "opposed"))
        zP0 = zB0 - cfg.LOWER_PLATE_THICK
        plate = ctx.cylinder("LoPlate", 0, 0, zP0, cfg.LOWER_PLATE_THICK, cfg.BACK_IRON_OD / 2.0,
                             cfg.BACK_IRON_MATERIAL, "(110 110 110)")
        if cfg.LOWER_BACK_ARRAY:
            face_b_flipped = cfg.LOWER_POLARITY == "opposed"
            lo += build_rotor.magnet_array(ctx, zP0 - cfg.MAG_THICK, "LoA_",
                                           flip=face_b_flipped != (cfg.R1_FACE_RELATION == "mirror"))
        r["magnets"] = list(r["magnets"]) + lo
        r["steel"] = list(r["steel"]) + [plate]
        r["lower"] = {"plate": plate, "zB1": zB1, "zP0": zP0, "board_bottom": bottom}
        ctx.state["objects"]["rotor"] = r
        ctx.log(("R-S-R board environment" if cfg.PROJECT_NAME.startswith("DIAG_RSR") else "Rev1-D S2 environment") + ": lower PM rotor below the board: face-B magnets z %.5f..%.5f (%.3f mm below the "
                "board bottom z=%.5f, %s), plate %s z %.5f..%.5f, %s"
                % (zB0, zB1, cfg.LOWER_PM_GAP, bottom, cfg.LOWER_POLARITY, plate, zP0, zB0,
                   "face-A magnets behind (%s)" % cfg.R1_FACE_RELATION if cfg.LOWER_BACK_ARRAY else "no face A"))
    if cfg.ROTOR_SWEEP:
        # rotor position as a design variable: the magnets are rotated about +Z by theta (parametric
        # history operation). Back iron + shaft are axisymmetric -> not rotated. Magnetisation stays +-Z.
        # NB: "theta" is a reserved/intrinsic name in AEDT (2026-10-05: "Can not create property named
        # 'theta'") -> the rotor angle variable is rot_angle
        ctx.set_var(ROT_VAR, "%gdeg" % cfg.THETA_START)
        if ctx.design.GetVariableValue(ROT_VAR) in (None, ""):
            raise StageError("Design variable %s was not created" % ROT_VAR)
        ctx.editor.Rotate(["NAME:Selections", "Selections:=", ",".join(r["magnets"]), "NewPartsModelFlag:=", "Model"],
                          ["NAME:RotateParameters", "RotateAxis:=", "Z", "RotateAngle:=", ROT_VAR])
        ctx.log("Rotor position: %d magnets rotated about +Z by design variable %s (= %g deg)"
                % (len(r["magnets"]), ROT_VAR, cfg.THETA_START))


def st_region_band(ctx, geo):
    cfg = ctx.cfg
    obj = ctx.state["objects"]
    try:
        ctx.disc_sheet("Plot_StatorSurface", obj["stator_top_surface"], 45.0)
    except Exception as e:
        ctx.log("Plot sheet skipped (%s)" % e, 1)
    if cfg.ROTOR_SWEEP:
        g = obj["rotor"]["geom"]
        r0, r1 = g["mag_r_in"] - 2.0, g["mag_r_out"] + 2.0
        z0, z1 = obj["stator_top_surface"], g["zm0"]
        outer = ctx.cylinder("GapLayer", 0, 0, z0, z1 - z0, r1, "vacuum", "(200 255 255)", 0, 0.95)
        inner = ctx.cylinder("GapLayer_hole", 0, 0, z0 - 0.01, z1 - z0 + 0.02, r0, "vacuum", "(0 0 0)")
        ctx.subtract([outer], [inner], keep_tools=False)
        obj["gap_layer"] = "GapLayer"
        zm = 0.5 * (z0 + z1)
        ctx.disc_sheet("GapMid", zm, r1)
        ctx.disc_sheet("GapMid_hole", zm, r0)
        ctx.subtract(["GapMid"], ["GapMid_hole"], keep_tools=False)
        obj["gap_sheet"] = {"name": "GapMid", "z": zm, "r0": r0, "r1": r1}
        ctx.log("Air-gap vacuum layer r %.1f-%.1f mm, z %.5f-%.5f (mesh op); mid-gap sheet GapMid at z %.5f"
                % (r0, r1, z0, z1, zm))
        low = obj["rotor"].get("lower")
        if low:   # Rev1-D: the gap between the board bottom and the face-B magnets gets the same mesh treatment
            lz0, lz1 = low["zB1"], low["board_bottom"]
            lo = ctx.cylinder("GapLayerLo", 0, 0, lz0, lz1 - lz0, r1, "vacuum", "(200 255 255)", 0, 0.95)
            lh = ctx.cylinder("GapLayerLo_hole", 0, 0, lz0 - 0.01, lz1 - lz0 + 0.02, r0, "vacuum", "(0 0 0)")
            ctx.subtract([lo], [lh], keep_tools=False)
            # each layer gets its own length op at half ITS thickness (one shared op would mesh the 1 mm gap at the
            # other gap's size); MESH_GAP_MAX overrides both
            obj["gap_layer"] = {"GapLayer": cfg.MESH_GAP_MAX or (z1 - z0) / 2.0,
                                "GapLayerLo": cfg.MESH_GAP_MAX or (lz1 - lz0) / 2.0}
            ctx.log("Lower air-gap vacuum layer GapLayerLo z %.5f-%.5f; mesh max length: upper %.3f mm, lower %.3f mm"
                    % (lz0, lz1, obj["gap_layer"]["GapLayer"], obj["gap_layer"]["GapLayerLo"]))
    # string-end leads of the five-board stack live in obj["stack"] (the boards themselves carry none) - missing
    # this on 2026-10-07 left the region +Y padding at 5 mm and AEDT rejected all six terminals as
    # "Illegal external terminal ... must border the edge of the problem region"
    leads_present = any(b["leads"] for b in obj.get("boards", [])) or bool((obj.get("stack") or {}).get("leads"))
    setup_model.create_region(ctx, plus_y_zero=leads_present)
    obj["region_plus_y_zero"] = bool(leads_present)
    ctx.log("Region: padding %g mm, +Y face %s" % (cfg.REGION_PADDING, "on the terminal lead ends (padding 0)"
                                                   if leads_present else "padded"))
    obj["band"] = None
    if cfg.BUILD_ROTOR and cfg.SOLUTION_TYPE == "Transient":
        g = obj["rotor"]["geom"]
        for b in obj.get("boards", []):
            for net, lg in b["leads"].items():
                if g["band_r"] >= lg["r_inner"] - 0.2:
                    raise StageError("Band radius %.2f mm would hit the %s terminal lead (r >= %.2f mm)"
                                     % (g["band_r"], net, lg["r_inner"]))
        if g["band_z0"] <= obj["stator_top_surface"]:
            raise StageError("Band floor is not above the stator surface")
        obj["band"] = ctx.cylinder("Band", 0, 0, g["band_z0"], g["band_z1"] - g["band_z0"], g["band_r"], "vacuum",
                                   "(128 255 255)", 0, 0.9)
        ctx.log("Band r=%.2f mm, z %.4f..%.4f (stator surface %.4f, magnets from %.4f)"
                % (g["band_r"], g["band_z0"], g["band_z1"], obj["stator_top_surface"], g["zm0"]))


def define_variables(ctx):
    """Design variables used by the winding current expressions. Must exist BEFORE the windings are
    assigned: on 2026-10-04 they were created afterwards and GATE2_TOMEGA solved with 0 A."""
    cfg = ctx.cfg
    ctx.set_var("rpm", "%grpm" % cfg.RPM)
    ctx.set_var("fe", "%gHz" % (cfg.RPM / 60.0 * (cfg.POLES // 2)))
    ctx.set_var("Ipk", "%gA" % cfg.IPK)
    names = ["rpm", "fe", "Ipk"]
    if cfg.ROTOR_SWEEP:
        ctx.set_var("Iamp", "%gA" % cfg.SWEEP_I)
        names += ["Iamp", ROT_VAR]
    if cfg.BUILD_ONLY:
        for n in cfg.PHASES:
            ctx.set_var("I_%s" % n[-1], "0A")
            names.append("I_%s" % n[-1])
    if cfg.SYNC_3PH:
        psi, fit, src = baseline_phase(ctx)
        ctx.state["sync"] = {"psi": psi, "fit": fit, "source": src}
        ctx.set_var("Isync", "%gA" % cfg.SYNC_IPK)
        ctx.set_var("phi_sync", "%.6gdeg" % (-psi))
        ctx.log("Current angle: psi = %.3f deg elec (%s) -> phi_sync = %.3f deg; I_X = %g A cos(%d rot_angle + "
                "phi_sync + PHASE_DEG[X]) puts each phase current in phase with its dLam/dtheta"
                % (psi, src, -psi, cfg.SYNC_IPK, cfg.POLES // 2))
        names += ["Isync", "phi_sync"]
    for v in names:
        try:
            ctx.log("Design variable %s = %s" % (v, ctx.design.GetVariableValue(v)))
        except Exception:
            pass


def baseline_phase(ctx):
    """psi (phase of dLam_A/dtheta) and the harmonic fit from the Phase-A baseline sweep summary."""
    import rotor_analysis
    cfg = ctx.cfg
    path = os.path.join(ctx.project_dir(), cfg.BASELINE_PROJECT + "_results", "rotor_sweep_summary.txt")
    if not os.path.isfile(path) and getattr(cfg, "SHARED_RESULTS_DIR", None):
        path = os.path.join(cfg.SHARED_RESULTS_DIR, cfg.BASELINE_PROJECT + "_results", "rotor_sweep_summary.txt")
    if not os.path.isfile(path):
        raise StageError("Baseline summary %s not found - run REF_ROTOR_MS_SWEEP first (the current angle must "
                         "come from the baseline, not the smoke test)" % path)
    b = rotor_analysis.read_summary(path)
    fit = b.get("fit_coeffs")
    if not isinstance(fit, dict):
        raise StageError("Baseline summary %s: fit_coeffs %s (%s) - run fix_baseline_summary.py; if it is already "
                         "there, send this message" % (path, "missing" if fit is None else "unreadable",
                                                       repr(fit)[:80]))
    if b.get("angles", 0) < 8:
        raise StageError("Baseline %s has only %s angles - a full-period sweep is required" % (path, b.get("angles")))
    psi = float(b["phase_of_k_elec_deg"]) if cfg.SYNC_PHI_DEG is None else -float(cfg.SYNC_PHI_DEG)
    src = "baseline %s" % path if cfg.SYNC_PHI_DEG is None else "override SYNC_PHI_DEG"
    return psi, fit, src


def st_excitation(ctx, geo):
    define_variables(ctx)
    obj = ctx.state["objects"]
    boards = obj.get("boards", [])
    obj["windings"] = {}
    if obj.get("stack"):
        obj["windings"] = setup_model.assign_excitations(ctx, obj["stack"]["phases"], obj["stack"]["leads"])
    elif boards and boards[0]["leads"]:
        obj["windings"] = setup_model.assign_excitations(ctx, boards[0]["phases"], boards[0]["leads"])
    else:
        ctx.log("No stator excitation in this profile")


def st_solver_setup(ctx, geo):
    cfg = ctx.cfg
    obj = ctx.state["objects"]
    if cfg.BUILD_ONLY:
        ctx.log("Build-only profile: no solver setup, mesh operations or reports (added by each test script)")
        return
    copper = [n for b in obj.get("boards", []) for n in b["phases"].values()]
    rotor = obj.get("rotor") or {"magnets": [], "steel": []}
    if cfg.SOLUTION_TYPE == "Transient":
        setup_model.set_eddy(ctx, rotor["magnets"], cfg.MAGNET_EDDY, "magnets")
        setup_model.set_eddy(ctx, copper, cfg.COPPER_EDDY, "PCB copper")
        if obj.get("band"):
            setup_model.assign_motion(ctx, obj["band"])
    setup_model.mesh_ops(ctx, obj.get("band"), rotor["magnets"], copper, obj.get("gap_layer"))
    obj["reports"] = setup_model.solver_setup(ctx, obj.get("windings", {}), bool(obj.get("band")),
                                              rotor=rotor if cfg.BUILD_ROTOR else None, copper=copper)


def st_validate(ctx, geo):
    cfg = ctx.cfg
    obj = ctx.state["objects"]
    problems = []
    if cfg.BUILD_ROTOR:
        g = obj["rotor"]["geom"]
        gap = g["zm0"] - obj["stator_top_surface"]
        ctx.log("Acceptance: air gap stator surface -> magnet face = %.4f mm (target %.4f)" % (gap, cfg.AIR_GAP))
        if abs(gap - cfg.AIR_GAP) > 1e-6:
            problems.append("air gap mismatch")
        ctx.log("Acceptance: magnets alternate +Z/-Z (CS_MagUp/CS_MagDown on even/odd), %d poles" % cfg.POLES)
        lead_sets = [b["leads"] for b in obj.get("boards", [])] + ([obj["stack"]["leads"]] if obj.get("stack") else [])
        for leads in lead_sets:
            for net, lg in leads.items():
                if g["r_parts"] >= lg["r_inner"] - 0.5 and g["zm0"] <= lg["z_top"] + 0.1:
                    problems.append("rotor (r %.2f mm, z from %.3f) clashes with the %s lead (r >= %.2f, z <= %.3f)"
                                    % (g["r_parts"], g["zm0"], net, lg["r_inner"], lg["z_top"]))
        ctx.log("Acceptance: rotor parts r <= %.2f mm; terminal leads start at r >= %.2f mm"
                % (g["r_parts"], min([lg["r_inner"] for leads in lead_sets for lg in leads.values()]
                                     or [float("nan")])))
    for b in obj.get("boards", []):
        if b["phases"]:
            ctx.log("Acceptance: PCB%d phases %s" % (b["k"], ", ".join(sorted(b["phases"].values()))))
    if obj.get("stack"):
        problems += stack_connectivity(ctx, obj["stack"])
    if obj.get("windings") and not obj.get("region_plus_y_zero"):
        problems.append("terminal leads exist but the region +Y face is padded - coil terminals would be illegal")
    try:
        ok = validate_geometry(ctx, "Design")
    except StageError as e:
        ok = False
        problems.append(str(e))
    ctx.log("AEDT Validation Check returned %s" % ok)
    if problems:
        raise StageError("; ".join(problems))
    if cfg.BUILD_ONLY:
        freeze_build(ctx)


def stack_connectivity(ctx, stack):
    """AEDT geometric proof of every inter-board junction: just inside board k's L6 Out pad, inside the bridge
    and just inside board k+1's L1 In pad, AEDT must report the expected conductor body. Together with the
    single-board conduction tests (each board's L1 In -> L6 Out path accepted by Maxwell) this shows each
    string is continuous; Maxwell's own conduction-path check runs at the first solve (STACK_JUNCTION_TEST)."""
    cfg = ctx.cfg
    problems = []
    geo_stacks = {}
    import pcb_geometry
    geo = pcb_geometry.load()
    for k in range(1, cfg.N_BOARDS + 1):
        geo_stacks[k] = build_pcb.board_stack(cfg, geo, k)

    def bodies(x, y, z):
        try:
            return [str(b) for b in ctx.editor.GetBodyNamesByPosition(
                ["NAME:Parameters", "XPosition:=", "%.6fmm" % x, "YPosition:=", "%.6fmm" % y, "ZPosition:=", "%.6fmm" % z])]
        except Exception as e:
            return None

    for net, s in sorted(stack["strings"].items()):
        tag = net[-1]
        x, y = cfg.TERMINAL_MAP[net]["in"][1], cfg.TERMINAL_MAP[net]["in"][2]
        boards = s["boards"]
        for k in range(1, cfg.N_BOARDS):
            L6 = geo_stacks[k]["layers"]["L6"]
            L1 = geo_stacks[k + 1]["layers"]["L1"]
            probes = [("PCB%d L6 Out pad" % k, 0.5 * (L6[0] + L6[1]), boards[k - 1]),
                      ("bridge %d-%d" % (k, k + 1), 0.5 * (L6[0] + L1[1]), s["bridges"][k - 1]),
                      ("PCB%d L1 In pad" % (k + 1), 0.5 * (L1[0] + L1[1]), boards[k])]
            res = []
            for label, z, want in probes:
                got = bodies(x, y, z)
                if got is None:
                    ctx.log("GetBodyNamesByPosition not available - junction %s %d-%d not checked" % (tag, k, k + 1), 1)
                    res = None
                    break
                if want not in got:
                    problems.append("Phase %s junction %d-%d: expected %s at %s, AEDT reports %s"
                                    % (tag, k, k + 1, want, label, got))
                res.append("%s=%s" % (label, ",".join(g for g in got if g.startswith(("Phase", "Bridge"))) or "-"))
            if res is not None:
                ctx.log("Junction %s %d->%d: %s" % (tag, k, k + 1, "; ".join(res)))
        ctx.log("Acceptance: Phase %s string %s with %d bridges" % (tag, " -> ".join(boards), len(s["bridges"])))
    return problems


def freeze_build(ctx):
    """Save, then copy the validated build to <PROJECT>_FROZEN.aedt (never modified; tests copy it)."""
    import json
    cfg = ctx.cfg
    ctx.project.Save()
    dst = os.path.join(ctx.project_dir(), cfg.PROJECT_NAME + "_FROZEN.aedt")
    if os.path.exists(dst):
        raise StageError("%s already exists - frozen builds are never overwritten; use a new PROJECT_NAME" % dst)
    shutil.copyfile(ctx.project_path(), dst)
    with open(os.path.join(ctx.results_dir(), "frozen_build_manifest.json"), "w") as f:
        json.dump({"frozen_project": dst, "profile": cfg.PROFILE, "boards": cfg.N_BOARDS, "pitch_mm": cfg.board_pitch(),
                   "air_gap_mm": cfg.AIR_GAP, "back_iron_mm": cfg.BACK_IRON_THICK, "magnet_centre_r_mm": cfg.MAG_CENTRE_R,
                   "assumptions": cfg.assumptions(), "windings": ctx.state["objects"].get("windings", {}),
                   "current_variables": ["I_%s" % n[-1] for n in cfg.PHASES]}, f, indent=1)
    ctx.log("FROZEN BUILD saved: %s (validated; star point open; currents I_A/I_B/I_C = 0 A)" % dst)


FATAL_PATTERNS = ["conduction path", "simulation completed with execution error", "solve failed",
                  "out of memory", "insufficient memory", "mesh generation failed", "aborted"]


def _messages(ctx, severity=2):
    try:
        return [str(m) for m in ctx.desktop.GetMessages(ctx.cfg.PROJECT_NAME, ctx.cfg.DESIGN_NAME, severity)]
    except Exception:
        return None


def _solve_problems(ctx, before):
    after = _messages(ctx)
    problems = []
    if after is None:
        ctx.log("Could not read AEDT messages - error scan skipped", 1)
    else:
        new = after[len(before):] if after[:len(before)] == before else [m for m in after if m not in before]
        for m in new:
            ctx.log("AEDT error message: %s" % m.strip(), 2)
            if any(p in m.lower() for p in FATAL_PATTERNS):
                problems.append(m.strip())
        if new and not problems:
            problems.append("%d error-level messages during the solve" % len(new))
    try:
        sols = [str(x) for x in ctx.design.GetModule("Solutions").GetValidISolutionList()]
        if not any(x.startswith("Setup1") for x in sols):
            problems.append("no valid Setup1 solution exists after Analyze")
    except Exception as e:
        ctx.log("Solution list not available (%s)" % e, 1)
    return problems


def sweep_points(cfg):
    n = int(round((cfg.THETA_STOP - cfg.THETA_START) / cfg.THETA_STEP))
    thetas = [round(cfg.THETA_START + k * cfg.THETA_STEP, 6) for k in range(n + 1)]
    currents = [cfg.SWEEP_I, -cfg.SWEEP_I] if cfg.SWEEP_MINUS_I else [cfg.SWEEP_I]
    return thetas, currents


def _progress_path(ctx):
    return os.path.join(ctx.results_dir(), "sweep_progress.json")


def load_progress(ctx):
    import json
    p = _progress_path(ctx)
    if os.path.isfile(p):
        with open(p) as f:
            return json.load(f)
    return {"done": {}}


def save_progress(ctx, prog):
    import json
    tmp = _progress_path(ctx) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(prog, f, indent=1, sort_keys=True)
    if os.path.isfile(_progress_path(ctx)):
        os.remove(_progress_path(ctx))
    os.rename(tmp, _progress_path(ctx))


def _key(t, i):
    return "%g|%g" % (t, i)


def _read_variation(ctx, theta, current):
    """Torque values (SI) of one solved variation, read through the report of that current."""
    import rotor_analysis
    name = "Torque_Iplus" if current > 0 else "Torque_Iminus"
    path = os.path.join(ctx.results_dir(), "_step_%s.csv" % name)
    ctx.design.GetModule("ReportSetup").ExportToFile(name, path)
    cols = rotor_analysis.read_report_csv(path)
    for j, t in enumerate(cols["theta"]):
        if abs(t - theta) < 1e-6:
            return dict((k, v[j]) for k, v in cols.items() if k != "theta")
    raise StageError("Solved variation rot_angle=%g deg, Iamp=%g A is missing from report %s" % (theta, current, name))


def _analyze_stepwise(ctx):
    """One Analyze per (rot_angle, Iamp); project saved and results written to sweep_progress.json after EVERY
    solve, so a PC crash loses at most the variation in progress (2026-10-05: lab PC crashed at 22:21 during
    an 18-solve Optimetrics run that only saves at the end)."""
    import time
    cfg = ctx.cfg
    thetas, currents = sweep_points(cfg)
    todo = [(t, i) for t in thetas for i in currents]
    prog = load_progress(ctx)
    done = prog["done"]
    ctx.log("Stepwise sweep: %d variations, %d already solved (%s)" % (len(todo), sum(_key(t, i) in done for t, i in todo),
                                                                       _progress_path(ctx)))
    for n, (t, i) in enumerate(todo):
        k = _key(t, i)
        if k in done:
            continue
        ctx.set_var(ROT_VAR, "%gdeg" % t)
        ctx.set_var("Iamp", "%gA" % i)
        t0 = time.time()
        ctx.log("Variation %d/%d: %s = %g deg, Iamp = %g A ... solving" % (n + 1, len(todo), ROT_VAR, t, i))
        before = _messages(ctx) or []
        ctx.design.Analyze("Setup1")
        problems = _solve_problems(ctx, before)
        if problems:
            raise StageError("Variation %s = %g deg, Iamp = %g A NOT accepted: %s" % (ROT_VAR, t, i, " | ".join(problems)))
        ctx.project.Save()
        vals = _read_variation(ctx, t, i)
        rec = {"theta": t, "I": i, "values_SI": vals, "minutes": round((time.time() - t0) / 60.0, 2),
               "finished": time.strftime("%Y-%m-%d %H:%M:%S")}
        if cfg.SWEEP_SAVE_FIELDS and i > 0:
            rec["fields"] = field_metrics_one(ctx, t, i)
        done[k] = rec
        save_progress(ctx, prog)
        if cfg.SWEEP_REOPEN_EVERY and (n + 1) % cfg.SWEEP_REOPEN_EVERY == 0 and n + 1 < len(todo):
            # close + reopen the project: releases the desktop's memory held for loaded solutions/fields
            # (the 22:21 freeze on 2026-10-05 came hours into one long session)
            continue_project(ctx, quiet=True)
        ctx.log("Variation %d/%d done in %.1f min: %s" % (n + 1, len(todo), rec["minutes"],
                ", ".join("%s %+.4f mN.m" % (q, 1e3 * v) for q, v in sorted(vals.items()))))
    ctx.set_var(ROT_VAR, "%gdeg" % cfg.THETA_START)
    ctx.set_var("Iamp", "%gA" % cfg.SWEEP_I)
    ctx.log("Stepwise sweep complete: all %d variations solved" % len(todo))


def cols_from_progress(ctx, current):
    """Rebuild {theta: [...], quantity: [...]} (SI) for one current from sweep_progress.json. Falls back to the
    exported report when the sweep was solved by Optimetrics (no progress file)."""
    if not os.path.isfile(_progress_path(ctx)):
        import rotor_analysis
        name = "Torque_Iplus" if current > 0 else "Torque_Iminus"
        ctx.log("No sweep_progress.json (Optimetrics-solved project) - using %s.csv" % name)
        return rotor_analysis.read_report_csv(os.path.join(ctx.results_dir(), name + ".csv"))
    thetas, _ = sweep_points(ctx.cfg)
    done = load_progress(ctx)["done"]
    cols = {"theta": []}
    for t in thetas:
        r = done.get(_key(t, current))
        if r is None:
            raise StageError("sweep_progress.json has no result for rot_angle %g deg, Iamp %g A" % (t, current))
        cols["theta"].append(t)
        for q, v in r["values_SI"].items():
            cols.setdefault(q, []).append(v)
    return cols


def st_analyze(ctx, geo):
    if ctx.cfg.ROTOR_SWEEP and ctx.cfg.SWEEP_MODE == "stepwise":
        _analyze_stepwise(ctx)
        ctx.log("Solve accepted: every variation solved without error-level messages")
        return
    before = _messages(ctx) or []
    if ctx.cfg.ROTOR_SWEEP:
        # Optimetrics setups are solved through the Optimetrics module (oDesign.Analyze("ParametricSetup1")
        # failed on 2026-10-05 with "Solution 'ParametricSetup1' was not found").
        oO = ctx.design.GetModule("Optimetrics")
        try:
            names = [str(x) for x in oO.GetSetupNames()]
        except Exception:
            names = []
        ctx.log("Optimetrics setups in the design: %s" % (names or "(list not available)"))
        target = "ParametricSetup1" if not names or "ParametricSetup1" in names else names[0]
        ctx.log("Solving Optimetrics %s ... (this blocks until all variations are solved)" % target)
        oO.SolveSetup(target)
    else:
        ctx.log("Analyze Setup1 ... (this blocks until the solve ends)")
        ctx.design.Analyze("Setup1")
    problems = _solve_problems(ctx, before)
    try:
        ctx.log("Valid solutions: %s" % [str(x) for x in ctx.design.GetModule("Solutions").GetValidISolutionList()])
    except Exception:
        pass
    if problems:
        raise StageError("Solve NOT accepted: " + " | ".join(problems))
    ctx.log("Solve accepted: no error-level messages, Setup1 solution present")


def st_export(ctx, geo):
    d = ctx.results_dir()
    oR = ctx.design.GetModule("ReportSetup")
    for name in ctx.state["objects"].get("reports", []):
        path = os.path.join(d, "%s.csv" % name)
        try:
            oR.ExportToFile(name, path)
        except Exception as e:
            raise StageError("Export of report %s failed (%s)" % (name, e))
        rows = 0
        try:
            with open(path) as f:
                rows = sum(1 for _ in f) - 1
        except Exception:
            pass
        if rows < 1:
            raise StageError("Report %s exported no data rows - the solve did not produce results" % name)
        ctx.log("Exported %s (%d data rows)" % (path, rows))
        if name == "PhaseCurrents":
            check_currents(ctx, path)
    if ctx.cfg.SYNC_3PH:
        sync_summary(ctx)
    elif ctx.cfg.ROTOR_SWEEP:
        rotor_sweep_summary(ctx)


def sync_summary(ctx):
    import rotor_analysis
    cfg = ctx.cfg
    d = ctx.results_dir()
    sy = ctx.state.get("sync") or {}
    if not sy:
        psi, fit, src = baseline_phase(ctx)
        sy = {"psi": psi, "fit": fit, "source": src}
    if cfg.SWEEP_MODE == "stepwise":
        cols = cols_from_progress(ctx, cfg.SWEEP_I)
    else:
        cols = rotor_analysis.read_report_csv(os.path.join(d, "Torque_Iplus.csv"))
    rows, s, warn = rotor_analysis.analyse_sync(cols, sy["fit"], sy["psi"], cfg.SYNC_IPK, cfg.POLES,
                                                cfg.PHASE_DEG, cfg.PHASE_ROT_MECH)
    rotor_analysis.write_csv(os.path.join(d, "sync_3ph_table.csv"), rows)
    with open(os.path.join(d, "sync_3ph_summary.txt"), "w") as f:
        f.write("Profile %s  project %s  baseline %s\n" % (cfg.PROFILE, cfg.PROJECT_NAME, sy["source"]))
        for k in s:
            f.write("%s = %s\n" % (k, s[k]))
        for w in warn:
            f.write("WARNING: %s\n" % w)
    for r in rows:
        ctx.log("theta %6.3f deg: Ia %+.3f Ib %+.3f Ic %+.3f A; T solved %+.4f mN.m (copper) / %+.4f (rotor), "
                "predicted %+.4f mN.m" % (r["theta_mech_deg"], r["I_A_A"], r["I_B_A"], r["I_C_A"],
                                          1e3 * r["T_solved_copper_Nm"], 1e3 * r.get("T_solved_rotor_Nm", float("nan")),
                                          1e3 * r["T_pred_Nm"]))
    ctx.log("SYNC RESULT: mean torque %.4f mN.m solved vs %.4f predicted (%+.2f%%), ideal 1.5*K1*Ipk = %.4f mN.m; "
            "ripple %.1f%% solved / %.1f%% predicted; superposition check %s"
            % (1e3 * s["T_solved_copper_mean_Nm"], 1e3 * s["T_pred_mean_Nm"], s["mean_torque_error_pct"],
               1e3 * s["T_ideal_1p5_K1_Ipk_Nm"], s["ripple_solved_pct"], s["ripple_pred_pct"],
               s["superposition_check"]))
    for w in warn:
        ctx.log("WARNING: " + w, 1)


def rotor_sweep_summary(ctx):
    """Torque reciprocity -> dLam/dtheta, back-EMF, k_t, cogging; optional B metrics per variation."""
    import rotor_analysis
    cfg = ctx.cfg
    d = ctx.results_dir()
    if cfg.SWEEP_MODE == "stepwise":
        plus = cols_from_progress(ctx, cfg.SWEEP_I)
        minus = cols_from_progress(ctx, -cfg.SWEEP_I) if cfg.SWEEP_MINUS_I else None
    else:
        plus = rotor_analysis.read_report_csv(os.path.join(d, "Torque_Iplus.csv"))
        minus = rotor_analysis.read_report_csv(os.path.join(d, "Torque_Iminus.csv")) if cfg.SWEEP_MINUS_I else None
    n = len(plus["theta"])
    expect = int(round((cfg.THETA_STOP - cfg.THETA_START) / cfg.THETA_STEP)) + 1
    if n != expect:
        raise StageError("Torque export has %d rotor angles, expected %d - some variations did not solve" % (n, expect))
    rows, s, warn = rotor_analysis.analyse(plus, minus, cfg.SWEEP_I, cfg.POLES, cfg.RPM)
    rotor_analysis.write_csv(os.path.join(d, "rotor_sweep_table.csv"), rows)
    with open(os.path.join(d, "rotor_sweep_summary.txt"), "w") as f:
        f.write("Profile %s  project %s\n" % (cfg.PROFILE, cfg.PROJECT_NAME))
        f.write("Geometry: air gap %.3f mm, back iron %.2f mm, magnet centre radius %.2f mm\n"
                % (cfg.AIR_GAP, cfg.BACK_IRON_THICK, cfg.MAG_CENTRE_R))
        if cfg.REAR_STEEL_GAP:
            f.write("Rear steel: gap %.3f mm, thickness %.2f mm\n" % (cfg.REAR_STEEL_GAP, cfg.REAR_STEEL_THICK))
        if cfg.LOWER_PM_GAP:
            f.write("Lower PM rotor (Rev1-D R1): gap %.3f mm, plate %.2f mm, polarity %s, face relation %s, face A %s\n"
                    % (cfg.LOWER_PM_GAP, cfg.LOWER_PLATE_THICK, cfg.LOWER_POLARITY, cfg.R1_FACE_RELATION,
                       "modelled" if cfg.LOWER_BACK_ARRAY else "not modelled"))
        for k in s:
            f.write("%s = %s\n" % (k, s[k]))
        for w in warn:
            f.write("WARNING: %s\n" % w)
    for r in rows:
        ctx.log("theta %6.3f deg (elec %6.1f): T(+I) %+.4f mN.m, dLam/dtheta %+.5f mWb/rad, e %+.4f V at %g rpm "
                "(Maxwell sign)" % (r["theta_mech_deg"], r["theta_elec_deg"], 1e3 * r["T_rotor_plus_Nm"],
                                    1e3 * r["dLam_dtheta_Wb_per_rad"], r["emf_V_at_rpm_maxwell_sign"], cfg.RPM))
    ctx.log("RESULT (board 1, %s): K1 = %.5f N.m/A (= dLam/dtheta peak), PM flux linkage peak %.4f mWb, "
            "|E1| = %.4f V peak / %.4f V rms at %g rpm, phase of k = %.1f deg elec; ideal fundamental 3-phase "
            "Tavg at optimum current phasing = %.4f N.m per A peak"
            % (cfg.PHASES[0], s["K1_dLam_dtheta_peak_Wb_per_rad"], 1e3 * s["Lam1_PM_flux_linkage_peak_Wb"],
               s["E1_peak_V_at_rpm"], s["E1_rms_V_at_rpm"], cfg.RPM, s["phase_of_k_elec_deg"],
               s["Tavg_ideal_fundamental_3ph_optimum_phasing_Nm_per_Apk"]))
    ctx.log("Polarity (Maxwell convention): %s" % s["polarity_maxwell_convention"])
    ctx.log("Sign convention: %s" % s["emf_sign_convention"])
    for k in ("cogging_plus_reluctance_max_abs_Nm", "action_reaction_mismatch_max_pct",
              "full_period_repeat_error_pct", "half_wave_antisymmetry_error_pct", "H3_over_H1_pct", "H5_over_H1_pct"):
        if k in s:
            ctx.log("Quality: %s = %.4g" % (k, s[k]))
    for w in warn:
        ctx.log("WARNING: " + w, 1)
    if cfg.SWEEP_SAVE_FIELDS:
        if cfg.SWEEP_MODE == "stepwise" and os.path.isfile(_progress_path(ctx)):
            done = load_progress(ctx)["done"]
            with open(os.path.join(d, "rotor_field_metrics.csv"), "w") as f:
                f.write(",".join(FIELD_COLS) + "\n")
                for t in plus["theta"]:
                    fm = done.get(_key(t, cfg.SWEEP_I), {}).get("fields") or {}
                    f.write("%g," % t + ",".join(str(fm.get(c, "")) for c in FIELD_COLS[1:]) + "\n")
        else:
            field_metrics(ctx, plus["theta"])


FIELD_COLS = ("theta_deg", "steel_Bmax_T", "gap_mean_absBz_T", "gap_Bmax_T", "plate_Bmax_T", "gap_Fz_upper_rotor_N")


def field_metrics_one(ctx, theta, current):
    """Field metrics of the variation just solved (nominal design point)."""
    rows = field_metrics(ctx, [theta], current, write=False)
    if not rows:
        return {}
    return dict(zip(FIELD_COLS[1:], rows[0][1:]))


def field_metrics(ctx, thetas, current=None, write=True):
    """Per rotor angle (+I): max |B| in the rotor steel, mean |Bz| and max |B| on the mid-gap sheet."""
    cfg = ctx.cfg
    oF = ctx.design.GetModule("FieldsReporter")
    sol = "Setup1 : LastAdaptive"
    sheet = ctx.state["objects"].get("gap_sheet", {}).get("name", "GapMid")
    steel = (ctx.state["objects"].get("rotor") or {}).get("steel", ["RotorSteel"])[0]

    def ev(build, var):
        try:
            oF.CalcStack("clear")
            build()
            for args in ((sol, var, "Fields"), (sol, var)):
                try:
                    oF.ClcEval(*args)
                    break
                except Exception:
                    continue
            v = oF.GetTopEntryValue(sol, var)
            oF.CalcStack("clear")
            return float(str(v[0]).split()[0])
        except Exception as e:
            ctx.log("Field metric failed (%s)" % e, 1)
            return None

    def max_b(geom, kind):
        def b():
            oF.EnterQty("B")
            oF.CalcOp("Mag")
            (oF.EnterVol if kind == "vol" else oF.EnterSurf)(geom)
            oF.CalcOp("Maximum")
        return b

    def mean_abs_bz(geom):
        def b():
            oF.EnterQty("B")
            oF.CalcOp("ScalarZ")
            oF.CalcOp("Abs")
            oF.EnterSurf(geom)
            oF.CalcOp("Integrate")
            oF.EnterScalar(1.0)
            oF.EnterSurf(geom)
            oF.CalcOp("Integrate")
            oF.CalcOp("/")
        return b

    def fz_upper(geom):
        # Maxwell stress on the mid-gap plane, outward normal of the region ABOVE it = -z:
        # Fz(upper rotor) = -int (Bz^2 - Bx^2 - By^2)/(2 mu0) dA = -int (2 Bz^2 - |B|^2)/(2 mu0) dA  (negative = pulled
        # down toward the board / lower rotor). Plane limited to the magnet annulus -> an estimate.
        def b():
            oF.EnterQty("B")
            oF.CalcOp("ScalarZ")
            oF.CalcStack("push")
            oF.CalcOp("*")
            oF.EnterScalar(2.0)
            oF.CalcOp("*")
            oF.EnterQty("B")
            oF.CalcOp("Mag")
            oF.CalcStack("push")
            oF.CalcOp("*")
            oF.CalcOp("-")
            oF.EnterScalar(-1.0 / (2 * 4e-7 * 3.141592653589793))
            oF.CalcOp("*")
            oF.EnterSurf(geom)
            oF.CalcOp("Integrate")
        return b

    plate = ((ctx.state["objects"].get("rotor") or {}).get("lower") or {}).get("plate")
    out = [FIELD_COLS]
    for t in thetas:
        var = [ROT_VAR + ":=", "%gdeg" % t, "Iamp:=", "%gA" % (cfg.SWEEP_I if current is None else current)]
        vals = (ev(max_b(steel, "vol"), var), ev(mean_abs_bz(sheet), var), ev(max_b(sheet, "surf"), var),
                ev(max_b(plate, "vol"), var) if plate else None, ev(fz_upper(sheet), var))
        out.append(tuple(["%g" % t] + ["" if v is None else "%.5g" % v for v in vals]))
        ctx.log("Fields theta %g deg: steel |B|max %s T, mid-gap mean|Bz| %s T, mid-gap |B|max %s T%s, axial force on "
                "the upper rotor ~%s N (Maxwell stress on the gap sheet; negative = attraction toward the board)"
                % (t, out[-1][1], out[-1][2], out[-1][3],
                   (", R1 shared plate |B|max %s T" % out[-1][4]) if plate else "", out[-1][5]))
    if not write:
        return out[1:]
    with open(os.path.join(ctx.results_dir(), "rotor_field_metrics.csv"), "w") as f:
        for r in out:
            f.write(",".join(r) + "\n")
    return out[1:]


def check_currents(ctx, path):
    """Numeric acceptance: the solved winding currents must follow the requested source."""
    import math
    cfg = ctx.cfg
    if cfg.SOLUTION_TYPE != "Transient" or cfg.IPK <= 0:
        return
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip()]
    head = [h.strip().strip('"') for h in lines[0].split(",")]
    tscale = 1e-6 if "[us]" in head[0] else (1e-3 if "[ms]" in head[0] else (1e-9 if "[ns]" in head[0] else 1.0))
    fe = cfg.RPM / 60.0 * (cfg.POLES // 2)
    worst = None
    for col in range(1, len(head)):
        iscale = 1e-3 if "[mA]" in head[col] else (1e-6 if "[uA]" in head[col] else 1.0)
        net = [n for n in cfg.PHASES if "Phase%s" % n[-1] in head[col]]
        ph = cfg.PHASE_DEG[net[0]] if net else 0.0
        for row in lines[1:]:
            v = row.split(",")
            t = float(v[0]) * tscale
            want = cfg.IPK * math.sin(2 * math.pi * fe * t + math.radians(ph))
            got = float(v[col]) * iscale
            if abs(want) > 0.02 * cfg.IPK:
                err = abs(got - want) / abs(want)
                worst = err if worst is None else max(worst, err)
                ctx.log("Current check %s t=%.6g s: requested %.5g A, solved %.5g A" % (head[col], t, want, got))
    if worst is None:
        ctx.log("Current check: no sample with a significant requested current", 1)
    elif worst > 0.05:
        raise StageError("Solved phase currents do not match the requested source (worst error %.0f%%) - "
                         "the winding was not driven" % (100 * worst))
    else:
        ctx.log("Current check passed: solved currents match the source within %.1f%%" % (100 * worst))


FUNCS = {"project": st_project, "stator": st_stator, "rotor": st_rotor, "region_band": st_region_band,
         "excitation": st_excitation, "solver_setup": st_solver_setup, "validate": st_validate,
         "analyze": st_analyze, "export": st_export}


# ------------------------------------------------------------------------------------ runner
def _ckpt_dir(ctx):
    d = os.path.join(ctx.results_dir(), "checkpoints")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def _ckpt_paths(ctx, stage):
    base = os.path.join(_ckpt_dir(ctx), "%02d_%s" % (STAGES.index(stage) + 1, stage))
    return base + ".aedt", base + "_state.json"


def checkpoint(ctx, stage):
    """After a SUCCESSFUL stage: save the working project and copy it (+ state) as that stage's checkpoint."""
    ctx.project.Save()
    ctx.save_state()
    aedt, js = _ckpt_paths(ctx, stage)
    shutil.copyfile(ctx.project_path(), aedt)
    shutil.copyfile(ctx.state_path(), js)
    ctx.log("Checkpoint saved: %s" % aedt)


def restore(ctx, last_ok_stage, files=None):
    """Discard the working project and reopen the checkpoint of the last successful stage."""
    cfg = ctx.cfg
    aedt, js = files or _ckpt_paths(ctx, last_ok_stage)
    if not os.path.isfile(aedt):
        raise StageError("No checkpoint for stage '%s' (%s) - start again from 'project'" % (last_ok_stage, aedt))
    try:
        ctx.desktop.CloseProject(cfg.PROJECT_NAME)      # closes WITHOUT saving the partial work
    except Exception:
        pass
    lock = ctx.project_path() + ".lock"
    if os.path.isfile(lock):
        os.remove(lock)
    shutil.copyfile(aedt, ctx.project_path())
    shutil.copyfile(js, ctx.state_path())
    ctx.project = ctx.desktop.OpenProject(ctx.project_path())
    ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    ctx.attach_design()
    ctx.load_state()
    ctx.log("Restored checkpoint after stage '%s'; stages done: %s"
            % (last_ok_stage, ", ".join(ctx.state.get("stages_done", []))))


def _last_board_ckpt(ctx):
    for k in range(ctx.cfg.N_BOARDS, 0, -1):
        aedt, js = _board_ckpt_paths(ctx, k)
        if os.path.isfile(aedt) and os.path.isfile(js):
            return k, (aedt, js)
    return None


def continue_project(ctx, quiet=False):
    """Reopen the WORKING project as it is (after a crash in a stepwise sweep) and continue."""
    cfg = ctx.cfg
    if quiet:
        ctx.project.Save()
    try:
        ctx.desktop.CloseProject(cfg.PROJECT_NAME)
    except Exception:
        pass
    lock = ctx.project_path() + ".lock"
    if os.path.isfile(lock):
        os.remove(lock)
    ctx.project = ctx.desktop.OpenProject(ctx.project_path())
    ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    ctx.attach_design()
    ctx.load_state()
    n = len(load_progress(ctx)["done"])
    if quiet:
        ctx.log("Project closed and reopened to release memory (%d variations solved so far)" % n)
        return
    ctx.log("Continuing the stepwise sweep in the working project (no rollback): %d variations already solved" % n)


def run(ctx, start_at="project", stop_after="export"):
    if start_at not in STAGES or stop_after not in STAGES:
        raise ValueError("Stages are: " + ", ".join(STAGES))
    geo = pcb_geometry.load()
    if ctx.cfg.BUILD_ONLY and STAGES.index(stop_after) > STAGES.index("validate"):
        stop_after = "validate"
    todo = STAGES[STAGES.index(start_at):STAGES.index(stop_after) + 1]
    if start_at == "analyze" and ctx.cfg.ROTOR_SWEEP and ctx.cfg.SWEEP_MODE == "stepwise" \
            and os.path.isfile(_progress_path(ctx)) and os.path.isfile(ctx.project_path()):
        continue_project(ctx)       # keep the variations already solved; do NOT roll back to the checkpoint
    elif start_at == "stator" and ctx.cfg.STACK_SERIES and _last_board_ckpt(ctx):
        k, files = _last_board_ckpt(ctx)
        restore(ctx, "stator (board %d)" % k, files)
    elif start_at != "project":
        restore(ctx, STAGES[STAGES.index(start_at) - 1])
        missing = [s for s in STAGES[:STAGES.index(start_at)] if s not in ctx.state.get("stages_done", [])]
        if missing:
            raise StageError("Cannot start at '%s': earlier stages not done: %s" % (start_at, ", ".join(missing)))
    for s in todo:
        ctx.log("=== STAGE %s ===" % s)
        try:
            FUNCS[s](ctx, geo)
        except Exception as e:
            ctx.log("STAGE %s FAILED: %s" % (s, e), 2)
            ctx.log("The project was NOT saved after the failure (partial objects discarded on resume). "
                    "Fix the cause, then set START_AT = '%s'; it restores the checkpoint of the previous "
                    "stage first." % s, 2)
            raise
        ctx.state.setdefault("stages_done", [])
        if s not in ctx.state["stages_done"]:
            ctx.state["stages_done"].append(s)
        checkpoint(ctx, s)
        ctx.log("Stage %s OK" % s)
    ctx.log("Pipeline finished: %s" % " -> ".join(todo))
