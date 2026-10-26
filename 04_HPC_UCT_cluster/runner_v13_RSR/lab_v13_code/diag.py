# -*- coding: utf-8 -*-
"""TARGETED FEM DIAGNOSTIC (v11.1, 22 Oct 2026): why do the detailed-copper single-board FEM values fall 1.4 % (board 1)
to 10 % (board 5) below the field map AND the independent analytical model, which agree with each other?

The archived detailed board models (REV0_DOE_D100_P20 ... D508_P20) are re-solved at two positions with the SAME
settings (one board, phase A copper, rotor, 20 mm padding, 4 passes / 20 %, gap mesh = distance / 2, rotor angles
0..16.875 deg), and three extra things are taken from the same solved project:

  (1) +I AND -I at every angle: k = (T(+I) - T(-I)) / 2I for the copper (Lorentz) and for the rotor (virtual
      work). Differencing removes the magnet-only (numerical "cogging") part, which the archived +I-only runs could
      not separate (their pointwise copper/rotor mismatch was 9-60 % at boards 2-5).
  (2) Iamp = 0 solve at every angle: Maxwell's magnet field of THIS detailed model exported on the layout trace
      centre-lines (traces_board.json, phase A) and integrated as filaments (same integration as the field map).
  (3) The same export from the +I solution (magnet + own field) for the self-field check.

Reading the result (board 5; board 1 is the control):
  * filament torque on the detailed model's field ~= detailed copper torque  -> the FIELD of the detailed model is
    weaker at the board than in the field map / analytical model (mesh / region resolution in the detailed model);
  * filament torque on the detailed model's field ~= field map / analytical  -> the field agrees; the difference is
    in how Maxwell integrates J x B over the thin solid copper (current distribution or its field sampling);
  * rotor (virtual-work) k from +-I differencing: an independent third route to the same K.
"""
import json
import math
import os
import time

import fieldmap
import pcb_geometry
import stages
from aedt_api import StageError
from setup_model import ROT_VAR

# archived and comparison values (for the summary only)
# keyed by (air gap to the magnets, rear-steel gap or None), mm. Rev0: S1 boards; Rev1-S S2 environment (v12).
ARCHIVED_K_CU = {(1.0, None): 6.2816, (5.08128, None): 1.8266,      # detailed single-board copper K, mN.m/A, +I only
                 (1.0, 5.08128): 6.5593, (5.08128, 1.0): 2.5965}    # REV1S_S2_J1 / J5_P20
FIELDMAP_K = {(1.0, None): 6.3697, (5.08128, None): 2.0154,         # FIELDMAP_REV0_P20 / FIELDMAP_REV1S_P20, phase A
              (1.0, 5.08128): 6.6506, (5.08128, 1.0): 2.8842}
ANALYTICAL_K = {(1.0, None): 6.3690, (5.08128, None): 2.0054,       # analytical model on the centre-lines (22 Oct)
                (1.0, 5.08128): 6.6710, (5.08128, 1.0): 2.8570}
SHEET_K = {(1.0, None): 6.2814, (5.08128, None): 1.8262,            # analytical field + 2D sheet currents (22 Oct)
           (1.0, 5.08128): 6.5712, (5.08128, 1.0): 2.6056}


def _key(cfg):
    rs = getattr(cfg, "REAR_STEEL_GAP", None)
    lo = getattr(cfg, "LOWER_PM_GAP", None)
    if lo:                                   # v13 R-S-R environment: no archived references
        return (round(cfg.AIR_GAP, 5), "RSR%.5f" % lo)
    return (round(cfg.AIR_GAP, 5), round(rs, 5) if rs else None)


def _pp(ctx):
    return os.path.join(ctx.results_dir(), "diag_progress.json")


def _start_stage(ctx):
    res = ctx.results_dir()
    if os.path.isfile(os.path.join(res, "checkpoints", "09_export.aedt")):
        return None
    if os.path.isfile(ctx.project_path()):
        if os.path.isfile(os.path.join(res, "sweep_progress.json")) or \
                os.path.isfile(os.path.join(res, "checkpoints", "07_validate.aedt")):
            return "analyze"
        # an interrupted BUILD (not a solve) is cheaper to redo than to repair: remove it and start again
        import shutil
        ctx.log("Partial build of %s found (never validated) - removed, rebuilding" % ctx.project_path(), 1)
        for pth in (ctx.project_path(), ctx.project_path() + ".lock", ctx.project_path() + "results"):
            try:
                if os.path.isdir(pth):
                    shutil.rmtree(pth)
                elif os.path.exists(pth):
                    os.remove(pth)
            except Exception:
                pass
        shutil.rmtree(os.path.join(res, "checkpoints"), ignore_errors=True)
        for fn in ("rev0_state.json",):
            try:
                os.remove(os.path.join(res, fn))
            except Exception:
                pass
    return "project"


