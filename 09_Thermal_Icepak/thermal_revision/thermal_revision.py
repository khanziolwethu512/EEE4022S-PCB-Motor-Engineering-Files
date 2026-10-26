"""Gate 2 - revised thermal operating limits, Rev0 and Rev1-S (series), original 1 mm-gap simulation geometry.

What is re-used and what is new
  * The archived Icepak steady solutions (REV0/REV1S_ICEPAK_STEADY_RUN1) are re-used as THERMAL-FEM evidence of the
    stator-to-air thermal resistance R_th = (T_hotspot - T_hood) / P_stator. Those solves applied the TRACE-MODEL
    copper resistance (0.2777 ohm per board-phase = 1.389 ohm per stator phase at 20 C), i.e. 27 % less heat per
    ampere than the measured winding. R_th is a property of the geometry and boundary conditions (only weakly of the
    heat level), so it is extracted from the solves and re-applied with the MEASURED resistance; its weak dependence
    on the temperature rise is kept by interpolating R_th(dT) between the solved points (log dT).
  * New here: measured R(T); ambient 25 and 30 C; eddy loss by speed; four cooling scenarios; short-time limits;
    Icepak RUN2 scripts that re-solve the limit points with the measured heat (confirmation, lab PC).
Two-stator heat distribution (Rev1-S): series connection -> equal current; measured R equal within 1.6 % (1.87-1.90
  ohm) -> equal copper heat per stator; the track eddy estimate differs (S1 20.35, S2 23.83 mW at 1000 rpm) and the
  larger value is applied to the limiting stator. Icepak shows S1 (between the stators) 2.9 K hotter than S2 at equal
  heat, so the limit is set by the S1 hotspot: R_th per stator = (T_S1,hot - T_hood) / (P_total / 2).
python thermal_revision.py -> out/*.csv, out/*.md, out/T*.png, icepak_run2/*.py
"""
import csv, json, math, os
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
ALPHA, T_LIM, T_MAG_LIM = 0.00393, 60.0, 80.0
R_LAYOUT20 = 0.2777 * 5                      # ohm per stator phase used by the Icepak solves
R_MEAS20 = 1.89                              # ohm per stator phase, measured (1.87-1.90), taken as 20 C
# measurement temperature not recorded (15-30 C assumed): R20 = 1.87..1.90 / (1 + a (Tm - 20)) -> 1.80..1.94
R20_RANGE = (1.87 / (1 + ALPHA * 10), 1.90 / (1 - ALPHA * 5))
EDDY1000 = {"Rev0": 0.02035, "Rev1-S": 0.02383}  # W per stator at 1000 rpm (limiting stator; FEM rotating model)
N_ST = {"Rev0": 1, "Rev1-S": 2}

# ---- archived Icepak solutions (T_hood 30 C, rotor still, acrylic housing in the bench hood, radiation off) ----
ICEPAK = {   # case: (I_pk, P_total_W, T_hotspot_C, fans_on, extra)
 "Rev0": [(0.737, 1.220, 40.9, True, "B1/B3/B5 mean 39.2/40.7/40.7"), (1.0, 2.317, 50.3, True, "47.2/49.9/49.9"),
          (2.0, 11.569, 124.9, True, "110.0/123.1/123.1"), (2.0, 11.870, 134.5, False, "119.3/132.6/132.6")],
 "Rev1-S": [(0.345, 0.523, 34.2, True, "S1/S2 mean 34.1/33.7"), (1.0, 4.842, 65.7, True, "S1/S2 mean 65.1/62.2"),
            (2.0, 28.901, 220.4, True, "S1/S2 mean 217.1/201.0"), (2.0, 29.941, 236.8, False, "S1/S2 mean 233.2/216.9")],
}
T_HOOD = 30.0
LUMPED_REV0_ROT = 5.07     # K/W board max, lumped network, sealed shell, fans on, rotor at 1000 rpm (stirring)
LUMPED_FANS_OFF_RATIO = 5.63 / 5.07   # lumped: fans off / fans on (1000 rpm) = 1.11; Icepak at 2 A: 1.07 / 1.05
CAUTIOUS = {"Rev0": 15.0, "Rev1-S": 25.3}       # K/W per stator, the rev. D planning basis (x1.71 on Icepak)
TAU_MIN = {"lumped 1000 rpm": 9.2, "lumped stalled": 24.0}   # min, first-order (Rev0 lumped network)


