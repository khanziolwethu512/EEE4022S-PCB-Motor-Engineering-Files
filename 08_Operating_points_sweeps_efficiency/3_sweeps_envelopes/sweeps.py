"""Gate 3 - consistent current (C1), speed (S1) and DC-bus voltage (E1) sweeps and the operating envelopes (F1),
Rev0 and Rev1-S (series, star), ORIGINAL 1 mm-gap simulation geometry. Circuit-model post-processing only: no new
FEM. Every input is taken from a verified source (provenance IDs from ../audit):

  K       FEM   Rev0 18.534 (S01 full motor), Rev1-S 39.50 (S04 board sum) mN.m/A, T = 1.5 K I_pk, E_ph,pk = K w_m
          cross-checks: analytical sheet-current 18.539 / 39.55 (S12), EQ current sweep 18.52 / 39.43 (S08/S09)
  K(I)    FEM   EQ current sweep, K(I)/K(1 A) (S08/S09), 0-3 A; 0.25 / 0.75 A interpolated (v12 run pending)
  e(t)    FEM   rotating model at 1000 rpm, scaled to K (S06/S07); speed scaling e ~ n (v12 500/2000 rpm pending)
  R       MEASURED 1.89 ohm per stator phase (S16), taken at 20 C, R(T) = R20 (1 + 0.00393 (T - 20)) at the hotspot T
  L       FEM   armature-only energy, EQ model: Rev0 33.5-51.2 uH; Rev1-S series 74.4-112.6 uH (calibrated-geometric
          turns bracket); NOT measured. The voltage limit uses the upper value; the lower is a sensitivity case.
  eddy    FEM-post track eddy at 1000 rpm, x (n/1000)^2: Rev0 20.35 mW; Rev1-S 44.18 mW (S1 20.35, S2 23.83)
  thermal THERMAL-FEM (Icepak R_th(dT), ../thermal) - scenario A (fans on, rotor still) and D (cautious, assumed)
  drive   ASSUMED star, FOC i_d = 0, SVPWM m = 0.95: V_ph,pk <= 0.95 V_dc / sqrt3 (V_dc is the bus, not the motor
          line voltage); inverter, bearing and windage losses NOT included.
  limits  winding 60 C; current <= 3 A pk (range over which the FEM linearity was checked); 4000 rpm (verified
          speed-scaling range; mechanically the rotor is qualified for nothing above 1000 rpm).

Outputs are ELECTROMAGNETIC quantities: T_em (Lorentz), P_em = T_em w (conversion power), P_out,EM = P_em - P_eddy
(eddy drag deducted, mechanical loss NOT deducted) and eta_EM = P_out,EM / (P_em + P_cu). None is a measured shaft
quantity. python sweeps.py -> out/*.csv, out/*.png, out/sweeps_summary.md
"""
import csv, json, math, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "thermal"))
import thermal_revision as TH
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
ARCH = os.path.join(SCR, "arch")
ALPHA, T_LIM, M_IDX, P = 0.00393, 60.0, 0.95, 8           # P = pole pairs
I_CAP, N_VERIFIED = 3.0, 4000.0
MACH = {
    "Rev0": dict(K=18.534e-3, K_an=18.539e-3, K_eq=18.52e-3, R20=1.89, L=(33.5e-6, 51.2e-6), n_st=1,
                 eddy=0.02035, eddy_st=0.02035, Vnom=12.0, fm="RESULTS_FMROT_REV0", K_fm=19.470e-3,
                 isw="RESULTS_EQ_REV0_ISWEEP", magnets=16, boards=5),
    "Rev1-S": dict(K=39.50e-3, K_an=39.55e-3, K_eq=39.43e-3, R20=3.78, L=(74.4e-6, 112.6e-6), n_st=2,
                   eddy=0.04418, eddy_st=0.02383, Vnom=24.0, fm="RESULTS_FMROT_REV1S", K_fm=41.570e-3,
                   isw="RESULTS_EQ_REV1S_ISWEEP", magnets=32, boards=10),
}
SC = dict((s[0], s) for s in TH.SCEN)          # A, B, C, D
COL = {"Rev0": "#1f4e79", "Rev1-S": "#b03a2e"}


