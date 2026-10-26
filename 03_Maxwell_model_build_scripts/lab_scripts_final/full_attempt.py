# -*- coding: utf-8 -*-
"""REV0_FULL_SOLVE_ATTEMPT - deliberate feasibility test: solve the COMPLETE detailed Rev0 motor (5 boards x
3 phases + bridges + leads + 16 magnets + steel) at ONE rotor angle, magnetostatic, on a 16 GB lab PC.

Purpose (Olwethu, 2026-10-07): either an independent full-model cross-check of the board-by-board method, or
documented evidence of the computational limit (stage, time, RAM) for the conclusions/recommendations.

- Source: a COPY of REV0_FINAL_G100_T20_FROZEN.aedt (the frozen file is never opened). Each attempt gets its own
  project: REV0_FULL_SOLVE_ATTEMPT, then _A2, _A3 ... so earlier attempts and their logs are kept.
- One operating point: rot_angle = FULL_THETA, three-phase synchronous currents at SYNC_IPK with the current angle
  from the Phase-A baseline (same law as REF_ROTOR_MS_3PH): I_X = Ipk*cos(8*theta + phi_sync + PHASE_DEG[X]).
- Magnetostatic, MS_MAX_PASSES adaptive passes, inductance matrix OFF, no motion, no sweep, no field export.
- Torques: Torque_Rotor (virtual, magnets + steel), Torque_Cu (Lorentz, all copper), Torque_PCB1..5 (Lorentz per
  board, all three phases). Prediction per board = 1.5 * K1(d_k) * Ipk from the single-board fit (stack_sum).
- attempt_status.json is written (and copied to the shared results folder) BEFORE the solve starts, so a frozen
  PC still leaves the start time and model size on OneDrive. Watch Task Manager during the solve.
"""
import json
import os
import shutil
import time

import setup_model
from aedt_api import StageError
from setup_model import ROT_VAR
from stages import validate_geometry, _messages, _solve_problems

TAGS = {"PHASE_A": "A", "PHASE_B": "B", "PHASE_C": "C"}


def _ram_gb():
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return {"total_GB": round(m.ullTotalPhys / 2.0 ** 30, 2), "free_GB_now": round(m.ullAvailPhys / 2.0 ** 30, 2),
                "pagefile_total_GB": round(m.ullTotalPageFile / 2.0 ** 30, 2)}
    except Exception:
        return {}


def _write_status(ctx, shared_dir, status):
    p = os.path.join(ctx.results_dir(), "attempt_status.json")
    with open(p, "w") as f:
        json.dump(status, f, indent=1)
    try:
        dst = os.path.join(shared_dir, "results", ctx.cfg.PROJECT_NAME + "_results")
        if not os.path.isdir(dst):
            os.makedirs(dst)
        shutil.copy2(p, os.path.join(dst, "attempt_status.json"))
        lp = ctx.log_path()
        if os.path.isfile(lp):
            shutil.copy2(lp, os.path.join(dst, os.path.basename(lp)))
    except Exception as e:
        ctx.log("Could not copy the attempt status to the shared folder (%s)" % e, 1)


def locate_source(cfg, shared_dir):
    for c in (os.path.join(shared_dir, "frozen", cfg.FULL_SOURCE), os.path.join(cfg.SAVE_DIR, cfg.FULL_SOURCE)):
        if os.path.isfile(c):
            return c
    raise StageError("%s not found in %s - run run_REV0_FINAL.py first" % (cfg.FULL_SOURCE, os.path.join(shared_dir, "frozen")))


def baseline_psi(cfg, shared_dir):
    import rotor_analysis
    for d in (cfg.SAVE_DIR, os.path.join(shared_dir, "results")):
        p = os.path.join(d, cfg.BASELINE_PROJECT + "_results", "rotor_sweep_summary.txt")
        if os.path.isfile(p):
            return float(rotor_analysis.read_summary(p)["phase_of_k_elec_deg"]), p
    raise StageError("Baseline summary not found (needed for the current angle)")


