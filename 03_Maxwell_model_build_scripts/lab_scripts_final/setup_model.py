# -*- coding: utf-8 -*-
"""Region, band, excitations, motion, mesh, solver setup and reports."""
from aedt_api import mm, StageError

TAG = {"PHASE_A": "A", "PHASE_B": "B", "PHASE_C": "C"}
ROT_VAR = "rot_angle"      # rotor angle design variable ("theta" is reserved in AEDT)


def create_region(ctx, plus_y_zero):
    p = mm(ctx.cfg.REGION_PADDING)
    py = mm(0.0) if plus_y_zero else p
    ctx.editor.CreateRegion(
        ["NAME:RegionParameters",
         "+XPaddingType:=", "Absolute Offset", "+XPadding:=", p, "-XPaddingType:=", "Absolute Offset", "-XPadding:=", p,
         "+YPaddingType:=", "Absolute Offset", "+YPadding:=", py, "-YPaddingType:=", "Absolute Offset", "-YPadding:=", p,
         "+ZPaddingType:=", "Absolute Offset", "+ZPadding:=", p, "-ZPaddingType:=", "Absolute Offset", "-ZPadding:=", p],
        ["NAME:Attributes", "Name:=", "Region", "Flags:=", "Wireframe#", "Color:=", "(143 175 143)",
         "Transparency:=", 0, "PartCoordinateSystem:=", "Global", "UDMId:=", "", "MaterialValue:=", "\"vacuum\"",
         "SurfaceMaterialValue:=", "\"\"", "SolveInside:=", True, "IsMaterialEditable:=", True,
         "UseMaterialAppearance:=", False, "IsLightweight:=", False])