def kfac(m):
    """FEM K(I)/K(1 A) from the EQ current sweep (S08/S09)."""
    d = json.load(open(os.path.join(ARCH, MACH[m]["isw"], "eq_isweep_results.json")))
    pts = sorted((p["Ipk"], p["K_mNm_per_A"]) for p in d["points"] if p["Ipk"] > 0)
    k1 = dict(pts)[1.0]
    return [p[0] for p in pts], [p[1] / k1 for p in pts]


def state(m, rpm, I, Ta=25.0, scen="A", L=None):
    """Steady operating point at q-axis current I (A pk) and speed rpm."""
    c = MACH[m]
    L = c["L"][1] if L is None else L
    wm = rpm * 2 * math.pi / 60.0
    we = P * wm
    ped = c["eddy"] * (rpm / 1000.0) ** 2
    fn = SC[scen][3]
    T = Ta
    for _ in range(300):
        R = c["R20"] * (1 + ALPHA * (T - 20.0))
        pcu = 1.5 * I * I * R
        heat = pcu / c["n_st"] + c["eddy_st"] * (rpm / 1000.0) ** 2
        Tn = Ta + heat * fn(m, max(T - Ta, 1.0))
        if abs(Tn - T) < 1e-7:
            break
        T = Tn if Tn < 600 else 600.0
    R = c["R20"] * (1 + ALPHA * (T - 20.0))
    pcu = 1.5 * I * I * R
    vq, vd = R * I + c["K"] * wm, we * L * I
    v = math.hypot(vq, vd)
    tem = 1.5 * c["K"] * I
    pem = tem * wm
    pout = pem - ped
    return dict(T_wind_C=T, R_ohm=R, P_cu_W=pcu, P_eddy_W=ped, V_ph_pk=v, V_line_rms=math.sqrt(1.5) * v,
                Vdc_req=math.sqrt(3) * v / M_IDX, T_em_mNm=1e3 * tem, P_em_W=pem, P_out_EM_W=pout,
                T_eddy_drag_mNm=1e3 * ped / wm if wm > 0 else 0.0, P_in_W=pem + pcu,
                eta_EM_pct=100 * pout / (pem + pcu) if pem + pcu > 0 and pout > 0 else 0.0,
                mod_index=math.sqrt(3) * v / M_IDX / 1.0)


def i_max(m, rpm, Vdc, Ta=25.0, scen="A", L=None, use_thermal=True):
    """Largest q-axis current meeting the voltage, thermal (60 C) and 3 A limits. Returns (I, limiting factor)."""
    vmax = M_IDX * Vdc / math.sqrt(3)
    c = MACH[m]
    if c["K"] * rpm * 2 * math.pi / 60.0 >= vmax:
        return 0.0, "back-EMF exceeds the bus"

    def ok(i):
        s = state(m, rpm, i, Ta, scen, L)
        return s["V_ph_pk"] <= vmax and (not use_thermal or s["T_wind_C"] <= T_LIM)
    if ok(I_CAP):
        return I_CAP, "3 A model range"
    lo, hi = 0.0, I_CAP
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    s = state(m, rpm, lo, Ta, scen, L)
    lim = "thermal" if use_thermal and abs(s["T_wind_C"] - T_LIM) < 0.05 else "voltage"
    return lo, lim


def w(path, rows):
    with open(os.path.join(OUT, path), "w", newline="") as f:
        ww = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        ww.writeheader()
        for r in rows:
            ww.writerow(dict((k, round(v, 5) if isinstance(v, float) else v) for k, v in r.items()))


def harmonics(m):
    c = MACH[m]
    d = np.genfromtxt(os.path.join(ARCH, c["fm"], "fmrot_waveforms.csv"), delimiter=",", names=True)
    sc = c["K"] / c["K_fm"]
    ea, eb = d["e_PHASE_A_V"] * sc, d["e_PHASE_B_V"] * sc
    out = {}
    for name, e in (("phase", ea), ("line", ea - eb)):
        F = np.fft.rfft(e) / len(e) * 2
        h1 = abs(F[1])
        out[name] = dict(rms=float(np.sqrt(np.mean(e ** 2))), H1_pk=float(h1),
                         H=[float(abs(F[k]) / h1 * 100) for k in range(1, 12)],
                         THD=float(math.sqrt(sum(abs(F[k]) ** 2 for k in range(2, len(F) - 1))) / h1 * 100))
    out["t_ms"] = d["t_ms"].tolist(); out["ea"] = ea.tolist(); out["eab"] = (ea - eb).tolist(); out["scale"] = sc
    return out


