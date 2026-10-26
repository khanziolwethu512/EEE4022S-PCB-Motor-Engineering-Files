# -*- coding: utf-8 -*-
"""FIELD-ONLY FEM WITH TRACE-RESOLVED WINDING POST-PROCESSING (v9.5)   - the full-motor model for Rev0, Rev1-S, Rev1-D

Maxwell solves only the permanent magnets, the steel rotors/shaft and the surrounding air (no PCB copper: copper and
FR-4 are mu_r = 1 and carry no current here, so they do not change the magnet field) at prescribed rotor angles.
The solved B field is sampled along the actual centre-lines of every PCB track and via (traces_board.json, extracted
from the ODB++ export; DC current share of every track piece for 1 A into the phase's L1 terminal) for every board of
every stator. The Lorentz torque per ampere is integrated here:

    tracks (dl in the board plane):  T = -I * Bz * (x dlx + y dly)          (= r x (I dl x B), z component)
    vias   (dl along z):             T =  I * dz * (x Bx + y By)
    k_x(theta) = dLambda_x/dtheta = -T_copper/I   (torque on the rotor per ampere; Maxwell terminal convention)
    back-EMF  e_x = omega * k_x(theta)   (reciprocity)

Neglected (as in the reduced method): armature reaction, eddy currents and skin/proximity effects in the copper, and
the averaging of B over the 0.5 mm x 35 um track cross-section (B is sampled on the centre-line).

VALIDATION GATE (reviewer, 2026-10-08): in the Rev0 run, board 1 of S1 (g = 1 mm) must reproduce the detailed
single-board FEM, K1 = 6.0917 mN.m/A and psi = -30.18 deg elec, within 2 % and 1 deg, before the five-board or Rev1
results are used. Boards 2..5 are also compared with the 0.5/1.0/5.0 mm distance law.

Restartable: fieldmap_progress.json records the build and every solved angle; run the same runner again after a crash.
"""
import json
import math
import os
import shutil
import time

import build_pcb
import build_rotor
import pcb_geometry
import setup_model
import stages
from aedt_api import StageError, mm
from setup_model import ROT_VAR

ORDER = ["L1", "L2", "L3", "L4", "L5", "L6"]
PHASES = ["PHASE_A", "PHASE_B", "PHASE_C"]
REF_K1, REF_PSI = 6.0917e-3, -30.18          # detailed single-board FEM at 1.0 mm (REV0_REF_ROTOR_MS_SWEEP)
LAW_A, LAW_K = 6.1006e-3, 0.3031             # K1(d) = LAW_A * exp(-LAW_K (d - 1))   (0.5 / 1.0 / 5.0 mm FEM fit)


# ----------------------------------------------------------------------------------------------------- geometry
def stator_offsets(cfg, geo):
    """z offset of every stator relative to S1 (S2 = S1 shifted along +Z, as in the final builds)."""
    top1 = build_pcb.board_stack(cfg, geo, 1)["top_surface"]
    botN = build_pcb.board_stack(cfg, geo, cfg.N_BOARDS)["bottom_surface"]
    if cfg.FM_DESIGN == "Rev0":
        return top1, botN, [0.0]
    r1_top = top1 + cfg.AIR_GAP + cfg.MAG_THICK + (cfg.LOWER_PLATE_THICK + cfg.MAG_THICK if cfg.FM_DESIGN == "Rev1D"
                                                     else cfg.BACK_IRON_THICK)
    return top1, botN, [0.0, (r1_top + cfg.AIR_GAP) - botN]


