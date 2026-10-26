# -*- coding: utf-8 -*-
"""
REV0 stack_sum.py - five-board stack back-EMF / torque versus air gap, from single-board results.

Physics: PCB copper and FR-4 are non-magnetic, so the PM field seen by board k does not depend on the other
boards. Board k of the stack sits at rotor distance d_k = g + (k-1)*pitch. Each board's Phase-A
dLam/dtheta fundamental is a phasor K1(d)*exp(j*psi(d)); the series string adds them as phasors:

    K_stack(g) = | sum_k K1(d_k) exp(j psi(d_k)) |          (all boards same orientation, series-aiding)

K1(d) and psi(d) come from the DOE distance series (REF_ROTOR_MS_DOE at AIR_GAP = d) plus the baseline
(d = 1.0 mm), interpolated log-linearly in K1 and linearly in psi. No extrapolation outside the solved range.

Run with plain Python (or AEDT Tools > Run Script). Writes <SAVE_DIR>/REV0_STACK_SUM/stack_vs_gap.csv,
board_curve.csv and stack_sum_report.txt.
"""
from __future__ import print_function

import cmath
import glob
import math
import os
import re

SAVE_DIR = ""             # "" = auto: <SHARED>\results (the OneDrive Motor run\results folder)
PATTERNS = ["REV0_DOE_D*_results", "REV0_REF_ROTOR_MS_SWEEP_results"]   # distance series + baseline
N_BOARDS = 5
PITCH = 1.02032          # mm, board pitch (1.0 mm board + 2 x 0.01016 mm mask)
POLES = 16
RPM = 1000.0
R_BOARD = 0.2777         # ohm per board-phase (GATE1 mean; R_phase = 5 x R_BOARD, jumpers excluded)
GAPS = [0.5, 0.75, 1.0, 1.25, 1.5]
MAG_R = 28.0             # mm, magnet centre radius -> pole pitch tau = 2*pi*MAG_R/POLES
MODEL = "exp"            # "exp": K1(d) = K1(1 mm)*exp(-k_eff*(d-1)), k_eff fitted to the solved points
                         # "interp": piecewise interpolation between solved points only (needs d up to g+4.08 mm)
REQUIRE_BACK_IRON = 2.0  # only use runs with the baseline back iron / magnet radius
REQUIRE_MAG_R = 28.0


def _shared_results_dir():
    """The results folder next to rev0 (OneDrive Motor run folder)."""
    sub = os.path.join("EEE4022S Ansys files", "Motor run")
    cands = []
    try:
        cands.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except NameError:
        pass
    for env in ("OneDriveCommercial", "OneDrive"):
        if os.environ.get(env):
            cands.append(os.path.join(os.environ[env], sub))
    cands += [os.path.join(os.path.expanduser("~"), "OneDrive - University of Cape Town", sub),
              r"C:\Users\khanz\OneDrive - University of Cape Town\EEE4022S Ansys files\Motor run"]
    for c in cands:
        if os.path.isdir(os.path.join(c, "results")):
            return os.path.join(c, "results")
    return r"D:\New folder"


def read_summary(path):
    out = {}
    with open(path) as f:
        for line in f:
            m = re.match(r"Geometry: air gap ([\d.]+) mm, back iron ([\d.]+) mm, magnet centre radius ([\d.]+) mm", line)
            if m:
                out["gap"], out["bi"], out["rmag"] = [float(x) for x in m.groups()]
            elif " = " in line:
                k, v = line.split(" = ", 1)
                out[k.strip()] = v.strip()
    return out