def rth_points(m, fans=True):
    pts = []
    for I, P, Th, f, _ in ICEPAK[m]:
        if f == fans:
            pts.append((Th - T_HOOD, (Th - T_HOOD) / (P / N_ST[m])))
    return sorted(pts)


def rth_icepak(m, dT):
    """Interpolate R_th(dT) between the solved fans-on points in log(dT); clamp outside."""
    pts = rth_points(m, True)
    x = np.log([p[0] for p in pts]); y = [p[1] for p in pts]
    return float(np.interp(math.log(dT), x, y))


SCEN = [  # key, label, evidence, function(m, dT) -> R_th per stator (K/W), validity
 ("A", "Icepak: hood fans on (1 m/s), rotor still, hypothetical acrylic housing", "THERMAL-FEM",
  lambda m, dT: rth_icepak(m, dT), "all speeds (no rotor stirring credited)"),
 ("B", "Icepak, fans off (natural convection), rotor still", "THERMAL-FEM x inferred ratio 1.11",
  lambda m, dT: rth_icepak(m, dT) * LUMPED_FANS_OFF_RATIO, "all speeds"),
 ("C", "Lumped network, rotor turning 1000 rpm, fans on (Rev1-S scaled by the Icepak Rev1-S/Rev0 ratio)",
  "THERMAL-LUMPED (+ inferred for Rev1-S)",
  lambda m, dT: LUMPED_REV0_ROT * (1.0 if m == "Rev0" else rth_icepak("Rev1-S", dT) / rth_icepak("Rev0", dT)),
  "about 1000 rpm only; optimistic bound"),
 ("D", "Cautious planning basis (as-built open frame / unknown cooling)", "ASSUMED (x1.71 on Icepak)",
  lambda m, dT: CAUTIOUS[m], "all speeds"),
]


def limit_current(m, rth_fn, Ta, R20, rpm):
    dT = T_LIM - Ta
    rth = rth_fn(m, dT)
    p_allow = dT / rth
    p_cu = p_allow - EDDY1000[m] * (rpm / 1000.0) ** 2
    if p_cu <= 0:
        return 0.0, rth, p_allow
    R = R20 * (1 + ALPHA * (T_LIM - 20.0))           # winding R at the limit (hotspot) temperature: conservative
    return math.sqrt(p_cu / (1.5 * R)), rth, p_allow


def temp_at(m, rth_fn, Ta, R20, I, rpm):
    T = Ta
    for _ in range(200):
        R = R20 * (1 + ALPHA * (T - 20.0))
        p = 1.5 * I * I * R + EDDY1000[m] * (rpm / 1000.0) ** 2
        Tn = Ta + p * rth_fn(m, max(T - Ta, 1.0))
        if abs(Tn - T) < 1e-6:
            break
        T = 0.5 * (T + Tn) if Tn > 400 else Tn
        if T > 400:
            return float("nan"), p
    return T, p