def assign_excitations(ctx, conductors, leads):
    """conductors: {net: object}, leads: {net: lead geometry}. One In + one Out coil terminal per phase."""
    cfg = ctx.cfg
    oB = ctx.design.GetModule("BoundarySetup")
    windings = {}
    for net, obj in conductors.items():
        tag = TAG[net]
        terms = []
        for key, suffix, point_out in (("face_in", "In", False), ("face_out", "Out", True)):
            fx, fy, fz = leads[net][key]
            body = leads[net].get("obj_in" if suffix == "In" else "obj_out", obj)
            fid = ctx.editor.GetFaceByPosition(["NAME:FaceParameters", "BodyName:=", body, "XPosition:=", mm(fx),
                                                "YPosition:=", mm(fy), "ZPosition:=", mm(fz)])
            name = "Phase%s_%s" % (tag, suffix)
            oB.AssignCoilTerminal(["NAME:" + name, "Faces:=", [int(fid)], "Conductor number:=", "1",
                                   "Point out of terminal:=", point_out])
            terms.append(name)
        if cfg.BUILD_ONLY:
            cur = "I_%s" % tag                 # design variable (0 A in the frozen build; set by each test)
        elif cfg.SOLUTION_TYPE == "Magnetostatic" and cfg.SYNC_3PH:
            cur = "Isync*cos(%d*%s + phi_sync + (%gdeg))" % (cfg.POLES // 2, ROT_VAR, cfg.PHASE_DEG[net])
        elif cfg.SOLUTION_TYPE == "Magnetostatic" and cfg.ROTOR_SWEEP:
            cur = "Iamp"
        elif cfg.SOLUTION_TYPE == "Magnetostatic":
            first = sorted(conductors)[0]
            cur = "%gA" % (cfg.MAGNETOSTATIC_I if net == first else -cfg.MAGNETOSTATIC_I / 2.0)
        else:
            cur = "Ipk*sin(2*pi*fe*Time + (%g)*pi/180)" % cfg.PHASE_DEG[net]
        w = "Phase%s" % tag
        oB.AssignWindingGroup(["NAME:" + w, "Type:=", "Current", "IsSolid:=", True, "Current:=", cur,
                               "Resistance:=", "0ohm", "Inductance:=", "0nH", "Voltage:=", "0mV",
                               "ParallelBranchesNum:=", "1", "Phase:=", "0deg"])
        oB.AddWindingTerminals(w, terms)
        if cfg.is_aphi():
            # A-Phi: source applied at the first terminal, last terminal is the reference -> make it explicit
            oB.OrderCoilTerminals(["Name:" + w] + terms)
            ctx.log("A-Phi terminal order for %s: %s" % (w, " -> ".join(terms)))
        windings[net] = w
        ctx.log("Winding %s: terminals %s, current %s" % (w, terms, cur))
    return windings


def set_eddy(ctx, objs, flag, label):
    if not objs:
        return
    vec = ["NAME:EddyEffectVector"]
    for o in objs:
        vec.append(["NAME:Data", "Object Name:=", o, "Eddy Effect:=", flag, "Displacement Current:=", False])
    try:
        ctx.design.GetModule("BoundarySetup").SetEddyEffect(["NAME:Eddy Effect Setting", vec])
        ctx.log("Eddy effect %s on %s" % ("ON" if flag else "OFF", label))
    except Exception as e:
        ctx.log("Eddy setting for %s skipped (%s)" % (label, e), 1)


def assign_motion(ctx, band):
    ctx.design.GetModule("ModelSetup").AssignBand(
        ["NAME:Data", "Move Type:=", "Rotate", "Coordinate System:=", "Global", "Axis:=", "Z", "Is Positive:=", True,
         "InitPos:=", "0deg", "HasRotateLimit:=", False, "NonCylindrical:=", False,
         "Consider Mechanical Transient:=", False, "Angular Velocity:=", "%grpm" % ctx.cfg.RPM, "Objects:=", [band]])
    ctx.log("Motion: band %s rotates about +Z at %g rpm" % (band, ctx.cfg.RPM))


def mesh_ops(ctx, band, magnets, copper, gap_layer=None):
    m = ctx.design.GetModule("MeshSetup")
    if isinstance(gap_layer, dict):
        ctx.log("Air-gap mesh: %s, at most %d elements added per layer" % (", ".join(
            "%s max %.3f mm" % kv for kv in sorted(gap_layer.items())), ctx.cfg.MESH_GAP_MAX_ELEMS))
    elif gap_layer:
        ctx.log("Air-gap mesh: max element length %.3f mm (gap %.3f mm), at most %d elements added"
                % (ctx.cfg.gap_mesh_max(), ctx.cfg.AIR_GAP, ctx.cfg.MESH_GAP_MAX_ELEMS))
    if isinstance(gap_layer, dict):        # Rev1-D: {layer: max length} -> one op per gap layer
        gap_ops = [("Len_" + n, [n], L) for n, L in sorted(gap_layer.items())]
    else:
        gap_ops = [("Len_Gap", [gap_layer] if gap_layer else [], ctx.cfg.gap_mesh_max())]
    for name, objs, L in tuple(gap_ops) + ((
                          ("Len_Band", [band] if band else [], ctx.cfg.MESH_BAND_MAX),
                          ("Len_Magnets", magnets, ctx.cfg.MESH_MAGNET_MAX),
                          ("Len_Copper", copper, ctx.cfg.MESH_COPPER_MAX))):
        if objs and L > 0:
            cap = ctx.cfg.MESH_GAP_MAX_ELEMS if name.startswith(("Len_Gap", "Len_GapLayer")) else 0
            try:
                m.AssignLengthOp(["NAME:" + name, "RefineInside:=", True, "Enabled:=", True, "Objects:=", objs,
                                  "RestrictElem:=", bool(cap), "NumMaxElem:=", str(cap or 1000),
                                  "RestrictLength:=", True,
                                  "MaxLength:=", mm(L)])
            except Exception as e:
                ctx.log("Mesh op %s skipped (%s)" % (name, e), 1)


def assign_torques(ctx, rotor, copper):
    """Torque about +Z (global origin): virtual work on the rotor parts, Lorentz on the stator copper."""
    oP = ctx.design.GetModule("MaxwellParameterSetup")
    rot = list(rotor["magnets"]) + list(rotor["steel"])
    oP.AssignTorque(["NAME:Torque_Rotor", "Is Virtual:=", True, "Coordinate System:=", "Global", "Axis:=", "Z",
                     "Is Positive:=", True, "Objects:=", rot])
    ctx.log("Torque_Rotor: virtual torque about +Z on %d rotor objects (magnets + steel)" % len(rot))
    made = ["Torque_Rotor"]
    if copper and len(copper) > 1:
        for obj in copper:                      # per-phase Lorentz torque (e.g. PhaseB1_Cu -> Torque_Cu_B)
            n = "Torque_Cu_%s" % obj[len("Phase")]
            try:
                oP.AssignTorque(["NAME:" + n, "Is Virtual:=", False, "Coordinate System:=", "Global", "Axis:=", "Z",
                                 "Is Positive:=", True, "Objects:=", [obj]])
                made.append(n)
            except Exception as e:
                ctx.log("Per-phase torque %s not assigned (%s)" % (n, e), 1)
    if copper:
        try:
            oP.AssignTorque(["NAME:Torque_Cu", "Is Virtual:=", False, "Coordinate System:=", "Global",
                             "Axis:=", "Z", "Is Positive:=", True, "Objects:=", list(copper)])
            made.append("Torque_Cu")
            ctx.log("Torque_Cu: Lorentz torque about +Z on %s (reaction; should equal -Torque_Rotor)" % copper)
        except Exception as e:
            ctx.log("Lorentz torque on copper not assigned (%s) - action/reaction check unavailable" % e, 1)
    return made


def parametric_sweep(ctx):
    cfg = ctx.cfg
    oO = ctx.design.GetModule("Optimetrics")
    n = int(round((cfg.THETA_STOP - cfg.THETA_START) / cfg.THETA_STEP))
    tdata = ("LIN %gdeg %gdeg %gdeg" % (cfg.THETA_START, cfg.THETA_STOP, cfg.THETA_STEP)) if n > 0 \
        else "%gdeg" % cfg.THETA_START
    idata = ("LIN %gA %gA %gA" % (-cfg.SWEEP_I, cfg.SWEEP_I, 2 * cfg.SWEEP_I)) if cfg.SWEEP_MINUS_I \
        else "%gA" % cfg.SWEEP_I
    oO.InsertSetup("OptiParametric", [
        "NAME:ParametricSetup1", "IsEnabled:=", True,
        ["NAME:ProdOptiSetupDataV2", "SaveFields:=", bool(cfg.SWEEP_SAVE_FIELDS), "CopyMesh:=", False,
         "SolveWithCopiedMeshOnly:=", False],
        ["NAME:StartingPoint"], "Sim. Setups:=", ["Setup1"],
        ["NAME:Sweeps",
         ["NAME:SweepDefinition", "Variable:=", ROT_VAR, "Data:=", tdata, "OffsetF1:=", False, "Synchronize:=", 0],
         ["NAME:SweepDefinition", "Variable:=", "Iamp", "Data:=", idata, "OffsetF1:=", False, "Synchronize:=", 0]],
        ["NAME:Sweep Operations"], ["NAME:Goals"]])
    nvar = (n + 1) * (2 if cfg.SWEEP_MINUS_I else 1)
    ctx.log("ParametricSetup1: theta %s x Iamp %s = %d magnetostatic solves, fields %s"
            % (tdata, idata, nvar, "saved" if cfg.SWEEP_SAVE_FIELDS else "not saved"))


def torque_reports(ctx, torques):
    cfg = ctx.cfg
    oR = ctx.design.GetModule("ReportSetup")
    ys = ["%s.Torque" % t for t in torques]
    currents = [("Torque_Iplus", "%gA" % cfg.SWEEP_I)]
    if cfg.SWEEP_MINUS_I:
        currents.append(("Torque_Iminus", "%gA" % -cfg.SWEEP_I))
    made = []
    for name, iv in currents:
        fam = [ROT_VAR + ":=", ["All"], "Iamp:=", [iv]]
        err = None
        for ctxarg in ([], ["Context:=", "Torque_Rotor"]):
            try:
                oR.CreateReport(name, "Magnetostatic", "Rectangular Plot", "Setup1 : LastAdaptive", ctxarg, fam,
                                ["X Component:=", ROT_VAR, "Y Component:=", ys])
                err = None
                break
            except Exception as e:
                err = e
        if err is not None:
            raise StageError("Required report %s could not be created (%s)" % (name, err))
        made.append(name)
        ctx.log("Report %s: %s vs %s at Iamp = %s" % (name, ", ".join(ys), ROT_VAR, iv))
    return made


def solver_setup(ctx, windings, has_band, rotor=None, copper=None):
    cfg = ctx.cfg
    oA = ctx.design.GetModule("AnalysisSetup")
    if cfg.SOLUTION_TYPE == "Magnetostatic":
        oA.InsertSetup("Magnetostatic", ["NAME:Setup1", "Enabled:=", True, "MaximumPasses:=", cfg.MS_MAX_PASSES,
                                         "MinimumPasses:=", min(2, cfg.MS_MAX_PASSES), "MinimumConvergedPasses:=", 1,
                                         "PercentRefinement:=", cfg.MS_PERCENT_REFINE, "SolveFieldOnly:=", False,
                                         "PercentError:=", 1, "SolveMatrixAtLast:=", bool(cfg.MS_MATRIX),
                                         "UseNonLinearIterNum:=", False, "UseIterativeSolver:=", False,
                                         "RelativeResidual:=", 1e-06, "NonLinearResidual:=", 0.001])
        if windings and cfg.MS_MATRIX:
            try:
                e = ["NAME:MatrixEntry"]
                for net in sorted(windings):
                    e.append(["NAME:MatrixEntry", "Source:=", windings[net], "NumberOfTurns:=", "1"])
                ctx.design.GetModule("MaxwellParameterSetup").AssignMatrix(["NAME:Inductance", e])
            except Exception as ex:
                ctx.log("Inductance matrix skipped (%s)" % ex, 1)
        ctx.log("Magnetostatic setup: %d passes, %d%% refinement, inductance matrix %s"
                % (cfg.MS_MAX_PASSES, cfg.MS_PERCENT_REFINE, "ON" if cfg.MS_MATRIX else "OFF"))
        if rotor:
            torques = assign_torques(ctx, rotor, copper or [])
            if cfg.ROTOR_SWEEP:
                if cfg.SWEEP_MODE == "optimetrics":
                    parametric_sweep(ctx)
                else:
                    ctx.log("Stepwise sweep: %s and Iamp set per variation at the analyze stage" % ROT_VAR)
                return torque_reports(ctx, torques)
        return []
    fe = cfg.RPM / 60.0 * (cfg.POLES // 2)
    period = 1000.0 / fe
    step = period / cfg.STEPS_PER_PERIOD
    stop = step * cfg.TRANSIENT_STEPS if cfg.TRANSIENT_STEPS else period * cfg.ELECTRICAL_PERIODS
    nsave = max(1, min(cfg.SAVE_FIELDS_EVERY, int(round(stop / step))))
    setup_args = ["NAME:Setup1", "Enabled:=", True, ["NAME:MeshLink", "ImportMesh:=", False],
                                 "NonlinearSolverResidual:=", "0.005", "TimeIntegrationMethod:=", 0,
                                 "StopTime:=", "%gms" % stop, "TimeStep:=", "%gms" % step, "OutputError:=", False,
                                 "UseControlProgram:=", False, "ControlProgramName:=", " ", "ControlProgramArg:=", " ",
                                 "CallCtrlProgAfterLastStep:=", False, "FastReachSteadyState:=", False,
                                 "AutoDetectSteadyState:=", False, "IsGeneralTransient:=", True,
                                 "IsHalfPeriodicTransient:=", False] + (
                     ["SaveFieldsType:=", "Every N Steps", "N Steps:=", str(nsave), "Steps From:=", "0ms",
                      "Steps To:=", "%gms" % stop] if cfg.SAVE_FIELDS else ["SaveFieldsType:=", "None"]) + [
                                 "UseNonLinearIterNum:=", False, "CacheSaveKind:=", "Count", "NumberSolveSteps:=", 1,
                                 "RangeStart:=", "0s", "RangeEnd:=", "0.1s"]
    if cfg.is_aphi():
        # native AEDT scripting name first; PyAEDT's internal identifier only as a fallback
        try:
            oA.InsertSetup("Transient APhi", setup_args)
            used = "Transient APhi"
        except Exception:
            oA.InsertSetup("TransientAPhiFormulation", setup_args)
            used = "TransientAPhiFormulation"
        ctx.log("A-Phi setup inserted with setup type '%s'" % used)
    else:
        oA.InsertSetup("Transient", setup_args)
    try:
        if "Setup1" not in [str(x) for x in oA.GetSetups()]:
            raise StageError("Setup1 was not created")
    except StageError:
        raise
    except Exception:
        pass
    ctx.log("Transient (%s) setup: fe %.3f Hz, stop %.4f ms, step %.5f ms (%d steps), fields %s"
            % (cfg.TRANSIENT_FORMULATION, fe, stop, step, int(round(stop / step)),
               ("every %d steps" % nsave) if cfg.SAVE_FIELDS else "not saved"))
    # (name, quantities, required). Required reports fail the stage if they cannot be created.
    reports = []
    if windings:
        ws = [windings[n] for n in sorted(windings)]
        reports.append(("BackEMF", ["InducedVoltage(%s)" % w for w in ws], True))
        reports.append(("PhaseCurrents", ["Current(%s)" % w for w in ws], True))
        reports.append(("FluxLinkage", ["FluxLinkage(%s)" % w for w in ws], False))
    if has_band:
        reports.append(("Torque", ["Moving1.Torque"], True))
        reports.append(("RotorPosition", ["Moving1.Position"], True))
    # AEDT 2025 R2: report type "Transient APhi" for A-Phi designs; solution name stays "Setup1 : Transient"
    rtype = "Transient APhi" if cfg.is_aphi() else "Transient"
    oR = ctx.design.GetModule("ReportSetup")
    made, missing = [], []
    for name, ys, required in reports:
        try:
            oR.CreateReport(name, rtype, "Rectangular Plot", "Setup1 : Transient", ["Domain:=", "Sweep"],
                            ["Time:=", ["All"]], ["X Component:=", "Time", "Y Component:=", ys])
            made.append(name)
            ctx.log("Report %s created (type %s): %s" % (name, rtype, ", ".join(ys)))
        except Exception as e:
            if required:
                missing.append("%s (%s)" % (name, e))
            else:
                ctx.log("Optional report %s not created (%s)" % (name, e), 1)
    if missing:
        raise StageError("Required reports could not be created: " + "; ".join(missing))
    return made