def build_rotors(ctx, geo):
    cfg = ctx.cfg
    top1, botN, offs = stator_offsets(cfg, geo)
    mags, levels = [], {"S1_top": top1, "S1_bottom": botN}
    if cfg.FM_DESIGN == "Rev0":
        r1 = build_rotor.build_rotor(ctx, top1)
        mags += r1["magnets"]
        levels["R1_magnet_face"] = r1["geom"]["zm0"]
        zones = [("S1Zone", botN - 0.3, top1 + cfg.AIR_GAP)]
    else:
        double = cfg.FM_DESIGN == "Rev1D"
        dz = offs[1]
        top2 = top1 + dz
        bi_r2 = cfg.BACK_IRON_THICK
        if double:
            cfg.BACK_IRON_THICK = cfg.LOWER_PLATE_THICK
        g1 = build_rotor.rotor_geometry(cfg, top1)
        cfg.BACK_IRON_THICK = bi_r2
        g2 = build_rotor.rotor_geometry(cfg, top2)
        if double:
            cfg.BACK_IRON_THICK = cfg.LOWER_PLATE_THICK
        try:
            r1 = build_rotor.build_rotor(ctx, top1, prefix="R1_", shaft=True, shaft_top=g2["zb1"] + cfg.SHAFT_ABOVE_ROTOR)
        finally:
            cfg.BACK_IRON_THICK = bi_r2
        mags += r1["magnets"]
        r1_top = g1["zb1"]
        if double:
            mags += build_rotor.magnet_array(ctx, g1["zb1"], "R1B_", flip=False)
            r1_top += cfg.MAG_THICK
        r2 = build_rotor.build_rotor(ctx, top2, prefix="R2_", make_cs=False, shaft=False)
        mags += r2["magnets"]
        ctx.rename(ctx.unite(r1["steel"] + r2["steel"]), "RotorSteel")
        levels.update({"R1_magnet_face": g1["zm0"], "R1_S2_facing_surface": r1_top, "S2_bottom": botN + dz,
                       "S2_top": top2, "R2_magnet_face": g2["zm0"], "S2_offset_dz": dz})
        if abs((botN + dz) - r1_top - cfg.AIR_GAP) > 1e-6:
            raise StageError("R1 -> S2 clearance mismatch")
        zones = [("S1Zone", botN - 0.3, top1 + cfg.AIR_GAP), ("S2Zone", r1_top, top2 + cfg.AIR_GAP)]
    ctx.set_var(ROT_VAR, "%gdeg" % cfg.FM_THETAS[0])
    ctx.editor.Rotate(["NAME:Selections", "Selections:=", ",".join(mags), "NewPartsModelFlag:=", "Model"],
                      ["NAME:RotateParameters", "RotateAxis:=", "Z", "RotateAngle:=", ROT_VAR])
    made = []
    for name, z0, z1 in zones:        # air annulus around each stator volume: mesh control where B is sampled
        outer = ctx.cylinder(name, 0, 0, z0, z1 - z0, cfg.FM_ZONE_R1, "vacuum", "(200 255 200)", 0, 0.95)
        hole = ctx.cylinder(name + "_hole", 0, 0, z0 - 0.01, z1 - z0 + 0.02, cfg.FM_ZONE_R0, "vacuum", "(0 0 0)")
        ctx.subtract([outer], [hole], keep_tools=False)
        made.append(name)
        ctx.log("Stator field zone %s: r %.1f-%.1f mm, z %.5f..%.5f (no copper; B sampled on the trace paths)"
                % (name, cfg.FM_ZONE_R0, cfg.FM_ZONE_R1, z0, z1))
    for k, v in sorted(levels.items(), key=lambda kv: kv[1]):
        ctx.log("Axial level %-22s z = %9.5f mm" % (k, v))
    ctx.log("Rotor position: %d magnets rotated about +Z by %s" % (len(mags), ROT_VAR))
    return mags, made, offs


# ----------------------------------------------------------------------------------------------------- points
def load_traces(here):
    p = os.path.join(here, "traces_board.json")
    if not os.path.isfile(p):
        raise StageError("traces_board.json is missing next to fieldmap.py (%s)" % p)
    with open(p) as f:
        return json.load(f)


def point_list(cfg, T, offs):
    """[(x, y, z) mm] + parallel bookkeeping [(stator, board, phase, kind, I, a, b)]:
       track: a = dlx, b = dly (mm);  via: a = dz (mm), b = 0."""
    zc = T["_meta"]["z_layer_board1_mm"]
    pitch = cfg.board_pitch()
    pts, meta = [], []
    for s, off in enumerate(offs):
        for kb in range(cfg.N_BOARDS):
            zb = off - kb * pitch
            for ph in PHASES:
                for L, x0, y0, x1, y1, I in T[ph]["tracks"]:
                    pts.append((0.5 * (x0 + x1), 0.5 * (y0 + y1), zb + zc[L]))
                    meta.append((s, kb, ph, 0, I, x1 - x0, y1 - y0))
                for x, y, La, Lb, I in T[ph]["vias"]:
                    pts.append((x, y, zb + 0.5 * (zc[La] + zc[Lb])))
                    meta.append((s, kb, ph, 1, I, zc[Lb] - zc[La], 0.0))
    return pts, meta