def main():
    summary = ["# Operating sweeps and envelopes (Gate 3) - circuit model on verified FEM / measured inputs", ""]
    # ------------------------------------------------------------------ constants table
    const = []
    for m, c in MACH.items():
        H = harmonics(m)
        Ith_A = i_max(m, 1000, 1e3, 25.0, "A")[0]
        Ith_D = i_max(m, 1000, 1e3, 25.0, "D")[0]
        R25 = c["R20"] * (1 + ALPHA * 5)
        const.append(dict(machine=m, magnets=c["magnets"], series_boards_per_phase=c["boards"],
                          K_FEM_mNm_per_A=1e3 * c["K"], K_analytical_sheet=1e3 * c["K_an"], K_EQ_sweep=1e3 * c["K_eq"],
                          an_vs_FEM_pct=100 * (c["K_an"] / c["K"] - 1),
                          torque_per_A_pk_mNm=1.5e3 * c["K"], Ke_line_Vrms_per_krpm=math.sqrt(3) * c["K"] * 1000 * 2 * math.pi / 60 / math.sqrt(2),
                          E_phase_THD_pct=H["phase"]["THD"], E_line_THD_pct=H["line"]["THD"],
                          R_ph_20C_ohm=c["R20"], L_ph_uH_lo=1e6 * c["L"][0], L_ph_uH_hi=1e6 * c["L"][1],
                          tau_e_us_hi=1e6 * c["L"][1] / c["R20"],
                          Km_mNm_per_sqrtW_25C=1.5e3 * c["K"] / math.sqrt(1.5 * R25),
                          psi_pm_mWb=1e3 * c["K"] / P, char_current_A_pk=c["K"] / P / c["L"][1],
                          eddy_1000rpm_mW=1e3 * c["eddy"],
                          I_thermal_A_pk_scenA_25C=Ith_A, I_thermal_A_pk_scenD_25C=Ith_D,
                          T_em_thermal_A_mNm=1.5e3 * c["K"] * Ith_A, T_em_thermal_D_mNm=1.5e3 * c["K"] * Ith_D,
                          no_load_speed_12V_rpm=M_IDX * 12 / math.sqrt(3) / c["K"] * 60 / (2 * math.pi),
                          no_load_speed_24V_rpm=M_IDX * 24 / math.sqrt(3) / c["K"] * 60 / (2 * math.pi)))
    w("K0_motor_constants.csv", const)
    summary += ["## Comparative constants", "", "| Quantity | Rev0 | Rev1-S (series) | Evidence |", "|---|---|---|---|"]
    rowsdef = [("K (mN·m/A), T = 1.5 K Î", "K_FEM_mNm_per_A", "%.3f", "FEM"),
               ("K, analytical sheet-current", "K_analytical_sheet", "%.3f", "ANALYTICAL"),
               ("K, equivalent-coil sweep", "K_EQ_sweep", "%.2f", "FEM (calibrated)"),
               ("Torque per A pk (mN·m)", "torque_per_A_pk_mNm", "%.2f", "FEM"),
               ("Line back-EMF (V rms per 1000 rpm)", "Ke_line_Vrms_per_krpm", "%.3f", "FEM"),
               ("Back-EMF THD phase / line (%)", None, None, "FEM"),
               ("Phase resistance, 20 °C (Ω)", "R_ph_20C_ohm", "%.2f", "MEASURED"),
               ("Phase inductance L−M (µH)", None, None, "FEM (not measured)"),
               ("Characteristic current ψ/L (A pk)", "char_current_A_pk", "%.0f", "CIRCUIT"),
               ("Motor constant K_m at 25 °C (mN·m/√W)", "Km_mNm_per_sqrtW_25C", "%.2f", "FEM + MEASURED"),
               ("Track eddy loss at 1000 rpm (mW)", "eddy_1000rpm_mW", "%.1f", "FEM-post"),
               ("Thermal current, scenario A, 25 °C, 1000 rpm (A pk)", "I_thermal_A_pk_scenA_25C", "%.3f", "THERMAL-FEM"),
               ("Thermal current, scenario D (A pk)", "I_thermal_A_pk_scenD_25C", "%.3f", "ASSUMED R_th"),
               ("EM torque at those currents (mN·m)", None, None, "CIRCUIT"),
               ("No-load speed 12 / 24 V bus (rpm)", None, None, "CIRCUIT")]
    a, b = const
    for lab, key, fmt, ev in rowsdef:
        if key:
            summary.append("| %s | %s | %s | %s |" % (lab, fmt % a[key], fmt % b[key], ev))
        elif "THD" in lab:
            summary.append("| %s | %.1f / %.1f | %.1f / %.1f | %s |" % (lab, a["E_phase_THD_pct"], a["E_line_THD_pct"],
                                                                     b["E_phase_THD_pct"], b["E_line_THD_pct"], ev))
        elif "inductance" in lab:
            summary.append("| %s | %.1f–%.1f | %.1f–%.1f | %s |" % (lab, a["L_ph_uH_lo"], a["L_ph_uH_hi"], b["L_ph_uH_lo"], b["L_ph_uH_hi"], ev))
        elif "EM torque" in lab:
            summary.append("| %s | %.1f (A) / %.1f (D) | %.1f (A) / %.1f (D) | %s |" % (lab, a["T_em_thermal_A_mNm"], a["T_em_thermal_D_mNm"],
                                                                                   b["T_em_thermal_A_mNm"], b["T_em_thermal_D_mNm"], ev))
        else:
            summary.append("| %s | %.0f / %.0f | %.0f / %.0f | %s |" % (lab, a["no_load_speed_12V_rpm"], a["no_load_speed_24V_rpm"],
                                                                     b["no_load_speed_12V_rpm"], b["no_load_speed_24V_rpm"], ev))
    # ------------------------------------------------------------------ C1 current sweep at 1000 rpm
    C1 = []
    for m, c in MACH.items():
        Ii, kf = kfac(m)
        for I in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
            f = float(np.interp(I, Ii, kf)) if I > 0 else 1.0
            sA = state(m, 1000, I, 25.0, "A")
            sD = state(m, 1000, I, 25.0, "D")
            sL = state(m, 1000, I, 25.0, "A", c["L"][0])
            C1.append(dict(machine=m, I_pk_A=I, rpm=1000, T_em_FEM_mNm=1.5e3 * c["K"] * I * f,
                           K_ratio_FEM_sweep=f, K_ratio_source="FEM EQ sweep" if I in Ii else ("interpolated (v12 pending)" if I > 0 else "-"),
                           T_em_analytical_mNm=1.5e3 * c["K_an"] * I, P_cu_W_scenA=sA["P_cu_W"], T_wind_C_scenA=sA["T_wind_C"],
                           T_wind_C_scenD=sD["T_wind_C"], Vdc_req_V_Lhi=sA["Vdc_req"], Vdc_req_V_Llo=sL["Vdc_req"],
                           V_line_rms=sA["V_line_rms"], P_em_W=sA["P_em_W"], P_out_EM_W=sA["P_out_EM_W"],
                           eta_EM_pct=sA["eta_EM_pct"], within_60C_A=sA["T_wind_C"] <= T_LIM, within_60C_D=sD["T_wind_C"] <= T_LIM))
    w("C1_current_sweep_1000rpm.csv", C1)
    # ------------------------------------------------------------------ S1 speed sweep
    S1 = []
    for m, c in MACH.items():
        H = harmonics(m)
        IA = i_max(m, 1000, 1e3, 25.0, "A")[0]
        for rpm in (250, 500, 750, 1000, 1500, 2000, 3000, 4000):
            r0 = state(m, rpm, 0.0)
            for lab, I in (("0 A (no load)", 0.0), ("0.5 A", 0.5), ("thermal A at 1000 rpm", IA)):
                s = state(m, rpm, I, 25.0, "A")
                S1.append(dict(machine=m, rpm=rpm, f_e_Hz=rpm / 60.0 * P, current_case=lab, I_pk_A=I,
                               E_ph_rms_V=c["K"] * rpm * 2 * math.pi / 60 / math.sqrt(2),
                               E_line_rms_V=math.sqrt(3) * c["K"] * rpm * 2 * math.pi / 60 / math.sqrt(2),
                               E_line_rms_incl_harm_V=H["line"]["rms"] * rpm / 1000.0, E_line_THD_pct=H["line"]["THD"],
                               P_eddy_W=s["P_eddy_W"], T_eddy_drag_mNm=s["T_eddy_drag_mNm"], T_em_mNm=s["T_em_mNm"],
                               T_wind_C=s["T_wind_C"], Vdc_req_V=s["Vdc_req"], P_out_EM_W=s["P_out_EM_W"],
                               eta_EM_pct=s["eta_EM_pct"],
                               evidence="FEM 1000 rpm x n/1000 (v12 500/2000 rpm FEM pending)" if rpm != 1000 else "FEM"))
    w("S1_speed_sweep.csv", S1)
    # ------------------------------------------------------------------ E1 DC-bus sweep
    E1 = []
    for m, c in MACH.items():
        for Vdc in (6.0, 9.0, 12.0, 15.0, 18.0, 24.0):
            vmax = M_IDX * Vdc / math.sqrt(3)
            n0 = vmax / c["K"] * 60 / (2 * math.pi)
            for scen in ("A", "D"):
                IthA = i_max(m, 1000, 1e3, 25.0, scen)[0]
                I1k, lim = i_max(m, 1000, Vdc, 25.0, scen)
                I1k_lo, _ = i_max(m, 1000, Vdc, 25.0, scen, c["L"][0])
                s = state(m, 1000, I1k, 25.0, scen) if I1k > 0 else None
                # corner speed: highest speed at which the thermal current can still be driven
                lo, hi = 0.0, n0
                for _ in range(60):
                    mid = 0.5 * (lo + hi)
                    if state(m, mid, IthA, 25.0, scen)["V_ph_pk"] <= vmax:
                        lo = mid
                    else:
                        hi = mid
                sth = state(m, 1000, IthA, 25.0, scen)
                E1.append(dict(machine=m, Vdc_V=Vdc, thermal_scenario=scen, V_ph_pk_max_V=vmax, no_load_speed_rpm=n0,
                               I_max_1000rpm_A=I1k, limit_1000rpm=lim, I_max_1000rpm_Llo_A=I1k_lo,
                               T_em_max_1000rpm_mNm=1.5e3 * c["K"] * I1k, P_out_EM_1000rpm_W=s["P_out_EM_W"] if s else 0.0,
                               I_thermal_A=IthA, corner_speed_at_I_thermal_rpm=lo,
                               mod_depth_at_I_thermal_1000rpm=sth["V_ph_pk"] / vmax if sth["V_ph_pk"] < 10 * vmax else float("nan"),
                               Vdc_req_at_I_thermal_1000rpm_V=sth["Vdc_req"]))
    w("E1_vdc_sweep.csv", E1)
    # ------------------------------------------------------------------ F1 envelopes
    F1 = []
    speeds = list(range(0, 7001, 50))
    env = {}
    for m, c in MACH.items():
        for Vdc in (6.0, 9.0, 12.0, 15.0, 18.0, 24.0):
            for scen in ("A", "D"):
                key = (m, Vdc, scen); env[key] = []
                for n in speeds:
                    I, lim = i_max(m, max(n, 1e-6), Vdc, 25.0, scen)
                    if I <= 0:
                        break
                    s = state(m, n, I, 25.0, scen)
                    env[key].append((n, s["T_em_mNm"], s["P_out_EM_W"], s["eta_EM_pct"], I, lim))
                    F1.append(dict(machine=m, Vdc_V=Vdc, thermal_scenario=scen, rpm=n, I_pk_A=I, limit=lim,
                                   T_em_mNm=s["T_em_mNm"], P_em_W=s["P_em_W"], P_out_EM_W=s["P_out_EM_W"], eta_EM_pct=s["eta_EM_pct"],
                                   T_wind_C=s["T_wind_C"], V_line_rms=s["V_line_rms"],
                                   region="verified speed range" if n <= N_VERIFIED else "extrapolated beyond 4000 rpm"))
    w("F1_envelopes.csv", F1)
    # efficiency grids (nominal bus)
    grids = {}
    for m, c in MACH.items():
        ns = np.linspace(100, 4000, 79); Is = np.linspace(0.02, I_CAP, 150)
        G = []
        for n in ns:
            for I in Is:
                s = state(m, n, I, 25.0, "A")
                feas = s["Vdc_req"] <= c["Vnom"]
                G.append(dict(machine=m, Vdc_V=c["Vnom"], rpm=n, I_pk_A=I, T_em_mNm=s["T_em_mNm"], eta_EM_pct=s["eta_EM_pct"],
                              T_wind_C=s["T_wind_C"], Vdc_req_V=s["Vdc_req"], voltage_ok=feas, thermal_ok_A=s["T_wind_C"] <= T_LIM))
        grids[m] = (ns, Is, G)
        w("F2_grid_%s_%gV.csv" % (m.replace("-", ""), c["Vnom"]), G)
    # ------------------------------------------------------------------ summary tables
    summary += ["", "## C1 - current sweep at 1000 rpm, 25 °C (scenario A thermal; L upper)", "",
                "| Machine | I pk (A) | T_em FEM (mN·m) | T_em analytical (mN·m) | Winding A / D (°C) | Bus needed (V) | η_EM (%) |", "|---|---|---|---|---|---|---|"]
    tf = lambda t: ("%.0f" % t) if t < 200 else ">200"
    summary += ["| %s | %.2f | %.2f | %.2f | %s / %s | %.2f | %.0f |" % (r["machine"], r["I_pk_A"], r["T_em_FEM_mNm"], r["T_em_analytical_mNm"],
                tf(r["T_wind_C_scenA"]), tf(r["T_wind_C_scenD"]), r["Vdc_req_V_Lhi"], r["eta_EM_pct"]) for r in C1]
    summary += ["", "Winding temperatures above 200 C are outside the thermal model (no steady state below the 600 C cap); they mark "
                "currents that are not continuous."]
    summary += ["", "## E1 - DC-bus sweep (25 °C)", "",
                "| Machine | Vdc (V) | Thermal | No-load speed (rpm) | Max I at 1000 rpm (A pk) | Limited by | T_em at 1000 rpm (mN·m) | Corner speed at thermal I (rpm) | Bus use at thermal I, 1000 rpm |",
                "|---|---|---|---|---|---|---|---|---|"]
    summary += ["| %s | %g | %s | %.0f | %.3f | %s | %.1f | %.0f | %s |" % (r["machine"], r["Vdc_V"], r["thermal_scenario"], r["no_load_speed_rpm"],
                r["I_max_1000rpm_A"], r["limit_1000rpm"], r["T_em_max_1000rpm_mNm"], r["corner_speed_at_I_thermal_rpm"],
                ("%.0f %%" % (100 * r["mod_depth_at_I_thermal_1000rpm"])) if r["mod_depth_at_I_thermal_1000rpm"] == r["mod_depth_at_I_thermal_1000rpm"] else "-")
                for r in E1]
    summary += ["", "## S1 - speed sweep at the scenario-A thermal current (25 °C)", "",
                "| Machine | rpm | E line (V rms) | Eddy (mW) | Eddy drag (mN·m) | T_em (mN·m) | Winding (°C) | Bus needed (V) | η_EM (%) |",
                "|---|---|---|---|---|---|---|---|---|"]
    summary += ["| %s | %d | %.3f | %.1f | %.3f | %.1f | %.1f | %.2f | %.0f |" % (r["machine"], r["rpm"], r["E_line_rms_V"], 1e3 * r["P_eddy_W"],
                r["T_eddy_drag_mNm"], r["T_em_mNm"], r["T_wind_C"], r["Vdc_req_V"], r["eta_EM_pct"])
                for r in S1 if r["current_case"].startswith("thermal")]
    open(os.path.join(OUT, "sweeps_summary.md"), "w").write("\n".join(summary) + "\n")
    print("\n".join(summary))
    plots(C1, S1, E1, env, grids)


