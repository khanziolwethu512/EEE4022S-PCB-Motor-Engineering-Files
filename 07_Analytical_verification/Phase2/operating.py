"""Consistent steady-state operating analysis (voltage-, current- and thermal-limited), Rev0 and Rev1-S (series).

In a voltage-fed PMSM, speed, current and voltage are not independent: the controller fixes the current angle and
the inverter fixes the voltage limit, and the load sets the torque. Assumed here (stated, not measured):
  * star connection, field-oriented control with i_d = 0 (current on the q axis), balanced sinusoidal currents;
  * SVPWM inverter: peak phase voltage limit V_max = m * V_dc / sqrt3, m = 0.95; V_dc 12 V (Rev0), 24 V (Rev1-S);
  * steady state: V_q = R I + E, V_d = -omega_e L I  ->  |V| = sqrt((R I + E)^2 + (omega_e L I)^2) <= V_max;
  * thermal limit: 60 C board limit, 25 C lab air (as Test D / rev. D), T = 25 + R_th * P_stator; copper loss with R(T); speed-dependent
    track eddy loss added (scaled with n^2 from the rotating FEM value at 1000 rpm).
For each speed the largest current meeting all three limits is found; torque T = 1.5 K I (electromagnetic).

Every input carries its source, and each case is run with the analytical K and with the FEM K so the two can be
compared directly:
  K       ANALYTICAL (analytical_em.py, primary)  |  FEM (Rev0 full-motor 18.534; Rev1-S board sum 39.50 mN.m/A)
  R       MEASURED (bench, 1.89 ohm per stator phase at ~20 C)  -- layout value 1.33-1.35 ohm shown separately
  L       FEM (Maxwell armature-only energy, 34-51 uH per stator; 51 used, worst case for voltage)
  R_th    FEM (Icepak, rotor still): 8.75 K/W (Rev0), 14.8 K/W per stator (Rev1-S); CAUTIOUS: 15 / 25.3 K/W
  eddy    FEM (rotating field-only model): 20 mW (Rev0) / 44 mW (Rev1-S) at 1000 rpm, proportional to n^2
python operating.py
"""
import csv, json, math, os
HERE = os.path.dirname(os.path.abspath(__file__))
ALPHA, T_AIR, T_LIM, M_IDX, POLES = 0.00393, 25.0, 60.0, 0.95, 16   # 25 C lab air: same basis as Test D / rev. D
MACH = {
    "Rev0": dict(K_FEM=18.534e-3, R20=1.89, L=51e-6, n_st=1, Vdc=12.0, Rth=8.75, Rth_c=15.0, eddy1000=0.020),
    "Rev1-S": dict(K_FEM=39.50e-3, R20=3.78, L=113e-6, n_st=2, Vdc=24.0, Rth=14.8, Rth_c=25.3, eddy1000=0.044),
}


def point(m, K, rpm, rth, i_cap=None):
    """Largest q-axis current at this speed within the voltage and thermal limits (bisection)."""
    wm = rpm * 2 * math.pi / 60.0
    we = wm * POLES / 2
    vmax = M_IDX * m["Vdc"] / math.sqrt(3)
    eddy = m["eddy1000"] * (rpm / 1000.0) ** 2

    def state(i):
        T = T_AIR
        for _ in range(60):
            R = m["R20"] * (1 + ALPHA * (T - 20.0))
            p = 1.5 * i * i * R + eddy
            T = T_AIR + p / m["n_st"] * rth
        R = m["R20"] * (1 + ALPHA * (T - 20.0))
        v = math.hypot(R * i + K * wm, we * m["L"] * i)
        return T, R, v, p

    if K * wm > vmax:
        return None
    lo, hi = 0.0, 20.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        T, R, v, p = state(mid)
        if T <= T_LIM + 1e-9 and v <= vmax + 1e-12 and (i_cap is None or mid <= i_cap):
            lo = mid
        else:
            hi = mid
    i = lo
    T, R, v, p = state(i)
    limit = "thermal" if abs(T - T_LIM) < 0.05 else ("voltage" if abs(v - vmax) < 1e-3 else "current cap")
    tem = 1.5 * K * i
    pmech = tem * wm
    return dict(rpm=rpm, I_pk=i, T_em_mNm=1e3 * tem, P_mech_W=pmech, P_in_W=pmech + p, eff_pct=100 * pmech / (pmech + p) if pmech + p > 0 else 0,
                V_line_rms=math.sqrt(3) * v / math.sqrt(2), T_wind_C=T, limit=limit)