def write_points(path, pts, unit_header, scale):
    with open(path, "w") as f:
        if unit_header:
            f.write("Unit=mm\n")
        for x, y, z in pts:
            f.write("%.6f %.6f %.6f\n" % (x * scale, y * scale, z * scale))


def read_fld(path):
    rows = []
    with open(path) as f:
        for line in f:
            parts = line.replace(",", " ").split()
            if len(parts) < 6:
                continue
            try:
                rows.append([float(v) for v in parts[:6]])
            except ValueError:
                continue
    return rows


EXPORT_VARIANTS = [   # (points-file header, coordinate scale, PtInSI) - the first that echoes the points back wins
    (False, 1.0, False), (True, 1.0, False), (False, 1e-3, True), (True, 1.0, True)]


def export_B(ctx, pts_path, out_path, theta, variant):
    oF = ctx.design.GetModule("FieldsReporter")
    oF.CalcStack("clear")
    oF.EnterQty("B")
    oF.ExportToFile(out_path, pts_path, "Setup1 : LastAdaptive", [ROT_VAR + ":=", "%gdeg" % theta],
                    ["NAME:ExportOption", "IncludePtInOutput:=", True, "RefCSName:=", "Global",
                     "PtInSI:=", variant[2], "FieldInRefCS:=", False])
    oF.CalcStack("clear")