def main():
    rows = []
    # 1. extraction of R_th from the archived Icepak solves
    ext = []
    for m in ICEPAK:
        for I, P, Th, f, extra in ICEPAK[m]:
            ps = P / N_ST[m]
            ext.append(dict(machine=m, I_pk=I, fans="on" if f else "off", P_total_W_icepak=P, P_per_stator_W=ps,
                            T_hotspot_C=Th, dT_K=Th - T_HOOD, Rth_K_per_W=(Th - T_HOOD) / ps,
                            R_implied_ohm=P / N_ST[m] / (1.5 * I * I), notes=extra))
    with open(os.path.join(OUT, "T0_icepak_rth_extraction.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ext[0].keys())); w.writeheader()
        for r in ext:
            w.writerow(dict((k, round(v, 4) if isinstance(v, float) else v) for k, v in r.items()))
    # interpolation self-check: the interpolated R_th must reproduce each solved fans-on point exactly
    for r in ext:
        if r["fans"] == "on":
            assert abs(rth_icepak(r["machine"], r["dT_K"]) - r["Rth_K_per_W"]) < 1e-9
    # same-current comparison: archived Icepak heat vs measured-R heat
    cmp_rows = []
    for m in ICEPAK:
        I, P, Th, f, _ = ICEPAK[m][1]                      # the 1 A fans-on point
        T, p = temp_at(m, SCEN[0][3], T_HOOD, R_MEAS20, I, 0.0)
        cmp_rows.append((m, I, P / N_ST[m], Th, p, T))
    # 2. limit currents
    for m in ("Rev0", "Rev1-S"):
        for key, label, ev, fn, valid in SCEN:
            for Ta in (25.0, 30.0):
                for rb, R20 in (("measured 1.89", R_MEAS20), ("upper 1.94", R20_RANGE[1]), ("lower 1.80", R20_RANGE[0])):
                    for rpm in (0, 1000, 2000, 4000):
                        if key == "C" and rpm != 1000:
                            continue
                        I, rth, pa = limit_current(m, fn, Ta, R20, rpm)
                        K = {"Rev0": 18.534, "Rev1-S": 39.50}[m]
                        rows.append(dict(machine=m, scenario=key, scenario_label=label, evidence=ev, validity=valid,
                                         T_amb_C=Ta, R20_basis=rb, R20_ohm=R20 * N_ST[m], rpm=rpm, Rth_K_per_W_per_stator=rth,
                                         P_allow_per_stator_W=pa, I_lim_pk_A=I, I_lim_rms_A=I / math.sqrt(2),
                                         T_em_at_I_lim_mNm=1.5 * K * I))
    keys = list(rows[0].keys())
    with open(os.path.join(OUT, "T1_thermal_limits.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows:
            w.writerow(dict((k, round(v, 4) if isinstance(v, float) else v) for k, v in r.items()))
    # 3. short-time (first-order, scenario A, 25 C, standstill heat): time from cold (Ta) to the 60 C limit at a
    #    constant current. Heat taken at R(60 C) throughout (conservative: faster heating than the real R(T) rise), so
    #    dT_ss = P(60 C) * R_th and t = -tau ln(1 - dT_lim / dT_ss). tau from the Rev0 lumped network; applied to
    #    Rev1-S as well (its larger heat capacity and R_th give a LONGER real tau, so this is conservative).
    st = []
    for m in ("Rev0", "Rev1-S"):
        for I in (1.0, 1.25, 1.5, 2.0, 3.0):
            p60 = 1.5 * I * I * R_MEAS20 * (1 + ALPHA * (T_LIM - 20.0))
            dss = p60 * rth_icepak(m, max(T_LIM - 25.0, p60 * 8.0))
            t = dict((k, (-tau * math.log(1 - (T_LIM - 25.0) / dss)) if dss > T_LIM - 25.0 else float("inf"))
                     for k, tau in TAU_MIN.items())
            st.append(dict(machine=m, I_pk_A=I, P_per_stator_at_60C_W=p60, dT_steady_equiv_K=dss,
                           t_to_60C_min_tau9=t["lumped 1000 rpm"], t_to_60C_min_tau24=t["lumped stalled"]))
    with open(os.path.join(OUT, "T2_short_time_limits.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(st[0].keys())); w.writeheader()
        for r in st:
            w.writerow(dict((k, round(v, 3) if isinstance(v, float) else v) for k, v in r.items()))
    # 4. markdown summary
    def pick(m, key, Ta, rb, rpm):
        for r in rows:
            if (r["machine"], r["scenario"], r["T_amb_C"], r["R20_basis"], r["rpm"]) == (m, key, Ta, rb, rpm):
                return r
    md = ["# Revised thermal limits (Gate 2)", "",
          "Winding limit 60 C (holder material unconfirmed); N35 magnets 80 C (not reached: Icepak magnets run "
          "below the winding). R_th per stator from the archived Icepak solves; heat from the MEASURED resistance.", "",
          "## R_th extracted from Icepak (T_hood 30 C)", "",
          "| Machine | I pk (A) | Fans | Icepak heat per stator (W) | Hotspot (C) | R_th per stator (K/W) |", "|---|---|---|---|---|---|"]
    md += ["| %s | %.3f | %s | %.3f | %.1f | %.2f |" % (r["machine"], r["I_pk"], r["fans"], r["P_per_stator_W"], r["T_hotspot_C"],
                                                     r["Rth_K_per_W"]) for r in ext]
    md += ["", "Same current, archived heat vs measured-resistance heat (scenario A, 30 C hood, standstill):", "",
           "| Machine | I pk | Icepak heat/stator (layout R) | Icepak hotspot | Heat/stator with measured R | Predicted hotspot |",
           "|---|---|---|---|---|---|"]
    md += ["| %s | %.1f A | %.2f W | %.1f C | %.2f W | %.1f C |" % (m, I, p0, t0, p1, t1)
           for m, I, p0, t0, p1, t1 in cmp_rows]
    md += ["", "## Thermally limited current (A pk per stator; Rev1-S is the series terminal current), measured R 1.89 ohm", "",
           "| Machine | Scenario | Evidence | Ta 25 C, 0 rpm | Ta 25 C, 1000 rpm | Ta 30 C, 1000 rpm | Ta 25 C, 4000 rpm | R_th at 25 C (K/W) |",
           "|---|---|---|---|---|---|---|---|"]
    for m in ("Rev0", "Rev1-S"):
        for key, label, ev, fn, valid in SCEN:
            a = pick(m, key, 25.0, "measured 1.89", 0)
            b = pick(m, key, 25.0, "measured 1.89", 1000)
            c = pick(m, key, 30.0, "measured 1.89", 1000)
            d = pick(m, key, 25.0, "measured 1.89", 4000)
            fmt = lambda r: ("%.3f" % r["I_lim_pk_A"]) if r else "-"
            md.append("| %s | %s: %s | %s | %s | %s | %s | %s | %.2f |" % (m, key, label, ev, fmt(a), fmt(b), fmt(c), fmt(d),
                                                                     b["Rth_K_per_W_per_stator"]))
    md += ["", "Resistance sensitivity (scenario A, 25 C, 1000 rpm): " + "; ".join(
        "%s %s -> %.3f A" % (m, rb, pick(m, "A", 25.0, rb, 1000)["I_lim_pk_A"]) for m in ("Rev0", "Rev1-S")
        for rb in ("lower 1.80", "measured 1.89", "upper 1.94")),
        "", "Short-time (first-order, scenario A, 25 C, from cold): see T2_short_time_limits.csv. The time constants are "
        "from the Rev0 lumped network (9.2 min at 1000 rpm, 24 min stalled); Icepak was solved steady-state only."]
    open(os.path.join(OUT, "thermal_limits.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))
    json.dump({"R20_range": R20_RANGE, "rows": len(rows)}, open(os.path.join(OUT, "meta.json"), "w"))
    plots(rows)
    icepak_run2(rows)


def plots(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    # T1: winding hotspot vs current, both machines, scenarios A/B/D, 25 C, standstill heat
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.0), sharey=True)
    cols = {"A": "#1f4e79", "B": "#2e8b57", "C": "#7d7d7d", "D": "#b03a2e"}
    short = {"A": "A  Icepak, fans on, rotor still", "B": "B  Icepak fans off (x1.11)",
             "C": "C  lumped, rotor turning", "D": "D  cautious 15 / 25.3 K/W"}
    for ax, m in zip(axs, ("Rev0", "Rev1-S")):
        Is = np.linspace(0.05, 2.0, 80)
        for key, label, ev, fn, valid in SCEN:
            if key not in cols:
                continue
            T = [temp_at(m, fn, 25.0, R_MEAS20, I, 1000)[0] for I in Is]
            ax.plot(Is, T, color=cols[key], lw=1.4, ls=":" if key == "C" else "-", label=short[key])
        pts = [(I, Th - T_HOOD + 25.0) for I, P, Th, f, _ in ICEPAK[m] if f]
        ax.axhline(T_LIM, color="0.3", lw=0.8, ls="--")
        ax.text(0.06, T_LIM + 2, "60 °C winding limit", fontsize=7, color="0.3")
        ax.set_xlabel("Phase current (A peak)")
        ax.set_title("%s%s, Ta 25 °C, 1000 rpm" % (m, " (series)" if m == "Rev1-S" else ""), fontsize=9)
        ax.set_ylim(20, 160); ax.grid(alpha=0.3)
    axs[0].set_ylabel("Winding hotspot (°C)")
    axs[0].legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "T1_hotspot_vs_current.png"), dpi=200)
    plt.close(fig)
    # T0: R_th vs dT
    fig, ax = plt.subplots(figsize=(3.6, 2.8))
    for m, c in (("Rev0", "#1f4e79"), ("Rev1-S", "#b03a2e")):
        p = rth_points(m, True)
        x = np.exp(np.linspace(math.log(p[0][0]), math.log(p[-1][0]), 50))
        ax.plot(x, [rth_icepak(m, v) for v in x], color=c, lw=1.2)
        ax.plot([q[0] for q in p], [q[1] for q in p], "o", color=c, ms=4, label="%s fans on" % m)
        po = rth_points(m, False)
        ax.plot([q[0] for q in po], [q[1] for q in po], "s", mfc="none", color=c, ms=4, label="%s fans off" % m)
    ax.set_xscale("log"); ax.set_xlabel("Hotspot rise over hood air (K)"); ax.set_ylabel("R_th per stator (K/W)")
    ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "T0_rth_vs_dT.png"), dpi=200); plt.close(fig)


def icepak_run2(rows):
    """Lab-PC confirmation: the same frozen Icepak projects re-solved at the revised limit currents with the
    measured heat (R20 0.378 ohm per board-phase = 1.89 / 5), Ta 25 and 30 C, fans on and off."""
    src = os.path.join(os.path.dirname(os.path.dirname(HERE)), "in_thermal", "Thermal")
    dst = os.path.join(HERE, "icepak_run2"); os.makedirs(dst, exist_ok=True)
    for m, fn in (("Rev0", "run_REV0_ICEPAK_STEADY.py"), ("Rev1-S", "run_REV1_ICEPAK_STEADY.py")):
        s = open(os.path.join(src, fn)).read()
        I25 = [r for r in rows if (r["machine"], r["scenario"], r["T_amb_C"], r["R20_basis"], r["rpm"]) == (m, "A", 25.0, "measured 1.89", 0)][0]["I_lim_pk_A"]
        I30 = [r for r in rows if (r["machine"], r["scenario"], r["T_amb_C"], r["R20_basis"], r["rpm"]) == (m, "A", 30.0, "measured 1.89", 0)][0]["I_lim_pk_A"]
        cases = ('CASES = [   # name, I_pk (A), T_hood (C), V_fan (m/s)  - RUN2 (22 Oct): measured R, revised limit points\n'
                 '    ("I%s_Ta25_fans_on",  %.3f, 25.0, 1.0),\n    ("I%s_Ta30_fans_on",  %.3f, 30.0, 1.0),\n'
                 '    ("I%s_Ta25_fans_off", %.3f, 25.0, 0.0),\n    ("I1p0_Ta25_fans_on", 1.0, 25.0, 1.0),\n]\n'
                 % (("%.3f" % I25).replace(".", "p"), I25, ("%.3f" % I30).replace(".", "p"), I30, ("%.3f" % I25).replace(".", "p"), I25))
        a = s.index("CASES = ["); b = s.index("]\n", a) + 2
        s = s[:a] + cases + s[b:]
        s = s.replace("R20, ALPHA = 0.2777, 0.00393          # ohm per board-phase at 20 C [AEDT Gate 1]",
                      "R20, ALPHA = 1.89 / 5, 0.00393         # ohm per board-phase at 20 C - MEASURED 1.89 ohm per stator (RUN2)")
        assert "1.89 / 5" in s
        s = s.replace('_ICEPAK_STEADY_RUN1"', '_ICEPAK_STEADY_RUN2"')
        assert "RUN2" in s
        open(os.path.join(dst, fn.replace("STEADY", "STEADY_RUN2")), "w").write(s)


if __name__ == "__main__":
    main()
