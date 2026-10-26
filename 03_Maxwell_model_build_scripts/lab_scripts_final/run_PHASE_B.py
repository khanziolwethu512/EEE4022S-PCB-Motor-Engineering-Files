# -*- coding: utf-8 -*-
"""
REV0 run_PHASE_B.py - Phase B single-phase rotor sweep only (same model size as the Phase-A runs, ~1 h each), then run phase_check.py. Restartable.

  1. Pick a PROFILE (what to build/solve) - all engineering values live in config.py.
  2. Optionally choose START_AT / STOP_AFTER to resume or stop part-way.
  3. Run. Each stage saves the project + rev0_state.json; the first failing stage stops the run.

Stages: project -> stator -> rotor -> region_band -> excitation -> solver_setup -> validate
        -> analyze -> export
Logs:   AEDT Message Manager  +  <project dir>/<PROJECT_NAME>_results/rev0_run_log.txt

Profiles (config.py): GATE1, GATE1_B, GATE1_C, GATE2_TOMEGA, GATE2_APHI, BOARD_3PH_MS, BOARD_3PH_MS_AIR,
                      REF_ROTOR_MS_SMOKE, REF_ROTOR_MS_SWEEP, REF_ROTOR_MS_DOE, ROTOR_MOTION
Batch: fill RUNS with (profile, overrides) pairs to run several projects one after another
       (e.g. the air-gap DOE overnight); each gets its own project and results folder.
"""
from __future__ import print_function

import os
import sys

PROFILE = "REV0_STATOR_BUILD"
START_AT = "project"        # resume point, e.g. "validate"
STOP_AFTER = "export"       # e.g. "validate" to build + check without solving
OVERRIDES = {}              # one-off changes, e.g. {"PROJECT_NAME": "MY_TEST", "AIR_GAP": 1.5}

# Batch of design points (empty = a single run of PROFILE above). Restartable: after a crash just run main.py
# again - finished points are skipped and an interrupted point continues where it stopped.
#
# Reduced DOE (v8.1). The stator has no iron, so the rotor field does not depend on where the copper sits: the
#   gap and the back iron are decoupled, and the fundamental of the field decays ~exp(-pi*z/tau) above the
#   magnets (single-sided limit of the coreless-AFPM analytical model). stack_sum.py fits that exponential to
#   the solved points and sums the five boards at d_k = g + (k-1)*1.02032 mm.
#   Distance points: 0.5 mm (new), 1.0 mm (= baseline REF_ROTOR_MS_SWEEP, not repeated), 5.0 mm (new: checks the
#   exponential where boards 4-5 sit). Change the tuple to (0.5, 1.5) if you prefer 1.5 to 5.0.
DOE_DISTANCE = [("REF_ROTOR_MS_DOE", {"PROJECT_NAME": "REV0_DOE_D%03d" % int(round(d * 100)), "AIR_GAP": d})
                for d in (0.5, 5.0)]
# Back iron at 1.0 mm gap, fields kept (steel |B|max). 2.0 mm = baseline; 5.0 mm = "plenty of iron" reference.
DOE_STEEL = [("REF_ROTOR_MS_DOE_STEEL", {"PROJECT_NAME": "REV0_DOE_BI%02d" % int(round(t * 10)), "BACK_IRON_THICK": t})
             for t in (5.0,)]
# Two checks (separate runs - a 2-board three-phase model would double the heaviest mesh):
CHECK_3PH = [("REF_ROTOR_MS_3PH", {})]
CHECK_JUNCTION = [("STACK_JUNCTION_TEST", {})]
# Suggested split over two PCs (each ~4-5 h, unattended, restartable):
PC1 = CHECK_3PH + DOE_DISTANCE
PC2 = CHECK_JUNCTION + DOE_STEEL
RUNS = [("REF_ROTOR_MS_DOE", {"PROJECT_NAME": "REV0_CHECK_PHB", "PHASES": ["PHASE_B"]})]   # 1 mm gap, 2 mm plate, 4 angles each

# ---------------------------------------------------------------- folders (v8.3)
# SHARED folder (OneDrive, same on every PC): holds rev0\ (these scripts) and results\ (all finished results).
# WORK folder (local disk of THIS PC): AEDT projects are built and solved here, never inside OneDrive (OneDrive
# sync locks/uploads the multi-GB solver files while AEDT is writing them). After every run the small
# <PROJECT>_results folder (summaries, CSVs, logs - no checkpoints, no project files) is copied to SHARED\results.
# Leave all three "" for auto-detection.
REV0_DIR = ""       # folder with config.py etc.  auto: this script's folder, else the OneDrive / D:\New folder candidates
SHARED_DIR = ""     # auto: the folder that contains rev0\  (e.g. ...\OneDrive - University of Cape Town\EEE4022S Ansys files\Motor run)
WORK_DIR = ""       # auto: D:\Rev0_work if this PC has a D: drive (survives lab resets), else <home>\Rev0_work
SHARED_SUBPATH = os.path.join("EEE4022S Ansys files", "Motor run")


