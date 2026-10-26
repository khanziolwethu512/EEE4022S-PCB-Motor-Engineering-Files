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
    if cfg.FM_DESIGN in ("Rev0", "RSR"):
        return top1, botN, [0.0]
    if cfg.FM_DESIGN == "Rev1D":
        r1_top = top1 + cfg.AIR_GAP + cfg.MAG_THICK + cfg.LOWER_PLATE_THICK + cfg.MAG_THICK
        return top1, botN, [0.0, (r1_top + cfg.AIR_GAP) - botN]
    # Rev1-S / Rev2-S (v11): identical stages S_k | gap | R_k magnets | R_k steel | RS clearance | S_k+1
    stage = (top1 + cfg.AIR_GAP + cfg.MAG_THICK + cfg.BACK_IRON_THICK + cfg.rs_gap()) - botN
    return top1, botN, [k * stage for k in range(cfg.n_stators())]


def rsr_levels(cfg, top1, botN):
    """v13 R-S-R axial levels (pure numbers): upper rotor R2 exactly as Rev0's rotor; lower rotor R1 mirrored below
    the stack (magnets AIR_GAP below the board-5 bottom surface, steel plate behind them)."""
    g = build_rotor.rotor_geometry(cfg, top1)
    zB1 = botN - cfg.AIR_GAP
    zB0 = zB1 - cfg.MAG_THICK
    zP0 = zB0 - cfg.BACK_IRON_THICK
    return {"R2_magnet_face": g["zm0"], "R2_steel_mid": g["zm1"] + cfg.BACK_IRON_THICK / 2.0, "R2_steel_top": g["zb1"],
            "R1_magnet_face": zB1, "R1_magnet_back": zB0, "R1_steel_mid": zB0 - cfg.BACK_IRON_THICK / 2.0,
            "R1_steel_bottom": zP0, "shaft_z0": zP0, "shaft_join": g["shaft_z0"], "upper": g}


def build_rsr(ctx, top1, botN):
    """v13 R-S-R: R1 (lower) - S1 - R2 (upper). Both arrays carry the SAME magnetisation vector at the same angle, so N
    faces S across the stator and the axial field passes through it (flux closes through both plates). A 19 mm steel
    shaft joins the lower plate to the upper rotor's shaft through the stator bore (inside the zone hole)."""
    cfg = ctx.cfg
    lv = rsr_levels(cfg, top1, botN)
    r2 = build_rotor.build_rotor(ctx, top1, prefix="R2_", shaft=True)        # makes CS_MagUp / CS_MagDown
    lo = build_rotor.magnet_array(ctx, lv["R1_magnet_back"], "R1_", flip=False)
    plate = ctx.cylinder("R1_BackIron", 0, 0, lv["R1_steel_bottom"], cfg.BACK_IRON_THICK, cfg.BACK_IRON_OD / 2.0,
                         cfg.BACK_IRON_MATERIAL, "(160 160 160)")
    shaft = ctx.cylinder("R1_Shaft", 0, 0, lv["shaft_z0"], lv["shaft_join"] - lv["shaft_z0"] + 0.5, cfg.SHAFT_D / 2.0,
                         cfg.SHAFT_MATERIAL, "(120 120 120)")
    if cfg.FM_ZONE_R0 <= cfg.SHAFT_D / 2.0:
        raise StageError("RSR: the shaft (r %.1f mm) would cut the stator field zone (inner r %.1f mm)"
                         % (cfg.SHAFT_D / 2.0, cfg.FM_ZONE_R0))
    steel = ctx.rename(ctx.unite(list(r2["steel"]) + [plate, shaft]), "RotorSteel")
    mags = list(r2["magnets"]) + list(lo)
    ctx.log("RSR: upper rotor R2 magnets z %.5f..%.5f, lower rotor R1 magnets z %.5f..%.5f (same vectors: additive, "
            "through-flux), plate z %.5f..%.5f; 19 mm shaft z %.5f..%.5f through the stator bore; steel united as %s"
            % (lv["R2_magnet_face"], lv["R2_magnet_face"] + cfg.MAG_THICK, lv["R1_magnet_back"], lv["R1_magnet_face"],
               lv["R1_steel_bottom"], lv["R1_magnet_back"], lv["shaft_z0"], lv["shaft_join"] + 0.5, steel))
    return mags, [steel], lv


