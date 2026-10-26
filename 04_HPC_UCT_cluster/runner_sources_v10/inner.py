# -*- coding: utf-8 -*-
"""hpc_motor - the part that runs INSIDE AEDT.

Started by the supervisor as
    ansysedt -ng -RunScriptAndExit inner.py          (task file path in the environment variable HPCM_TASK)
or imported by the PyAEDT fallback worker, which calls main(odesktop).

One process = one task. A task never trusts earlier state it cannot verify: it cleans up what a killed
attempt left behind, does its job, and writes <task>.result.json. The supervisor decides what happens next.

Keep this file Python 2.7 / IronPython compatible (AEDT may run scripts with either engine):
no f-strings, no pathlib, no keyword-only arguments, no exist_ok.
"""
from __future__ import print_function

import json
import math
import os
import shutil
import sys
import time
import traceback

ROT_VAR_DEFAULT = "rot_angle"
TAGS = {"PHASE_A": "A", "PHASE_B": "B", "PHASE_C": "C"}

# Rev0 = S1-R1, Rev1-S = S1-R1(PM/Fe)-S2-R2, Rev1-D = S1-R1(PM/Fe/PM)-S2-R2
MOTORS = {
    "Rev0": {"profile": "REV0_FINAL_BUILD", "stators": 1, "magnets": 16, "overrides": {}},
    "Rev1S": {"profile": "REV1_FINAL_BUILD", "stators": 2, "magnets": 32, "overrides": {}},
    "Rev1D": {"profile": "REV1D_FINAL_BUILD", "stators": 2, "magnets": 48, "overrides": {"LOWER_PLATE_THICK": 2.0}},
    "Rev2S": {"profile": "REV1_FINAL_BUILD", "stators": 3, "magnets": 48, "overrides": {"N_STAGES": 3}},
}

# Maxwell 3D HPC configuration (same file format PyAEDT ships as pyaedt_local_config.acf)
ACF = """$begin 'Configs'
	$begin 'Configs'
		$begin 'DSOConfig'
			ConfigName='hpc_motor'
			DesignType='Maxwell 3D'
			$begin 'DSOMachineList'
				$begin 'DSOMachineInfo'
					MachineName='localhost'
					NumEngines=1
					NumCores=%d
					IsEnabled=true
					RAMPercent=%d
					NumJobCores=0
					NumGPUs=0
				$end 'DSOMachineInfo'
			$end 'DSOMachineList'
			UseAutoSettings=true
			NumVariationsToDistribute=1
			$begin 'DSOJobDistributionInfo'
				AllowedDistributionTypes[9: 'Variations', 'Frequencies', 'Mesh Assembly','Mesher', 'Transient Excitations', 'Domain Solver', 'Solver', 'Iterative Solver', 'Direct Solver']
				Enable2LevelDistribution=false
				NumL1Engines=1
				UseDefaultsForDistributionTypes=false
				Context()
			$end 'DSOJobDistributionInfo'
			$begin 'DSOMachineOptionsInfo'
				MenuValues()
				IntValues()
				BoolValues(AllowOffCore=true)
				DoubleValues()
			$end 'DSOMachineOptionsInfo'
		$end 'DSOConfig'
	$end 'Configs'
$end 'Configs'
"""


# ------------------------------------------------------------------------------------------- task plumbing
class Task(object):
    def __init__(self, path):
        self.path = path
        with open(path) as f:
            self.d = json.load(f)
        self.kind = self.d["kind"]
        self.p = self.d.get("params", {})
        self.t0 = time.time()

    def progress(self, msg):
        line = "%s %7.1fs %s" % (time.strftime("%H:%M:%S"), time.time() - self.t0, msg)
        print("[hpc_motor] " + line)
        try:
            with open(self.d["progress_file"], "a") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def write_result(self, status, **kw):
        out = {"status": status, "kind": self.kind, "task_id": self.d.get("task_id"),
               "finished": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - self.t0, 1)}
        out.update(kw)
        _atomic_json(self.d["result_file"], out)

    def stage(self, name, **kw):
        """Last-known stage, read by the supervisor when the process dies (e.g. 'solving' -> memory ladder)."""
        st = {"stage": name, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        st.update(kw)
        _atomic_json(self.d["stage_file"], st)
        self.progress("STAGE " + name)


def _atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)