def load_points(save_dir):
    pts = {}
    for pat in PATTERNS:
        for d in glob.glob(os.path.join(save_dir, pat)):
            p = os.path.join(d, "rotor_sweep_summary.txt")
            if not os.path.isfile(p):
                continue
            s = read_summary(p)
            if "gap" not in s or "K1_dLam_dtheta_peak_Wb_per_rad" not in s:
                continue
            if abs(s["bi"] - REQUIRE_BACK_IRON) > 1e-6 or abs(s["rmag"] - REQUIRE_MAG_R) > 1e-6:
                continue
            pts[round(s["gap"], 4)] = (float(s["K1_dLam_dtheta_peak_Wb_per_rad"]), float(s["phase_of_k_elec_deg"]),
                                       os.path.basename(d))
    return [(d,) + pts[d] for d in sorted(pts)]


def interp(points, d):
    """K1, psi at distance d (log-linear in K1, linear in unwrapped psi). None outside the solved range."""
    ds = [p[0] for p in points]
    if d < ds[0] - 1e-9 or d > ds[-1] + 1e-9:
        return None
    psis = [points[0][2]]
    for p in points[1:]:
        x = p[2]
        while x - psis[-1] > 180:
            x -= 360
        while x - psis[-1] < -180:
            x += 360
        psis.append(x)
    for i in range(len(ds) - 1):
        if ds[i] - 1e-9 <= d <= ds[i + 1] + 1e-9:
            t = 0.0 if ds[i + 1] == ds[i] else (d - ds[i]) / (ds[i + 1] - ds[i])
            k = math.exp(math.log(points[i][1]) * (1 - t) + math.log(points[i + 1][1]) * t)
            return k, psis[i] * (1 - t) + psis[i + 1] * t
    return points[-1][1], psis[-1]


def back_iron_table(save_dir):
    """Back-iron DOE (REV0_DOE_BI*) + baseline: K1 and peak steel |B| at a 1.0 mm gap, per thickness."""
    rows = []
    for pat in ("REV0_DOE_BI*_results", "REV0_REF_ROTOR_MS_SWEEP_results"):
        for d in glob.glob(os.path.join(save_dir, pat)):
            p = os.path.join(d, "rotor_sweep_summary.txt")
            if not os.path.isfile(p):
                continue
            s = read_summary(p)
            if "bi" not in s or abs(s["gap"] - 1.0) > 1e-6 or abs(s["rmag"] - REQUIRE_MAG_R) > 1e-6:
                continue
            bmax = None
            fm = os.path.join(d, "rotor_field_metrics.csv")
            if os.path.isfile(fm):
                vals = []
                for line in open(fm).readlines()[1:]:
                    c = line.strip().split(",")
                    try:
                        vals.append(float(c[1]))
                    except (IndexError, ValueError):
                        pass
                bmax = max(vals) if vals else None
            rows.append((s["bi"], float(s["K1_dLam_dtheta_peak_Wb_per_rad"]), bmax, os.path.basename(d)))
    return sorted(rows)


def pts_at1(points):
    for p in points:
        if abs(p[0] - 1.0) < 1e-6:
            return p[1]
    return points[0][1]


def fit_exp(points):
    """Least squares ln K1 = a - k*d and psi = p0 + p1*d over the solved points."""
    n = float(len(points))
    ds = [p[0] for p in points]
    ls = [math.log(p[1]) for p in points]
    psis = [p[2] for p in points]
    md, ml, mp = sum(ds) / n, sum(ls) / n, sum(psis) / n
    sdd = sum((d - md) ** 2 for d in ds)
    k = -sum((d - md) * (l - ml) for d, l in zip(ds, ls)) / sdd
    p1 = sum((d - md) * (q - mp) for d, q in zip(ds, psis)) / sdd
    a, p0 = ml + k * md, mp - p1 * md
    resid = [100.0 * (math.exp(a - k * d) / p[1] - 1) for d, p in zip(ds, points)]
    return k, a, p0, p1, resid


REV1S_ROWS = []