def build_rotors(ctx, geo):
    cfg = ctx.cfg
    top1, botN, offs = stator_offsets(cfg, geo)
    mags, levels = [], {"S1_top": top1, "S1_bottom": botN}
    if cfg.FM_DESIGN == "Rev0":
        r1 = build_rotor.build_rotor(ctx, top1)
        mags += r1["magnets"]
        levels["R1_magnet_face"] = r1["geom"]["zm0"]
        zones = [("S1Zone", botN - 0.3, top1 + cfg.AIR_GAP)]
    elif cfg.FM_DESIGN == "RSR":
        mags, _steel, lv = build_rsr(ctx, top1, botN)
        levels.update(dict((k, v) for k, v in lv.items() if k != "upper"))
        zones = [("S1Zone", botN - cfg.AIR_GAP, top1 + cfg.AIR_GAP)]       # touches both magnet faces (as Rev0's top)
    elif cfg.FM_DESIGN in ("Rev1S", "Rev2S"):
        # v11: n single-sided rotors; R1 carries the shaft up to the top rotor; all steel united (static model)
        n = cfg.n_stators()
        tops = [top1 + o for o in offs]
        gs = [build_rotor.rotor_geometry(cfg, t) for t in tops]
        steel = []
        zones = []
        for k in range(n):
            if k == 0:
                rk = build_rotor.build_rotor(ctx, tops[0], prefix="R1_", shaft=True,
                                             shaft_top=gs[-1]["zb1"] + cfg.SHAFT_ABOVE_ROTOR)
            else:
                rk = build_rotor.build_rotor(ctx, tops[k], prefix="R%d_" % (k + 1), make_cs=False, shaft=False)
            mags += rk["magnets"]
            steel += list(rk["steel"])
            levels["R%d_magnet_face" % (k + 1)] = gs[k]["zm0"]
            levels["R%d_steel_top" % (k + 1)] = gs[k]["zb1"]
            levels["S%d_top" % (k + 1)] = tops[k]
            levels["S%d_bottom" % (k + 1)] = botN + offs[k]
            if k > 0:
                clr = (botN + offs[k]) - gs[k - 1]["zb1"]
                if abs(clr - cfg.rs_gap()) > 1e-6:
                    raise StageError("R%d -> S%d clearance %.6f mm, expected %.6f" % (k, k + 1, clr, cfg.rs_gap()))
                zones.append(("S%dZone" % (k + 1), gs[k - 1]["zb1"], tops[k] + cfg.AIR_GAP))
            else:
                zones.append(("S1Zone", botN - 0.3, top1 + cfg.AIR_GAP))
        ctx.rename(ctx.unite(steel), "RotorSteel")
        ctx.log("%s: %d stators, R-S clearance %.3f mm, stage pitch %.5f mm" % (cfg.FM_DESIGN, n, cfg.rs_gap(),
                                                                               offs[1] if n > 1 else 0.0))
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
                 cfg.FM_ZONE_MESH, cfg.MS_MAX_PASSES),
             "Backplate OD/ID %.1f / %.1f mm, inter-board gap %.3f mm%s, region padding %.1f mm" % (
                 cfg.BACK_IRON_OD, cfg.BACK_IRON_ID, cfg.INTERBOARD_GAP,
                 (", rotor steel -> next stator %.3f mm" % cfg.rs_gap()) if cfg.FM_DESIGN in ("Rev1S", "Rev2S") else "",
                 cfg.REGION_PADDING), ""]
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
                    if kb == 0 and cfg.is_reference_geometry():   # v11: the gate only applies to the 1 mm geometry
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
        if len(offs) >= 2:
            tot, parts, rels = list(s1["k"]), ["S1 %.3f" % (1e3 * s1["K1"])], []
            for s in range(1, len(offs)):
                sk = res["stators"]["S%d_%s" % (s + 1, ph)]
                rel = ((sk["psi"] - s1["psi"]) + 180) % 360 - 180
                sign = -1.0 if abs(rel) > 90 else 1.0
                tot = [a + sign * b for a, b in zip(tot, sk["k"])]
                parts.append("S%d %.3f" % (s + 1, 1e3 * sk["K1"]))
                rels.append("S%d %+.1f deg -> %s" % (s + 1, rel, "REVERSED" if sign < 0 else "same sense"))
            K1, psi, h3 = fourier(thetas, tot, p)
            lines.append("MACHINE %s: phase vs S1: %s; K = %.3f mN.m/A (%s), psi %+.2f deg, H3/H1 %.1f %%"
                         % (ph, "; ".join(rels), 1e3 * K1, " + ".join(parts), psi, h3))
        else:
            K1, psi, h3 = s1["K1"], s1["psi"], s1["H3pct"]
            tot = list(s1["k"])
            lines.append("MACHINE %s: K = %.3f mN.m/A, psi %+.2f deg, H3/H1 %.1f %%" % (ph, 1e3 * K1, psi, h3))
        res.setdefault("machine", {})[ph] = {"K1": K1, "psi": psi, "k": tot}
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