def main():
    an = json.load(open(os.path.join(HERE, "out", "analytical_primary.json")))
    K_AN = {"Rev0": an["Rev0"]["machine"]["PHASE_A"]["K1_mNm_per_A"] * 1e-3,
            "Rev1-S": an["Rev1S"]["machine"]["PHASE_A"]["K1_mNm_per_A"] * 1e-3}
    rows, md = [], []
    speeds = [100, 250, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000, 6000]
    for name, m in MACH.items():
        vmax = M_IDX * m["Vdc"] / math.sqrt(3)
        for ksrc, K in (("analytical", K_AN[name]), ("FEM", m["K_FEM"])):
            n0 = vmax / K * 60 / (2 * math.pi)
            for tb, rth in (("Icepak", m["Rth"]), ("cautious", m["Rth_c"])):
                for n in speeds:
                    r = point(m, K, n, rth)
                    if r is None:
                        continue
                    r.update(machine=name, K_source=ksrc, K_mNm_per_A=1e3 * K, thermal_basis=tb, no_load_speed_rpm=n0)
                    rows.append(r)
    keys = ["machine", "K_source", "K_mNm_per_A", "thermal_basis", "rpm", "I_pk", "T_em_mNm", "P_mech_W", "P_in_W",
            "eff_pct", "V_line_rms", "T_wind_C", "limit", "no_load_speed_rpm"]
    with open(os.path.join(HERE, "out", "operating_envelope.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(dict((k, round(r[k], 4) if isinstance(r[k], float) else r[k]) for k in keys))
    md += ["| Machine | K source | Thermal basis | Speed (rpm) | Max current (A pk) | Torque (mN·m) | EM power T·ω (W) | Efficiency (EM) | Line voltage (V rms) | Winding (°C) | Limited by |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["rpm"] in (250, 500, 1000, 2000, 4000):
            md.append("| %s | %s | %s | %d | %.3f | %.1f | %.2f | %.0f %% | %.2f | %.0f | %s |" % (
                r["machine"], r["K_source"], r["thermal_basis"], r["rpm"], r["I_pk"], r["T_em_mNm"], r["P_mech_W"],
                r["eff_pct"], r["V_line_rms"], r["T_wind_C"], r["limit"]))
    md += ["", "No-load (voltage-limited) speed: " + "; ".join(
        "%s %s K: %.0f rpm" % (r["machine"], r["K_source"], r["no_load_speed_rpm"]) for r in rows
        if r["rpm"] == 100 and r["thermal_basis"] == "Icepak")]
    open(os.path.join(HERE, "out", "operating_envelope.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(10.5, 3.8))
    for ax, name in zip(axs, MACH):
        m = MACH[name]
        for ksrc, K, c in (("analytical", K_AN[name], "C0"), ("FEM", m["K_FEM"], "C1")):
            for tb, rth, ls in (("Icepak", m["Rth"], "-"), ("cautious", m["Rth_c"], "--")):
                ns = list(range(50, 8001, 50))
                pts = [point(m, K, n, rth) for n in ns]
                ns2 = [n for n, p in zip(ns, pts) if p]
                ax.plot(ns2, [p["T_em_mNm"] for p in pts if p], ls, color=c, label="K %s, R_th %s" % (ksrc, tb))
        ax.axvline(1000, color="0.5", lw=0.8, ls=":")
        ax.set_title("%s, %g V dc, 60 °C winding limit" % (name, m["Vdc"]), fontsize=9)
        ax.set_xlabel("Speed (rpm)")
        ax.set_ylabel("Continuous electromagnetic torque (mN·m)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "out", "O1_torque_speed_envelope.png"), dpi=200)


if __name__ == "__main__":
    main()