def predictions(cfg, shared_dir):
    """Per-board 1.5*K1(d_k)*Ipk from the single-board exponential fit (stack_sum)."""
    import math
    import stack_sum
    pts = stack_sum.load_points(os.path.join(shared_dir, "results"))
    if len(pts) < 2:
        return None, "fewer than two single-board distances in results - no prediction"
    k, a, p0, p1, resid = stack_sum.fit_exp(pts)
    out = []
    for kb in range(cfg.N_BOARDS):
        d = cfg.AIR_GAP + kb * cfg.board_pitch()
        out.append(1.5 * math.exp(a - k * d) * cfg.SYNC_IPK)
    return out, "fit through %s mm, k_eff %.4f /mm" % ([p[0] for p in pts], k)


def run(ctx, shared_dir):
    import math
    cfg = ctx.cfg
    src = locate_source(cfg, shared_dir)
    base = cfg.PROJECT_NAME
    n = 1
    while os.path.exists(os.path.join(cfg.SAVE_DIR, cfg.PROJECT_NAME + ".aedt")) or \
            os.path.exists(os.path.join(cfg.SAVE_DIR, cfg.PROJECT_NAME + "_results", "attempt_status.json")) or \
            os.path.exists(os.path.join(shared_dir, "results", cfg.PROJECT_NAME + "_results", "attempt_status.json")):
        n += 1
        cfg.PROJECT_NAME = "%s_A%d" % (base, n)
    if not os.path.isdir(cfg.SAVE_DIR):
        os.makedirs(cfg.SAVE_DIR)
    dst = ctx.project_path()
    shutil.copyfile(src, dst)
    ctx.log("Attempt %d: copied %s -> %s (the frozen file is never opened)" % (n, src, dst))
    ctx.state = {"stages_done": [], "objects": {}, "profile": cfg.PROFILE, "source": src}
    status = {"attempt": n, "project": cfg.PROJECT_NAME, "source": src, "stage": "opening",
              "started": time.strftime("%Y-%m-%d %H:%M:%S"), "pc": os.environ.get("COMPUTERNAME", "?"),
              "cpu_count": os.cpu_count() if hasattr(os, "cpu_count") else None, "ram": _ram_gb(),
              "settings": {"rotor_angle_deg": cfg.FULL_THETA, "Ipk_A": cfg.SYNC_IPK, "max_passes": cfg.MS_MAX_PASSES,
                           "percent_refinement": cfg.MS_PERCENT_REFINE, "matrix": False, "motion": False}}
    _write_status(ctx, shared_dir, status)
    t_open = time.time()
    ctx.project = ctx.desktop.OpenProject(dst)
    ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    ctx.attach_design()
    try:
        ctx.desktop.EnableAutoSave(False)
    except Exception:
        pass
    status["open_seconds"] = round(time.time() - t_open, 1)

    try:
        solids = [str(o) for o in ctx.editor.GetObjectsInGroup("Solids")]
    except Exception:
        solids = [str(o) for o in (ctx.objects_present() or [])]
    mags = sorted(o for o in solids if o.startswith("Magnet_"))
    steel = [o for o in solids if o in ("RotorSteel", "BackIron", "Shaft")]
    copper = sorted(o for o in solids if (o.startswith("Phase") and o.endswith("_Cu")) or o.startswith("Bridge"))
    boards = {}
    for k in range(1, cfg.N_BOARDS + 1):
        boards[k] = ["Phase%s%d_Cu" % (TAGS[nt], k) for nt in cfg.PHASES]
        miss = [o for o in boards[k] if o not in solids]
        if miss:
            raise StageError("Not the REV0_FINAL model: %s missing" % miss)
    if len(mags) != cfg.POLES or not steel:
        raise StageError("Rotor not found in the copied model (%d magnets, steel %s)" % (len(mags), steel))
    status["model"] = {"solids": len(solids), "copper_objects": len(copper), "magnets": len(mags), "steel": steel}
    ctx.log("Model: %d solids; copper %d objects (15 board-phase strings + %d bridges); %d magnets; steel %s"
            % (len(solids), len(copper), len(copper) - 15, len(mags), steel))

    # operating point: synchronous three-phase currents at FULL_THETA (same law as REF_ROTOR_MS_3PH)
    psi, psi_src = baseline_psi(cfg, shared_dir)
    p = cfg.POLES // 2
    cur = {}
    for nt in cfg.PHASES:
        cur[nt] = cfg.SYNC_IPK * math.cos(math.radians(p * cfg.FULL_THETA - psi + cfg.PHASE_DEG[nt]))
        ctx.set_var("I_%s" % TAGS[nt], "%.6gA" % cur[nt])
    ctx.set_var(ROT_VAR, "%gdeg" % cfg.FULL_THETA)
    ctx.log("Operating point: rot_angle %g deg; I_A %+.4f, I_B %+.4f, I_C %+.4f A (Ipk %g A, phi_sync = -psi = %+.2f deg "
            "from %s)" % (cfg.FULL_THETA, cur["PHASE_A"], cur["PHASE_B"], cur["PHASE_C"], cfg.SYNC_IPK, -psi, psi_src))
    status["currents_A"] = dict((TAGS[k], round(v, 6)) for k, v in cur.items())

    setup_model.solver_setup(ctx, None, False)
    oP = ctx.design.GetModule("MaxwellParameterSetup")
    torques = []
    oP.AssignTorque(["NAME:Torque_Rotor", "Is Virtual:=", True, "Coordinate System:=", "Global", "Axis:=", "Z",
                     "Is Positive:=", True, "Objects:=", mags + steel])
    torques.append("Torque_Rotor")
    oP.AssignTorque(["NAME:Torque_Cu", "Is Virtual:=", False, "Coordinate System:=", "Global", "Axis:=", "Z",
                     "Is Positive:=", True, "Objects:=", copper])
    torques.append("Torque_Cu")
    for k in range(1, cfg.N_BOARDS + 1):
        oP.AssignTorque(["NAME:Torque_PCB%d" % k, "Is Virtual:=", False, "Coordinate System:=", "Global", "Axis:=", "Z",
                         "Is Positive:=", True, "Objects:=", boards[k]])
        torques.append("Torque_PCB%d" % k)
    ctx.log("Torques: %s" % ", ".join(torques))
    oR = ctx.design.GetModule("ReportSetup")
    ys = ["%s.Torque" % t for t in torques]
    err = None
    for ctxarg in ([], ["Context:=", "Torque_Rotor"]):
        try:
            oR.CreateReport("Torque_Full", "Magnetostatic", "Rectangular Plot", "Setup1 : LastAdaptive", ctxarg,
                            [ROT_VAR + ":=", ["All"]], ["X Component:=", ROT_VAR, "Y Component:=", ys])
            err = None
            break
        except Exception as e:
            err = e
    if err is not None:
        raise StageError("Report Torque_Full could not be created (%s)" % err)

    ok = validate_geometry(ctx, "Full motor")
    ctx.log("AEDT Validation Check returned %s" % ok)
    ctx.project.Save()
    status["stage"] = "solving (if this is the last status, the PC/AEDT stopped during the solve)"
    status["solve_started"] = time.strftime("%Y-%m-%d %H:%M:%S")
    status["ram_at_solve_start"] = _ram_gb()
    _write_status(ctx, shared_dir, status)
    ctx.log("=== SOLVE STARTED %s: full 5-board 3-phase motor, %d passes, matrix OFF. Watch Task Manager (RAM, "
            "pagefile) and screenshot near the limit; note the adaptive pass shown in the progress bar. ==="
            % (status["solve_started"], cfg.MS_MAX_PASSES))
    t0 = time.time()
    before = _messages(ctx) or []
    try:
        ctx.design.Analyze("Setup1")
    except Exception as e:
        status["stage"] = "FAILED in Analyze"
        status["error"] = str(e)
    minutes = round((time.time() - t0) / 60.0, 1)
    status["solve_minutes"] = minutes
    problems = _solve_problems(ctx, before)
    try:
        status["messages"] = [m.strip() for m in (_messages(ctx, 0) or [])][-40:]
    except Exception:
        pass
    try:
        mp = os.path.join(ctx.results_dir(), "mesh_stats.txt")
        ctx.design.GetModule("Solutions").ExportMeshStats("Setup1", "All", mp)
        status["mesh_stats_file"] = os.path.basename(mp)
    except Exception as e:
        ctx.log("Mesh statistics not exported (%s)" % e, 1)
    if problems or status.get("error"):
        status["stage"] = "FAILED after %.1f min" % minutes
        status["problems"] = problems
        _write_status(ctx, shared_dir, status)
        raise StageError("Full-motor solve not accepted after %.1f min: %s" % (minutes, problems or status.get("error")))
    ctx.project.Save()

    import rotor_analysis
    csv = os.path.join(ctx.results_dir(), "Torque_Full.csv")
    oR.ExportToFile("Torque_Full", csv)
    cols = rotor_analysis.read_report_csv(csv)
    val = dict((k, v[0]) for k, v in cols.items() if k != "theta")
    pred, how = predictions(cfg, shared_dir)
    lines = ["REV0 FULL-MOTOR SOLVE (attempt %d, %s): rot_angle %g deg, Ipk %g A, %d passes, %.1f min"
             % (n, cfg.PROJECT_NAME, cfg.FULL_THETA, cfg.SYNC_IPK, cfg.MS_MAX_PASSES, minutes)]
    tcu = val.get("Torque_Cu.Torque", float("nan"))
    trot = val.get("Torque_Rotor.Torque", float("nan"))
    lines.append("Torque on the rotor: %+.3f mN.m (virtual); copper reaction %+.3f mN.m (Lorentz, sign flipped: %+.3f)"
                 % (1e3 * trot, 1e3 * tcu, -1e3 * tcu))
    tot_pred = sum(pred) if pred else None
    for k in range(1, cfg.N_BOARDS + 1):
        t = val.get("Torque_PCB%d.Torque" % k, float("nan"))
        if pred:
            lines.append("  PCB%d: |T| %.3f mN.m solved vs %.3f predicted (%+.1f %%)"
                         % (k, 1e3 * abs(t), 1e3 * pred[k - 1], 100.0 * (abs(t) / pred[k - 1] - 1)))
        else:
            lines.append("  PCB%d: T %+.3f mN.m" % (k, 1e3 * t))
    if pred:
        lines.append("TOTAL |T_Cu| %.3f mN.m solved vs %.3f predicted by the board-by-board method (%+.1f %%) [%s]"
                     % (1e3 * abs(tcu), 1e3 * tot_pred, 100.0 * (abs(tcu) / tot_pred - 1), how))
        lines.append("Prediction = ideal fundamental 1.5*K1(d_k)*Ipk per board; the solved value also contains torque "
                     "ripple at this one angle (5th/7th harmonics), so a few % difference is expected.")
    for l in lines:
        ctx.log(l)
    with open(os.path.join(ctx.results_dir(), "full_attempt_summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    status["stage"] = "SOLVED"
    status["torques_mNm"] = dict((k, round(1e3 * v, 4)) for k, v in val.items())
    status["prediction_mNm"] = [round(1e3 * x, 4) for x in pred] if pred else None
    status["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_status(ctx, shared_dir, status)
    with open(os.path.join(ctx.results_dir(), "run_complete.txt"), "w") as f:
        f.write("%s solved in %.1f min\n" % (cfg.PROJECT_NAME, minutes))