def steel_planes(cfg, top1, botN):
    if cfg.FM_DESIGN == "RSR":
        lv = rsr_levels(cfg, top1, botN)
        return [("R2_BackIron", lv["R2_steel_mid"]), ("R1_BackIron", lv["R1_steel_mid"])]
    if cfg.FM_DESIGN == "Rev0":
        g = build_rotor.rotor_geometry(cfg, top1)
        return [("R1_BackIron", g["zm1"] + cfg.BACK_IRON_THICK / 2.0)]
    return []


def steel_probe(ctx, cfg, geo, theta, variant, echo_scale, rdir):
    """|B| statistics at mid-thickness of every rotor plate (r 10..42.5 mm every 1 mm, 2 deg)."""
    top1, botN, _ = stator_offsets(cfg, geo)
    out = {}
    for name, z in steel_planes(cfg, top1, botN):
        pts = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), z)
               for r in [10.0 + 1.0 * i for i in range(33)] for a in range(0, 360, 2)]
        pp = os.path.join(rdir, "steel_%s.pts" % name)
        fo = os.path.join(rdir, "steel_%s.fld" % name)
        try:
            write_points(pp, pts, variant[0], variant[1])
            export_B(ctx, pp, fo, theta, variant)
            rows = read_fld(fo)
        except Exception as e:
            ctx.log("Steel probe %s failed (%s)" % (name, e), 1)
            continue
        bs = sorted(math.sqrt(r[3] ** 2 + r[4] ** 2 + r[5] ** 2) for r in rows
                    if all(v == v for v in r[3:6]))
        if not bs:
            ctx.log("Steel probe %s returned no finite values" % name, 1)
            continue
        out[name] = {"z_mm": z, "max": bs[-1], "p99": bs[int(0.99 * (len(bs) - 1))], "mean": sum(bs) / len(bs),
                     "pct_above_1p6": 100.0 * sum(1 for b in bs if b > 1.6) / len(bs), "points": len(bs)}
        ctx.log("Steel probe %s (z %.4f mm): |B| max %.3f T, mean %.3f T" % (name, z, bs[-1], out[name]["mean"]))
    return out


