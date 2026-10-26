# -*- coding: utf-8 -*-
"""FIELD-ONLY ROTATING TRANSIENT (FMROT, v10.0)  - Model A: the full motor rotating, no PCB copper in the mesh

The validated field-only method (fieldmap.py, gate passed 2026-10-08: board 1 within 1.4 % of the detailed FEM) run as a
real Maxwell 3D TRANSIENT with motion instead of at fixed rotor angles:

  * Maxwell: magnets (eddy currents ON) + rotor steel (non-linear) + air. The rotor turns at RPM inside a cylindrical
    band (T-Omega). Rev1-S: two bands, rotor steel split exactly as in the HPC model (transient.py); the stator volumes
    are stationary air zones with a fixed length mesh (where B is sampled).
  * No PCB copper is meshed (copper and FR-4 are mu_r = 1 and carry no current at no load -> no effect on the field).
  * At every time step B is exported on the trace centre-lines of every board (traces_board.json, the same 180 775 /
    361 550 points as the field map) and the copper is evaluated there:
        k_x(t)  = -T_copper/I   (Lorentz, per phase, per board)      -> back-EMF e_x(t) = omega_m * k_x(t)
        T(t)    = sum_x i_x(t) k_x(t), i_x = Ipk cos(p*theta - psi_x)  (synchronous load, armature reaction neglected)
        P_eddy  = sum over track pieces sigma/12 * (w^2 (dBz/dt)^2 + t^2 (dBn/dt)^2) * w t dl   (thin-conductor estimate)
  * Maxwell also gives the magnet eddy loss (SolidLoss) and the cogging torque on the rotor (Moving1.Torque).

VALIDATION: the rotor angle at step n is omega_m * t_n. With 48 steps per electrical period every 6th step lands on a
field-map angle (5.625 deg mech), so k(t) is compared point by point with the static field map
(<shared>/results/<FM_REF_PROJECT>_results/fieldmap_results.json) and by its fundamental (K1, psi). Gate: board 1
within 2 % / 1 deg, machine K within 2 %.

Restartable: fmrot_progress.json. Build -> solve -> export are separate steps; run the same runner again after a crash
(a finished solve is never repeated; the export restarts from the first step).
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

ZONE_EPS = 0.02                 # mm, stationary zones stop this short of the band faces
HARMONICS = (3, 5, 7, 9, 11, 13)


# ---------------------------------------------------------------------------------------------- geometry
def levels_for(cfg):
    if cfg.FM_DESIGN not in ("Rev0", "Rev1S"):
        raise StageError("FMROT supports Rev0 and Rev1S (FM_DESIGN = %s)" % cfg.FM_DESIGN)
    cfg.N_STAGES = 1 if cfg.FM_DESIGN == "Rev0" else 2
    cfg.R1_DOUBLE = False
    return TR.levels(cfg)


def build(ctx, geo):
    cfg = ctx.cfg
    L = levels_for(cfg)
    problems, notes = TR.check_levels(cfg, L)
    for n in notes:
        ctx.log("Band geometry: " + n)
    if problems:
        raise StageError("Band geometry: " + "; ".join(problems))
    top1, botN, offs = fieldmap.stator_offsets(cfg, geo)
    if len(offs) > 1 and abs(offs[1] - L["dz"]) > 1e-6:
        raise StageError("S2 offset mismatch: field map %.6f vs band levels %.6f mm" % (offs[1], L["dz"]))
    stages.st_project(ctx, geo)
    ctx.log("FMROT %s: field-only ROTATING transient, no PCB copper; B sampled on %d boards x 3 phases of trace "
            "centre-lines at every time step" % (cfg.FM_DESIGN, len(offs) * cfg.N_BOARDS))
    stationary_steel = []
    if cfg.FM_DESIGN == "Rev0":
        r1 = build_rotor.build_rotor(ctx, top1)
        mags, steel = list(r1["magnets"]), list(r1["steel"])
    else:
        top2 = top1 + offs[1]
        g2 = build_rotor.rotor_geometry(cfg, top2)
        r1 = build_rotor.build_rotor(ctx, top1, prefix="R1_", shaft=True, shaft_top=g2["zb1"] + cfg.SHAFT_ABOVE_ROTOR)
        r2 = build_rotor.build_rotor(ctx, top2, prefix="R2_", make_cs=False, shaft=False)
        ctx.rename(ctx.unite(list(r1["steel"]) + list(r2["steel"])), "RotorSteel")
        split = TR.split_rotor_steel(ctx, cfg, L)
        mags = list(r1["magnets"]) + list(r2["magnets"])
        steel = sum(split["moving"].values(), [])
        stationary_steel = list(split["stationary"])
    g = cfg.AIR_GAP
    zones = [("S1Zone", botN - 0.3, top1 + g / 2.0 - ZONE_EPS)]
    if cfg.FM_DESIGN != "Rev0":
        zones.append(("S2Zone", L["stator_bots"][1] - g / 2.0 + ZONE_EPS, L["stator_tops"][1] + g / 2.0 - ZONE_EPS))
    made = []
    for name, z0, z1 in zones:
        outer = ctx.cylinder(name, 0, 0, z0, z1 - z0, cfg.FM_ZONE_R1, "vacuum", "(200 255 200)", 0, 0.95)
        hole = ctx.cylinder(name + "_hole", 0, 0, z0 - 0.01, z1 - z0 + 0.02, cfg.FM_ZONE_R0, "vacuum", "(0 0 0)")
        ctx.subtract([outer], [hole], keep_tools=False)
        made.append(name)
        ctx.log("Stationary stator zone %s: r %.1f-%.1f mm, z %.5f..%.5f (no copper; B sampled on the trace paths)"
                % (name, cfg.FM_ZONE_R0, cfg.FM_ZONE_R1, z0, z1))
    bands = TR.add_bands(ctx, cfg, L, cfg.RPM)
    setup_model.create_region(ctx, plus_y_zero=False)
    ctx.log("Region padding %.1f mm on every side (the validated field map used 20 mm)" % cfg.REGION_PADDING)
    setup_model.set_eddy(ctx, mags, bool(cfg.MAGNET_EDDY), "magnets")
    setup_model.set_eddy(ctx, steel + stationary_steel, False, "rotor steel")
    m = ctx.design.GetModule("MeshSetup")
    for name, objs, Lmax, cap in (("Len_Zones", made, cfg.FM_ZONE_MESH, cfg.FM_ZONE_MAX_ELEMS),
                                  ("Len_Band", bands, cfg.FMR_BAND_MESH, 0),
                                  ("Len_Magnets", mags, cfg.FMR_MAG_MESH, 0),
                                  ("Len_Steel", steel + stationary_steel, cfg.FMR_STEEL_MESH, 0)):
        m.AssignLengthOp(["NAME:" + name, "RefineInside:=", True, "Enabled:=", True, "Objects:=", list(objs),
                          "RestrictElem:=", bool(cap), "NumMaxElem:=", str(cap or 1000), "RestrictLength:=", True,
                          "MaxLength:=", mm(Lmax)])
    ctx.log("Fixed transient mesh: zones %.2f mm (at most %d elements), band %.2f mm, magnets %.2f mm, steel %.2f mm"
            % (cfg.FM_ZONE_MESH, cfg.FM_ZONE_MAX_ELEMS, cfg.FMR_BAND_MESH, cfg.FMR_MAG_MESH, cfg.FMR_STEEL_MESH))
    fe, period, step, n = timing(cfg)
    TR.transient_setup(ctx, step * n, step, 1)
    oR = ctx.design.GetModule("ReportSetup")
    rep = []
    for name, ys, req in (("FMR_Torque", ["Moving%d.Torque" % (i + 1) for i in range(len(bands))], True),
                          ("FMR_Loss", ["SolidLoss"], False),
                          ("FMR_Position", ["Moving%d.Position" % (i + 1) for i in range(len(bands))], False)):
        try:
            oR.CreateReport(name, "Transient", "Rectangular Plot", "Setup1 : Transient", ["Domain:=", "Sweep"],
                            ["Time:=", ["All"]], ["X Component:=", "Time", "Y Component:=", ys])
            rep.append(name)
        except Exception as e:
            if req:
                raise StageError("Report %s could not be created (%s)" % (name, e))
            ctx.log("Optional report %s not created (%s)" % (name, e), 1)
    ok = stages.validate_geometry(ctx, "FMROT model", allow_no_excitation=True)
    ctx.log("AEDT Validation Check returned %s" % ok)
    ctx.project.Save()
    return {"offsets": offs, "bands": bands, "reports": rep, "magnets": len(mags), "zones": made}


def timing(cfg):
    fe = cfg.RPM / 60.0 * (cfg.POLES // 2)
    period = 1000.0 / fe                                  # ms
    step = period / cfg.FMR_SPP
    n = int(cfg.FMR_STEPS) if cfg.FMR_STEPS else int(round(cfg.FMR_SPP * cfg.FMR_PERIODS))
    return fe, period, step, n


# ---------------------------------------------------------------------------------------------- export
def _export(ctx, out, pts_path, t_ms, variant, tfmt):
    oF = ctx.design.GetModule("FieldsReporter")
    oF.CalcStack("clear")
    oF.EnterQty("B")
    oF.ExportToFile(out, pts_path, "Setup1 : Transient", ["Time:=", tfmt % (t_ms if "ms" in tfmt else t_ms * 1e-3)],
                    ["NAME:ExportOption", "IncludePtInOutput:=", True, "RefCSName:=", "Global",
                     "PtInSI:=", variant[2], "FieldInRefCS:=", False])
    oF.CalcStack("clear")


TFMTS = ["%.9gms", "%.12gs"]


def pick_export(ctx, pts, t_ms, rdir):
    """Field-export variant + time format that echo the requested points (probe of 20 points)."""
    probe = pts[:: max(1, len(pts) // 20)][:20]
    for vi, v in enumerate(fieldmap.EXPORT_VARIANTS):
        for tf in TFMTS:
            pp = os.path.join(rdir, "probe.pts")
            out = os.path.join(rdir, "probe.fld")
            try:
                fieldmap.write_points(pp, probe, v[0], v[1])
                _export(ctx, out, pp, t_ms, v, tf)
                rows = fieldmap.read_fld(out)
            except Exception as e:
                ctx.log("Export variant %d / %s failed (%s)" % (vi, tf, e), 1)
                continue
            if len(rows) != len(probe):
                continue
            for s_out in (1.0, 1e3):
                if all(abs(r[0] * s_out - p[0]) < 1e-3 and abs(r[2] * s_out - p[2]) < 1e-3 for r, p in zip(rows, probe)):
                    bmax = max(math.sqrt(r[3] ** 2 + r[4] ** 2 + r[5] ** 2) for r in rows)
                    if bmax > 5.0 or bmax < 1e-4:
                        raise StageError("Probe |B| = %.4g T is not plausible - check the field export" % bmax)
                    ctx.log("Field export: variant %d, time format %s accepted (points echoed in %s, probe |B|max %.3f T)"
                            % (vi, tf, "mm" if s_out == 1.0 else "m", bmax))
                    return vi, tf, s_out
    raise StageError("No field-export variant / time format returned the requested points at t = %.4f ms" % t_ms)


class Eddy(object):
    """Thin-conductor eddy loss in the PCB tracks from dB/dt between consecutive saved steps (periodic)."""

    def __init__(self, meta, cfg, width_mm):
        self.idx = [i for i, m in enumerate(meta) if m[3] == 0]
        self.key = [(meta[i][0], meta[i][1]) for i in self.idx]
        geo = []
        for i in self.idx:
            dlx, dly = meta[i][5], meta[i][6]
            dl = math.hypot(dlx, dly)
            geo.append((-dly / dl if dl else 0.0, dlx / dl if dl else 0.0, dl))
        self.geo = geo
        self.w = width_mm * 1e-3
        self.t = 0.035e-3
        self.sigma = cfg.CU_SIGMA
        self.first = None
        self.prev = None
        self.acc = {}
        self.pairs = 0

    def _comp(self, rows):
        out = []
        for i, (nx, ny, dl) in zip(self.idx, self.geo):
            r = rows[i]
            out.append((r[5], r[3] * nx + r[4] * ny))
        return out

    def _add(self, a, b, dt):
        c = self.sigma / 12.0 / (dt * dt)
        for (bz0, bn0), (bz1, bn1), (nx, ny, dl), key in zip(a, b, self.geo, self.key):
            p = c * (self.w * self.w * (bz1 - bz0) ** 2 + self.t * self.t * (bn1 - bn0) ** 2) * self.w * self.t * dl * 1e-3
            self.acc[key] = self.acc.get(key, 0.0) + p
        self.pairs += 1

    def step(self, rows, dt):
        cur = self._comp(rows)
        if self.first is None:
            self.first = cur
        else:
            self._add(self.prev, cur, dt)
        self.prev = cur

    def close(self, dt, periodic):
        if periodic and self.first is not None and self.prev is not None:
            self._add(self.prev, self.first, dt)
        n = max(1, self.pairs)
        return dict((k, v / n) for k, v in self.acc.items())


# ---------------------------------------------------------------------------------------------- analysis
def dft(ys, h):
    n = len(ys)
    c = sum(y * cmath.exp(-2j * math.pi * h * i / float(n)) for i, y in enumerate(ys)) * 2.0 / n
    return c


def fund(thetas, ks, p):
    K1, psi, _ = fieldmap.fourier(thetas, ks, p)
    return K1, psi


def load_fm_reference(cfg):
    if not cfg.FM_REF_PROJECT:
        return None
    for base in (cfg.SHARED_RESULTS_DIR, cfg.SAVE_DIR):
        if not base:
            continue
        p = os.path.join(base, cfg.FM_REF_PROJECT + "_results", "fieldmap_results.json")
        if os.path.isfile(p):
            with open(p) as f:
                return json.load(f), p
    return None


def summarise(ctx, prog, offs, full, loss_rep, torque_rep):
    cfg = ctx.cfg
    p = cfg.POLES // 2
    wm = cfg.RPM * 2 * math.pi / 60.0
    keys = sorted(prog["steps"])
    ts = [prog["steps"][k]["t_ms"] for k in keys]
    th = [wm * t * 1e-3 * 180.0 / math.pi for t in ts]                     # deg mech
    nst = len(offs)
    phases = ["PHASE_A", "PHASE_B", "PHASE_C"]

    def series(s, kb, ph):
        return [prog["steps"][k]["k"]["%d|%d|%s" % (s, kb, ph)] for k in keys]

    res = {"design": cfg.FM_DESIGN, "t_ms": ts, "theta_deg": th, "boards": {}, "stators": {}, "machine": {}}
    lines = ["FIELD-ONLY ROTATING TRANSIENT (FMROT) - %s (%s), %g rpm, %d steps of %.5f ms (%s)"
             % (cfg.PROJECT_NAME, cfg.FM_DESIGN, cfg.RPM, len(ts), ts[1] - ts[0] if len(ts) > 1 else ts[0],
                "one full electrical period" if full else "SHORT run - not a full period"),
             "k = -T_copper/I per phase (Lorentz on the trace centre-lines, 1 A into L1), e = omega_m * k", ""]
    for s in range(nst):
        for ph in phases:
            tot = [0.0] * len(ts)
            for kb in range(cfg.N_BOARDS):
                ks = series(s, kb, ph)
                tot = [a + b for a, b in zip(tot, ks)]
                res["boards"]["S%d_B%d_%s" % (s + 1, kb + 1, ph)] = {"k": ks}
            res["stators"]["S%d_%s" % (s + 1, ph)] = {"k": tot}
    for ph in phases:
        k = list(res["stators"]["S1_%s" % ph]["k"])
        for s in range(1, nst):
            k = [a + b for a, b in zip(k, res["stators"]["S%d_%s" % (s + 1, ph)]["k"])]
        res["machine"][ph] = {"k": k, "emf_V": [wm * x for x in k]}
    gate = {}
    if full:
        for grp in ("boards", "stators"):
            for name, d in res[grp].items():
                d["K1"], d["psi"] = fund(th, d["k"], p)
        for ph in phases:
            d = res["machine"][ph]
            d["K1"], d["psi"] = fund(th, d["k"], p)
            c1 = dft(d["k"], 1)
            d["H_pct"] = dict(("H%d" % h, 100.0 * abs(dft(d["k"], h)) / abs(c1)) for h in HARMONICS if h < len(ts) / 2)
            d["THD_pct"] = math.sqrt(sum(v * v for v in d["H_pct"].values()))
            d["E1_rms_V"] = wm * d["K1"] / math.sqrt(2)
        KA = res["machine"]["PHASE_A"]["K1"]
        lines.append("MACHINE (all stators in series):")
        for ph in phases:
            d = res["machine"][ph]
            lines.append("  %s: K1 = %.3f mN.m/A, psi = %+.2f deg elec, E1 = %.4f V rms at %g rpm, THD %.1f %% (%s)"
                         % (ph, 1e3 * d["K1"], d["psi"], d["E1_rms_V"], cfg.RPM, d["THD_pct"],
                            ", ".join("%s %.1f%%" % (h, v) for h, v in sorted(d["H_pct"].items(), key=lambda x: int(x[0][1:])))))
        Ks = [res["machine"][ph]["K1"] for ph in phases]
        ps = [res["machine"][ph]["psi"] for ph in phases]
        steps_d = [((ps[(i + 1) % 3] - ps[i]) + 180) % 360 - 180 for i in range(3)]
        res["balance"] = {"K_spread_pct": 100 * (max(Ks) - min(Ks)) / (sum(Ks) / 3), "phase_steps_deg": steps_d}
        lines.append("  balance: K spread %.2f %%, phase steps %s deg elec (ideal +-120)"
                     % (res["balance"]["K_spread_pct"], ", ".join("%+.1f" % x for x in steps_d)))
        # synchronous load: i_x = Ipk cos(p theta - psi_x) -> T(t) = sum i_x k_x
        ipk = cfg.FMR_IPK
        T = []
        for i, t in enumerate(th):
            T.append(sum(ipk * math.cos(math.radians(p * t - res["machine"][ph]["psi"])) * res["machine"][ph]["k"][i]
                         for ph in phases))
        Tm = sum(T) / len(T)
        res["load"] = {"Ipk_A": ipk, "T_Nm": T, "T_mean_Nm": Tm, "ripple_pkpk_pct": 100 * (max(T) - min(T)) / abs(Tm) if Tm else None,
                       "K_from_load_mNm_per_A": 1e3 * Tm / (1.5 * ipk)}
        lines.append("  synchronous load %.2f A pk: T mean %.3f mN.m (K = %.3f mN.m/A), ripple %.2f %% pk-pk "
                     "(armature reaction neglected)" % (ipk, 1e3 * Tm, 1e3 * Tm / (1.5 * ipk), res["load"]["ripple_pkpk_pct"]))
        R = nst * cfg.N_BOARDS * 0.2656
        pcu = 1.5 * ipk * ipk * R
        res["copper_dc_W"] = pcu
        lines.append("  copper DC loss at %.2f A pk: %.4f W (R = %.3f ohm per phase, 0.2656 ohm per board-phase, trace model)"
                     % (ipk, pcu, R))
        lines.append("")
        lines.append("Stators (series sum of the 5 boards):")
        for s in range(nst):
            for ph in phases:
                d = res["stators"]["S%d_%s" % (s + 1, ph)]
                lines.append("  S%d %s: K1 = %.3f mN.m/A, psi = %+.2f deg" % (s + 1, ph, 1e3 * d["K1"], d["psi"]))
        lines.append("Phase A per board (S1): " + ", ".join(
            "B%d %.4f" % (kb + 1, 1e3 * res["boards"]["S1_B%d_PHASE_A" % (kb + 1)]["K1"]) for kb in range(cfg.N_BOARDS)))
    # ---- validation against the static field map
    ref = load_fm_reference(cfg)
    if ref:
        fm, path = ref
        lines += ["", "VALIDATION against the static field map %s" % path]
        fth = [float(x) for x in fm["thetas"]]
        devs = []
        for ph in phases:
            for s_ in range(nst):
                for kb in range(cfg.N_BOARDS):
                    name = "S%d_B%d_%s" % (s_ + 1, kb + 1, ph)
                    if name not in fm["boards"]:
                        continue
                    K1f = fm["boards"][name]["K1"]
                    for i, t in enumerate(th):
                        for jj, f in enumerate(fth):
                            if abs(((t - f) + 22.5) % 45.0 - 22.5) < 1e-3:
                                a = res["boards"][name]["k"][i]
                                b = fm["boards"][name]["k"][jj]
                                devs.append((name, t, a, b, 100 * (a - b) / K1f))
        for name, t, a, b, d in [x for x in devs if x[0].startswith("S1_B1_")]:
            lines.append("  %s theta %7.3f deg: rotating k = %+.5f, static k = %+.5f mWb/rad (%+.2f %% of K1)"
                         % (name, t, 1e3 * a, 1e3 * b, d))
        worst = max(devs, key=lambda x: abs(x[4])) if devs else None
        gate["pointwise_max_pct_of_K1"] = abs(worst[4]) if worst else float("nan")
        if worst:
            lines.append("  largest point difference over all %d board-phase-angle points: %.2f %% of K1 (%s at %.3f deg)"
                         % (len(devs), abs(worst[4]), worst[0], worst[1]))
        if full:
            lines.append("  per board (all phases): rotating / static K1 ratio and psi difference")
            worst_b = (0.0, 0.0, "")
            for ph in phases:
                cells = []
                for s_ in range(nst):
                    for kb in range(cfg.N_BOARDS):
                        name = "S%d_B%d_%s" % (s_ + 1, kb + 1, ph)
                        if name not in fm["boards"]:
                            continue
                        r = res["boards"][name]["K1"] / fm["boards"][name]["K1"]
                        dp = ((res["boards"][name]["psi"] - fm["boards"][name]["psi"]) + 180) % 360 - 180
                        res["boards"][name].update({"ratio_fm": r, "dpsi_fm": dp})
                        cells.append("S%dB%d %.4f/%+.2f" % (s_ + 1, kb + 1, r, dp))
                        if abs(100 * (r - 1)) > abs(worst_b[0]):
                            worst_b = (100 * (r - 1), dp, name)
                lines.append("    %s: %s" % (ph, ", ".join(cells)))
            dM = {}
            for ph in phases:
                mK = fm.get("machine", {}).get(ph, {}).get("K1")
                if mK:
                    dM[ph] = 100 * (res["machine"][ph]["K1"] / mK - 1)
            b1 = [(ph, 100 * (res["boards"]["S1_B1_%s" % ph]["K1"] / fm["boards"]["S1_B1_%s" % ph]["K1"] - 1),
                   ((res["boards"]["S1_B1_%s" % ph]["psi"] - fm["boards"]["S1_B1_%s" % ph]["psi"]) + 180) % 360 - 180)
                  for ph in phases if "S1_B1_%s" % ph in fm["boards"]]
            ok = all(abs(dk) <= 2.0 and abs(dp) <= 1.0 for ph, dk, dp in b1) and all(abs(v) <= 2.0 for v in dM.values())
            gate.update({"board1": dict((ph, {"dK_pct": dk, "dpsi_deg": dp}) for ph, dk, dp in b1),
                         "dK_machine_pct": dM, "worst_board": {"name": worst_b[2], "dK_pct": worst_b[0], "dpsi": worst_b[1]},
                         "pass": ok})
            lines.append("  GATE: board 1 %s; machine K %s (limits 2 %% / 1 deg / 2 %%); worst board %s %+.2f %% -> %s"
                         % ("; ".join("%s %+.2f %% / %+.2f deg" % x for x in b1),
                            ", ".join("%s %+.2f %%" % (ph[-1], v) for ph, v in sorted(dM.items())),
                            worst_b[2], worst_b[0], "PASS" if ok else "FAIL"))
        else:
            ok = gate["pointwise_max_pct_of_K1"] <= 3.0
            gate["pass_short"] = ok
            lines.append("  SHORT-RUN CHECK (all phases, all boards): largest point difference %.2f %% of K1 (limit 3 %%) -> %s"
                         % (gate["pointwise_max_pct_of_K1"], "PASS" if ok else "FAIL"))
    else:
        lines += ["", "No static field-map results found for %s - validation skipped (copy %s_results into the shared "
                  "results folder)" % (cfg.FM_REF_PROJECT, cfg.FM_REF_PROJECT)]
    res["gate"] = gate
    # ---- losses and cogging from Maxwell
    if loss_rep:
        res["magnet_eddy_W_mean"] = loss_rep
        lines.append("Magnet eddy loss (Maxwell SolidLoss, mean over the run): %.4g W" % loss_rep)
    if torque_rep:
        res["cogging_pkpk_mNm"] = torque_rep
        lines.append("Rotor torque at no load (cogging + reluctance, Maxwell): %.4f mN.m pk-pk" % torque_rep)
    if prog.get("eddy"):
        tot = sum(prog["eddy"].values())
        res["copper_eddy_W"] = prog["eddy"]
        lines.append("Copper eddy loss estimate at %g rpm (thin-conductor formula on the trace pieces, vias excluded): %.4g W"
                     % (cfg.RPM, tot) + ("" if full else " (SHORT run: not a full period - indicative only)"))
        for s in range(nst):
            lines.append("  S%d: " % (s + 1) + ", ".join("B%d %.3g W" % (kb + 1, prog["eddy"].get("%d|%d" % (s, kb), 0.0))
                                                         for kb in range(cfg.N_BOARDS)))
    fl = prog.get("fields") or {}
    if fl.get("steel"):
        res["steel_B"] = fl["steel"]
        lines.append("")
        lines.append("Magnetic field distribution (8 instants per period, point files B_*.fld / Bsteel_*.fld for plots):")
        for name, st in sorted(fl["steel"].items()):
            lines.append("  %s: |B| max %.3f T, p99 %.3f T, mean %.3f T, %.1f %% above 1.6 T"
                         % (name, st["max_T"], st["p99_T"], st["mean_T"], 100 * st["frac_above_1p6T"]))
        for name, st in sorted(fl.get("gap", {}).items()):
            lines.append("  %s (0.25 mm off the stator face): |B| max %.3f T, mean %.3f T" % (name, st["max_T"], st["mean_T"]))
    cd = prog.get("current_density") or {}
    if cd:
        res["current_density_per_A"] = cd
        lines.append("Current density in the tracks per 1 A phase current (DC share over 0.5 mm x 35 um; file "
                     "current_density_board1_per_A.csv): " + "; ".join(
                         "%s max %.1f / p95 %.1f / mean %.1f A/mm2" % (ph[-1], d["J_max_A_per_mm2"], d["J_p95_A_per_mm2"],
                                                                       d["J_mean_A_per_mm2"]) for ph, d in sorted(cd.items())))
    if full and "load" in res:
        Rph = nst * cfg.N_BOARDS * 0.2656
        Pe_cu = sum(prog.get("eddy", {}).values())
        Pe_mag = res.get("magnet_eddy_W_mean") or 0.0
        K = res["load"]["T_mean_Nm"] / (1.5 * cfg.FMR_IPK)
        lines.append("")
        lines.append("EFFICIENCY (EM only, no bearing/windage; copper eddy and magnet eddy scale with speed^2, copper DC "
                     "with current^2, torque = 1.5 K I):")
        lines.append("  %6s %6s %9s %9s %9s %9s %9s %7s" % ("rpm", "Ipk A", "T mN.m", "Pout W", "Pcu W", "Peddy W", "Pin W", "eta %"))
        table = []
        for rpm in (500.0, 1000.0, 2000.0):
            for ipk in (0.5, 1.0, 2.0):
                wmx = rpm * 2 * math.pi / 60.0
                Tq = 1.5 * K * ipk
                pout = Tq * wmx
                pcu = 1.5 * ipk * ipk * Rph
                ped = (Pe_cu + Pe_mag) * (rpm / cfg.RPM) ** 2
                pin = pout + pcu + ped
                eta = 100 * pout / pin if pin > 0 else float("nan")
                table.append({"rpm": rpm, "Ipk_A": ipk, "T_Nm": Tq, "Pout_W": pout, "Pcu_W": pcu, "Peddy_W": ped,
                              "Pin_W": pin, "eta_pct": eta})
                lines.append("  %6.0f %6.2f %9.3f %9.4f %9.4f %9.4f %9.4f %7.1f" % (rpm, ipk, 1e3 * Tq, pout, pcu, ped, pin, eta))
        res["efficiency_table"] = table
        with open(os.path.join(ctx.results_dir(), "loss_table_for_icepak.csv"), "w") as f:
            f.write("part,stator,board,P_W_at_%grpm_%gApk,note\n" % (cfg.RPM, cfg.FMR_IPK))
            for s_ in range(nst):
                for kb in range(cfg.N_BOARDS):
                    f.write("PCB copper DC,S%d,%d,%.6f,3 phases x 1.5 Ipk^2 x 0.2656/3 ohm per board-phase\n"
                            % (s_ + 1, kb + 1, 1.5 * cfg.FMR_IPK ** 2 * 0.2656))
                    f.write("PCB copper eddy,S%d,%d,%.6f,thin-conductor estimate\n"
                            % (s_ + 1, kb + 1, prog.get("eddy", {}).get("%d|%d" % (s_, kb), 0.0)))
            f.write("Magnets (all),-,-,%.6f,Maxwell SolidLoss mean\n" % Pe_mag)
        lines.append("  per-board loss table for the thermal model: loss_table_for_icepak.csv")
    lines += ["", "Neglected: armature reaction (no copper in the field solve), skin/proximity effects, the averaging of "
              "B over the 0.5 mm x 35 um track cross-section (centre-line sampling), via eddy currents."]
    d = ctx.results_dir()
    with open(os.path.join(d, "fmrot_summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(d, "fmrot_results.json"), "w") as f:
        json.dump(res, f, indent=1)
    with open(os.path.join(d, "fmrot_waveforms.csv"), "w") as f:
        cols = ["t_ms", "theta_mech_deg"] + ["k_%s_Wb_per_rad" % ph for ph in phases] + ["e_%s_V" % ph for ph in phases]
        if "load" in res:
            cols.append("T_load_Nm")
        f.write(",".join(cols) + "\n")
        for i in range(len(ts)):
            row = [ts[i], th[i]] + [res["machine"][ph]["k"][i] for ph in phases] + \
                  [res["machine"][ph]["emf_V"][i] for ph in phases]
            if "load" in res:
                row.append(res["load"]["T_Nm"][i])
            f.write(",".join("%.8g" % v for v in row) + "\n")
    for l in lines:
        ctx.log(l)
    return res


def field_maps(ctx, cfg, rdir, times, here):
    """Magnetic field distribution: B on polar grids 0.25 mm off every stator face (in the stationary air) and on the
    mid-thickness plane of every rotor steel disc, at 8 instants per electrical period (point files for plots and
    animations), plus |B| statistics in the steel (saturation check, steel_1010 knee ~1.5-1.6 T)."""
    L = dict(levels_for(cfg))
    L["gap"] = 0.5                                  # planes 0.25 mm off each stator face (export_fields uses gap/2)
    every = max(1, len(times) // 8)
    sel = times[every - 1::every]
    try:
        files = TR.export_fields(ctx, cfg, L, rdir, sel, False, here)
    except Exception as e:
        ctx.log("Field maps not exported (%s)" % e, 1)
        return {}
    out = {"times_ms": sel, "files": len(files), "steel": {}, "gap": {}}
    for fn in files:
        rows = fieldmap.read_fld(os.path.join(rdir, fn))
        st = TR.bstats(rows)
        if not st:
            continue
        grp = "steel" if fn.startswith("Bsteel_") else "gap"
        name = fn.split("_t")[0]
        prev = out[grp].get(name)
        if prev is None or st["max_T"] > prev["max_T"]:
            out[grp][name] = st
    for name, st in sorted(out["steel"].items()):
        ctx.log("Steel %s: |B| max %.3f T, 99th percentile %.3f T, mean %.3f T, %.1f %% of points above 1.6 T"
                % (name, st["max_T"], st["p99_T"], st["mean_T"], 100 * st["frac_above_1p6T"]))
    for name, st in sorted(out["gap"].items()):
        ctx.log("Field map %s: |B| max %.3f T, mean %.3f T" % (name, st["max_T"], st["mean_T"]))
    return out


def current_density(cfg, T, rdir):
    """Current density in every track piece of board 1 for 1 A into each phase (DC share from the nodal solve in
    traces_board.json over the 0.5 mm x 35 um cross-section). At 133 Hz the skin depth (5.7 mm) is far larger than the
    copper, so the DC distribution holds; multiply by the phase current."""
    w = T["_meta"].get("width_mm", 0.5)
    t = 0.035
    out = {}
    with open(os.path.join(rdir, "current_density_board1_per_A.csv"), "w") as f:
        f.write("phase,layer,x0_mm,y0_mm,x1_mm,y1_mm,I_share_A,J_A_per_mm2\n")
        for ph in ("PHASE_A", "PHASE_B", "PHASE_C"):
            js = []
            for L, x0, y0, x1, y1, I in T[ph]["tracks"]:
                J = abs(I) / (w * t)
                js.append(J)
                f.write("%s,%s,%.4f,%.4f,%.4f,%.4f,%.5f,%.4f\n" % (ph, L, x0, y0, x1, y1, I, J))
            js.sort()
            out[ph] = {"J_max_A_per_mm2": js[-1], "J_p95_A_per_mm2": js[int(0.95 * (len(js) - 1))],
                       "J_mean_A_per_mm2": sum(js) / len(js)}
    return out


def report_stats(ctx, rdir):
    """Mean SolidLoss and pk-pk rotor torque from the Maxwell reports (None if unavailable)."""
    loss, tq = None, None
    oR = ctx.design.GetModule("ReportSetup")
    for name in ("FMR_Loss", "FMR_Torque"):
        p = os.path.join(rdir, name + ".csv")
        try:
            oR.ExportToFile(name, p)
            c = TR.read_csv(p)
            ys = [v for k, v in c.items() if not k.lower().startswith("time")]
            if not ys:
                continue
            if name == "FMR_Loss":
                y = ys[0][1:] if len(ys[0]) > 2 else ys[0]
                loss = sum(y) / len(y)
            else:
                tot = [sum(v[i] for v in ys) for i in range(len(ys[0]))]
                tq = 1e3 * (max(tot) - min(tot))
        except Exception as e:
            ctx.log("Report %s not exported (%s)" % (name, e), 1)
    return loss, tq


# ---------------------------------------------------------------------------------------------- run
def _pp(ctx):
    return os.path.join(ctx.results_dir(), "fmrot_progress.json")


def _save(ctx, prog):
    with open(_pp(ctx), "w") as f:
        json.dump(prog, f)


def run(ctx, shared_dir, here):
    cfg = ctx.cfg
    geo = pcb_geometry.load()
    T = fieldmap.load_traces(here)
    rdir = ctx.results_dir()
    prog = {"built": False, "solved": False, "steps": {}}
    if os.path.isfile(_pp(ctx)):
        with open(_pp(ctx)) as f:
            prog = json.load(f)
    fe, period, step, n = timing(cfg)
    if prog.get("built") and os.path.isfile(ctx.project_path()):
        ctx.project = ctx.desktop.OpenProject(ctx.project_path())
        ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
        ctx.attach_design()
        ctx.log("Resumed %s (built%s)" % (cfg.PROJECT_NAME, ", solved" if prog.get("solved") else ""))
        levels_for(cfg)
    else:
        if os.path.isfile(ctx.project_path()):
            raise StageError("%s exists but was never fully built - delete it and its _results folder, then run again"
                             % ctx.project_path())
        info = build(ctx, geo)
        prog.update({"built": True, "offsets": info["offsets"], "build": info})
        _save(ctx, prog)
    offs = prog["offsets"]
    ctx.log("Transient: fe %.3f Hz, period %.4f ms, %d steps per period, %d steps (%.4f ms), fields saved every step"
            % (fe, period, cfg.FMR_SPP, n, n * step))
    if not prog.get("solved"):
        before = stages._messages(ctx) or []
        t0 = time.time()
        ctx.log("Solving the rotating transient (this blocks until the last step) ...")
        ctx.design.Analyze("Setup1")
        problems = stages._solve_problems(ctx, before)
        if problems:
            raise StageError("Transient solve NOT accepted: %s" % " | ".join(problems))
        ctx.project.Save()
        prog["solved"] = True
        prog["solve_minutes"] = round((time.time() - t0) / 60.0, 1)
        _save(ctx, prog)
        ctx.log("Transient solved in %.1f min (%.2f min per step)" % (prog["solve_minutes"], prog["solve_minutes"] / n))
    pts, meta = fieldmap.point_list(cfg, T, offs)
    ctx.log("Trace sample points: %d (%d stator(s) x %d boards x 3 phases)" % (len(pts), len(offs), cfg.N_BOARDS))
    times = [k * step for k in range(1, n + 1)]
    if "variant" not in prog:
        prog["variant"], prog["tfmt"], prog["echo"] = pick_export(ctx, pts, times[0], rdir)
        _save(ctx, prog)
    v = fieldmap.EXPORT_VARIANTS[prog["variant"]]
    pp = os.path.join(rdir, "trace_points.pts")
    fieldmap.write_points(pp, pts, v[0], v[1])
    meta_m = [(m[0], m[1], m[2], m[3], m[4], m[5] * 1e-3, m[6] * 1e-3) for m in meta]
    eddy = Eddy(meta, cfg, T["_meta"].get("width_mm", 0.5))
    prog["steps"] = {}
    s = prog["echo"]
    for k, t in enumerate(times):
        t0 = time.time()
        out = os.path.join(rdir, "B_on_traces_step%03d.fld" % (k + 1))
        _export(ctx, out, pp, t, v, prog["tfmt"])
        rows = fieldmap.read_fld(out)
        if len(rows) != len(pts):
            raise StageError("Field export returned %d of %d points at t = %.5f ms" % (len(rows), len(pts), t))
        rows = [[r[0] * s * 1e-3, r[1] * s * 1e-3, r[2] * s * 1e-3, r[3], r[4], r[5]] for r in rows]
        for (x, y, z), r in zip(pts[:: max(1, len(pts) // 50)], rows[:: max(1, len(pts) // 50)]):
            if abs(r[0] * 1e3 - x) > 1e-3 or abs(r[1] * 1e3 - y) > 1e-3:
                raise StageError("Exported points are not in the requested order - cannot map B to the traces")
        Tq = fieldmap.torques(meta_m, rows, len(offs), cfg.N_BOARDS)
        eddy.step(rows, step * 1e-3)
        prog["steps"]["%03d" % (k + 1)] = {"t_ms": t, "k": dict(("%d|%d|%s" % kk, -val) for kk, val in Tq.items())}
        _save(ctx, prog)
        if k > 0:
            try:
                os.remove(out)                   # keep only the first step's field file (large)
            except Exception:
                pass
        ctx.log("Step %d/%d (t = %.4f ms, rotor %.3f deg): S1 board 1 phase A k = %+.4f mWb/rad (export %.1f s)"
                % (k + 1, n, t, cfg.RPM * 6.0 * t * 1e-3, 1e3 * prog["steps"]["%03d" % (k + 1)]["k"]["0|0|PHASE_A"],
                   time.time() - t0))
    full = cfg.FMR_STEPS is None and abs(cfg.FMR_PERIODS - round(cfg.FMR_PERIODS)) < 1e-9
    e = eddy.close(step * 1e-3, periodic=full)
    prog["eddy"] = dict(("%d|%d" % kk, val) for kk, val in e.items())
    _save(ctx, prog)
    prog["fields"] = field_maps(ctx, cfg, rdir, times, here)
    prog["current_density"] = current_density(cfg, T, rdir)
    _save(ctx, prog)
    loss, tq = report_stats(ctx, rdir)
    res = summarise(ctx, prog, offs, full and n >= 8, loss, tq)
    try:
        os.remove(pp)
    except Exception:
        pass
    with open(os.path.join(rdir, "run_complete.txt"), "w") as f:
        f.write("%s FMROT finished (%d steps); gate %s\n" % (cfg.PROJECT_NAME, n, res.get("gate")))
    return res