def plots(C1, S1, E1, env, grids):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
    # P1 torque vs current
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    for m, c in MACH.items():
        Is = np.linspace(0, 3, 50)
        ax.plot(Is, 1.5e3 * c["K"] * Is, color=COL[m], lw=1.3, label="%s: 1.5·K·I (K = %.2f, FEM)" % (m, 1e3 * c["K"]))
        d = json.load(open(os.path.join(ARCH, c["isw"], "eq_isweep_results.json")))
        k1 = [p for p in d["points"] if p["Ipk"] == 1.0][0]["K_mNm_per_A"]
        pts = [(p["Ipk"], 1.5 * c["K"] * 1e3 * p["Ipk"] * p["K_mNm_per_A"] / k1) for p in d["points"] if p["Ipk"] > 0]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "o", mfc="white", color=COL[m], ms=5, label="%s: FEM current-sweep points" % m)
        for scen, ls in (("A", "--"), ("D", ":")):
            I = i_max(m, 1000, 1e3, 25.0, scen)[0]
            ax.axvline(I, color=COL[m], ls=ls, lw=0.9)
    ax.text(0.03, 0.97, "dashed: 60 °C limit, scenario A (Icepak)\ndotted: scenario D (cautious)", transform=ax.transAxes,
            fontsize=7, va="top")
    ax.set_xlabel("Phase current (A peak), i_d = 0"); ax.set_ylabel("Electromagnetic torque (mN·m)")
    ax.legend(fontsize=6.5, loc="lower right"); fig.tight_layout(); fig.savefig(os.path.join(OUT, "P1_torque_vs_current.png"), dpi=220); plt.close(fig)
    # P2 back-EMF waveforms and harmonics
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.9))
    for m in MACH:
        H = harmonics(m)
        t = np.array(H["t_ms"]); T = 7.5
        tt = np.concatenate([[0.0], t]); ea = np.concatenate([[H["ea"][-1]], H["ea"]]); eab = np.concatenate([[H["eab"][-1]], H["eab"]])
        axs[0].plot(tt / T * 360, ea, "-", color=COL[m], lw=1.2, label="%s phase" % m)
        axs[0].plot(tt / T * 360, eab, "--", color=COL[m], lw=1.0, label="%s line A−B" % m)
        k = np.arange(1, 12)
        off = -0.2 if m == "Rev0" else 0.2
        axs[1].bar(k + off, H["phase"]["H"], width=0.38, color=COL[m], label="%s phase" % m)
    axs[0].set_xlabel("Electrical angle (°)"); axs[0].set_ylabel("Back-EMF at 1000 rpm (V)"); axs[0].set_xlim(0, 360)
    axs[0].legend(fontsize=6.5, ncol=2, loc="lower left")
    axs[1].set_yscale("log"); axs[1].set_ylim(0.01, 150); axs[1].set_xticks(range(1, 12))
    axs[1].set_xlabel("Harmonic order"); axs[1].set_ylabel("Phase back-EMF (% of H1)"); axs[1].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "P2_backemf_waveform_harmonics.png"), dpi=220); plt.close(fig)
    # P3 EMF and eddy vs speed
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.8))
    for m, c in MACH.items():
        rs = [r for r in S1 if r["machine"] == m and r["current_case"].startswith("0 A")]
        axs[0].plot([r["rpm"] for r in rs], [r["E_line_rms_V"] for r in rs], "-o", color=COL[m], ms=3, label=m)
        axs[0].plot([1000], [[r for r in rs if r["rpm"] == 1000][0]["E_line_rms_V"]], "s", color="k", ms=5)
        axs[1].plot([r["rpm"] for r in rs], [1e3 * r["P_eddy_W"] for r in rs], "-o", color=COL[m], ms=3, label=m)
    axs[0].set_xlabel("Speed (rpm)"); axs[0].set_ylabel("Line back-EMF (V rms)")
    axs[0].text(0.03, 0.95, "■ FEM solve (1000 rpm); line: e ∝ n\n500 / 2000 rpm FEM checks pending (v12)", transform=axs[0].transAxes, fontsize=7, va="top")
    axs[1].set_xlabel("Speed (rpm)"); axs[1].set_ylabel("Track eddy loss (mW), ∝ n²")
    axs[0].legend(fontsize=7, loc="lower right"); axs[1].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "P3_emf_eddy_vs_speed.png"), dpi=220); plt.close(fig)
    # P4 Vdc sweep
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.8))
    for m in MACH:
        for scen, ls in (("A", "-"), ("D", "--")):
            rs = [r for r in E1 if r["machine"] == m and r["thermal_scenario"] == scen]
            axs[0].plot([r["Vdc_V"] for r in rs], [r["T_em_max_1000rpm_mNm"] for r in rs], ls, marker="o", ms=3, color=COL[m],
                        label="%s, thermal %s" % (m, scen))
        rs = [r for r in E1 if r["machine"] == m and r["thermal_scenario"] == "A"]
        axs[1].plot([r["Vdc_V"] for r in rs], [r["no_load_speed_rpm"] for r in rs], "-o", ms=3, color=COL[m], label="%s no-load" % m)
        axs[1].plot([r["Vdc_V"] for r in rs], [r["corner_speed_at_I_thermal_rpm"] for r in rs], "--s", ms=3, color=COL[m], label="%s at thermal I (A)" % m)
    axs[1].axhline(1000, color="0.4", lw=0.8, ls=":"); axs[1].text(6.2, 1080, "1000 rpm target", fontsize=7, color="0.3")
    axs[0].set_xlabel("DC bus (V)"); axs[0].set_ylabel("Max EM torque at 1000 rpm (mN·m)"); axs[0].legend(fontsize=6.5)
    axs[1].set_xlabel("DC bus (V)"); axs[1].set_ylabel("Voltage-limited speed (rpm)"); axs[1].legend(fontsize=6.5)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "P4_vdc_sweep.png"), dpi=220); plt.close(fig)
    # P5 envelopes at 12 and 24 V
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.0), sharey=True)
    for ax, Vdc in zip(axs, (12.0, 24.0)):
        for m in MACH:
            for scen, ls in (("A", "-"), ("D", "--")):
                e = env[(m, Vdc, scen)]
                ax.plot([p[0] for p in e] + [e[-1][0] + 50], [p[1] for p in e] + [0], ls, color=COL[m], lw=1.3,
                        label="%s, %s" % (m, "Icepak (A)" if scen == "A" else "cautious (D)"))
        ax.axvspan(4000, 7000, color="0.92", zorder=0); ax.text(4100, 2, "beyond verified\nspeed range", fontsize=7, color="0.35")
        ax.axvline(1000, color="0.4", lw=0.8, ls=":")
        ax.set_xlim(0, 7000); ax.set_title("%g V bus, SVPWM m = 0.95, 25 °C, 60 °C winding" % Vdc, fontsize=8.5)
        ax.set_xlabel("Speed (rpm)")
    axs[0].set_ylabel("Continuous EM torque (mN·m)"); axs[0].legend(fontsize=6.5, loc="upper right")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "P5_torque_speed_envelopes.png"), dpi=220); plt.close(fig)
    # P6 EM efficiency maps at the nominal bus
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.0))
    for ax, m in zip(axs, MACH):
        ns, Is, G = grids[m]
        Z = np.array([g["eta_EM_pct"] for g in G]).reshape(len(ns), len(Is))
        Tq = np.array([g["T_em_mNm"] for g in G]).reshape(len(ns), len(Is))
        V = np.array([g["voltage_ok"] for g in G]).reshape(len(ns), len(Is))
        Th = np.array([g["thermal_ok_A"] for g in G]).reshape(len(ns), len(Is))
        Z = np.where(V, Z, np.nan)
        N = np.repeat(ns[:, None], len(Is), axis=1)
        cs = ax.contourf(N, Tq, Z, levels=[0, 20, 40, 50, 60, 70, 80, 85, 90, 95], cmap="Blues")
        e = env[(m, MACH[m]["Vnom"], "A")]
        ax.plot([p[0] for p in e if p[0] <= 4000], [p[1] for p in e if p[0] <= 4000], "k-", lw=1.6)
        ax.set_title("%s, %g V bus (shaded: voltage-feasible)\nblack: continuous envelope, scenario A" % (m, MACH[m]["Vnom"]), fontsize=8)
        ax.set_xlabel("Speed (rpm)"); ax.set_ylabel("EM torque (mN·m)")
        ax.set_ylim(0, 1.05 * np.nanmax(np.where(V, Tq, np.nan)))
        cb = fig.colorbar(cs, ax=ax, shrink=0.85); cb.set_label("η_EM (%)", fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "P6_efficiency_maps.png"), dpi=220); plt.close(fig)


if __name__ == "__main__":
    main()