def _rm(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def clean_project_files(directory, name):
    """Remove a project and everything AEDT keeps next to it (locks, results, autosave)."""
    base = os.path.join(directory, name)
    for p in (base + ".aedt", base + ".aedt.lock", base + ".aedtresults", base + ".aedt.auto", base + ".aedtz",
              base + ".aedb"):
        _rm(p)


def set_hpc(odesktop, cores, ram_percent, work, task):
    """Tell Maxwell how many cores it may use (registry config, as PyAEDT does)."""
    info = {"cores": cores}
    try:
        acf = os.path.join(work, "hpc_motor_maxwell3d.acf")
        with open(acf, "w") as f:
            f.write(ACF % (int(cores), int(ram_percent)))
        odesktop.SetRegistryFromFile(acf)
        odesktop.SetRegistryString("Desktop/ActiveDSOConfigurations/Maxwell 3D", "hpc_motor")
        info["acf"] = "set"
    except Exception as e:
        info["acf"] = "failed: %s" % e
    for key in ("Desktop/Settings/ProjectOptions/NumberOfProcessors",
                "Desktop/Settings/ProjectOptions/NumberOfProcessorsDistributed"):
        try:
            odesktop.SetRegistryInt(key, int(cores))
        except Exception:
            pass
    try:
        info["active_config"] = str(odesktop.GetRegistryString("Desktop/ActiveDSOConfigurations/Maxwell 3D"))
    except Exception:
        pass
    task.progress("HPC settings: %s" % info)
    return info


def _import_pipeline():
    import config
    import aedt_api
    import stages
    import final_build
    import setup_model
    import rotor_analysis
    return config, aedt_api, stages, final_build, setup_model, rotor_analysis


class _LogHook(object):
    """Wrap Context.log so every pipeline log line also reaches the progress file (supervisor heartbeat)."""

    def __init__(self, ctx, task):
        orig = ctx.log

        def log(msg, level=0):
            orig(msg, level)
            try:
                with open(task.d["progress_file"], "a") as f:
                    f.write("%s %7.1fs [pipeline] %s\n" % (time.strftime("%H:%M:%S"), time.time() - task.t0, msg))
            except Exception:
                pass
        ctx.log = log


# ------------------------------------------------------------------------------------------- tasks
def task_probe(task, odesktop):
    """AEDT starts, a licence is checked out, a Maxwell 3D design can be created and saved."""
    work = task.d["work_dir"]
    name = "HPC_PROBE"
    clean_project_files(work, name)
    info = {}
    try:
        info["aedt_version"] = str(odesktop.GetVersion())
    except Exception as e:
        info["aedt_version"] = "unknown (%s)" % e
    info["python"] = sys.version.split()[0]
    info["engine"] = "IronPython" if "IronPython" in sys.version or sys.platform == "cli" else "CPython"
    task.stage("new_project")
    proj = odesktop.NewProject()
    proj.InsertDesign("Maxwell 3D", "probe", "Magnetostatic", "")
    proj.SaveAs(os.path.join(work, name + ".aedt"), True)
    info["project_saved"] = os.path.isfile(os.path.join(work, name + ".aedt"))
    try:
        odesktop.CloseProject(name)
    except Exception:
        pass
    clean_project_files(work, name)
    info["hpc"] = set_hpc(odesktop, task.d["cores"], task.d.get("ram_percent", 85), work, task)
    task.write_result("ok", info=info)


def task_smoke(task, odesktop):
    """Gate 1 of the lab pipeline (one board, Phase A, magnetostatic 1 A, 2 passes): geometry from the embedded
    ODB++ data, coil terminals, mesh, solve, export - the whole chain on a small model."""
    config, aedt_api, stages, final_build, setup_model, rotor_analysis = _import_pipeline()
    work = task.d["work_dir"]
    name = "HPC_SMOKE_GATE1"
    clean_project_files(work, name)
    _rm(os.path.join(work, name + "_results"))
    set_hpc(odesktop, task.d["cores"], task.d.get("ram_percent", 85), work, task)
    cfg = config.Config("GATE1", {"SAVE_DIR": work, "PROJECT_NAME": name})
    ctx = aedt_api.Context(odesktop, cfg)
    _LogHook(ctx, task)
    task.stage("build_and_solve")
    stages.run(ctx, "project", "export")
    res = os.path.join(work, name + "_results")
    files = sorted(os.listdir(res)) if os.path.isdir(res) else []
    task.write_result("ok", info={"results_files": files, "project": os.path.join(work, name + ".aedt")})
    try:
        odesktop.CloseProject(name)
    except Exception:
        pass


def _stator_cfg(config, work):
    return config.Config("REV0_STATOR_BUILD", {"SAVE_DIR": work})


def task_stator(task, odesktop):
    """The 5-board, 3-phase stator (PCB1..PCB5 one at a time, rim bridges, junction probes, windings, Validation
    Check, frozen copy). Resumes from the lab pipeline's own checkpoints: board by board, stage by stage."""
    config, aedt_api, stages, final_build, setup_model, rotor_analysis = _import_pipeline()
    work = task.d["work_dir"]
    cfg = _stator_cfg(config, work)
    frozen = os.path.join(work, cfg.PROJECT_NAME + "_FROZEN.aedt")
    if os.path.isfile(frozen):
        task.write_result("ok", info={"frozen": frozen, "note": "already built"})
        return
    ctx = aedt_api.Context(odesktop, cfg)
    _LogHook(ctx, task)
    done = [s for s in stages.STAGES if os.path.isfile(stages._ckpt_paths(ctx, s)[0])]
    if done:
        last = done[-1]
        start = stages.STAGES[min(stages.STAGES.index(last) + 1, stages.STAGES.index("validate"))]
        if last == "validate":
            start = "validate"          # validated but the frozen copy is missing: redo validate (restores excitation)
        ctx.load_state()
    else:
        start = "project"
        clean_project_files(work, cfg.PROJECT_NAME)
        _rm(os.path.join(work, cfg.PROJECT_NAME + "_results"))
    _rm(ctx.project_path() + ".lock")
    task.stage("stator_build", start_at=start, checkpoints=done)
    task.progress("Stator build starts at stage '%s' (stage checkpoints present: %s)" % (start, done))
    stages.run(ctx, start, "validate")
    if not os.path.isfile(frozen):
        raise RuntimeError("Stator build finished without %s" % frozen)
    task.write_result("ok", info={"frozen": frozen})
    try:
        odesktop.CloseProject(cfg.PROJECT_NAME)
    except Exception:
        pass


def final_name(motor):
    return {"Rev0": "REV0_FINAL_HPC", "Rev1S": "REV1S_FINAL_HPC", "Rev1D": "REV1D_FINAL_HPC",
            "Rev2S": "REV2S_FINAL_HPC"}[motor]


def _final_cfg(config, motor, work, p):
    m = MOTORS[motor]
    o = {"SAVE_DIR": work, "PROJECT_NAME": final_name(motor), "AIR_GAP": float(p.get("air_gap", 1.0)),
         "BACK_IRON_THICK": float(p.get("back_iron", 2.0)), "REGION_PADDING": float(p.get("lead_padding", 5.0))}
    o.update(m["overrides"])
    return config.Config(m["profile"], o)


def task_final(task, odesktop):
    """Rotor(s) (and S2 for Rev1) added to a COPY of the frozen stator, junctions re-probed, region recreated,
    validated, frozen. Same code as run_REV0_FINAL / run_REV1_FINAL / run_REV1D_FINAL on the lab PCs; the only
    change is the air-region padding used for the solve (lead lengths stay those of the stator build)."""
    config, aedt_api, stages, final_build, setup_model, rotor_analysis = _import_pipeline()
    motor = task.p["motor"]
    work = task.d["work_dir"]
    cfg = _final_cfg(config, motor, work, task.p)
    frozen_out = os.path.join(work, cfg.PROJECT_NAME + "_FROZEN.aedt")
    if os.path.isfile(frozen_out):
        task.write_result("ok", info={"frozen": frozen_out, "note": "already built"})
        return
    stator = os.path.join(work, cfg.FROZEN_STATOR)
    if not os.path.isfile(stator):
        raise RuntimeError("Frozen stator %s missing - the stator task must run first" % stator)
    clean_project_files(work, cfg.PROJECT_NAME)          # a killed earlier attempt leaves a partial project
    _rm(os.path.join(work, cfg.PROJECT_NAME + "_results"))
    ctx = aedt_api.Context(odesktop, cfg)
    _LogHook(ctx, task)

    solve_pad = float(task.p.get("region_padding", 20.0))
    orig_region = setup_model.create_region

    def create_region(c, plus_y_zero):
        keep = c.cfg.REGION_PADDING
        c.cfg.REGION_PADDING = solve_pad
        try:
            return orig_region(c, plus_y_zero)
        finally:
            c.cfg.REGION_PADDING = keep
    setup_model.create_region = create_region
    task.stage("final_build", motor=motor, region_padding=solve_pad)
    try:
        if MOTORS[motor]["stators"] >= 3:
            import rev2
            rev2.run(ctx, os.path.join(work, "_shared"))
        else:
            final_build.run(ctx, os.path.join(work, "_shared"))
    finally:
        setup_model.create_region = orig_region
    if not os.path.isfile(frozen_out):
        raise RuntimeError("Final build finished without %s" % frozen_out)
    _rm(os.path.join(work, "_shared"))                    # final_build's extra copy for the lab OneDrive
    manifest = os.path.join(ctx.results_dir(), "final_build_manifest.json")
    info = {"frozen": frozen_out, "region_padding_mm": solve_pad}
    if os.path.isfile(manifest):
        with open(manifest) as f:
            info["manifest"] = json.load(f)
    task.write_result("ok", info=info)
    try:
        odesktop.CloseProject(cfg.PROJECT_NAME)
    except Exception:
        pass


def classify_solids(solids, n_stators):
    mags = sorted(o for o in solids if "Magnet_" in o)
    steel = sorted(o for o in solids if o.endswith("RotorSteel") or o.endswith("BackIron") or o.endswith("Shaft")
                   or o.endswith("_Steel") or (o.startswith("Shaft_S") and o.endswith("bore")))
    stators = {}
    for s in range(1, n_stators + 1):
        pre = "" if s == 1 else "S2_"
        boards = {}
        bridges = []
        for o in solids:
            if not o.startswith(pre):
                continue
            rest = o[len(pre):]
            if pre == "" and len(rest) > 3 and rest[0] == "S" and rest[1].isdigit() and rest[2] == "_":
                continue
            if rest.startswith("Phase") and rest.endswith("_Cu") and len(rest) >= 9 and rest[5] in "ABC":
                try:
                    k = int(rest[6:-3])
                except ValueError:
                    continue
                boards.setdefault(k, []).append(o)
            elif rest.startswith("Bridge") and len(rest) > 7 and rest[6] in "ABC":
                bridges.append(o)
        stators["S%d" % s] = {"boards": dict((k, sorted(v)) for k, v in boards.items()), "bridges": sorted(bridges)}
    known = set(mags) | set(steel) | set(["Region"])
    for st in stators.values():
        known |= set(st["bridges"])
        for v in st["boards"].values():
            known |= set(v)
    other = sorted(o for o in solids if o not in known)
    return mags, steel, stators, other


def task_solve(task, odesktop):
    """One rotor angle of the complete motor: synchronous 3-phase currents, magnetostatic, torque on the rotor
    (virtual work) and on the copper (Lorentz) - total, per stator, per board."""
    config, aedt_api, stages, final_build, setup_model, rotor_analysis = _import_pipeline()
    p = task.p
    motor = p["motor"]
    m = MOTORS[motor]
    work = task.d["work_dir"]
    frozen = p["frozen"]
    if not os.path.isfile(frozen):
        raise RuntimeError("Frozen final model %s missing - the final task must run first" % frozen)
    sdir = os.path.join(work, "solve")
    if not os.path.isdir(sdir):
        os.makedirs(sdir)
    cfg = _final_cfg(config, motor, sdir, p)
    cfg.PROJECT_NAME = "%s_A%02d" % (final_name(motor).replace("_FINAL_HPC", ""), int(p["angle_index"]))
    cfg.BUILD_ONLY = False
    clean_project_files(sdir, cfg.PROJECT_NAME)
    _rm(os.path.join(sdir, cfg.PROJECT_NAME + "_results"))
    dst = os.path.join(sdir, cfg.PROJECT_NAME + ".aedt")
    shutil.copyfile(frozen, dst)
    ctx = aedt_api.Context(odesktop, cfg)
    _LogHook(ctx, task)
    task.stage("opening")
    ctx.project = odesktop.OpenProject(dst)
    ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    ctx.attach_design()
    try:
        odesktop.EnableAutoSave(False)
    except Exception:
        pass
    rot_var = getattr(setup_model, "ROT_VAR", ROT_VAR_DEFAULT)
    if p.get("split_shaft"):
        import transient as TR
        task.stage("split_shaft")
        TR.split_rotor_steel(ctx, cfg, TR.levels(cfg))

    try:
        solids = [str(o) for o in ctx.editor.GetObjectsInGroup("Solids")]
    except Exception:
        solids = [str(o) for o in (ctx.objects_present() or [])]
    mags, steel, stators, other = classify_solids(solids, m["stators"])
    copper = []
    for st in stators.values():
        copper += st["bridges"]
        for v in st["boards"].values():
            copper += v
    copper = sorted(copper)
    model = {"solids": len(solids), "magnets": len(mags), "steel": steel, "copper_objects": len(copper),
             "unclassified": other,
             "boards": dict((s, sorted(st["boards"])) for s, st in stators.items())}
    task.progress("Model: %s" % json.dumps(model))
    want_cu = m["stators"] * (cfg.N_BOARDS * len(cfg.PHASES) + (cfg.N_BOARDS - 1) * len(cfg.PHASES))
    bad = []
    if len(mags) != m["magnets"]:
        bad.append("%d magnets, expected %d" % (len(mags), m["magnets"]))
    if not steel:
        bad.append("no rotor steel")
    if len(copper) != want_cu:
        bad.append("%d copper objects, expected %d" % (len(copper), want_cu))
    for s, st in stators.items():
        if sorted(st["boards"]) != list(range(1, cfg.N_BOARDS + 1)):
            bad.append("%s boards %s" % (s, sorted(st["boards"])))
    if bad:
        task.write_result("error", error_kind="model_mismatch", message="; ".join(bad), model=model)
        return

    # operating point
    theta = float(p["theta_deg"])
    ipk = float(p.get("ipk", 1.0))
    psi = float(p["psi_deg"])
    pp = cfg.POLES // 2
    cur = {}
    for net in cfg.PHASES:
        cur[TAGS[net]] = ipk * math.cos(math.radians(pp * theta - psi + cfg.PHASE_DEG[net]))
        ctx.set_var("I_%s" % TAGS[net], "%.9gA" % cur[TAGS[net]])
    ctx.set_var(rot_var, "%.9gdeg" % theta)
    readback = {}
    for t in ("A", "B", "C"):
        try:
            readback["I_" + t] = str(ctx.design.GetVariableValue("I_" + t))
        except Exception:
            pass
    try:
        readback[rot_var] = str(ctx.design.GetVariableValue(rot_var))
    except Exception:
        pass
    task.progress("Operating point: theta %.4f deg, currents %s, read back %s" % (theta, cur, readback))

    # solver setup (the memory ladder level decides these)
    L = p["level"]
    oA = ctx.design.GetModule("AnalysisSetup")
    try:
        for s in [str(x) for x in oA.GetSetups()]:
            oA.DeleteSetups([s])
    except Exception:
        pass
    oA.InsertSetup("Magnetostatic", ["NAME:Setup1", "Enabled:=", True, "MaximumPasses:=", int(L["max_passes"]),
                                     "MinimumPasses:=", min(2, int(L["max_passes"])), "MinimumConvergedPasses:=", 1,
                                     "PercentRefinement:=", int(L["refine"]), "SolveFieldOnly:=", False,
                                     "PercentError:=", float(L["error"]), "SolveMatrixAtLast:=", False,
                                     "UseNonLinearIterNum:=", False, "UseIterativeSolver:=", bool(L["iterative"]),
                                     "RelativeResidual:=", 1e-06, "NonLinearResidual:=", 0.001])
    task.progress("Setup1: %s" % L)

    oP = ctx.design.GetModule("MaxwellParameterSetup")

    def torque(name, objs, virtual):
        oP.AssignTorque(["NAME:" + name, "Is Virtual:=", bool(virtual), "Coordinate System:=", "Global",
                         "Axis:=", "Z", "Is Positive:=", True, "Objects:=", list(objs)])
        return name

    names = [torque("Torque_Rotor", mags + steel, True), torque("Torque_Cu", copper, False)]
    for s, st in sorted(stators.items()):
        objs = list(st["bridges"])
        for v in st["boards"].values():
            objs += v
        if m["stators"] > 1:
            names.append(torque("Torque_%s" % s, objs, False))
        for k in sorted(st["boards"]):
            names.append(torque("Torque_%s_PCB%d" % (s, k), st["boards"][k], False))
    oR = ctx.design.GetModule("ReportSetup")
    ys = ["%s.Torque" % n for n in names]
    err = None
    for ctxarg in ([], ["Context:=", "Torque_Rotor"]):
        try:
            oR.CreateReport("Torque_Full", "Magnetostatic", "Rectangular Plot", "Setup1 : LastAdaptive", ctxarg,
                            [rot_var + ":=", ["All"]], ["X Component:=", rot_var, "Y Component:=", ys])
            err = None
            break
        except Exception as e:
            err = e
    if err is not None:
        raise RuntimeError("Report Torque_Full could not be created (%s)" % err)
    task.progress("Torques: %s" % ", ".join(names))

    task.stage("validate")
    ok = stages.validate_geometry(ctx, "Full motor")
    task.progress("AEDT Validation Check returned %s" % ok)
    ctx.project.Save()
    set_hpc(odesktop, task.d["cores"], task.d.get("ram_percent", 85), work, task)

    task.stage("solving", level=L)
    before = stages._messages(ctx) or []
    t0 = time.time()
    analyze_error = None
    try:
        ctx.design.Analyze("Setup1")
    except Exception as e:
        analyze_error = str(e)
    minutes = round((time.time() - t0) / 60.0, 2)
    task.stage("post", solve_minutes=minutes)
    problems = stages._solve_problems(ctx, before)
    try:
        msgs = [x.strip() for x in (stages._messages(ctx, 0) or [])][-60:]
    except Exception:
        msgs = []
    rdir = ctx.results_dir()
    extras = {}
    oS = ctx.design.GetModule("Solutions")
    for label, fn, calls in (
            ("mesh_stats", "mesh_stats.txt", (lambda f: oS.ExportMeshStats("Setup1", "All", f),)),
            ("convergence", "convergence.conv", (lambda f: oS.ExportConvergence("Setup1", "", f, True),
                                                 lambda f: oS.ExportConvergence("Setup1", "", f))),
            ("profile", "profile.prof", (lambda f: oS.ExportProfile("Setup1", "", f, True),
                                         lambda f: oS.ExportProfile("Setup1", "", f)))):
        path = os.path.join(rdir, fn)
        for c in calls:
            try:
                c(path)
                break
            except Exception:
                continue
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    extras[label] = f.read()[-20000:]
            except Exception:
                pass
    if analyze_error or problems:
        text = " | ".join([analyze_error or ""] + problems + msgs[-10:]).lower()
        kind = "solve_oom" if ("memory" in text or "bad_alloc" in text or "allocate" in text) else \
            ("license" if "licens" in text else "solve_error")
        task.write_result("error", error_kind=kind, message=analyze_error or "; ".join(problems),
                          problems=problems, messages=msgs, solve_minutes=minutes, level=L, model=model,
                          extras=extras)
        return

    csv = os.path.join(rdir, "Torque_Full.csv")
    oR.ExportToFile("Torque_Full", csv)
    cols = rotor_analysis.read_report_csv(csv)
    val = dict((k, v[0]) for k, v in cols.items() if k != "theta" and v)
    missing = [n for n in names if not _finite(val.get(n + ".Torque"))]
    if missing:
        task.write_result("error", error_kind="export_error", message="torques missing or not finite: %s" % missing,
                          columns=sorted(cols), solve_minutes=minutes, level=L, model=model, extras=extras)
        return
    torques = dict((n, val[n + ".Torque"]) for n in names)
    t_rot, t_cu = torques["Torque_Rotor"], torques["Torque_Cu"]
    boards_sum = sum(v for k, v in torques.items() if "_PCB" in k)
    checks = {
        "rotor_vs_copper_pct": 100.0 * abs(t_rot + t_cu) / max(abs(t_cu), 1e-15),
        "bridges_and_leads_share_pct": 100.0 * (t_cu - boards_sum) / t_cu if t_cu else None,
        "currents_readback": readback,
    }
    steel_B = {}
    try:
        import fieldmap
        import transient as TR
        sets = TR.steel_points(TR.levels(cfg))
        vi, s_out = fieldmap.pick_variant(ctx, sets[0][1], theta, rdir)
        for nm, pts in sets:
            pp = os.path.join(rdir, "steel_%s.pts" % nm)
            out = os.path.join(rdir, "steel_%s.fld" % nm)
            fieldmap.write_points(pp, pts, fieldmap.EXPORT_VARIANTS[vi][0], fieldmap.EXPORT_VARIANTS[vi][1])
            fieldmap.export_B(ctx, pp, out, theta, fieldmap.EXPORT_VARIANTS[vi])
            steel_B[nm] = TR.bstats(fieldmap.read_fld(out))
        task.progress("Steel |B|: %s" % steel_B)
    except Exception as e:
        task.progress("Steel |B| export skipped (%s)" % e)
    task.write_result("ok", torques_Nm=torques, currents_A=cur, theta_deg=theta, ipk_A=ipk, psi_deg=psi,
                      solve_minutes=minutes, level=L, model=model, checks=checks, messages=msgs, extras=extras,
                      validation=str(ok), steel_B=steel_B, split_shaft=bool(p.get("split_shaft")))
    keep = bool(p.get("keep_project"))
    try:
        if keep:
            ctx.project.Save()
        odesktop.CloseProject(cfg.PROJECT_NAME)
    except Exception:
        pass
    if not keep:
        clean_project_files(sdir, cfg.PROJECT_NAME)


def _finite(x):
    try:
        return x is not None and not math.isnan(x) and not math.isinf(x)
    except Exception:
        return False




# ------------------------------------------------------------------------------------------- transient tasks
def _lab_profile_run(task, odesktop, profile, name, overrides):
    """Run one of the lab's own profiles end to end (used for the T0 transient gates)."""
    config, aedt_api, stages, final_build, setup_model, rotor_analysis = _import_pipeline()
    work = task.d["work_dir"]
    clean_project_files(work, name)
    _rm(os.path.join(work, name + "_results"))
    set_hpc(odesktop, task.d["cores"], task.d.get("ram_percent", 85), work, task)
    o = {"SAVE_DIR": work, "PROJECT_NAME": name}
    o.update(overrides)
    cfg = config.Config(profile, o)
    ctx = aedt_api.Context(odesktop, cfg)
    _LogHook(ctx, task)
    task.stage("build_and_solve", profile=profile)
    t0 = time.time()
    stages.run(ctx, "project", "export")
    res = os.path.join(work, name + "_results")
    task.write_result("ok", info={"profile": profile, "minutes": round((time.time() - t0) / 60.0, 2),
                                  "results_files": sorted(os.listdir(res)) if os.path.isdir(res) else []})
    try:
        odesktop.CloseProject(name)
    except Exception:
        pass


def task_tgate(task, odesktop):
    """T0a: the lab's GATE2_TOMEGA (one board, Phase A, stationary Transient T-Omega, 2 steps): does the T-Omega
    solver accept the PCB copper as a conduction path on this cluster (where the lab run once failed)?"""
    _lab_profile_run(task, odesktop, "GATE2_TOMEGA", "HPC_T0_GATE2_TOMEGA", {})


def task_trot(task, odesktop):
    """T0b: the lab's REF_BOARD_NOLOAD (one detailed 3-phase board + rotor, band, 1000 rpm) for 3 time steps: band,
    motion and rotating mesh work with the PCB copper."""
    _lab_profile_run(task, odesktop, "REF_BOARD_NOLOAD", "HPC_T0_ROTATING_BOARD",
                     {"TRANSIENT_STEPS": 3, "SAVE_FIELDS": False, "BUILD_FR4": False, "REGION_PADDING": 5.0})


def tr_name(motor):
    return final_name(motor).replace("_FINAL_HPC", "")


def task_tprep(task, odesktop):
    """Transient base model: COPY of the frozen final build -> (Rev1: rotor steel split) -> Transient T-Omega ->
    band(s) + motion -> synchronous sinusoidal windings -> eddy settings -> Lorentz torques -> Validation Check ->
    <MOTOR>_TR_BASE.aedt. No setup, no mesh operations (those belong to each run)."""
    config, aedt_api, stages, final_build, setup_model, rotor_analysis = _import_pipeline()
    import transient as TR
    p = task.p
    motor = p["motor"]
    m = MOTORS[motor]
    work = task.d["work_dir"]
    tdir = os.path.join(work, "transient")
    if not os.path.isdir(tdir):
        os.makedirs(tdir)
    cfg = _final_cfg(config, motor, tdir, p)
    base_out = os.path.join(tdir, tr_name(motor) + "_TR_BASE.aedt")
    if os.path.isfile(base_out):
        task.write_result("ok", info={"base": base_out, "note": "already built"})
        return
    frozen = os.path.join(work, final_name(motor) + "_FROZEN.aedt")
    if not os.path.isfile(frozen):
        raise RuntimeError("Frozen final model %s missing" % frozen)
    L = TR.levels(cfg)
    problems, notes = TR.check_levels(cfg, L)
    for n in notes:
        task.progress("Band geometry: " + n)
    if problems:
        task.write_result("error", error_kind="model_mismatch", message="band geometry: " + "; ".join(problems),
                          notes=notes)
        return
    cfg.PROJECT_NAME = tr_name(motor) + "_TR_PREP"
    cfg.BUILD_ONLY = False
    clean_project_files(tdir, cfg.PROJECT_NAME)
    dst = os.path.join(tdir, cfg.PROJECT_NAME + ".aedt")
    shutil.copyfile(frozen, dst)
    ctx = aedt_api.Context(odesktop, cfg)
    _LogHook(ctx, task)
    task.stage("opening")
    ctx.project = odesktop.OpenProject(dst)
    ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    ctx.attach_design()
    try:
        odesktop.EnableAutoSave(False)
    except Exception:
        pass
    task.stage("geometry")
    split = TR.split_rotor_steel(ctx, cfg, L)
    solids = [str(o) for o in ctx.editor.GetObjectsInGroup("Solids")]
    mags, steel, stators, other = classify_solids(solids, m["stators"])
    copper = []
    for st in stators.values():
        copper += st["bridges"]
        for v in st["boards"].values():
            copper += v
    per_band = TR.magnets_by_band(solids, L)
    bad = []
    if sum(len(v) for v in per_band.values()) != m["magnets"]:
        bad.append("magnets per band %s, expected %d in total" % (dict((k, len(v)) for k, v in per_band.items()), m["magnets"]))
    if m["stators"] == 2 and (len(per_band["Band_R1"]) != m["magnets"] - 16 or len(per_band["Band_R2"]) != 16):
        bad.append("R1/R2 magnet split %d/%d" % (len(per_band["Band_R1"]), len(per_band.get("Band_R2", []))))
    if bad:
        task.write_result("error", error_kind="model_mismatch", message="; ".join(bad))
        return
    task.stage("transient_setup")
    TR.set_solution_transient(ctx)
    rpm = float(p.get("rpm", 1000.0))
    fe = rpm / 60.0 * (cfg.POLES // 2)
    ctx.set_var("Ipk", "%gA" % float(p.get("ipk", 1.0)))
    ctx.set_var("fe", "%.9gHz" % fe)
    bands = TR.add_bands(ctx, cfg, L, rpm)
    windings = TR.set_windings(ctx, cfg, float(p["psi_deg"]), m["stators"])
    TR.set_eddy(ctx, copper, mags, steel)
    oP = ctx.design.GetModule("MaxwellParameterSetup")
    tq = []
    for nm, objs in [("Torque_Cu", copper)] + ([("Torque_S%d" % (i + 1), sorted(
            stators["S%d" % (i + 1)]["bridges"] + sum(stators["S%d" % (i + 1)]["boards"].values(), [])))
            for i in range(m["stators"])] if m["stators"] > 1 else []):
        oP.AssignTorque(["NAME:" + nm, "Is Virtual:=", False, "Coordinate System:=", "Global", "Axis:=", "Z",
                         "Is Positive:=", True, "Objects:=", list(objs)])
        tq.append(nm)
    task.stage("validate")
    ok = stages.validate_geometry(ctx, "Transient model", allow_no_excitation=True)
    ctx.project.Save()
    shutil.copyfile(dst, base_out)
    info = {"base": base_out, "bands": bands, "levels": dict((k, v) for k, v in L.items() if k != "split"),
            "split": L.get("split"), "notes": notes, "windings": windings, "torques": tq,
            "magnets_per_band": dict((k, len(v)) for k, v in per_band.items()), "steel": steel,
            "copper_objects": len(copper), "unclassified": other, "fe_Hz": fe, "validation": str(ok)}
    task.write_result("ok", info=info)
    try:
        odesktop.CloseProject(cfg.PROJECT_NAME)
    except Exception:
        pass
    clean_project_files(tdir, cfg.PROJECT_NAME)


def task_trun(task, odesktop):
    """A transient run on a COPY of the base model: short-step verification (TSTEP, 3 steps) or production
    (TPROD, 1.25 electrical periods). salvage=True re-opens a killed production run and exports what was solved."""
    config, aedt_api, stages, final_build, setup_model, rotor_analysis = _import_pipeline()
    import transient as TR
    p = task.p
    motor = p["motor"]
    m = MOTORS[motor]
    work = task.d["work_dir"]
    tdir = os.path.join(work, "transient")
    cfg = _final_cfg(config, motor, tdir, p)
    cfg.PROJECT_NAME = "%s_%s" % (tr_name(motor), p["run_name"])
    cfg.BUILD_ONLY = False
    base = os.path.join(tdir, tr_name(motor) + "_TR_BASE.aedt")
    dst = os.path.join(tdir, cfg.PROJECT_NAME + ".aedt")
    L = TR.levels(cfg)
    rpm = float(p.get("rpm", 1000.0))
    fe = rpm / 60.0 * (cfg.POLES // 2)
    period_ms = 1000.0 / fe
    spp = int(p["steps_per_period"])
    step_ms = period_ms / spp
    n_steps = int(p["n_steps"])
    stop_ms = step_ms * n_steps
    save_every = int(p.get("save_every") or 0)
    salvage = bool(p.get("salvage"))
    if salvage and not os.path.isfile(dst):
        task.write_result("error", error_kind="model_mismatch", message="nothing to salvage (%s missing)" % dst)
        return
    if not salvage:
        if not os.path.isfile(base):
            raise RuntimeError("Transient base model %s missing - tprep must run first" % base)
        clean_project_files(tdir, cfg.PROJECT_NAME)
        _rm(os.path.join(tdir, cfg.PROJECT_NAME + "_results"))
        shutil.copyfile(base, dst)
    else:
        _rm(dst + ".lock")
    ctx = aedt_api.Context(odesktop, cfg)
    _LogHook(ctx, task)
    task.stage("opening")
    ctx.project = odesktop.OpenProject(dst)
    ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    ctx.attach_design()
    try:
        odesktop.EnableAutoSave(False)
    except Exception:
        pass
    rdir = ctx.results_dir()
    solids = [str(o) for o in ctx.editor.GetObjectsInGroup("Solids")]
    mags, steel, stators, other = classify_solids(solids, m["stators"])
    bands = [b["name"] for b in L["bands"]]
    windings = ["Phase%s" % TAGS[n] for n in cfg.PHASES]
    tq = ["Torque_Cu"] + (["Torque_S%d" % (i + 1) for i in range(m["stators"])] if m["stators"] > 1 else [])
    minutes = None
    msgs, problems = [], []
    if not salvage:
        ipk = float(p.get("ipk", 1.0))
        ctx.set_var("Ipk", "%gA" % ipk)
        lvl = TR.MESH_LEVELS[int(p["mesh_level"])]
        TR.mesh_ops(ctx, lvl, bands, mags, steel)
        TR.transient_setup(ctx, stop_ms, step_ms, save_every)
        made = TR.reports(ctx, len(bands), tq, windings)
        ok = stages.validate_geometry(ctx, "Transient run")
        task.progress("Validation Check: %s" % ok)
        ctx.project.Save()
        set_hpc(odesktop, task.d["cores"], task.d.get("ram_percent", 85), work, task)
        task.stage("solving", steps=n_steps, step_ms=step_ms, ipk=ipk, mesh=lvl["name"])
        before = stages._messages(ctx) or []
        t0 = time.time()
        err = None
        try:
            ctx.design.Analyze("Setup1")
        except Exception as e:
            err = str(e)
        minutes = round((time.time() - t0) / 60.0, 2)
        task.stage("post", solve_minutes=minutes)
        problems = stages._solve_problems(ctx, before)
        try:
            msgs = [x.strip() for x in (stages._messages(ctx, 0) or [])][-60:]
        except Exception:
            msgs = []
        if err or problems:
            text = " | ".join([err or ""] + problems + msgs[-10:]).lower()
            kind = "solve_oom" if ("memory" in text or "bad_alloc" in text or "allocate" in text) else \
                ("license" if "licens" in text else "solve_error")
            data = export_partial(ctx, TR, rdir, len(bands), tq, windings)
            task.write_result("error", error_kind=kind, message=err or "; ".join(problems), problems=problems,
                              messages=msgs, solve_minutes=minutes, data=data)
            return
    else:
        made = ["TR_Torque", "TR_BackEMF", "TR_Current", "TR_Flux", "TR_Loss", "TR_Position"]
    data = TR.export_reports(ctx, rdir, made)
    if not data.get("time_s"):
        task.write_result("error", error_kind="export_error", message="no transient time samples exported",
                          solve_minutes=minutes)
        return
    fields = []
    if save_every and not p.get("no_fields"):
        task.stage("fields")
        t_end = data["time_s"][-1] * 1e3
        times = [k * save_every * step_ms for k in range(0, n_steps // save_every + 1) if k * save_every * step_ms <= t_end + 1e-9]
        fields = TR.export_fields(ctx, cfg, L, rdir, times, float(p.get("ipk", 1.0)) > 0, task.d["code_dir"])
    extras = {}
    oS = ctx.design.GetModule("Solutions")
    for label, fn, calls in (("mesh_stats", "mesh_stats.txt", (lambda f: oS.ExportMeshStats("Setup1", "All", f),)),
                             ("profile", "profile.prof", (lambda f: oS.ExportProfile("Setup1", "", f, True),
                                                          lambda f: oS.ExportProfile("Setup1", "", f)))):
        path = os.path.join(rdir, fn)
        for c in calls:
            try:
                c(path)
                break
            except Exception:
                continue
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    extras[label] = f.read()[-20000:]
            except Exception:
                pass
    task.write_result("ok", data=data, solve_minutes=minutes, steps=n_steps, step_ms=step_ms, period_ms=period_ms,
                      steps_per_period=spp, rpm=rpm, ipk=float(p.get("ipk", 1.0)), mesh=p.get("mesh_level"),
                      run_name=p["run_name"], fields=fields, field_dir=rdir, messages=msgs, extras=extras,
                      salvaged=salvage, n_bands=len(bands))
    try:
        ctx.project.Save()
        odesktop.CloseProject(cfg.PROJECT_NAME)
    except Exception:
        pass


def export_partial(ctx, TR, rdir, nb, tq, windings):
    try:
        oR = ctx.design.GetModule("ReportSetup")
        names = [str(x) for x in oR.GetAllReportNames()]
        return TR.export_reports(ctx, rdir, [n for n in names if n.startswith("TR_")])
    except Exception:
        return {}


def task_lab(task, odesktop):
    """v10 simplified rotating models on the cluster: FMROT_* (field-only rotating transient, fm_rotating.py) and
    EQ_* (equivalent-coil stator, eqcoil.py), exactly the lab-PC code, with SAVE_DIR = this motor's aedt folder and
    the field-map references in params['shared_dir']. Both modules resume from their own progress files."""
    config, aedt_api, stages, final_build, setup_model, rotor_analysis = _import_pipeline()
    import fm_rotating
    import eqcoil
    p = task.p
    work = task.d["work_dir"]
    if not os.path.isdir(work):
        os.makedirs(work)
    ov = dict(p.get("overrides") or {})
    ov.update({"SAVE_DIR": work, "SHARED_RESULTS_DIR": p["shared_dir"]})
    cfg = config.Config(p["profile"], ov)
    ctx = aedt_api.Context(odesktop, cfg)
    _LogHook(ctx, task)
    set_hpc(odesktop, task.d["cores"], task.d.get("ram_percent", 85), work, task)
    task.stage("solving", profile=p["profile"])
    mod = fm_rotating if p["profile"].startswith("FMROT") else eqcoil
    res = mod.run(ctx, p["shared_dir"], task.d["code_dir"])
    rdir = ctx.results_dir()
    summ = ""
    for fn in ("fmrot_summary.txt", "eq_calibration_summary.txt", "eq_rot_summary.txt"):
        fp = os.path.join(rdir, fn)
        if os.path.isfile(fp):
            with open(fp) as f:
                summ = f.read()
    gate = None
    try:
        gate = res.get("gate") if hasattr(res, "get") else None
    except Exception:
        pass
    task.write_result("ok", results_dir=rdir, summary=summ[-20000:], gate=gate)
    try:
        odesktop.CloseProject(cfg.PROJECT_NAME)
    except Exception:
        pass


TASKS = {"lab": task_lab, "probe": task_probe, "smoke": task_smoke, "stator": task_stator, "final": task_final, "solve": task_solve,
         "tgate": task_tgate, "trot": task_trot, "tprep": task_tprep, "trun": task_trun}



def main(odesktop=None):
    path = os.environ.get("HPCM_TASK")
    if not path:
        try:
            path = ScriptArgument  # noqa: F821  (set by AEDT for -ScriptArgs)
        except NameError:
            path = None
    if not path:
        raise SystemExit("hpc_motor inner: no task file (HPCM_TASK not set)")
    task = Task(path)
    if task.d["code_dir"] not in sys.path:
        sys.path.insert(0, task.d["code_dir"])
    task.progress("inner start: %s (python %s)" % (task.kind, sys.version.split()[0]))
    try:
        if odesktop is None:
            g = globals()
            if "oDesktop" not in g:
                import __main__
                g = dict(vars(__main__))
            import aedt_api
            odesktop = aedt_api.attach_desktop(g)
        task.stage("started")
        TASKS[task.kind](task, odesktop)
    except Exception as e:
        tb = traceback.format_exc()
        msg = str(e)
        low = (msg + tb).lower()
        if "licens" in low:
            kind = "license"
        elif "memory" in low or "bad_alloc" in low:
            kind = "solve_oom" if task.kind == "solve" else "oom"
        elif type(e).__name__ == "StageError":
            kind = "build_error"
        else:
            kind = "python_error"
        task.progress("FAILED (%s): %s" % (kind, msg))
        try:
            task.write_result("error", error_kind=kind, message=msg, traceback=tb[-8000:])
        except Exception:
            pass
    task.progress("inner end")


if os.environ.get("HPCM_INNER_IMPORT") != "1":
    main()