def _full_period(cfg, thetas, k):
    """Extend a half-wave set by antisymmetry: k(theta + half period) = -k(theta)."""
    if not cfg.FM_HALF_WAVE:
        return list(thetas), list(k)
    hp = 360.0 / cfg.POLES
    return list(thetas) + [t + hp for t in thetas], list(k) + [-x for x in k]


def _dft(th, k, h, p):
    import cmath
    n = len(th)
    return sum(v * cmath.exp(-1j * math.radians(h * p * t)) for t, v in zip(th, k)) * 2.0 / n


def waveform(cfg, res):
    """Back-EMF waveform quantities from k(theta) of the whole machine (field-only, position-dependent)."""
    p = cfg.POLES // 2
    wm = cfg.RPM * 2 * math.pi / 60.0
    out, lines = {}, ["", "BACK-EMF WAVEFORM at %g rpm (from k(theta) at %d angles%s):" % (
        cfg.RPM, len(res["thetas"]), ", second half-period by antisymmetry" if cfg.FM_HALF_WAVE else "")]
    full = {}
    for ph in PHASES:
        th, k = _full_period(cfg, res["thetas"], res["machine"][ph]["k"])
        full[ph] = (th, k)
        n = len(th)
        hs = [abs(_dft(th, k, h, p)) for h in range(1, n // 2)]
        thd = math.sqrt(sum(x * x for x in hs[1:])) / hs[0] * 100.0
        out[ph] = {"K1": hs[0], "E1_rms_V": hs[0] * wm / math.sqrt(2), "THD_pct": thd,
                   "H_pct": dict(("H%d" % (i + 1), 100.0 * x / hs[0]) for i, x in enumerate(hs) if i + 1 <= 11)}
        lines.append("  %s: K1 = %.3f mN.m/A, E1 = %.4f V rms, THD %.1f %% (%s)" % (
            ph, 1e3 * hs[0], out[ph]["E1_rms_V"], thd,
            ", ".join("H%d %.2f%%" % (h, out[ph]["H_pct"]["H%d" % h]) for h in (3, 5, 7, 9, 11) if "H%d" % h in out[ph]["H_pct"])))
    th, ka = full["PHASE_A"]
    kab = [a - b for a, b in zip(ka, full["PHASE_B"][1])]
    hs = [abs(_dft(th, kab, h, p)) for h in range(1, len(th) // 2)]
    lthd = math.sqrt(sum(x * x for x in hs[1:])) / hs[0] * 100.0
    out["line_AB"] = {"E1_rms_V": hs[0] * wm / math.sqrt(2), "THD_pct": lthd}
    lines.append("  line A-B: E1 = %.4f V rms, THD %.2f %%" % (out["line_AB"]["E1_rms_V"], lthd))
    T = []
    for i, t in enumerate(th):
        T.append(sum(full[ph][1][i] * math.cos(math.radians(p * t - res["machine"][ph]["psi"])) for ph in PHASES))
    mean = sum(T) / len(T)
    out["ripple_pct"] = (max(T) - min(T)) / mean * 100.0 if mean else float("nan")
    out["T_mean_per_A_mNm"] = 1e3 * mean
    lines.append("  sinusoidal currents at 1 A pk in phase with each back-EMF: T mean %.3f mN.m, ripple %.2f %% pk-pk "
                 "(armature reaction neglected)" % (1e3 * mean, out["ripple_pct"]))
    return out, lines


def eddy_from_static(ctx, cfg, meta, rdir, here):
    """Thin-conductor track eddy loss at RPM from the per-angle static B files (field-only solution = function of
    rotor position only, so dB/dt = dB/dtheta * omega)."""
    import fm_rotating
    T = load_traces(here)
    E = fm_rotating.Eddy(meta, cfg, T["_meta"].get("width_mm", 0.5))
    th = list(cfg.FM_THETAS)
    st = [b - a for a, b in zip(th, th[1:])]
    if not st or max(st) - min(st) > 1e-9:
        raise StageError("FM_EDDY needs equally spaced FM_THETAS")
    wm = cfg.RPM * 2 * math.pi / 60.0
    dt = math.radians(st[0]) / wm
    for t in th:
        f = os.path.join(rdir, "B_on_traces_%s.fld" % ("%g" % t).replace(".", "p"))
        if not os.path.isfile(f):
            raise StageError("FM_EDDY: field file for %g deg is missing (%s)" % (t, f))
        E.step(read_fld(f), dt)
    full = abs(len(th) * st[0] - 2 * 360.0 / cfg.POLES) < 1e-6
    acc = E.close(dt, periodic=cfg.FM_HALF_WAVE or full, anti=cfg.FM_HALF_WAVE)
    tot = sum(acc.values())
    per = {}
    for (s, kb), v in acc.items():
        per["S%d_B%d" % (s + 1, kb + 1)] = per.get("S%d_B%d" % (s + 1, kb + 1), 0.0) + v
    lines = ["", "Copper eddy loss estimate at %g rpm (thin-conductor formula on the trace pieces, vias excluded; from the "
             "static field at %d angles, dt = %.4f ms): %.5f W" % (cfg.RPM, len(th), dt * 1e3, tot),
             "  per board: " + ", ".join("%s %.2f mW" % (k, 1e3 * v) for k, v in sorted(per.items()))]
    return {"rpm": cfg.RPM, "total_W": tot, "per_board_W": per, "dt_ms": dt * 1e3}, lines


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
        if th == cfg.FM_THETAS[0] and cfg.FM_STEEL_PROBE and "steel" not in prog:
            prog["steel"] = steel_probe(ctx, cfg, geo, th, v, prog["echo_scale"], rdir)
            _save(ctx, prog)
        if th != cfg.FM_THETAS[0] and not cfg.FM_EDDY:
            try:
                os.remove(out)            # keep only the first angle's field file (they are large)
            except Exception:
                pass
        kA = prog["done"][key]["k"]["0|0|PHASE_A"]
        ctx.log("Angle %g deg done in %.1f min: S1 board 1 phase A k = %+.4f mWb/rad (detailed FEM at 0 deg: +5.317)"
                % (th, prog["done"][key]["minutes"], 1e3 * kA))
    res = summarise(ctx, prog, prog.get("offsets", offs))
    extra = []
    if cfg.FM_WAVEFORM:
        res["waveform"], l2 = waveform(cfg, res)
        extra += l2
    if cfg.FM_EDDY:
        res["eddy"], l2 = eddy_from_static(ctx, cfg, meta, rdir, here)
        extra += l2
    if prog.get("steel"):
        res["steel"] = prog["steel"]
        extra += ["", "Rotor steel |B| at mid-thickness (rotor angle %g deg, r 10-42.5 mm):" % cfg.FM_THETAS[0]]
        extra += ["  %s: max %.3f T, p99 %.3f T, mean %.3f T, %.1f %% of points above 1.6 T"
                  % (n, d["max"], d["p99"], d["mean"], d["pct_above_1p6"]) for n, d in sorted(prog["steel"].items())]
    if extra:
        with open(os.path.join(rdir, "fieldmap_summary.txt"), "a") as f:
            f.write("\n".join(extra) + "\n")
        with open(os.path.join(rdir, "fieldmap_results.json"), "w") as f:
            json.dump(res, f, indent=1)
        for l in extra:
            ctx.log(l)
    for fn in ("trace_points.pts",):                 # large and reproducible from traces_board.json
        try:
            os.remove(os.path.join(rdir, fn))
        except Exception:
            pass
    with open(os.path.join(rdir, "run_complete.txt"), "w") as f:
        f.write("%s field map finished (%d angles); gate %s\n" % (cfg.PROJECT_NAME, len(prog["done"]),
                                                                  res.get("gate", {}).get("pass", "n/a")))
    return res