def rev1_section(save_dir, out_dir, model, kfit, bi):
    """Rev1 = S1 (as Rev0) + S2 in series. S2 board k sees R2 like S1 sees R1, plus R1's back iron at distance
    L = 2g + 5*pitch from R2's magnet face. First-order image of an iron plane: K1_S2(d) = K1(d) *
    (1 + c * exp(-2 k (L - d - pitch/2))); c (= 1 for ideal iron) is calibrated on the REV1_S2_ENV FEM point."""
    out = ["", "Rev1-S (S1-R1(PM/Fe)-S2-R2, 32 magnets, stators in series, rotors aligned):"]
    envs = []
    for d in glob.glob(os.path.join(save_dir, "REV1_S2ENV_*_results")):
        p = os.path.join(d, "rotor_sweep_summary.txt")
        if not os.path.isfile(p):
            continue
        s = read_summary(p)
        rear = None
        for line in open(p):
            m = re.match(r"Rear steel: gap ([\d.]+) mm, thickness ([\d.]+) mm", line)
            if m:
                rear = [float(x) for x in m.groups()]
        if rear and "K1_dLam_dtheta_peak_Wb_per_rad" in s:
            envs.append((rear[0], rear[1], s["gap"], float(s["K1_dLam_dtheta_peak_Wb_per_rad"]), os.path.basename(d)))
    if not envs:
        out.append("  no REV1_S2ENV result yet (run_REV1_S2_ENV.py) - Rev1 not computed")
        return out
    k2 = [r[1] for r in bi if abs(r[0] - 2.0) < 1e-6]
    rows = []
    for g, t, d_env, k_env, src in sorted(envs):
        iron = 1.0
        kt = [r[1] for r in bi if abs(r[0] - t) < 1e-6]
        if abs(t - 2.0) > 1e-6:
            if kt and k2:
                iron = kt[0] / k2[0]
            else:
                out.append("  WARNING %s: no single-board result at back iron %.1f mm - K_iron(t)/K_iron(2) = 1 assumed"
                           % (src, t))
        L = 2 * g + N_BOARDS * PITCH
        k_free = iron * model(d_env)[0]
        c = (k_env / k_free - 1.0) / math.exp(-2 * kfit * (L - d_env - PITCH / 2.0))
        s1 = s2 = 0j
        per2 = []
        for kb in range(N_BOARDS):
            d = g + kb * PITCH
            k1, psi = model(d)
            k1 *= iron
            f = 1.0 + c * math.exp(-2 * kfit * (L - d - PITCH / 2.0))
            s1 += k1 * cmath.exp(1j * math.radians(psi))
            s2 += f * k1 * cmath.exp(1j * math.radians(psi))
            per2.append(f)
        K1s, K2s = abs(s1), abs(s2)
        K = abs(s1 + s2)
        r0, r1 = N_BOARDS * R_BOARD, 2 * N_BOARDS * R_BOARD
        km0 = 1.5 * K1s / math.sqrt(1.5 * r0)
        km1 = 1.5 * K / math.sqrt(1.5 * r1)
        wm = RPM * 2 * math.pi / 60.0
        rows.append((g, t, K1s, K2s, K, km0, km1))
        REV1S_ROWS.append({"g": g, "t": t, "K": K, "K_S1": K1s, "K_S2": K2s})
        out.append("  %s: gap %.2f mm, back iron %.1f mm. FEM S2-board-5 point: K1 = %.4f mN.m/A vs %.4f without "
                   "R1 steel (x%.3f) -> image coefficient c = %.3f (1 = ideal iron)"
                   % (src, g, t, 1e3 * k_env, 1e3 * k_free, k_env / k_free, c))
        out.append("    S2 board factors (board 1 nearest R2 ... board 5 nearest R1 steel): %s"
                   % " / ".join("%.3f" % f for f in per2))
        out.append("    K_S1 = %.2f, K_S2 = %.2f, K_Rev1 = %.2f mN.m/A (Rev1/Rev0 = %.2f); T_ideal = %.1f mN.m per A_pk; "
                   "E1 = %.3f V rms @ %g rpm; R_phase = %.3f ohm; Km = %.4f N.m/sqrt(W) (Rev0 %.4f, ratio %.2f)"
                   % (1e3 * K1s, 1e3 * K2s, 1e3 * K, K / K1s, 1.5e3 * K, wm * K / math.sqrt(2), RPM, r1, km1, km0,
                      km1 / km0))
    with open(os.path.join(out_dir, "rev1_vs_rev0.csv"), "w") as f:
        f.write("gap_mm,back_iron_mm,K_S1_Nm_per_A,K_S2_Nm_per_A,K_Rev1_Nm_per_A,Km_Rev0,Km_Rev1\n")
        for r in rows:
            f.write("%g,%g,%.6g,%.6g,%.6g,%.6g,%.6g\n" % r)
    out.append("  Assumptions: S1 and S2 phases add in phase (identical boards, rotors aligned); rotor-1 magnets' "
               "leakage through its back iron neglected; first-order iron image calibrated on one FEM point.")
    return out