def _export(ctx, out, pts_path, theta, iamp, variant):
    oF = ctx.design.GetModule("FieldsReporter")
    oF.CalcStack("clear")
    oF.EnterQty("B")
    oF.ExportToFile(out, pts_path, "Setup1 : LastAdaptive", [ROT_VAR + ":=", "%gdeg" % theta, "Iamp:=", "%gA" % iamp],
                    ["NAME:ExportOption", "IncludePtInOutput:=", True, "RefCSName:=", "Global",
                     "PtInSI:=", variant[2], "FieldInRefCS:=", False])
    oF.CalcStack("clear")


def _pick(ctx, pts, theta, iamp, rdir):
    probe = pts[:: max(1, len(pts) // 20)][:20]
    for i, v in enumerate(fieldmap.EXPORT_VARIANTS):
        pp = os.path.join(rdir, "diag_probe_%d.pts" % i)
        out = os.path.join(rdir, "diag_probe_%d.fld" % i)
        try:
            fieldmap.write_points(pp, probe, v[0], v[1])
            _export(ctx, out, pp, theta, iamp, v)
            rows = fieldmap.read_fld(out)
        except Exception as e:
            ctx.log("Diag export variant %d failed (%s)" % (i, e), 1)
            continue
        fin = [r for r in rows if all(c == c for c in r[3:6])]
        if len(rows) != len(probe) or len(fin) < len(probe) // 2:
            continue
        for s_out in (1.0, 1e3):
            if all(abs(r[0] * s_out - p[0]) < 1e-3 and abs(r[2] * s_out - p[2]) < 1e-3 for r, p in zip(rows, probe)):
                ctx.log("Diag export variant %d accepted (points echoed in %s)" % (i, "mm" if s_out == 1.0 else "m"))
                return i, s_out
    raise StageError("No field-export variant returned the requested trace points")


def run(ctx, shared_dir, here):
    cfg = ctx.cfg
    T = fieldmap.load_traces(here)
    s0 = _start_stage(ctx)
    if s0 is not None:
        stages.run(ctx, s0, "export")          # build + stepwise +-I sweep + export (the archived pipeline)
    else:
        stages.continue_project(ctx)             # project not open yet in this process: reopen it as it is
    rdir = ctx.results_dir()
    prog = {"done": {}}
    if os.path.isfile(_pp(ctx)):
        with open(_pp(ctx)) as f:
            prog = json.load(f)
    thetas, _ = stages.sweep_points(cfg)
    pts, meta = fieldmap.point_list(cfg, T, [0.0])
    keep = [i for i, m in enumerate(meta) if m[1] == 0 and m[2] == "PHASE_A"]
    pts = [pts[i] for i in keep]
    meta = [meta[i] for i in keep]
    ctx.log("Diagnostic: %d phase-A trace sample points of the one detailed board (gap %.5f mm)" % (len(pts), cfg.AIR_GAP))
    if "variant" not in prog:
        ctx.set_var(ROT_VAR, "%gdeg" % thetas[0])
        ctx.set_var("Iamp", "%gA" % cfg.SWEEP_I)
        prog["variant"], prog["echo"] = _pick(ctx, pts, thetas[0], cfg.SWEEP_I, rdir)
        with open(_pp(ctx), "w") as f:
            json.dump(prog, f, indent=1)
    v = fieldmap.EXPORT_VARIANTS[prog["variant"]]
    pp = os.path.join(rdir, "diag_points.pts")
    fieldmap.write_points(pp, pts, v[0], v[1])
    meta_m = [(m[0], m[1], m[2], m[3], m[4], m[5] * 1e-3, m[6] * 1e-3) for m in meta]
    for th in thetas:
        for iamp in (0.0, cfg.SWEEP_I):
            key = "%g|%g" % (th, iamp)
            if key in prog["done"]:
                continue
            t0 = time.time()
            ctx.set_var(ROT_VAR, "%gdeg" % th)
            ctx.set_var("Iamp", "%gA" % iamp)
            if iamp == 0.0:                     # the magnet-only field of this detailed model needs its own solve
                before = stages._messages(ctx) or []
                ctx.log("Diagnostic solve: %s = %g deg, Iamp = 0 A ..." % (ROT_VAR, th))
                ctx.design.Analyze("Setup1")
                problems = stages._solve_problems(ctx, before)
                if problems:
                    raise StageError("Iamp = 0 solve at %g deg NOT accepted: %s" % (th, " | ".join(problems)))
                ctx.project.Save()
            out = os.path.join(rdir, "diag_B_%s.fld" % key.replace("|", "_").replace(".", "p"))
            _export(ctx, out, pp, th, iamp, v)
            rows = fieldmap.read_fld(out)
            if len(rows) != len(pts):
                raise StageError("Diag export returned %d of %d points" % (len(rows), len(pts)))
            s = prog["echo"]
            rows = [[r[0] * s * 1e-3, r[1] * s * 1e-3, r[2] * s * 1e-3, r[3], r[4], r[5]] for r in rows]
            nan = sum(1 for r in rows if not all(c == c for c in r[3:6]))
            if nan:
                ctx.log("WARNING: %d of %d exported points returned NaN (inside a meshed object?) - set to 0" % (nan, len(rows)), 1)
                rows = [r if all(c == c for c in r[3:6]) else r[:3] + [0.0, 0.0, 0.0] for r in rows]
            Tq = fieldmap.torques(meta_m, rows, 1, 1)
            prog["done"][key] = {"theta": th, "Iamp": iamp, "k_filament": -Tq[(0, 0, "PHASE_A")], "nan_points": nan,
                                 "minutes": round((time.time() - t0) / 60.0, 2)}
            with open(_pp(ctx), "w") as f:
                json.dump(prog, f, indent=1)
            try:
                if th != thetas[0]:
                    os.remove(out)
            except Exception:
                pass
            ctx.log("Diagnostic %s: filament k on the detailed model's field = %+.4f mWb/rad (%.1f min)"
                    % (key, 1e3 * prog["done"][key]["k_filament"], prog["done"][key]["minutes"]))
    return summarise(ctx, prog, thetas)


def summarise(ctx, prog, thetas):
    cfg = ctx.cfg
    p = cfg.POLES // 2
    sw = stages.load_progress(ctx)["done"]

    def col(q, i):
        return [sw["%g|%g" % (t, i)]["values_SI"][q] for t in thetas]
    k_cu_pm = [(-a + b) / (2 * cfg.SWEEP_I) for a, b in zip(col("Torque_Cu.Torque", cfg.SWEEP_I), col("Torque_Cu.Torque", -cfg.SWEEP_I))]
    k_rot_pm = [(a - b) / (2 * cfg.SWEEP_I) for a, b in zip(col("Torque_Rotor.Torque", cfg.SWEEP_I), col("Torque_Rotor.Torque", -cfg.SWEEP_I))]
    k_cu_plus = [-a / cfg.SWEEP_I for a in col("Torque_Cu.Torque", cfg.SWEEP_I)]
    cog = [(a + b) / 2 for a, b in zip(col("Torque_Rotor.Torque", cfg.SWEEP_I), col("Torque_Rotor.Torque", -cfg.SWEEP_I))]
    k_fil0 = [prog["done"]["%g|0" % t]["k_filament"] for t in thetas]
    k_fil1 = [prog["done"]["%g|%g" % (t, cfg.SWEEP_I)]["k_filament"] for t in thetas]
    rows = []
    for name, ks in (("copper Lorentz, +I only (archived method)", k_cu_plus),
                     ("copper Lorentz, (+I - -I)/2", k_cu_pm),
                     ("rotor virtual work, (+I - -I)/2", k_rot_pm),
                     ("filament on the detailed model's MAGNET field (Iamp = 0)", k_fil0),
                     ("filament on the detailed model's TOTAL field (Iamp = +1 A)", k_fil1)):
        K1, psi, h3 = fieldmap.fourier(thetas, ks, p)
        rows.append((name, 1e3 * K1, psi, ks))
    g = _key(cfg)
    ref = [("archived detailed copper (DOE, +I only)", ARCHIVED_K_CU.get(g)), ("FEM field map (P20)", FIELDMAP_K.get(g)),
           ("independent analytical model (centre-lines)", ANALYTICAL_K.get(g)),
           ("independent analytical field + 2D sheet currents", SHEET_K.get(g))]
    lines = ["TARGETED FEM DIAGNOSTIC - %s: one detailed board, phase A, %.5f mm from the magnets%s"
             % (cfg.PROJECT_NAME, cfg.AIR_GAP, ((", lower magnets %s mm below (R-S-R environment)" % g[1][3:]) if isinstance(g[1], str) else
                (", rear steel %.5f mm behind (Rev1-S S2 environment)" % g[1])) if g[1] else ""),
             "Same settings as the archived detailed board models: padding %.0f mm, %d passes / %d %%, gap mesh %.3f mm; "
             "rotor angles %s deg" % (cfg.REGION_PADDING, cfg.MS_MAX_PASSES, cfg.MS_PERCENT_REFINE, cfg.gap_mesh_max(),
                                     ", ".join("%g" % t for t in thetas)), "",
             "Route | K1 (mN.m/A) | psi (deg elec) | k at each angle (mWb/rad)"]
    for name, K1, psi, ks in rows:
        lines.append("%s | %.4f | %+.2f | %s" % (name, K1, psi, ", ".join("%+.4f" % (1e3 * x) for x in ks)))
    lines += ["", "Rotor torque with no net current effect, (T(+I) + T(-I))/2 (numerical 'cogging'): %s mN.m"
              % ", ".join("%+.4f" % (1e3 * c) for c in cog), "", "Comparison values (not solved here):"]
    for name, v in ref:
        if v:
            lines.append("  %s: %.4f mN.m/A" % (name, v))
    sk = SHEET_K.get(g)
    if sk:
        lines.append("  copper (+I - -I)/2 vs analytical sheet-current K: %+.2f %%; rotor (+I - -I)/2 vs copper (+I - -I)/2: %+.2f %%"
                     % (100 * (rows[1][1] / sk - 1), 100 * (rows[2][1] / rows[1][1] - 1)))
    out = {"project": cfg.PROJECT_NAME, "air_gap_mm": cfg.AIR_GAP, "rear_steel_gap_mm": getattr(cfg, "REAR_STEEL_GAP", None), "lower_pm_gap_mm": getattr(cfg, "LOWER_PM_GAP", None), "thetas": thetas,
           "routes": dict((n, {"K1_mNm_per_A": K1, "psi_deg": psi, "k": ks}) for n, K1, psi, ks in rows),
           "rotor_magnet_only_Nm": cog, "references": dict((n, v) for n, v in ref if v)}
    fil = rows[3][1]
    cu = rows[1][1]
    fm = FIELDMAP_K.get(g)
    if fm:
        if abs(fil / cu - 1) < 0.02 and abs(fil / fm - 1) > 0.03:
            verdict = ("FIELD: the detailed model's own magnet field, integrated as filaments, reproduces its copper torque "
                       "(%+.1f %%) but not the field map (%+.1f %%) -> the field at the board is weaker in the detailed model"
                       % (100 * (fil / cu - 1), 100 * (fil / fm - 1)))
        elif abs(fil / fm - 1) < 0.02 and abs(fil / cu - 1) > 0.03:
            verdict = ("CONDUCTOR: the detailed model's field agrees with the field map (%+.1f %%) but its copper Lorentz torque "
                       "is %+.1f %% below the filament torque on that same field -> the difference is in the J x B integration over "
                       "the solid copper (current distribution or field sampling in the thin copper)"
                       % (100 * (fil / fm - 1), 100 * (cu / fil - 1)))
        else:
            verdict = ("MIXED: filament on the detailed field differs from the copper torque by %+.1f %% and from the field map "
                       "by %+.1f %% - both contribute" % (100 * (fil / cu - 1), 100 * (fil / fm - 1)))
        lines += ["", "VERDICT: " + verdict]
        out["verdict"] = verdict
    with open(os.path.join(ctx.results_dir(), "diag_summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(ctx.results_dir(), "diag_results.json"), "w") as f:
        json.dump(out, f, indent=1)
    for l in lines:
        ctx.log(l)
    with open(os.path.join(ctx.results_dir(), "run_complete.txt"), "w") as f:
        f.write("%s diagnostic finished\n" % cfg.PROJECT_NAME)
    return out
