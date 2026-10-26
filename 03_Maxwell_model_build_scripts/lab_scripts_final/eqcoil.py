# -*- coding: utf-8 -*-
"""EQUIVALENT-COIL STATOR (EQ, v10.0)  - Model B: the copper IS in Maxwell, as simple stranded coils

Each phase of each board is replaced by 8 closed sector-shaped coils (one per pole pair) whose two radial sides sit
where the real traces carry their radial current (measured from traces_board.json at run time: phase A sides at
~19 and ~41 deg mod 45, ~5.5 deg wide, active radius ~16-37.5 mm). Phases cross each other on a real board, so each
phase is split into two half-coils on two copper layers placed symmetrically about the board mid-plane:
    A -> L1 + L6,  B -> L2 + L5,  C -> L3 + L4      (same mean height for all three phases)
Every coil is a stranded conductor (uniform current density, no eddy currents) with a sheet coil terminal on the
cross-section of its outer arc; all coils of a phase are in series (one winding per phase, S1 and S2 in series).
The winding current is Ncoil x I (ampere-turns per coil); Maxwell's induced voltage / flux linkage are per turn and
are multiplied by Ncoil in post-processing.

Unlike the field-only model, the coils' own field is solved (armature reaction included) and Maxwell computes the
torque, back-EMF and flux linkage directly. The price: the coil geometry is an idealisation, so it is CALIBRATED
against the validated field map before it is used:

  EQ_<M>_CAL  magnetostatic, all three phases at 1 A x Ncoil, rotor at the 8 field-map angles: Lorentz torque on
              every phase of every board -> K1, psi per board, stator and machine (all phases) vs the field map (FIELDMAP_<M>_P20). Writes
              eq_calibration.json: Ncoil_cal = Ncoil x K_FM/K_EQ (stack), polarity, per-board ratios (axial fidelity),
              psi error, harmonic content.
  EQ_<M>_ROT  transient T-Omega, rotor turning in its band(s), calibrated Ncoil: no-load run (Ipk = 0: back-EMF,
              cogging) then loaded run (Ipk = 1 A, synchronous, i_X = Ipk cos(p theta - psi + PHASE_DEG[X]): torque
              and ripple WITH armature reaction). SHORT variants run 6 steps (timing / validation).
"""
import cmath
import json
import math
import os
import time

import build_pcb
import build_rotor
import fieldmap
import pcb_geometry
import setup_model
import stages
import transient as TR
from aedt_api import StageError, mm
from setup_model import ROT_VAR

PHASES = ["PHASE_A", "PHASE_B", "PHASE_C"]
TAG = {"PHASE_A": "A", "PHASE_B": "B", "PHASE_C": "C"}
SLABS = {"PHASE_A": ("L1", "L6"), "PHASE_B": ("L2", "L5"), "PHASE_C": ("L3", "L4")}


# ---------------------------------------------------------------------------------------------- coil geometry
def measure(T, p=8):
    """Radial-current sides of every phase from the trace data (board 1, all layers)."""
    out = {}
    pitch = 360.0 / p                        # one pole pair, deg mech
    for ph in PHASES:
        sides = {+1: [], -1: []}
        radii = []
        W1 = 0j
        for L, x0, y0, x1, y1, I in T[ph]["tracks"]:
            xm, ym = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            r = math.hypot(xm, ym)
            if r == 0:
                continue
            dl = math.hypot(x1 - x0, y1 - y0)
            rdr = xm * (x1 - x0) + ym * (y1 - y0)
            W1 += I * rdr * cmath.exp(-1j * p * math.atan2(ym, xm))
            dr = rdr / r
            if dl == 0 or abs(dr) / dl < 0.9 or abs(I * dr) < 1e-9:
                continue
            ang = math.degrees(math.atan2(ym, xm)) % pitch
            sides[1 if I * dr > 0 else -1].append((ang, abs(I * dr)))
            radii.append((math.hypot(x0, y0), math.hypot(x1, y1), abs(I * dr)))
        def circ_mean(lst):
            c = sum(w * cmath.exp(1j * math.radians(a * 360.0 / pitch)) for a, w in lst)
            mu = (math.degrees(cmath.phase(c)) * pitch / 360.0) % pitch
            var = sum(w * ((((a - mu) + pitch / 2) % pitch) - pitch / 2) ** 2 for a, w in lst) / sum(w for a, w in lst)
            return mu, math.sqrt(var)
        neg, sneg = circ_mean(sides[-1])
        pos, spos = circ_mean(sides[1])
        # radial extent of the radial current (5 % / 95 % of the current-weighted span)
        segs = []
        for r0, r1, w in radii:
            a, b = min(r0, r1), max(r0, r1)
            n = max(1, int((b - a) / 0.25))
            for i in range(n):
                segs.append((a + (b - a) * (i + 0.5) / n, w / n))
        segs.sort()
        tot = sum(w for r, w in segs)
        acc, r_in, r_out = 0.0, None, None
        for r, w in segs:
            acc += w
            if r_in is None and acc >= 0.05 * tot:
                r_in = r
            if r_out is None and acc >= 0.95 * tot:
                r_out = r
        amp_turns = sum(w for a, w in sides[1] + sides[-1]) / (2 * p) / max(1e-9, (r_out - r_in))
        out[ph] = {"phi_in": neg, "phi_out": pos, "w_in": 2 * math.sqrt(3) * sneg, "w_out": 2 * math.sqrt(3) * spos,
                   "r_in": r_in, "r_out": r_out, "amp_turns_per_side": amp_turns, "W1": abs(W1),
                   "W1_phase_deg": math.degrees(cmath.phase(W1))}
    return out