def _field_max(d, col):
    p = os.path.join(d, "rotor_field_metrics.csv")
    if not os.path.isfile(p):
        return None
    rows = [l.strip().split(",") for l in open(p) if l.strip()]
    if col not in rows[0]:
        return None
    j = rows[0].index(col)
    vals = []
    for r in rows[1:]:
        try:
            vals.append(float(r[j]))
        except (IndexError, ValueError):
            pass
    return max(vals, key=abs) if vals else None


def rev1d_section(save_dir, out_dir, model, rph):
    """Rev1-D = S1 (as Rev0, sees R1 face A) + S2 between R1 face B and R2 (opposite poles facing, fields add).
    S2 board j (1 = next to R1 face B, 5 = next to R2) is at d_L = g + (j-1)p from face B and d_R = g + (5-j)p from R2.
    Superposition prediction (single-sided law, no interaction): P_j = K(d_L) + K(d_R) as phasors. FEM boards
    (REV1D_S2_K<j>) give M_j; f_j = |M_j|/|P_j| corrects the prediction (mirror symmetry j <-> 6-j, linear in j between
    solved boards). Polarity: S2 phase vs S1 phase from the FEM psi."""
    out = ["", "Rev1-D (S1-[PM|Fe|PM]-S2-[PM|Fe], 48 magnets, stators in series, rotors aligned):"]
    meas = {}
    for d in glob.glob(os.path.join(save_dir, "REV1D_S2_K*_results")):
        p = os.path.join(d, "rotor_sweep_summary.txt")
        m = re.search(r"REV1D_S2_K(\d)_G(\d{3})_T(\d{2})_results$", d)
        if not (m and os.path.isfile(p)):
            continue
        s = read_summary(p)
        if "K1_dLam_dtheta_peak_Wb_per_rad" not in s:
            continue
        j, g = int(m.group(1)), int(m.group(2)) / 100.0
        meas.setdefault(g, {})[j] = (float(s["K1_dLam_dtheta_peak_Wb_per_rad"]), float(s["phase_of_k_elec_deg"]),
                                     _field_max(d, "plate_Bmax_T"), _field_max(d, "steel_Bmax_T"),
                                     _field_max(d, "gap_Fz_upper_rotor_N"), os.path.basename(d))
    gaps = sorted(meas) or [1.0]
    rows = []
    for g in gaps:
        P, phS1 = {}, 0j
        for j in range(1, N_BOARDS + 1):
            dl, dr = g + (j - 1) * PITCH, g + (N_BOARDS - j) * PITCH
            kl, pl = model(dl)
            kr, pr = model(dr)
            P[j] = kl * cmath.exp(1j * math.radians(pl)) + kr * cmath.exp(1j * math.radians(pr))
            k1, p1 = model(g + (j - 1) * PITCH)
            phS1 += k1 * cmath.exp(1j * math.radians(p1))
        M = meas.get(g, {})
        f = {}
        for j, v in M.items():
            f[j] = f[N_BOARDS + 1 - j] = v[0] / abs(P[j])
        known = sorted(f)
        for j in range(1, N_BOARDS + 1):
            if j not in f:
                if not known:
                    f[j] = 1.0
                else:
                    lo = [q for q in known if q < j]
                    hi = [q for q in known if q > j]
                    if lo and hi:
                        a, b = lo[-1], hi[0]
                        f[j] = f[a] + (f[b] - f[a]) * (j - a) / float(b - a)
                    else:
                        f[j] = f[(lo or hi)[-1 if lo else 0]]
        s2 = sum(f[j] * P[j] for j in P)
        sign, pol = 1.0, "same sense as S1 (predicted; no FEM board yet)"
        if M:
            dpsi = [((v[1] - math.degrees(cmath.phase(P[j]))) + 180) % 360 - 180 for j, v in M.items()]
            rel = ((math.degrees(cmath.phase(s2)) + sum(dpsi) / len(dpsi) - math.degrees(cmath.phase(phS1))) + 180) % 360 - 180
            if abs(rel) > 90:
                sign, pol = -1.0, "OPPOSITE to S1 (FEM psi differs by %.1f deg) -> connect S2 reversed (S2_REVERSED=True)" % rel
            else:
                pol = "same sense as S1 (FEM psi differs by %+.1f deg) -> S2_REVERSED=False" % rel
        K1s, K2s = abs(phS1), abs(s2)
        K = K1s + K2s
        r1 = 2 * rph
        wm = RPM * 2 * math.pi / 60.0
        km0, km1 = 1.5 * K1s / math.sqrt(1.5 * rph), 1.5 * K / math.sqrt(1.5 * r1)
        rows.append({"g": g, "K": K, "K_S1": K1s, "K_S2": K2s, "km": km1})
        out.append("  gap %.2f mm. S2 boards (1 = next to R1 face B ... 5 = next to R2):" % g)
        for j in range(1, N_BOARDS + 1):
            if j in M:
                v = M[j]
                out.append("    board %d: FEM K1 = %.4f mN.m/A, psi %.1f deg; superposition prediction %.4f -> f = %.4f (%+.2f %%)"
                           "; R1 plate |B|max %s, R2 steel |B|max %s, axial force on R2 ~ %s  (%s)"
                           % (j, 1e3 * v[0], v[1], 1e3 * abs(P[j]), f[j], 100 * (f[j] - 1),
                              "n/a" if v[2] is None else "%.2f T" % v[2], "n/a" if v[3] is None else "%.2f T" % v[3],
                              "n/a" if v[4] is None else "%.1f N" % v[4], v[5]))
            else:
                out.append("    board %d: prediction %.4f mN.m/A x f %.4f (%s)" % (j, 1e3 * abs(P[j]), f[j],
                           "mirror/interpolated from the FEM boards" if known else "no FEM board yet: pure superposition"))
        out.append("    S2 polarity: %s" % pol)
        out.append("    K_S1 = %.2f, K_S2 = %.2f (S2/S1 = %.2f), K_Rev1D = %.2f mN.m/A (Rev1-D/Rev0 = %.2f); T_ideal = %.1f mN.m "
                   "per A_pk; E1 = %.3f V rms @ %g rpm; R_phase = %.3f ohm; Km = %.4f N.m/sqrt(W) (Rev0 %.4f, ratio %.2f)"
                   % (1e3 * K1s, 1e3 * K2s, K2s / K1s, 1e3 * K, K / K1s, 1.5e3 * K, wm * K / math.sqrt(2), RPM, r1, km1,
                      km0, km1 / km0))
    # three-design comparison (same gap)
    out.append("")
    out.append("Design comparison (per phase, stack sums; R_board %.4f ohm; magnets N35 20x6x2):" % R_BOARD)
    out.append("  %-8s %-26s %4s %9s %10s %11s %9s %11s" % ("design", "topology", "mag", "K mN.m/A", "T mN.m/Apk",
                                                            "T/magnet", "R ohm", "Km N.m/rtW"))
    for g in gaps:
        base = [r for r in rows if r["g"] == g][0]
        K0 = base["K_S1"]
        lst = [("Rev0", "S-R", 16, K0, rph)]
        rs = [r for r in REV1S_ROWS if abs(r["g"] - g) < 1e-6 and abs(r["t"] - 2.0) < 1e-6]
        if rs:
            lst.append(("Rev1-S", "S-R(PM/Fe)-S-R", 32, rs[0]["K"], 2 * rph))
        lst.append(("Rev1-D", "S-R(PM/Fe/PM)-S-R", 48, base["K"], 2 * rph))
        for name, top, n, K, R in lst:
            out.append("  %-8s %-26s %4d %9.2f %10.1f %11.3f %9.3f %11.4f"
                       % (name, top, n, 1e3 * K, 1.5e3 * K, 1.5e3 * K / n, R, 1.5 * K / math.sqrt(1.5 * R)))
        if not rs:
            out.append("  (Rev1-S row appears once REV1_S2ENV_G%03d_T20 is solved)" % int(round(g * 100)))
    with open(os.path.join(out_dir, "rev1d_vs_rev0.csv"), "w") as fo:
        fo.write("gap_mm,K_S1_Nm_per_A,K_S2_Nm_per_A,K_Rev1D_Nm_per_A,Km_Rev1D\n")
        for r in rows:
            fo.write("%g,%.6g,%.6g,%.6g,%.6g\n" % (r["g"], r["K_S1"], r["K_S2"], r["K"], r["km"]))
    out.append("  Assumptions: S1 of Rev1-D = Rev0 stack (R1 plate unsaturated, face B's leakage through it neglected); "
               "S2 per-board superposition of the single-sided law, corrected by the FEM boards; phases add in "
               "series with the polarity above; copper resistance excludes jumpers.")
    return out