def _find_dir():
    cands = [REV0_DIR]
    try:
        cands.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    for env in ("OneDriveCommercial", "OneDrive"):
        if os.environ.get(env):
            cands.append(os.path.join(os.environ[env], SHARED_SUBPATH, "rev0"))
    cands += [os.path.join(os.path.expanduser("~"), "OneDrive - University of Cape Town", SHARED_SUBPATH, "rev0"),
              r"C:\Users\khanz\OneDrive - University of Cape Town\EEE4022S Ansys files\Motor run\rev0",
              os.getcwd(), r"D:\New folder\rev0"]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "config.py")):
            return c
    raise RuntimeError("Cannot find the rev0 scripts (config.py). Set REV0_DIR at the top of this file to the "
                       "folder that contains config.py. Tried: %s" % [c for c in cands if c])


_d = _find_dir()
if _d not in sys.path:
    sys.path.insert(0, _d)

import config, aedt_api, pcb_geometry, build_pcb, build_rotor, setup_model, rotor_analysis, stages, final_build, full_attempt  # noqa: E402

try:                                   # AEDT keeps Python alive between runs: pick up edits
    from importlib import reload as _reload
except ImportError:                    # IronPython 2.7
    _reload = reload  # noqa: F821
for _m in (config, aedt_api, build_pcb, build_rotor, setup_model, rotor_analysis, stages, final_build, full_attempt):
    _reload(_m)

_shared = SHARED_DIR or os.path.dirname(_d)
_work = WORK_DIR or (r"D:\Rev0_work" if os.path.isdir("D:\\") else os.path.join(os.path.expanduser("~"), "Rev0_work"))
_shared_results = os.path.join(_shared, "results")
for _f in (_work, _shared_results):
    if not os.path.isdir(_f):
        os.makedirs(_f)
config.BASE["SAVE_DIR"] = _work                       # projects are solved on the local disk
config.BASE["SHARED_RESULTS_DIR"] = _shared_results   # baseline lookup + published results


def _publish(profile, overrides):
    """Copy <WORK>/<PROJECT>_results to <SHARED>/results (no checkpoints, nothing over 20 MB)."""
    cfg = None
    try:
        import shutil
        cfg = config.Config(profile, overrides)
        src = os.path.join(cfg.SAVE_DIR, cfg.PROJECT_NAME + "_results")
        dst = os.path.join(_shared_results, cfg.PROJECT_NAME + "_results")
        if not os.path.isdir(src) or os.path.abspath(src) == os.path.abspath(dst):
            return
        n = 0
        for root, dirs, files in os.walk(src):
            dirs[:] = [x for x in dirs if x != "checkpoints"]
            out = os.path.join(dst, os.path.relpath(root, src))
            if not os.path.isdir(out):
                os.makedirs(out)
            for fn in files:
                fp = os.path.join(root, fn)
                if os.path.getsize(fp) <= 20 * 1024 * 1024:
                    shutil.copy2(fp, os.path.join(out, fn))
                    n += 1
        _desktop.AddMessage("", "", 0, "[REV0] %d result files copied to %s" % (n, dst))
    except Exception as e:
        _desktop.AddMessage("", "", 1, "[REV0] could not copy results to the shared folder (%s) - copy %s by hand"
                            % (e, (cfg.PROJECT_NAME if cfg else profile) + "_results"))

_desktop = aedt_api.attach_desktop(globals())
for _p in [PROFILE] + [r[0] for r in RUNS]:
    if _p not in config.PROFILES:
        _desktop.AddMessage("", "", 2, "[REV0] Profile %s is not in %s - that config.py is older than this script. "
                            "Copy the config.py that came with this script into that folder (and let OneDrive "
                            "finish syncing), then run again." % (_p, os.path.join(_d, "config.py")))
        raise SystemExit("config.py too old for profile %s" % _p)
try:
    _desktop.RestoreWindow()
except Exception:
    pass


FINAL_PROFILES = ("REV0_FINAL_BUILD", "REV1_FINAL_BUILD", "REV1D_FINAL_BUILD")


def _final_name(profile, overrides):
    """REV0_FINAL_G100_T20 = gap 1.00 mm, back iron 2.0 mm (unless PROJECT_NAME is given)."""
    o = dict(overrides or {})
    if profile in FINAL_PROFILES and "PROJECT_NAME" not in o:
        cfg = config.Config(profile, o)
        o["PROJECT_NAME"] = "%s_G%03d_T%02d" % (cfg.PROJECT_NAME, int(round(cfg.AIR_GAP * 100)),
                                               int(round(cfg.BACK_IRON_THICK * 10)))
    return o