def pick_variant(ctx, pts, theta, rdir):
    """Probe the export with 20 points; accept the variant whose echoed coordinates match (in m or mm)."""
    probe = pts[:: max(1, len(pts) // 20)][:20]
    for i, v in enumerate(EXPORT_VARIANTS):
        pp = os.path.join(rdir, "probe_%d.pts" % i)
        out = os.path.join(rdir, "probe_%d.fld" % i)
        try:
            write_points(pp, probe, v[0], v[1])
            export_B(ctx, pp, out, theta, v)
            rows = read_fld(out)
        except Exception as e:
            ctx.log("Field export variant %d failed (%s)" % (i, e), 1)
            continue
        if len(rows) != len(probe):
            ctx.log("Field export variant %d returned %d of %d points" % (i, len(rows), len(probe)), 1)
            continue
        for s_out in (1.0, 1e3):          # echoed coordinates in mm or in m
            if all(abs(r[0] * s_out - p[0]) < 1e-3 and abs(r[2] * s_out - p[2]) < 1e-3 for r, p in zip(rows, probe)):
                bmax = max(math.sqrt(r[3] ** 2 + r[4] ** 2 + r[5] ** 2) for r in rows)
                ctx.log("Field export variant %d accepted (points echoed in %s; |B|max of the probe %.3f T)"
                        % (i, "mm" if s_out == 1.0 else "m", bmax))
                if bmax > 5.0 or bmax < 1e-4:
                    raise StageError("Probe |B| = %.4g T is not plausible - check the field export" % bmax)
                return i, s_out
        ctx.log("Field export variant %d: echoed points do not match the requested ones" % i, 1)
    raise StageError("No field-export variant returned the requested points - see the log")


def torques(meta, rows, nst, nb):
    """Copper torque per ampere for every (stator, board, phase)."""
    T = {}
    for (s, kb, ph, kind, I, a, b), r in zip(meta, rows):
        x, y = r[0], r[1]
        key = (s, kb, ph)
        if kind == 0:
            t = -I * r[5] * (x * a + y * b)        # -I Bz (x dlx + y dly)
        else:
            t = I * a * (x * r[3] + y * r[4])      #  I dz (x Bx + y By)
        T[key] = T.get(key, 0.0) + t
    return T


# ----------------------------------------------------------------------------------------------------- analysis
def fourier(thetas, ks, p):
    """Least-squares fundamental + 3rd harmonic of k(theta) (theta in deg mech)."""
    import cmath
    n = len(thetas)
    c1 = sum(k * cmath.exp(-1j * math.radians(p * t)) for t, k in zip(thetas, ks)) * 2.0 / n
    c3 = sum(k * cmath.exp(-3j * math.radians(p * t)) for t, k in zip(thetas, ks)) * 2.0 / n
    K1 = abs(c1)
    psi = math.degrees(math.atan2(-c1.imag, c1.real))
    return K1, psi, (abs(c3) / K1 * 100.0 if K1 else float("nan"))


def summarise(ctx, prog, offs):
    cfg = ctx.cfg
    p = cfg.POLES // 2
    thetas = sorted(float(t) for t in prog["done"])
    keys = sorted(set(tuple(k.split("|")) for t in prog["done"] for k in prog["done"][t]["k"]))
    def k_of(s, kb, ph):
        return [prog["done"]["%g" % t]["k"]["%s|%s|%s" % (s, kb, ph)] for t in thetas]
    lines = ["FIELD-ONLY FEM + TRACE-RESOLVED WINDING POST-PROCESSING - %s (%s)" % (cfg.PROJECT_NAME, cfg.FM_DESIGN),
             "Rotor angles (deg mech): %s; k = dLambda/dtheta = -T_copper/I per phase, 1 A into the L1 terminal"
             % ", ".join("%g" % t for t in thetas),
             "Gap %.3f mm, R2 / R1 steel %.2f / %.2f mm, zone mesh %.2f mm, %d passes" % (
                 cfg.AIR_GAP, cfg.BACK_IRON_THICK, cfg.LOWER_PLATE_THICK if cfg.FM_DESIGN == "Rev1D" else cfg.BACK_IRON_THICK,
                 cfg.FM_ZONE_MESH, cfg.MS_MAX_PASSES), ""]
    res = {"design": cfg.FM_DESIGN, "thetas": thetas, "boards": {}, "stators": {}}
    gate = None
    for s in range(len(offs)):
        lines.append("Stator S%d (z offset %.5f mm):" % (s + 1, offs[s]))
        for ph in PHASES:
            tot = [0.0] * len(thetas)
            for kb in range(cfg.N_BOARDS):
                ks = k_of(s, kb, ph)
                tot = [a + b for a, b in zip(tot, ks)]
                K1, psi, h3 = fourier(thetas, ks, p)
                res["boards"]["S%d_B%d_%s" % (s + 1, kb + 1, ph)] = {"K1": K1, "psi": psi, "H3pct": h3, "k": ks}
                note = ""
                if ph == "PHASE_A" and s == 0:
                    d = cfg.AIR_GAP + kb * cfg.board_pitch()
                    law = LAW_A * math.exp(-LAW_K * (d - 1.0))
                    note = "; single-sided distance law at %.3f mm: %.4f (%+.2f %%)" % (d, 1e3 * law, 100 * (K1 / law - 1))
                    if kb == 0:
                        dk = 100 * (K1 / REF_K1 - 1)
                        dpsi = ((psi - REF_PSI) + 180) % 360 - 180
                        gate = (abs(dk) <= 2.0 and abs(dpsi) <= 1.0, dk, dpsi)
                if ph == "PHASE_A":
                    lines.append("  board %d %s: K1 = %.4f mN.m/A, psi = %+.2f deg, H3/H1 = %.1f %%%s"
                                 % (kb + 1, ph, 1e3 * K1, psi, h3, note))
            K1, psi, h3 = fourier(thetas, tot, p)
            res["stators"]["S%d_%s" % (s + 1, ph)] = {"K1": K1, "psi": psi, "H3pct": h3, "k": tot}
            lines.append("  STACK S%d %s: K = %.3f mN.m/A, psi = %+.2f deg, H3/H1 = %.1f %%"
                         % (s + 1, ph, 1e3 * K1, psi, h3))
        lines.append("")
    # whole machine: S1 + S2 in series, same sense unless the phases say otherwise
    wm = cfg.RPM * 2 * math.pi / 60.0
    for ph in PHASES:
        s1 = res["stators"]["S1_%s" % ph]
        if len(offs) == 2:
            s2 = res["stators"]["S2_%s" % ph]
            rel = ((s2["psi"] - s1["psi"]) + 180) % 360 - 180
            sign = -1.0 if abs(rel) > 90 else 1.0
            tot = [a + sign * b for a, b in zip(s1["k"], s2["k"])]
            K1, psi, h3 = fourier(thetas, tot, p)
            lines.append("MACHINE %s: S2 vs S1 phase %+.1f deg -> S2 connected %s; K = %.3f mN.m/A (S1 %.3f + S2 %.3f), "
                         "psi %+.2f deg, H3/H1 %.1f %%" % (ph, rel, "REVERSED (S2_REVERSED=True)" if sign < 0 else
                         "in the same sense as S1", 1e3 * K1, 1e3 * s1["K1"], 1e3 * s2["K1"], psi, h3))
        else:
            K1, psi, h3 = s1["K1"], s1["psi"], s1["H3pct"]
            lines.append("MACHINE %s: K = %.3f mN.m/A, psi %+.2f deg, H3/H1 %.1f %%" % (ph, 1e3 * K1, psi, h3))
        res.setdefault("machine", {})[ph] = {"K1": K1, "psi": psi}
    KA = res["machine"]["PHASE_A"]["K1"]
    nst = len(offs)
    R = nst * cfg.N_BOARDS * 0.2777
    lines += ["", "Machine (phase A): T_ideal = %.1f mN.m per A_pk (1.5 K), E1 = %.3f V rms at %g rpm, R_phase = %.3f ohm, "
              "Km = %.4f N.m/sqrt(W)" % (1.5e3 * KA, wm * KA / math.sqrt(2), cfg.RPM, R, 1.5 * KA / math.sqrt(1.5 * R))]
    if gate is not None:
        lines += ["", "VALIDATION GATE (S1 board 1 vs detailed single-board FEM 6.0917 mN.m/A, -30.18 deg): %s "
                  "(K1 %+.2f %%, psi %+.2f deg; limits 2 %% / 1 deg)" % ("PASS" if gate[0] else "FAIL", gate[1], gate[2])]
        res["gate"] = {"pass": bool(gate[0]), "dK_pct": gate[1], "dpsi_deg": gate[2]}
    lines += ["", "Neglected: armature reaction, copper eddy/skin/proximity effects, B averaged over the track cross-"
              "section (centre-line sampling). R_phase uses the Gate-1 FEM value 0.2777 ohm per board-phase."]
    d = ctx.results_dir()
    with open(os.path.join(d, "fieldmap_summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(d, "fieldmap_results.json"), "w") as f:
        json.dump(res, f, indent=1)
    with open(os.path.join(d, "fieldmap_k_theta.csv"), "w") as f:
        cols = sorted(res["stators"])
        f.write("theta_deg," + ",".join("k_%s_Wb_per_rad" % c for c in cols) + "\n")
        for i, t in enumerate(thetas):
            f.write("%g," % t + ",".join("%.6e" % res["stators"][c]["k"][i] for c in cols) + "\n")
    for l in lines:
        ctx.log(l)
    return res


# ----------------------------------------------------------------------------------------------------- run
def _progress_path(ctx):
    return os.path.join(ctx.results_dir(), "fieldmap_progress.json")


def _save(ctx, prog):
    with open(_progress_path(ctx), "w") as f:
        json.dump(prog, f)


def run(ctx, shared_dir, here):
    cfg = ctx.cfg
    geo = pcb_geometry.load()
    T = load_traces(here)
    rdir = ctx.results_dir()
    prog = {"built": False, "done": {}}
    if os.path.isfile(_progress_path(ctx)):
        with open(_progress_path(ctx)) as f:
            prog = json.load(f)
    top1, botN, offs = stator_offsets(cfg, geo)
    if prog.get("built") and os.path.isfile(ctx.project_path()):
        ctx.project = ctx.desktop.OpenProject(ctx.project_path())
        ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
        ctx.attach_design()
        ctx.log("Resumed %s: %d of %d angles already solved" % (cfg.PROJECT_NAME, len(prog["done"]), len(cfg.FM_THETAS)))
    else:
        if os.path.isfile(ctx.project_path()):
            raise StageError("%s exists but was never fully built - delete it and its _results folder, then run again"
                             % ctx.project_path())
        stages.st_project(ctx, geo)
        ctx.log("FIELD-ONLY FULL-MOTOR MODEL %s: no PCB copper; B sampled on %d boards x 3 phases of trace centre-lines"
                % (cfg.FM_DESIGN, len(offs) * cfg.N_BOARDS))
        mags, zones, offs = build_rotors(ctx, geo)
        setup_model.create_region(ctx, plus_y_zero=False)
        m = ctx.design.GetModule("MeshSetup")
        m.AssignLengthOp(["NAME:Len_Zones", "RefineInside:=", True, "Enabled:=", True, "Objects:=", zones,
                          "RestrictElem:=", True, "NumMaxElem:=", str(cfg.FM_ZONE_MAX_ELEMS), "RestrictLength:=", True,
                          "MaxLength:=", mm(cfg.FM_ZONE_MESH)])
        m.AssignLengthOp(["NAME:Len_Magnets", "RefineInside:=", True, "Enabled:=", True, "Objects:=", mags,
                          "RestrictElem:=", False, "NumMaxElem:=", "1000", "RestrictLength:=", True,
                          "MaxLength:=", mm(cfg.MESH_MAGNET_MAX)])
        ctx.log("Mesh: stator zones max %.2f mm (at most %d elements), magnets max %.2f mm"
                % (cfg.FM_ZONE_MESH, cfg.FM_ZONE_MAX_ELEMS, cfg.MESH_MAGNET_MAX))
        setup_model.solver_setup(ctx, {}, False)
        ok = stages.validate_geometry(ctx, "Design", allow_no_excitation=True)
        ctx.log("AEDT Validation Check returned %s" % ok)
        ctx.project.Save()
        prog["built"] = True
        prog["offsets"] = offs
        _save(ctx, prog)
    pts, meta = point_list(cfg, T, offs)
    ctx.log("Trace sample points: %d (track pieces + via steps, %d stator(s) x %d boards x 3 phases)"
            % (len(pts), len(offs), cfg.N_BOARDS))
    for th in cfg.FM_THETAS:
        key = "%g" % th
        if key in prog["done"]:
            continue
        ctx.set_var(ROT_VAR, "%gdeg" % th)
        before = stages._messages(ctx) or []
        t0 = time.time()
        ctx.log("Angle %s = %g deg ... solving (field only)" % (ROT_VAR, th))
        ctx.design.Analyze("Setup1")
        problems = stages._solve_problems(ctx, before)
        if problems:
            raise StageError("Angle %g deg NOT accepted: %s" % (th, " | ".join(problems)))
        ctx.project.Save()
        if "variant" not in prog:
            prog["variant"], prog["echo_scale"] = pick_variant(ctx, pts, th, rdir)
            _save(ctx, prog)
        v = EXPORT_VARIANTS[prog["variant"]]
        pp = os.path.join(rdir, "trace_points.pts")
        write_points(pp, pts, v[0], v[1])
        out = os.path.join(rdir, "B_on_traces_%s.fld" % key.replace(".", "p"))
        export_B(ctx, pp, out, th, v)
        rows = read_fld(out)
        if len(rows) != len(pts):
            raise StageError("Field export returned %d of %d points at %g deg" % (len(rows), len(pts), th))
        s = prog["echo_scale"]
        rows = [[r[0] * s * 1e-3, r[1] * s * 1e-3, r[2] * s * 1e-3, r[3], r[4], r[5]] for r in rows]   # -> m, T
        for (x, y, z), r in zip(pts[:: max(1, len(pts) // 50)], rows[:: max(1, len(pts) // 50)]):
            if abs(r[0] * 1e3 - x) > 1e-3 or abs(r[1] * 1e3 - y) > 1e-3:
                raise StageError("Exported points are not in the requested order - cannot map B to the traces")
        Tq = torques([(m[0], m[1], m[2], m[3], m[4], m[5] * 1e-3, m[6] * 1e-3) for m in meta], rows, len(offs),
                     cfg.N_BOARDS)
        prog["done"][key] = {"k": dict(("%d|%d|%s" % kk, -v_) for kk, v_ in Tq.items()),
                             "minutes": round((time.time() - t0) / 60.0, 2),
                             "finished": time.strftime("%Y-%m-%d %H:%M:%S")}
        _save(ctx, prog)
        if th != cfg.FM_THETAS[0]:
            try:
                os.remove(out)            # keep only the first angle's field file (they are large)
            except Exception:
                pass
        kA = prog["done"][key]["k"]["0|0|PHASE_A"]
        ctx.log("Angle %g deg done in %.1f min: S1 board 1 phase A k = %+.4f mWb/rad (detailed FEM at 0 deg: +5.317)"
                % (th, prog["done"][key]["minutes"], 1e3 * kA))
    res = summarise(ctx, prog, prog.get("offsets", offs))
    for fn in ("trace_points.pts",):                 # large and reproducible from traces_board.json
        try:
            os.remove(os.path.join(rdir, fn))
        except Exception:
            pass
    with open(os.path.join(rdir, "run_complete.txt"), "w") as f:
        f.write("%s field map finished (%d angles); gate %s\n" % (cfg.PROJECT_NAME, len(prog["done"]),
                                                                  res.get("gate", {}).get("pass", "n/a")))
    return res
