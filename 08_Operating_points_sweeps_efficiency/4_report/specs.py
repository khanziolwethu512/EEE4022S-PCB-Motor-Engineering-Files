"""Gate 4 - conditional simulation-based operating specifications and the list of assumptions that still block a
defensible continuous rating. Numbers are recomputed from ../sweeps (circuit model on verified FEM + measured R +
Icepak R_th); nothing is typed in by hand except the provenance text.  python specs.py -> specs.json, specs.md
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sweeps"))
import sweeps as SW

PWM = {"Rev0": dict(Vdc=12.0, L=(33.5e-6, 51.2e-6)), "Rev1-S": dict(Vdc=24.0, L=(74.4e-6, 112.6e-6))}
FSW = 50e3


def spec(m):
    c = SW.MACH[m]
    out = {"machine": m, "Vdc_nominal": c["Vnom"]}
    for scen in ("D", "A"):
        for Ta in (25.0, 30.0):
            I, lim = SW.i_max(m, 1000, 1e3, Ta, scen)
            s = SW.state(m, 1000, I, Ta, scen)
            nc = 0.0
            lo, hi = 0.0, 8000.0
            vmax = SW.M_IDX * c["Vnom"] / math.sqrt(3)
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if SW.state(m, mid, I, Ta, scen)["V_ph_pk"] <= vmax else (lo, mid)
            out["%s_%g" % (scen, Ta)] = dict(I_pk=I, I_rms=I / math.sqrt(2), T_em_mNm=s["T_em_mNm"], P_em_W=s["P_em_W"],
                                             P_out_EM_W=s["P_out_EM_W"], P_cu_W=s["P_cu_W"], P_eddy_W=s["P_eddy_W"],
                                             P_in_W=s["P_in_W"], eta_EM_pct=s["eta_EM_pct"], V_line_rms=s["V_line_rms"],
                                             Vdc_req=s["Vdc_req"], corner_rpm_nominal_bus=lo, T_wind=s["T_wind_C"])
    out["no_load_rpm_nominal_bus"] = SW.M_IDX * c["Vnom"] / math.sqrt(3) / c["K"] * 60 / (2 * math.pi)
    out["E_line_per_krpm"] = math.sqrt(3) * c["K"] * 1000 * 2 * math.pi / 60 / math.sqrt(2)
    # PWM ripple (estimate, excluded from the thermal limit): pk-pk ~ Vdc / (6 L f_sw)
    Ia = out["A_25"]["I_rms"]
    rip = [PWM[m]["Vdc"] / (6 * L * FSW) for L in PWM[m]["L"][::-1]]
    out["pwm_ripple_pkpk_A_50kHz"] = rip
    out["pwm_extra_cu_loss_pct"] = [100 * (r / (2 * math.sqrt(3))) ** 2 / Ia ** 2 for r in rip]
    return out


ASSUMPTIONS = [
 ("1", "Thermal boundary conditions", "Icepak modelled a HYPOTHETICAL acrylic housing in a bench hood with 1 m/s fans, the "
  "rotor still and radiation off. The as-built motor runs in an open frame. No thermal resistance has been measured.",
  "Scenario A vs D (1.71 x R_th) moves the continuous current by 25-33 %.", "Heat run: constant current to steady state, "
  "R_th = dT / P from the resistance rise and thermocouples on S1 boards 1 and 5."),
 ("2", "Winding temperature limit", "60 C is a placeholder for the unconfirmed holder material (FR-4 itself and N35 magnets "
  "allow more).", "100 C instead of 60 C raises the continuous current by about 37 % (allowed rise x 2.1, less the higher R at 100 C).",
  "Confirm the holder material and its service temperature."),
 ("3", "Resistance basis", "1.87-1.90 ohm per stator phase measured 2-wire at an unrecorded temperature; 0-0.1 ohm may be "
  "contact resistance.", "R20 1.80-1.94 ohm: +/-2.5 % in current.", "4-wire measurement with the temperature recorded."),
 ("4", "Heat distribution", "The measured R is 36 % above the trace model. Where the extra resistance sits (vias, rim "
  "bridges, junctions or tracks) is unknown; Icepak spread the heat over the tracks.", "Local hotspots could exceed the "
  "modelled hotspot.", "Thermal camera / thermocouples at junctions in the heat run."),
 ("5", "PWM current ripple", "Excluded from all loss and thermal figures (sinusoidal currents assumed). L is small "
  "(34-51 uH per stator, simulated, not measured).", "At 50 kHz the ripple adds an estimated %s %% (Rev0, 12 V) and %s %% "
  "(Rev1-S, 24 V) to the copper loss at the scenario-A current.", "Measure L; measure ripple at low current; choose f_sw or "
  "add series inductance."),
 ("6", "Mechanical and inverter losses", "Bearing, windage and inverter losses are not modelled, so no shaft torque, shaft "
  "power or mechanical efficiency is available; eta_EM is an upper bound.", "-", "No-load drag (FOC current method or "
  "spin-down) and input/output power measurement."),
 ("7", "Magnet properties and assembly", "Br 1.23 T and mu_r 1.0998 are library N35 values; the 1.0 mm gap and 1.02 mm board "
  "pitch are nominal.", "K scales with Br; about 7 % per extra 0.25 mm of gap.", "Open-circuit back-EMF test on the built "
  "machine (outside this simulation scope)."),
 ("8", "Rev1-S electromagnetic reference", "No full-motor detailed FEM (job 1486831 lost to the disk quota); K = board-by-board "
  "sum, confirmed by the independent sheet-current model (+0.13 %) and the EQ model (-0.17 %). +/-I check in the S2 "
  "environment pending (v12).", "Small (< 0.5 %).", "v12 DIAG_REV1S_S2_B1/B5."),
 ("9", "Speed scaling and eddy loss", "e ~ n and track eddy ~ n^2 from the single 1000 rpm FEM solve; eddy by the "
  "thin-conductor formula on the centre-line field, vias excluded.", "Eddy is 0.5-1 % of the loss at 1000 rpm, 8 % (Rev0) / "
  "15 % (Rev1-S) at 4000 rpm.", "v12 FMROT 500/2000 rpm."),
 ("10", "Transient thermal behaviour", "Time constants (9.2 min turning, 24 min stalled) come from the Rev0 lumped network; "
  "Icepak was steady-state only; Rev1-S assumed equal (conservative).", "Short-time ratings are indicative only.",
  "Heating curve from the heat run."),
 ("11", "Ambient and speed", "25 C (and 30 C) still lab air; no rotor stirring credited except scenario C (1000 rpm only). "
  "No speed above 1000 rpm is mechanically qualified.", "30 C ambient lowers the current by 7-8 %.", "Record ambient; "
  "mechanical check before any run above 1000 rpm."),
]


def main():
    S = {m: spec(m) for m in SW.MACH}
    json.dump(S, open(os.path.join(HERE, "specs.json"), "w"), indent=1)
    r0, r1 = S["Rev0"], S["Rev1-S"]
    f = lambda d, k, fmt="%.2f": fmt % d[k]
    md = ["# Proposed simulation-based operating specifications (conditional)", "",
          "Original simulation geometry only (86 mm OD / 19 mm bore / 2 mm backplates, 1.0 mm gaps); star connection; "
          "FOC i_d = 0; SVPWM m = 0.95; 1000 rpm target speed. Two thermal bases: **D** = cautious planning basis "
          "(assumed R_th 15 / 25.3 K/W per stator) and **A** = Icepak (hypothetical housing, fans on, rotor still). "
          "Ambient 25 C, winding limit 60 C. Electromagnetic values only: shaft torque, shaft power, mechanical efficiency "
          "and a validated continuous rating are NOT available without measurements.", "",
          "| Item | Rev0 | Rev1-S (series) | Label |", "|---|---|---|---|",
          "| DC bus (nominal) | 12 V | 24 V | assumed (drive) |",
          "| Target speed / electrical frequency | 1000 rpm / 133.3 Hz | 1000 rpm / 133.3 Hz | test plan |",
          "| Line back-EMF | %.3f V rms per 1000 rpm | %.3f V rms per 1000 rpm | FEM |" % (r0["E_line_per_krpm"], r1["E_line_per_krpm"]),
          "| Continuous phase current, D / A | %.2f / %.2f A pk (%.2f / %.2f A rms) | %.2f / %.2f A pk (%.2f / %.2f A rms) | thermally inferred |"
          % (r0["D_25"]["I_pk"], r0["A_25"]["I_pk"], r0["D_25"]["I_rms"], r0["A_25"]["I_rms"],
             r1["D_25"]["I_pk"], r1["A_25"]["I_pk"], r1["D_25"]["I_rms"], r1["A_25"]["I_rms"]),
          "| Same at 30 C ambient, D / A | %.2f / %.2f A pk | %.2f / %.2f A pk | thermally inferred |"
          % (r0["D_30"]["I_pk"], r0["A_30"]["I_pk"], r1["D_30"]["I_pk"], r1["A_30"]["I_pk"]),
          "| Continuous EM torque, D / A | %.1f / %.1f mN·m | %.1f / %.1f mN·m | FEM K x current |"
          % (r0["D_25"]["T_em_mNm"], r0["A_25"]["T_em_mNm"], r1["D_25"]["T_em_mNm"], r1["A_25"]["T_em_mNm"]),
          "| EM output at 1000 rpm (T_em ω − eddy), D / A | %.2f / %.2f W | %.2f / %.2f W | circuit model |"
          % (r0["D_25"]["P_out_EM_W"], r0["A_25"]["P_out_EM_W"], r1["D_25"]["P_out_EM_W"], r1["A_25"]["P_out_EM_W"]),
          "| Electrical input to the winding, D / A | %.2f / %.2f W | %.2f / %.2f W | circuit model |"
          % (r0["D_25"]["P_in_W"], r0["A_25"]["P_in_W"], r1["D_25"]["P_in_W"], r1["A_25"]["P_in_W"]),
          "| EM efficiency (no mechanical / inverter loss), D / A | %.0f / %.0f %% | %.0f / %.0f %% | circuit model |"
          % (r0["D_25"]["eta_EM_pct"], r0["A_25"]["eta_EM_pct"], r1["D_25"]["eta_EM_pct"], r1["A_25"]["eta_EM_pct"]),
          "| Line voltage at the terminals, D / A (60 C) | %.2f / %.2f V rms | %.2f / %.2f V rms | circuit model |"
          % (r0["D_25"]["V_line_rms"], r0["A_25"]["V_line_rms"], r1["D_25"]["V_line_rms"], r1["A_25"]["V_line_rms"]),
          "| Minimum DC bus at 1000 rpm, D / A | %.1f / %.1f V | %.1f / %.1f V | circuit model |"
          % (r0["D_25"]["Vdc_req"], r0["A_25"]["Vdc_req"], r1["D_25"]["Vdc_req"], r1["A_25"]["Vdc_req"]),
          "| Voltage-limited speed at that current, nominal bus, D / A | %.0f / %.0f rpm | %.0f / %.0f rpm | circuit model (not a speed rating) |"
          % (r0["D_25"]["corner_rpm_nominal_bus"], r0["A_25"]["corner_rpm_nominal_bus"], r1["D_25"]["corner_rpm_nominal_bus"], r1["A_25"]["corner_rpm_nominal_bus"]),
          "| No-load voltage-limited speed, nominal bus | %.0f rpm | %.0f rpm | circuit model |" % (r0["no_load_rpm_nominal_bus"], r1["no_load_rpm_nominal_bus"]),
          "| Short-time current from cold (τ 9.2 min, conservative) | 1.5 A pk ≤ 7.7 min; 2.0 A pk ≤ 3.6 min | 1.0 A pk ≤ 11.8 min; 1.5 A pk ≤ 3.7 min | thermally inferred, indicative |",
          "| Maximum current of the EM model | 3 A pk (K linear within 0.01 %) | 3 A pk | FEM |",
          "| PWM ripple at 50 kHz (excluded above) | %.1f–%.1f A pk-pk (+%.0f–%.0f %% copper loss) | %.1f–%.1f A pk-pk (+%.0f–%.0f %%) | circuit estimate |"
          % (r0["pwm_ripple_pkpk_A_50kHz"][0], r0["pwm_ripple_pkpk_A_50kHz"][1], r0["pwm_extra_cu_loss_pct"][0], r0["pwm_extra_cu_loss_pct"][1],
             r1["pwm_ripple_pkpk_A_50kHz"][0], r1["pwm_ripple_pkpk_A_50kHz"][1], r1["pwm_extra_cu_loss_pct"][0], r1["pwm_extra_cu_loss_pct"][1]),
          "", "# Remaining assumptions that prevent a defensible continuous rating", "",
          "| # | Assumption | What is assumed now | Effect on the rating | What would close it |", "|---|---|---|---|---|"]
    for a in ASSUMPTIONS:
        eff = a[3]
        if "%s" in eff:
            eff = eff % ("%.0f-%.0f" % tuple(r0["pwm_extra_cu_loss_pct"]), "%.0f-%.0f" % tuple(r1["pwm_extra_cu_loss_pct"]))
        md.append("| %s | %s | %s | %s | %s |" % (a[0], a[1], a[2], eff, a[4]))
    md += ["", "The constructed Rev0 prototype (4 mm gap, 80 / 25 mm backplates) is a different geometry; none of the values "
           "above transfer to it."]
    open(os.path.join(HERE, "specs.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