def main(save_dir=None):
    save_dir = save_dir or SAVE_DIR or _shared_results_dir()
    print("Reading results from %s" % save_dir)
    pts = load_points(save_dir)
    out_dir = os.path.join(save_dir, "REV0_STACK_SUM")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    lines = ["Single-board Phase-A fundamental vs rotor distance (back iron %.1f mm, magnet radius %.1f mm):"
             % (REQUIRE_BACK_IRON, REQUIRE_MAG_R)]
    with open(os.path.join(out_dir, "board_curve.csv"), "w") as f:
        f.write("distance_mm,K1_Nm_per_A,psi_elec_deg,source\n")
        for d, k, psi, src in pts:
            f.write("%g,%.6g,%.3f,%s\n" % (d, k, psi, src))
            lines.append("  d = %.3f mm: K1 = %.4f mN.m/A, psi = %.1f deg  (%s)" % (d, 1e3 * k, psi, src))
    if len(pts) < 2:
        lines.append("Need at least two solved distances - nothing summed.")
        print("\n".join(lines))
        return
    tau = 2 * math.pi * MAG_R / POLES
    dmax = max(p[0] for p in pts)
    if MODEL == "exp":
        k, a, p0, p1, resid = fit_exp(pts)
        lines.append("")
        lines.append("Exponential fit K1(d) = %.4f mN.m/A * exp(-%.4f/mm * (d - 1)): k_eff = %.4f /mm "
                     "(analytic fundamental pi/tau at r = %.0f mm: %.4f /mm, tau = %.2f mm); psi = %.2f %+.3f*d deg"
                     % (1e3 * math.exp(a - k), k, k, MAG_R, math.pi / tau, tau, p0, p1))
        lines.append("  fit residuals at the solved points: %s %%" % ", ".join("%+.2f" % r for r in resid))
        if len(pts) < 3:
            lines.append("  WARNING: only %d points - the fit has no redundancy (no residual check)" % len(pts))

        kfit = k

        def model(d, a=a, k=k, p0=p0, p1=p1):           # bound now: k is reused as a loop name below
            return math.exp(a - k * d), p0 + p1 * d
    else:
        kfit = math.pi / tau
        def model(d):
            return interp(pts, d)
    wm = RPM * 2 * math.pi / 60.0
    rph = N_BOARDS * R_BOARD
    rows = []
    for g in GAPS:
        ph, per, ok = 0j, [], True
        for kb in range(N_BOARDS):
            v = model(g + kb * PITCH)
            if v is None:
                ok = False
                break
            per.append(v[0])
            ph += v[0] * cmath.exp(1j * math.radians(v[1]))
        if not ok:
            lines.append("  gap %.2f mm: board distances %.2f..%.2f mm not all inside the solved range - skipped"
                         % (g, g, g + (N_BOARDS - 1) * PITCH))
            continue
        K = abs(ph)
        rows.append({"gap_mm": g, "farthest_board_mm": g + (N_BOARDS - 1) * PITCH,
                     "extrapolated": "yes" if g + (N_BOARDS - 1) * PITCH > dmax + 0.1 or g < pts[0][0] - 1e-9 else "no",
                     "stack_factor_vs_board1_at_1mm": K / pts_at1(pts), "K_stack_Nm_per_A": K, "sum_of_magnitudes": sum(per),
                     "phase_alignment_pct": 100.0 * K / sum(per),
                     "board_share_pct": "/".join("%.0f" % (100.0 * x / sum(per)) for x in per),
                     "E1_rms_V_1000rpm": wm * K / math.sqrt(2),
                     "T_ideal_3ph_Nm_per_Apk": 1.5 * K,
                     "Km_Nm_per_sqrtW": 1.5 * K / math.sqrt(1.5 * rph)})
    with open(os.path.join(out_dir, "stack_vs_gap.csv"), "w") as f:
        keys = list(rows[0].keys()) if rows else []
        f.write(",".join(keys) + "\n")
        for r in rows:
            f.write(",".join(str(r[k]) if isinstance(r[k], str) else "%.6g" % r[k] for k in keys) + "\n")
    lines.append("")
    lines.append("Five-board stack (series, phasor sum, R_phase = %.3f ohm excl. jumpers):" % rph)
    for r in rows:
        lines.append("  gap %.2f mm: K = %.2f mN.m/A, E1 = %.3f V rms @ %g rpm, T_ideal = %.1f mN.m per A_pk, "
                     "Km = %.4f N.m/sqrt(W), board shares %s %%%s"
                     % (r["gap_mm"], 1e3 * r["K_stack_Nm_per_A"], r["E1_rms_V_1000rpm"], RPM,
                        1e3 * r["T_ideal_3ph_Nm_per_Apk"], r["Km_Nm_per_sqrtW"], r["board_share_pct"],
                        "  [EXTRAPOLATED beyond solved distances]" if r["extrapolated"] == "yes" else ""))
    lines.append("Km = torque per square-root of copper loss: the current-independent figure of merit.")
    bi = back_iron_table(save_dir)
    lines.append("")
    lines.append("Back iron at 1.0 mm gap (single board): thickness, K1, peak steel |B| over the solved angles")
    with open(os.path.join(out_dir, "back_iron.csv"), "w") as f:
        f.write("back_iron_mm,K1_Nm_per_A,K1_rel_to_2mm_pct,steel_Bmax_T,source\n")
        k2 = [r[1] for r in bi if abs(r[0] - 2.0) < 1e-6]
        for t, kb_, b, src in bi:
            rel = 100.0 * kb_ / k2[0] if k2 else float("nan")
            f.write("%g,%.6g,%.2f,%s,%s\n" % (t, kb_, rel, "" if b is None else "%.4g" % b, src))
            lines.append("  %.1f mm: K1 = %.4f mN.m/A (%.1f %% of 2.0 mm), steel |B|max = %s  (%s)"
                         % (t, 1e3 * kb_, rel, "n/a" if b is None else "%.2f T" % b, src))
    lines += rev1_section(save_dir, out_dir, model, kfit, bi)
    lines += rev1d_section(save_dir, out_dir, model, rph)
    open(os.path.join(out_dir, "stack_sum_report.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