def coil_W1(g, ncoil, p=8, aw=1.5):
    """Fundamental of sum(I r dr e^{-j p phi}) of the 8 equivalent coils (both half-coils) for Ncoil turns each."""
    pitch = 360.0 / p
    a1, a2 = sorted((g["phi_in"], g["phi_out"]))
    W = 0j
    for j in range(p):
        for side, ang, w in ((g["phi_in"], g["phi_in"], g["w"]), (g["phi_out"], g["phi_out"], g["w"])):
            sgn = -1 if side == g["phi_in"] else 1
            n = 9
            for i in range(n):
                phi = math.radians(ang + j * pitch + w * ((i + 0.5) / n - 0.5))
                W += sgn * ncoil / float(n) * 0.5 * (g["r_out"] ** 2 - g["r_in"] ** 2) * cmath.exp(-1j * p * phi)
    return 2 * W          # two half-coils (two layers) per phase


def coil_layout(cfg, T):
    m = measure(T, cfg.POLES // 2)
    lay = {}
    for ph in PHASES:
        g = dict(m[ph])
        g["w"] = max(cfg.EQ_MIN_SIDE_W, 0.5 * (g["w_in"] + g["w_out"]) - cfg.EQ_SIDE_TRIM)
        g["r_in"] = round(g["r_in"], 2)
        g["r_out"] = round(g["r_out"], 2)
        n1 = coil_W1(g, 1.0, cfg.POLES // 2)
        g["Ncoil_geom"] = g["W1"] / abs(n1)
        g["phase_err_deg"] = ((math.degrees(cmath.phase(n1)) - g["W1_phase_deg"]) + 180) % 360 - 180
        lay[ph] = g
    return lay


def slab_z(cfg, T):
    """Centre heights (board-1 local) of the six half-coil slabs: the layer centres, clipped inside the copper."""
    zc = T["_meta"]["z_layer_board1_mm"]
    t = cfg.EQ_SLAB_T
    top = max(zc.values()) + 0.0178               # L1 top copper (L1 centre + half of 35.6 um)
    out = {}
    for L, z in zc.items():
        if z + t / 2.0 > top:
            z = top - t / 2.0
        if z - t / 2.0 < -top:
            z = -top + t / 2.0
        out[L] = z
    return out


def _arc(r, a0, a1, ac):
    """Arc vertices from a0 to a1 (deg) with a vertex exactly at ac, about 1 deg apart."""
    def lin(x, y):
        n = max(1, int(math.ceil(abs(y - x) / 1.0)))
        return [x + (y - x) * i / float(n) for i in range(n)]
    angs = (lin(a0, ac) + lin(ac, a1) + [a1]) if a0 < a1 else (lin(a0, ac) + lin(ac, a1) + [a1])
    return [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in angs]


def poly3d(ctx, name, pts, material, color):
    P = ["NAME:PolylinePoints"]
    for x, y, z in list(pts) + [pts[0]]:
        P.append(["NAME:PLPoint", "X:=", mm(x), "Y:=", mm(y), "Z:=", mm(z)])
    S = ["NAME:PolylineSegments"]
    for i in range(len(pts)):
        S.append(["NAME:PLSegment", "SegmentType:=", "Line", "StartIndex:=", i, "NoOfPoints:=", 2])
    X = ["NAME:PolylineXSection", "XSectionType:=", "None", "XSectionOrient:=", "Auto", "XSectionWidth:=", "0mm",
         "XSectionTopWidth:=", "0mm", "XSectionHeight:=", "0mm", "XSectionNumSegments:=", "0", "XSectionBendType:=",
         "Corner"]
    return ctx.editor.CreatePolyline(["NAME:PolylineParameters", "IsPolylineCovered:=", True, "IsPolylineClosed:=", True,
                                      P, S, X], ctx.attrs(name, material, color, 0.0))


def build_coils(ctx, T, offs):
    """All equivalent coils + their terminal sheets. Returns {(s, kb, ph): [coil objects]}, terminals per phase."""
    cfg = ctx.cfg
    lay = coil_layout(cfg, T)
    zs = slab_z(cfg, T)
    pitch_b = cfg.board_pitch()
    aw = cfg.EQ_ARC_W
    t = cfg.EQ_SLAB_T
    p = cfg.POLES // 2
    sector = 360.0 / p
    coils, terms = {}, dict((ph, []) for ph in PHASES)
    for ph in PHASES:
        g = lay[ph]
        ctx.log("EQ %s: sides at %.2f (in) / %.2f (out) deg mod %.1f, width %.2f deg, radial %.2f-%.2f mm, arcs %.2f mm, "
                "geometric Ncoil %.3f (fundamental phase error %+.2f deg vs the traces)"
                % (ph, g["phi_in"], g["phi_out"], sector, g["w"], g["r_in"], g["r_out"], aw, g["Ncoil_geom"],
                   g["phase_err_deg"]))
    for s, off in enumerate(offs):
        for kb in range(cfg.N_BOARDS):
            zb = off - kb * pitch_b
            for ph in PHASES:
                g = lay[ph]
                # every coil runs from its inward-current side (lo) counter-clockwise to its outward side (hi), so the
                # loop orientation - and with it the terminal direction - is the same for all three phases
                lo = g["phi_in"]
                hi = lo + ((g["phi_out"] - g["phi_in"]) % sector)
                objs = []
                for si, L in enumerate(SLABS[ph]):
                    z0 = zb + zs[L] - t / 2.0
                    for j in range(p):
                        a0 = lo - g["w"] / 2.0 + j * sector
                        a1 = hi + g["w"] / 2.0 + j * sector
                        b0 = lo + g["w"] / 2.0 + j * sector
                        b1 = hi - g["w"] / 2.0 + j * sector
                        ac = 0.5 * (a0 + a1)
                        Ri, Ro = g["r_in"] - aw, g["r_out"] + aw
                        outer = _arc(Ro, a0, a1, ac) + list(reversed(_arc(Ri, a0, a1, ac)))
                        inner = _arc(g["r_out"], b0, b1, ac) + list(reversed(_arc(g["r_in"], b0, b1, ac)))
                        nm = "EQ_S%dB%d_%s%d_C%d" % (s + 1, kb + 1, TAG[ph], si + 1, j + 1)
                        o = ctx.polygon_sheet(nm, outer, z0, "copper", "(255 160 40)")
                        h = ctx.polygon_sheet(nm + "_hole", inner, z0, "copper", "(0 0 0)")
                        ctx.subtract([o], [h], keep_tools=False)
                        ctx.sweep_z([o], t)
                        objs.append(o)
                        ca, sa = math.cos(math.radians(ac)), math.sin(math.radians(ac))
                        tp = [(g["r_out"] * ca, g["r_out"] * sa, z0), (Ro * ca, Ro * sa, z0),
                              (Ro * ca, Ro * sa, z0 + t), (g["r_out"] * ca, g["r_out"] * sa, z0 + t)]
                        tn = poly3d(ctx, "EQT" + nm[2:], tp, "vacuum", "(255 0 0)")
                        terms[ph].append(tn)
                coils[(s, kb, ph)] = objs
        ctx.log("EQ stator S%d: %d coils + %d terminal sheets built (%d boards x 3 phases x 2 layers x %d)"
                % (s + 1, sum(len(v) for k, v in coils.items() if k[0] == s), sum(len(v) for k, v in coils.items() if k[0] == s),
                   cfg.N_BOARDS, p))
    return coils, terms, lay


def assign_windings(ctx, terms, currents):
    """One stranded winding per phase, all coil terminals in series (1 conductor each; current = Ncoil x I)."""
    cfg = ctx.cfg
    oB = ctx.design.GetModule("BoundarySetup")
    pol = cfg.EQ_POINT_OUT
    for ph in PHASES:
        names = []
        for i, sheet in enumerate(terms[ph]):
            n = "T" + sheet[3:]
            oB.AssignCoilTerminal(["NAME:" + n, "Objects:=", [sheet], "Conductor number:=", "1",
                                   "Point out of terminal:=", bool(pol)])
            names.append(n)
        w = "Phase%s" % TAG[ph]
        oB.AssignWindingGroup(["NAME:" + w, "Type:=", "Current", "IsSolid:=", False, "Current:=", currents[ph],
                               "Resistance:=", "0ohm", "Inductance:=", "0nH", "Voltage:=", "0mV",
                               "ParallelBranchesNum:=", "1", "Phase:=", "0deg"])
        oB.AddWindingTerminals(w, names)
        ctx.log("Winding %s: %d coil terminals in series (stranded), current %s" % (w, len(names), currents[ph]))


# ---------------------------------------------------------------------------------------------- common build
def build_rotor_and_steel(ctx, cfg, geo, L, rotate):
    top1, botN, offs = fieldmap.stator_offsets(cfg, geo)
    stationary = []
    if cfg.FM_DESIGN == "Rev0":
        r1 = build_rotor.build_rotor(ctx, top1)
        mags, steel = list(r1["magnets"]), list(r1["steel"])
    else:
        top2 = top1 + offs[1]
        g2 = build_rotor.rotor_geometry(cfg, top2)
        r1 = build_rotor.build_rotor(ctx, top1, prefix="R1_", shaft=True, shaft_top=g2["zb1"] + cfg.SHAFT_ABOVE_ROTOR)
        r2 = build_rotor.build_rotor(ctx, top2, prefix="R2_", make_cs=False, shaft=False)
        st = ctx.rename(ctx.unite(list(r1["steel"]) + list(r2["steel"])), "RotorSteel")
        mags = list(r1["magnets"]) + list(r2["magnets"])
        if L is not None:
            split = TR.split_rotor_steel(ctx, cfg, L)
            steel = sum(split["moving"].values(), [])
            stationary = list(split["stationary"])
        else:
            steel = [st]
    if rotate:
        ctx.set_var(ROT_VAR, "%gdeg" % cfg.FM_THETAS[0])
        ctx.editor.Rotate(["NAME:Selections", "Selections:=", ",".join(mags), "NewPartsModelFlag:=", "Model"],
                          ["NAME:RotateParameters", "RotateAxis:=", "Z", "RotateAngle:=", ROT_VAR])
    return mags, steel, stationary, offs


def load_fm(cfg):
    for base in (cfg.SHARED_RESULTS_DIR, cfg.SAVE_DIR):
        if base:
            p = os.path.join(base, cfg.FM_REF_PROJECT + "_results", "fieldmap_results.json")
            if os.path.isfile(p):
                with open(p) as f:
                    return json.load(f), p
    return None, None


def calib_path(cfg):
    base = cfg.SHARED_RESULTS_DIR or cfg.SAVE_DIR
    return os.path.join(base, "EQ_%s_CALIBRATION.json" % cfg.FM_DESIGN.upper())


def _pp(ctx):
    return os.path.join(ctx.results_dir(), "eq_progress.json")


def _load(ctx, default):
    if os.path.isfile(_pp(ctx)):
        with open(_pp(ctx)) as f:
            return json.load(f)
    return default


def _save(ctx, prog):
    with open(_pp(ctx), "w") as f:
        json.dump(prog, f)


def _open(ctx):
    ctx.project = ctx.desktop.OpenProject(ctx.project_path())
    ctx.design = ctx.project.SetActiveDesign(ctx.cfg.DESIGN_NAME)
    ctx.attach_design()


# ---------------------------------------------------------------------------------------------- CALIBRATION (static)
def run_cal(ctx, shared_dir, here):
    import rotor_analysis
    cfg = ctx.cfg
    geo = pcb_geometry.load()
    T = fieldmap.load_traces(here)
    prog = _load(ctx, {"built": False, "done": {}})
    nst = 1 if cfg.FM_DESIGN == "Rev0" else 2
    if prog.get("built") and os.path.isfile(ctx.project_path()):
        _open(ctx)
        ctx.log("Resumed %s: %d of %d angles solved" % (cfg.PROJECT_NAME, len(prog["done"]), len(cfg.FM_THETAS)))
    else:
        if os.path.isfile(ctx.project_path()):
            raise StageError("%s exists but was never fully built - delete it and its _results folder" % ctx.project_path())
        stages.st_project(ctx, geo)
        mags, steel, stationary, offs = build_rotor_and_steel(ctx, cfg, geo, None, True)
        coils, terms, lay = build_coils(ctx, T, offs)
        setup_model.create_region(ctx, plus_y_zero=False)
        ncoil = lay["PHASE_A"]["Ncoil_geom"]
        ctx.set_var("Ncoil", "%.6f" % ncoil)
        ctx.set_var("Iamp", "1A")
        # all three phases carry +1 A x Ncoil (DC) at once; the Lorentz torque on each phase's coils of each board
        # gives k for that phase and board (the coil-on-coil torque between phases is ~1e-3 of the magnet torque:
        # coreless stator, mT armature field vs ~0.4 T magnet field)
        assign_windings(ctx, terms, dict((ph, "Ncoil*Iamp") for ph in PHASES))
        oP = ctx.design.GetModule("MaxwellParameterSetup")
        tq = []
        for s in range(nst):
            for kb in range(cfg.N_BOARDS):
                for ph in PHASES:
                    n = "Torque_EQ_S%dB%d%s" % (s + 1, kb + 1, TAG[ph])
                    oP.AssignTorque(["NAME:" + n, "Is Virtual:=", False, "Coordinate System:=", "Global", "Axis:=", "Z",
                                     "Is Positive:=", True, "Objects:=", coils[(s, kb, ph)]])
                    tq.append(n)
        oP.AssignTorque(["NAME:Torque_Rotor", "Is Virtual:=", True, "Coordinate System:=", "Global", "Axis:=", "Z",
                         "Is Positive:=", True, "Objects:=", mags + steel])
        tq.append("Torque_Rotor")
        m = ctx.design.GetModule("MeshSetup")
        allc = sum(coils.values(), [])
        m.AssignLengthOp(["NAME:Len_Coils", "RefineInside:=", True, "Enabled:=", True, "Objects:=", allc,
                          "RestrictElem:=", False, "NumMaxElem:=", "1000", "RestrictLength:=", True,
                          "MaxLength:=", mm(cfg.EQ_COIL_MESH)])
        m.AssignLengthOp(["NAME:Len_Magnets", "RefineInside:=", True, "Enabled:=", True, "Objects:=", mags,
                          "RestrictElem:=", False, "NumMaxElem:=", "1000", "RestrictLength:=", True,
                          "MaxLength:=", mm(cfg.MESH_MAGNET_MAX)])
        setup_model.solver_setup(ctx, {}, False)
        oR = ctx.design.GetModule("ReportSetup")
        oR.CreateReport("EQ_Torques", "Magnetostatic", "Rectangular Plot", "Setup1 : LastAdaptive", [],
                        [ROT_VAR + ":=", ["All"]], ["X Component:=", ROT_VAR, "Y Component:=", ["%s.Torque" % x for x in tq]])
        ok = stages.validate_geometry(ctx, "EQ calibration model")
        ctx.log("AEDT Validation Check returned %s" % ok)
        ctx.project.Save()
        prog.update({"built": True, "offsets": offs, "Ncoil": ncoil, "torques": tq,
                     "layout": dict((ph, dict((k, v) for k, v in g.items())) for ph, g in lay.items())})
        _save(ctx, prog)
    for th in cfg.FM_THETAS:
        key = "%g" % th
        if key in prog["done"]:
            continue
        ctx.set_var(ROT_VAR, "%gdeg" % th)
        before = stages._messages(ctx) or []
        t0 = time.time()
        ctx.log("EQ calibration: %s = %g deg ... solving" % (ROT_VAR, th))
        ctx.design.Analyze("Setup1")
        problems = stages._solve_problems(ctx, before)
        if problems:
            raise StageError("Angle %g deg NOT accepted: %s" % (th, " | ".join(problems)))
        ctx.project.Save()
        path = os.path.join(ctx.results_dir(), "EQ_Torques.csv")
        ctx.design.GetModule("ReportSetup").ExportToFile("EQ_Torques", path)
        cols = rotor_analysis.read_report_csv(path)
        row = None
        for j, t in enumerate(cols["theta"]):
            if abs(t - th) < 1e-6:
                row = dict((k, v[j]) for k, v in cols.items() if k != "theta")
        if row is None:
            raise StageError("Solved angle %g deg is missing from the EQ_Torques report" % th)
        prog["done"][key] = {"T": row, "minutes": round((time.time() - t0) / 60.0, 2)}
        _save(ctx, prog)
        ctx.log("Angle %g deg done in %.1f min: board 1 torque %+.4f mN.m" % (th, prog["done"][key]["minutes"],
                                                                            1e3 * row.get("Torque_EQ_S1B1A.Torque", 0)))
    return calibrate(ctx, prog)


def calibrate(ctx, prog):
    cfg = ctx.cfg
    p = cfg.POLES // 2
    thetas = sorted(float(t) for t in prog["done"])
    nst = len(prog["offsets"])
    nc = prog["Ncoil"]
    fm, fmp = load_fm(cfg)
    lines = ["EQUIVALENT-COIL CALIBRATION %s (%s) - magnetostatic, all three phases at Ncoil = %.4f x 1 A DC, %d angles"
             % (cfg.PROJECT_NAME, cfg.FM_DESIGN, nc, len(thetas)),
             "k = -T_copper/I per phase and board (Lorentz on the equivalent coils), compared with the field map %s"
             % (fmp or "(NOT FOUND)"), ""]
    res = {"boards": {}, "stators": {}, "machine": {}}
    for ph in PHASES:
        mtot = [0.0] * len(thetas)
        lines.append("%s:" % ph)
        for s in range(nst):
            tot = [0.0] * len(thetas)
            for kb in range(cfg.N_BOARDS):
                key = "Torque_EQ_S%dB%d%s.Torque" % (s + 1, kb + 1, TAG[ph])
                ks = [-prog["done"]["%g" % t]["T"][key] for t in thetas]
                tot = [a + b for a, b in zip(tot, ks)]
                K1, psi, h3 = fieldmap.fourier(thetas, ks, p)
                d = {"K1": K1, "psi": psi, "H3pct": h3}
                fb = "S%d_B%d_%s" % (s + 1, kb + 1, ph)
                if fm and fb in fm["boards"]:
                    f = fm["boards"][fb]
                    d.update({"K1_fm": f["K1"], "psi_fm": f["psi"], "ratio": K1 / f["K1"],
                              "dpsi": ((psi - f["psi"]) + 180) % 360 - 180, "H3_fm": f.get("H3pct")})
                det = (cfg.EQ_DETAILED_K or {}).get(cfg.FM_DESIGN, {}).get("S%d" % (s + 1))
                if det:
                    d["K1_det"] = det[kb] * 1e-3
                    d["ratio_det"] = K1 / d["K1_det"]
                res["boards"][fb] = d
                lines.append("  S%d board %d: K1 = %.4f mN.m/A, psi %+7.2f, H3 %4.1f %%%s" % (
                    s + 1, kb + 1, 1e3 * K1, psi, h3, ("  | field map %.4f, psi %+7.2f -> ratio %.4f, dpsi %+.2f"
                                                      % (1e3 * d["K1_fm"], d["psi_fm"], d["ratio"], d["dpsi"]))
                    if "ratio" in d else "") + ("  | detailed %.4f -> ratio %.4f" % (1e3 * d["K1_det"], d["ratio_det"])
                                                 if "ratio_det" in d else ""))
            K1, psi, h3 = fieldmap.fourier(thetas, tot, p)
            res["stators"]["S%d_%s" % (s + 1, ph)] = {"K1": K1, "psi": psi, "H3pct": h3}
            mtot = [a + b for a, b in zip(mtot, tot)]
            lines.append("  STACK S%d: K = %.3f mN.m/A, psi %+.2f, H3 %.1f %%" % (s + 1, 1e3 * K1, psi, h3))
        K1, psi, h3 = fieldmap.fourier(thetas, mtot, p)
        res["machine"][ph] = {"K1": K1, "psi": psi, "H3pct": h3}
        fmm = (fm or {}).get("machine", {}).get(ph)
        lines.append("  MACHINE %s: K = %.3f mN.m/A, psi %+.2f, H3 %.1f %%%s" % (
            ph, 1e3 * K1, psi, h3, ("  | field map %.3f, psi %+.2f" % (1e3 * fmm["K1"], fmm["psi"])) if fmm else ""))
        lines.append("")
    Ks = [res["machine"][ph]["K1"] for ph in PHASES]
    ps = [res["machine"][ph]["psi"] for ph in PHASES]
    steps = [((ps[(i + 1) % 3] - ps[i]) + 180) % 360 - 180 for i in range(3)]
    res["balance"] = {"K_spread_pct": 100 * (max(Ks) - min(Ks)) / (sum(Ks) / 3), "phase_steps_deg": steps}
    lines.append("Phase balance of the equivalent winding: K spread %.2f %%, phase steps %s deg elec (ideal +-120)"
                 % (res["balance"]["K_spread_pct"], ", ".join("%+.1f" % x for x in steps)))
    cal = {"design": cfg.FM_DESIGN, "Ncoil_run": nc, "layout": prog.get("layout"), "results": res}
    if fm:
        Ke = sum(Ks)
        Kf = sum(fm["boards"]["S%d_B%d_%s" % (s + 1, kb + 1, ph)]["K1"]
                 for ph in PHASES for s in range(nst) for kb in range(cfg.N_BOARDS))
        dps = []
        for ph in PHASES:
            ref = fm["machine"][ph]["psi"] if fm.get("machine", {}).get(ph) else fm["boards"]["S1_B1_%s" % ph]["psi"]
            dps.append(((res["machine"][ph]["psi"] - ref) + 180) % 360 - 180)
        pol = -1.0 if abs(dps[0]) > 90 else 1.0
        if pol < 0:
            dps = [((x + 180) + 180) % 360 - 180 for x in dps]
        ratios = [d["ratio"] for d in res["boards"].values() if "ratio" in d]
        ref_name = "field map"
        dets = [d["ratio_det"] for d in res["boards"].values() if "ratio_det" in d]
        if len(dets) == len(res["boards"]):
            # calibrate against the detailed / full-motor FEM per-board values (the field map reads 1-9 % high,
            # growing with distance from the magnets) - same K for all three phases (balanced winding)
            ratios = dets
            Kf = sum(d["K1_det"] for d in res["boards"].values())
            ref_name = "detailed FEM"
        spread = 100 * (max(ratios) - min(ratios)) / (sum(ratios) / len(ratios))
        ncal = nc * Kf / Ke
        cal.update({"Ncoil_cal": ncal, "calibrated_against": ref_name, "polarity": pol, "dpsi_deg": dict(zip(PHASES, dps)),
                    "board_ratio_spread_pct": spread, "K_fm_sum": Kf, "K_eq_sum": Ke,
                    "psi_fm": fm["machine"]["PHASE_A"]["psi"] if fm.get("machine") else fm["boards"]["S1_B1_PHASE_A"]["psi"]})
        # vs the detailed FEM the per-board ratio carries the known method gap (centre-line coils vs volume copper:
        # 1-9 % growing with distance) -> 15 % allowed; the per-board factors below remove it in post-processing
        lim = 15.0 if ref_name == "detailed FEM" else 10.0
        mr = sum(ratios) / len(ratios)
        cal["board_correction"] = dict((k, mr / d["ratio_det"]) for k, d in res["boards"].items() if "ratio_det" in d)
        ok = max(abs(x) for x in dps) <= 3.0 and spread <= lim and res["balance"]["K_spread_pct"] <= 3.0
        cal["usable"] = ok
        lines += ["", "CALIBRATION against the %s: Ncoil %.4f -> %.4f (x %.4f, all phases and boards together), polarity %s; machine psi "
                  "error A %+.2f / B %+.2f / C %+.2f deg; board-ratio spread %.1f %% over %d board-phases; phase K spread "
                  "%.2f %% -> %s" % (ref_name, nc, ncal, Kf / Ke, "+" if pol > 0 else "REVERSED (terminal direction; corrected in "
                                     "the rotating run)", dps[0], dps[1], dps[2], spread, len(ratios),
                                     res["balance"]["K_spread_pct"],
                                     ("USABLE (psi within 3 deg, boards within %g %%, phases within 3 %%)" % lim) if ok else
                                     "NOT USABLE as is - see the per-board ratios and the phase balance")]
    else:
        lines += ["", "No field map found (%s_results/fieldmap_results.json) - no calibration written" % cfg.FM_REF_PROJECT]
    with open(os.path.join(ctx.results_dir(), "eq_calibration_summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    if fm:
        with open(calib_path(cfg), "w") as f:
            json.dump(cal, f, indent=1)
        with open(os.path.join(ctx.results_dir(), os.path.basename(calib_path(cfg))), "w") as f:
            json.dump(cal, f, indent=1)
    for l in lines:
        ctx.log(l)
    with open(os.path.join(ctx.results_dir(), "run_complete.txt"), "w") as f:
        f.write("%s calibration finished\n" % cfg.PROJECT_NAME)
    return cal


# ---------------------------------------------------------------------------------------------- ROTATING (transient)
def run_rot(ctx, shared_dir, here):
    cfg = ctx.cfg
    geo = pcb_geometry.load()
    T = fieldmap.load_traces(here)
    cp = calib_path(cfg)
    if not os.path.isfile(cp):
        raise StageError("Calibration %s not found - run EQ_%s_CAL first" % (cp, cfg.FM_DESIGN.upper()))
    with open(cp) as f:
        cal = json.load(f)
    if not cal.get("usable", False) and not cfg.EQ_FORCE:
        raise StageError("Calibration %s is marked NOT USABLE (set EQ_FORCE=True to run anyway)" % cp)
    prog = _load(ctx, {"built": False, "runs": {}})
    nst = 1 if cfg.FM_DESIGN == "Rev0" else 2
    cfg.N_STAGES = nst
    cfg.R1_DOUBLE = False
    L = TR.levels(cfg)
    fe = cfg.RPM / 60.0 * (cfg.POLES // 2)
    period = 1000.0 / fe
    step = period / cfg.FMR_SPP
    n = int(cfg.FMR_STEPS) if cfg.FMR_STEPS else int(round(cfg.FMR_SPP * cfg.FMR_PERIODS))
    if prog.get("built") and os.path.isfile(ctx.project_path()):
        _open(ctx)
        ctx.log("Resumed %s (runs done: %s)" % (cfg.PROJECT_NAME, sorted(prog["runs"])))
    else:
        if os.path.isfile(ctx.project_path()):
            raise StageError("%s exists but was never fully built - delete it and its _results folder" % ctx.project_path())
        problems, notes = TR.check_levels(cfg, L)
        for x in notes:
            ctx.log("Band geometry: " + x)
        if problems:
            raise StageError("Band geometry: " + "; ".join(problems))
        stages.st_project(ctx, geo)
        mags, steel, stationary, offs = build_rotor_and_steel(ctx, cfg, geo, L if nst > 1 else None, False)
        coils, terms, lay = build_coils(ctx, T, offs)
        bands = TR.add_bands(ctx, cfg, L, cfg.RPM)
        setup_model.create_region(ctx, plus_y_zero=False)
        psi = cal.get("psi_fm", -30.18)
        pol = cal.get("polarity", 1.0)
        ctx.set_var("Ncoil", "%.6f" % cal["Ncoil_cal"])
        ctx.set_var("Ipk", "0A")
        ctx.set_var("fe", "%.9gHz" % fe)
        cur = {}
        for ph in PHASES:
            ang = -psi + cfg.PHASE_DEG[ph]
            cur[ph] = "%s*Ncoil*Ipk*cos(2*pi*fe*Time + (%.6f)*pi/180)" % ("-1" if pol < 0 else "1", ang)
        assign_windings(ctx, terms, cur)
        setup_model.set_eddy(ctx, mags, bool(cfg.MAGNET_EDDY), "magnets")
        setup_model.set_eddy(ctx, steel + stationary, False, "rotor steel")
        oP = ctx.design.GetModule("MaxwellParameterSetup")
        allc = sum(coils.values(), [])
        oP.AssignTorque(["NAME:Torque_Cu", "Is Virtual:=", False, "Coordinate System:=", "Global", "Axis:=", "Z",
                         "Is Positive:=", True, "Objects:=", allc])
        m = ctx.design.GetModule("MeshSetup")
        for name, objs, Lmax in (("Len_Coils", allc, cfg.EQ_COIL_MESH), ("Len_Band", bands, cfg.FMR_BAND_MESH),
                                 ("Len_Magnets", mags, cfg.FMR_MAG_MESH), ("Len_Steel", steel + stationary, cfg.FMR_STEEL_MESH)):
            m.AssignLengthOp(["NAME:" + name, "RefineInside:=", True, "Enabled:=", True, "Objects:=", list(objs),
                              "RestrictElem:=", False, "NumMaxElem:=", "1000", "RestrictLength:=", True,
                              "MaxLength:=", mm(Lmax)])
        TR.transient_setup(ctx, step * n, step, 0)
        windings = ["Phase%s" % TAG[ph] for ph in PHASES]
        made = TR.reports(ctx, len(bands), ["Torque_Cu"], windings)
        ok = stages.validate_geometry(ctx, "EQ rotating model")
        ctx.log("AEDT Validation Check returned %s" % ok)
        ctx.project.Save()
        prog.update({"built": True, "offsets": offs, "reports": made, "bands": len(bands)})
        _save(ctx, prog)
    for run_name, ipk in (("noload", 0.0), ("load", cfg.FMR_IPK)):
        if run_name in prog["runs"]:
            continue
        ctx.set_var("Ipk", "%gA" % ipk)
        before = stages._messages(ctx) or []
        t0 = time.time()
        ctx.log("EQ rotating run '%s' (Ipk = %g A, %d steps of %.5f ms) ... solving" % (run_name, ipk, n, step))
        ctx.design.Analyze("Setup1")
        problems = stages._solve_problems(ctx, before)
        if problems:
            raise StageError("Run %s NOT accepted: %s" % (run_name, " | ".join(problems)))
        ctx.project.Save()
        rdir = os.path.join(ctx.results_dir(), run_name)
        if not os.path.isdir(rdir):
            os.makedirs(rdir)
        data = TR.export_reports(ctx, rdir, prog["reports"])
        prog["runs"][run_name] = {"ipk": ipk, "minutes": round((time.time() - t0) / 60.0, 1), "data": data}
        _save(ctx, prog)
        ctx.log("Run %s done in %.1f min" % (run_name, prog["runs"][run_name]["minutes"]))
    return summarise_rot(ctx, prog, cal, n, step)


def summarise_rot(ctx, prog, cal, n, step):
    cfg = ctx.cfg
    p = cfg.POLES // 2
    wm = cfg.RPM * 2 * math.pi / 60.0
    nc = cal["Ncoil_cal"]
    full = cfg.FMR_STEPS is None and n >= 8
    lines = ["EQUIVALENT-COIL ROTATING TRANSIENT %s (%s), %g rpm, %d steps, Ncoil %.4f (calibrated), %s"
             % (cfg.PROJECT_NAME, cfg.FM_DESIGN, cfg.RPM, n, nc, "one electrical period" if full else "SHORT run"), ""]
    res = {"Ncoil": nc}
    nl = prog["runs"].get("noload", {}).get("data", {})
    ld = prog["runs"].get("load", {}).get("data", {})

    def last_period(t, y):
        if not t:
            return [], []
        t_end = t[-1]
        keep = [(a, b) for a, b in zip(t, y) if a > t_end - (n * step * 1e-3) + 1e-12]
        return [a for a, b in keep], [b for a, b in keep]

    for ph in PHASES:
        key = "InducedVoltage(Phase%s)" % TAG[ph]
        if key in nl and nl.get("time_s"):
            t, e = last_period(nl["time_s"], [nc * v for v in nl[key]])
            res.setdefault("emf", {})[ph] = {"t_s": t, "e_V": e}
            if full and len(e) >= 8:
                th = [wm * x * 180 / math.pi for x in t]
                K1, psi, h3 = fieldmap.fourier(th, [v / wm for v in e], p)
                res["emf"][ph].update({"K1": K1, "psi": psi, "H3pct": h3, "E1_rms_V": wm * K1 / math.sqrt(2)})
                lines.append("No-load %s: K from back-EMF = %.3f mN.m/A, E1 = %.4f V rms, H3 %.1f %%"
                             % (ph, 1e3 * K1, wm * K1 / math.sqrt(2), h3))
    for name, d in (("no-load", nl), ("load", ld)):
        tq = [k for k in d if k.startswith("Moving") and k.endswith("Torque")]
        if tq and d.get("time_s"):
            tot = [sum(d[k][i] for k in tq) for i in range(len(d["time_s"]))]
            t, y = last_period(d["time_s"], tot)
            if y:
                mean = sum(y) / len(y)
                res.setdefault("torque", {})[name] = {"mean_Nm": mean, "pkpk_Nm": max(y) - min(y)}
                lines.append("%s rotor torque (Maxwell, with armature reaction): mean %+.4f mN.m, pk-pk %.4f mN.m%s"
                             % (name, 1e3 * mean, 1e3 * (max(y) - min(y)),
                                (" -> K = %.3f mN.m/A, ripple %.2f %%" % (1e3 * abs(mean) / (1.5 * cfg.FMR_IPK),
                                                                          100 * (max(y) - min(y)) / abs(mean)))
                                if name == "load" and mean else ""))
    if "SolidLoss" in nl:
        t, y = last_period(nl["time_s"], nl["SolidLoss"])
        if y:
            res["magnet_eddy_W"] = sum(y) / len(y)
            lines.append("Magnet eddy loss at no load: %.4g W" % res["magnet_eddy_W"])
    if "SolidLoss" in ld and ld.get("time_s"):
        t, y = last_period(ld["time_s"], ld["SolidLoss"])
        if y:
            res["magnet_eddy_load_W"] = sum(y) / len(y)
    tl = res.get("torque", {}).get("load")
    if tl and full:
        nst = len(prog.get("offsets", [0]))
        R = nst * cfg.N_BOARDS * 0.2656
        pout = abs(tl["mean_Nm"]) * wm
        pcu = 1.5 * cfg.FMR_IPK ** 2 * R
        pmag = res.get("magnet_eddy_load_W", res.get("magnet_eddy_W", 0.0))
        pin = pout + pcu + pmag
        res["efficiency"] = {"Pout_W": pout, "Pcu_dc_W": pcu, "Pmagnet_eddy_W": pmag, "Pin_W": pin,
                             "eta_pct": 100 * pout / pin if pin else None}
        lines.append("Efficiency at %g rpm, %g A pk (EM only, Maxwell torque WITH armature reaction): Pout %.4f W, copper DC "
                     "%.4f W, magnet eddy %.4g W -> eta %.1f %% (copper eddy not in this model: add the model-A estimate)"
                     % (cfg.RPM, cfg.FMR_IPK, pout, pcu, pmag, res["efficiency"]["eta_pct"]))
    fm, fmp = load_fm(cfg)
    if fm and full and "emf" in res:
        for ph in PHASES:
            Kf = fm.get("machine", {}).get(ph, {}).get("K1")
            if Kf and "K1" in res["emf"].get(ph, {}):
                d = 100 * (res["emf"][ph]["K1"] / Kf - 1)
                lines.append("VALIDATION %s: no-load K %+.2f %% vs the field map - calibrated on the static K, so this "
                             "checks the rotating solve, not the calibration" % (ph, d))
                res.setdefault("dK_vs_fm_pct", {})[ph] = d
        Ks = [res["emf"][ph]["K1"] for ph in PHASES if "K1" in res["emf"].get(ph, {})]
        if len(Ks) == 3:
            res["emf_balance_pct"] = 100 * (max(Ks) - min(Ks)) / (sum(Ks) / 3)
            lines.append("Back-EMF balance: K spread %.2f %% between the three phases" % res["emf_balance_pct"])
    with open(os.path.join(ctx.results_dir(), "eq_rot_summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(ctx.results_dir(), "eq_rot_results.json"), "w") as f:
        json.dump(res, f, indent=1)
    for l in lines:
        ctx.log(l)
    with open(os.path.join(ctx.results_dir(), "run_complete.txt"), "w") as f:
        f.write("%s rotating runs finished\n" % cfg.PROJECT_NAME)
    return res


def run(ctx, shared_dir, here):
    if ctx.cfg.PROFILE.endswith("_CAL"):
        return run_cal(ctx, shared_dir, here)
    return run_rot(ctx, shared_dir, here)