def _one(profile, overrides, start_at, stop_after):
    cfg = config.Config(profile, overrides)
    ctx = aedt_api.Context(_desktop, cfg)
    if profile in FINAL_PROFILES:
        ctx.log("REV0 final build %s: %s, air gap %.3f mm, back iron %.2f mm, modules from %s, built in %s"
                % (profile, cfg.PROJECT_NAME, cfg.AIR_GAP, cfg.BACK_IRON_THICK, _d, cfg.SAVE_DIR))
        final_build.run(ctx, _shared)
        return ctx
    if profile == "REV0_FULL_ATTEMPT":
        ctx.log("REV0 full-motor solve attempt: copy of %s, rot_angle %g deg, %d passes, solving in %s"
                % (cfg.FULL_SOURCE, cfg.FULL_THETA, cfg.MS_MAX_PASSES, cfg.SAVE_DIR))
        full_attempt.run(ctx, _shared)
        return ctx
    ctx.log("REV0 pipeline, profile %s, stages %s -> %s, modules from %s, solving in %s, results copied to %s"
            % (profile, start_at, stop_after, _d, cfg.SAVE_DIR, _shared_results))
    stages.run(ctx, start_at, stop_after)
    if stop_after == "export":
        try:
            with open(os.path.join(cfg.SAVE_DIR, cfg.PROJECT_NAME + "_results", "run_complete.txt"), "w") as f:
                f.write("%s finished all stages\n" % cfg.PROJECT_NAME)
        except Exception:
            pass
    return ctx


def _batch_start(profile, overrides):
    """Restartable batch: finished design points are skipped, a design point interrupted by a crash continues
    its stepwise sweep (START_AT = analyze), anything else starts from scratch."""
    cfg = config.Config(profile, overrides)
    res = os.path.join(cfg.SAVE_DIR, cfg.PROJECT_NAME + "_results")
    shr = os.path.join(_shared_results, cfg.PROJECT_NAME + "_results")
    for done in ("rotor_sweep_summary.txt", "sync_3ph_summary.txt", "run_complete.txt"):
        if os.path.isfile(os.path.join(shr, done)):
            return None                      # finished on another PC (already in the shared folder)
    if os.path.isfile(os.path.join(res, "rotor_sweep_summary.txt")) or os.path.isfile(os.path.join(res, "sync_3ph_summary.txt")):
        return None
    if os.path.isfile(os.path.join(res, "checkpoints", "09_export.aedt")):      # non-sweep runs (junction test)
        return None
    if os.path.isfile(os.path.join(cfg.SAVE_DIR, cfg.PROJECT_NAME + ".aedt")):
        if os.path.isfile(os.path.join(res, "sweep_progress.json")):
            return "analyze"
        if os.path.isfile(os.path.join(res, "checkpoints", "07_validate.aedt")):
            return "analyze"
        raise RuntimeError("%s exists but never reached validate - delete it (and its _results folder) to rebuild"
                           % cfg.PROJECT_NAME)
    return "project"


if RUNS:
    for _i, (_p, _o) in enumerate(RUNS):
        try:
            _s = _batch_start(_p, _o)
            if _s is None:
                _desktop.AddMessage("", "", 0, "[REV0 batch] run %d (%s) already finished - skipped" % (_i + 1, _o))
                continue
            _one(_p, _o, _s, "export")
        except Exception as _e:              # one failed design point must not stop the night's batch
            _desktop.AddMessage("", "", 2, "[REV0 batch] run %d (%s %s) FAILED: %s" % (_i + 1, _p, _o, _e))
        _publish(_p, _o)                     # summaries + logs to the shared folder (also after a failure)
        try:                                 # free memory before the next design point
            _desktop.CloseProject(config.Config(_p, _o).PROJECT_NAME)
        except Exception:
            pass
else:
    OVERRIDES = _final_name(PROFILE, OVERRIDES)
    if START_AT == "auto":                   # resume a single run from wherever it stopped on THIS PC
        _c = config.Config(PROFILE, OVERRIDES)
        _ck = os.path.join(_c.SAVE_DIR, _c.PROJECT_NAME + "_results", "checkpoints")
        _done = [st for st in stages.STAGES if os.path.isfile(os.path.join(_ck, "%02d_%s.aedt" % (stages.STAGES.index(st) + 1, st)))]
        if os.path.isfile(os.path.join(_c.SAVE_DIR, _c.PROJECT_NAME + "_results", "sweep_progress.json")) or "validate" in _done:
            START_AT = "analyze"
        elif _done:
            START_AT = stages.STAGES[min(stages.STAGES.index(_done[-1]) + 1, len(stages.STAGES) - 1)]
        else:
            START_AT = "project"
        _desktop.AddMessage("", "", 0, "[REV0] START_AT auto -> %s (checkpoints found: %s)" % (START_AT, _done))
    try:
        _one(PROFILE, OVERRIDES, START_AT, STOP_AFTER)
    finally:
        _publish(PROFILE, OVERRIDES)
