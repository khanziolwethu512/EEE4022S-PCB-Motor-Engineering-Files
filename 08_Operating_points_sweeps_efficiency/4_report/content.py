"""Report-ready material for Chapters 3-5 (final operating characterisation). All numbers come from the generated
CSV/JSON outputs; this file only arranges them. python content.py -> report_content.json (rendered by render.js)."""
import csv, json, math, os
HERE = os.path.dirname(os.path.abspath(__file__))
FO = os.path.dirname(HERE)
rd = lambda p: list(csv.DictReader(open(os.path.join(FO, p))))
K0 = dict((r["machine"], r) for r in rd("sweeps/out/K0_motor_constants.csv"))
E1 = rd("sweeps/out/E1_vdc_sweep.csv")
TL = rd("thermal/out/T1_thermal_limits.csv")
ST = rd("thermal/out/T2_short_time_limits.csv")
SP = json.load(open(os.path.join(HERE, "specs.json")))
f = lambda x, n=2: ("%%.%df" % n) % float(x)
r0, r1 = SP["Rev0"], SP["Rev1-S"]
k0, k1 = K0["Rev0"], K0["Rev1-S"]
B = []
H1 = lambda t: B.append({"t": "h1", "x": t})
H2 = lambda t: B.append({"t": "h2", "x": t})
Pp = lambda t: B.append({"t": "p", "x": t})
EQ = lambda t, n: B.append({"t": "eq", "x": t, "n": n})
NOTE = lambda t: B.append({"t": "note", "x": t})


def TAB(cap, head, rows, widths):
    B.append({"t": "table", "cap": cap, "head": head, "rows": rows, "w": widths})


def FIG(path, cap, wid=6.3):
    B.append({"t": "fig", "path": os.path.join(FO, path), "cap": cap, "w": wid})


def tl(m, s, Ta, rpm, rb="measured 1.89"):
    for r in TL:
        if (r["machine"], r["scenario"], float(r["T_amb_C"]), int(r["rpm"]), r["R20_basis"]) == (m, s, Ta, rpm, rb):
            return float(r["I_lim_pk_A"])


NOTE("Report-ready material for insertion into Chapters 3-5. Section, table, figure and equation numbers are local "
     "(3.x, 4.x, 5.x) and should be renumbered on insertion. Every value refers to the ORIGINAL simulated geometry "
     "(86 mm OD, 19 mm bore, 2 mm backplates, 1.0 mm air gaps). The constructed Rev0 prototype is a different geometry "
     "and is reported separately. Experimental testing is postponed; no value here is measured except the winding "
     "resistance.")

# ======================================================================= CHAPTER 3
H1("Chapter 3 material: Methodology of the operating characterisation")
H2("3.x Scope and evidence labels")
Pp("The operating characterisation establishes simulation-based operating specifications for the two machines in their "
   "original simulated form: Rev0 (one stator, one rotor, five series PCBs per phase) and Rev1-S (two stators and two "
   "rotors, ten series PCBs per phase). Both are 16-pole, star-connected and driven by a three-phase inverter. The "
   "programme re-uses every completed and validated calculation, adds only the electromagnetic checks still missing from "
   "the test matrix, and then derives current, speed and DC-bus voltage characteristics with a steady-state circuit model.")
Pp("Each result carries one of the labels in Table 3.1. The labels keep three kinds of evidence apart: finite-element "
   "solutions, independent analytical predictions, and circuit-model extrapolations built on them. The electromagnetic "
   "power T_em·ω computed here is the power converted across the air gap. It is not a measured shaft output, because "
   "bearing, windage and inverter losses are neither modelled nor measured.")
TAB("Table 3.1. Evidence labels used in Chapters 4 and 5.", ["Label", "Meaning"], [
    ["FEM", "Ansys Maxwell 3D solution (magnetostatic or transient) of the modelled geometry"],
    ["FEM (calibrated)", "Equivalent-coil Maxwell model whose turns were calibrated on the detailed FEM"],
    ["ANALYTICAL", "Independent model with no Maxwell input: charged-sheet magnets, image planes, 2D sheet currents in the real copper"],
    ["THERMAL-FEM", "Ansys Icepak steady solution (hypothetical housing; see Section 3.x.4)"],
    ["THERMAL-LUMPED", "Lumped thermal network"],
    ["CIRCUIT", "dq steady-state model fed by the quantities above"],
    ["MEASURED", "Bench measurement on the built stators (winding resistance only)"],
    ["ASSUMED", "Engineering assumption stated in the text"]], [1.6, 4.7])
H2("3.x.1 Provenance and re-use of completed results")
Pp("Before any new calculation, the archived Maxwell, Icepak and HPC results were inventoried against the test matrix "
   "(Table 3.2). The inventory records the solver, run or SLURM job identifier, settings and key values for each source. "
   "Of the sixteen matrix rows, seven are complete from archived results (V1, V2, V3 and C1 for Rev0; V1, V3 and C1 for "
   "Rev1-S). Six are new post-processing completed here (E1, T1 and F1 for both machines). Three need targeted HPC "
   "runs, which were prepared: the Rev1-S ±I check (V2) and independent 500 and 2000 rpm rotating solves (S1, both "
   "machines).")
TAB("Table 3.2. Principal sources re-used (UCT HPC SLURM job numbers where applicable).",
    ["Source", "Machine", "Label", "Job / run", "Key result"], [
    ["Full detailed static motor", "Rev0", "FEM", "1470376", "K = 18.534 mN·m/A"],
    ["Full detailed static motor", "Rev1-S", "FEM", "1486831", "Not completed (disk quota); not rerun"],
    ["Detailed single boards, S1 and S2 environment", "Both", "FEM", "lab PCs (P20 runs)", "Rev0 18.54; Rev1-S 18.54 + 20.96 = 39.50 mN·m/A"],
    ["Rotating field-only transient, 1000 rpm", "Rev0", "FEM", "1500352", "E = 2.377 V rms line; THD 5.5 % phase; eddy 20.4 mW"],
    ["Rotating field-only transient, 1000 rpm", "Rev1-S", "FEM", "ID not recorded", "E = 5.066 V rms line; S1/S2 in phase"],
    ["Equivalent-coil current sweep 0-3 A", "Rev0 / Rev1-S", "FEM (calibrated)", "1504750 / 1504792", "K linear within 0.01 %; L−M 34-51 / 74-113 µH"],
    ["Targeted ±I diagnostic, boards 1 and 5", "Rev0", "FEM", "1517777 / 1517602", "Copper vs rotor torque −0.07 / +0.43 %"],
    ["Sheet-current analytical model", "Both", "ANALYTICAL", "offline", "K 18.539 / 39.55 mN·m/A"],
    ["Icepak steady, fans on/off", "Both", "THERMAL-FEM", "RUN1 (lab PC)", "R_th per stator 8.2-8.9 / 13.2-16.1 K/W"],
    ["Winding resistance", "Both", "MEASURED", "bench, 20 Oct", "1.87-1.90 Ω per stator phase"]],
    [1.75, 0.8, 0.9, 1.05, 1.8])
Pp("The series connection and terminals of both machines were checked from the archived rotating solution. Every board "
   "of both stators has a phase-A back-EMF angle of −30.0 ± 0.2° electrical, the Rev1-S stators S1 and S2 differ by "
   "0.02°, and phases A, B and C lie at −30°, +90° and −150° (120.0° steps, torque-constant spread ≤ 0.04 %). The series "
   "connection is therefore additive, and the simulated balanced currents (i_A + i_B + i_C = 0) correspond to the star connection.")
H2("3.x.2 Remaining electromagnetic checks")
Pp("Only checks that close an open matrix row were prepared, with acceptance criteria fixed before the runs. "
   "(i) The ±I diagnostic is repeated in the Rev1-S stator-2 environment (R2 magnets on one side, R1's bare steel "
   "backplate on the other) at the board-1 and board-5 positions. "
   "(ii) The rotating field-only model is solved at 500 and 2000 rpm, using 24 steps per period with half-wave symmetry, "
   "to test the speed scaling of back-EMF, harmonics and track eddy loss independently. "
   "(iii) Optionally, the calibrated current sweep is extended to 0.25 and 0.75 A. "
   "Until these runs return, the 250-4000 rpm characteristics use exact speed scaling of the 1000 rpm solution and are "
   "labelled accordingly.")
H2("3.x.3 Steady-state circuit model")
Pp("With field-oriented control and the current on the q-axis (i_d = 0), the phase quantities at mechanical speed ω_m "
   "and electrical speed ω_e = p·ω_m (p = 8 pole pairs) are")
EQ("T_em = 1.5 · K · Î,     e_ph,pk = K · ω_m", "3.1")
EQ("V_q = R(T) · Î + K · ω_m,     V_d = −ω_e · L · Î,     |V| = √(V_q² + V_d²) ≤ m · V_dc / √3", "3.2")
Pp("Here K is the FEM torque coefficient (Table 4.1), R(T) = R_20[1 + 0.00393(T − 20)] is the measured phase "
   "resistance evaluated at the winding hotspot temperature, L is the simulated synchronous inductance, and m = 0.95 is "
   "the usable SVPWM modulation depth. V_dc is the DC-bus voltage, not the motor line voltage. Because the "
   "characteristic current ψ/L is about 45 A against an operating range below 3 A, field weakening is ineffective and "
   "i_d = 0 is the only useful strategy. The voltage limit uses the upper inductance value; the lower value is a "
   "sensitivity case. Powers and efficiency are defined as")
EQ("P_em = T_em · ω_m,   P_out,EM = P_em − P_eddy,   P_in = P_em + 1.5 · Î² · R(T),   η_EM = P_out,EM / P_in", "3.3")
Pp("P_eddy is the track eddy loss from the rotating FEM at 1000 rpm, scaled with speed squared. η_EM excludes "
   "mechanical and inverter losses and is therefore an upper bound on the real efficiency. PWM current ripple is not "
   "included; its effect is estimated separately in Chapter 5.")
H2("3.x.4 Thermal model revision")
Pp("The Icepak models represent each machine in a hypothetical acrylic housing inside a bench hood. Their boundary "
   "conditions are a 30 °C inlet, fans at 1 m/s or off, the rotor stationary and radiation neglected. The housing is "
   "not the as-built open frame. The archived solves applied the trace-model resistance (1.389 Ω per stator phase at "
   "20 °C), which is 27 % below the measured 1.89 Ω. Rather than repeat the solves, the stator-to-air thermal resistance "
   "was extracted from them,")
EQ("R_th = (T_hotspot − T_inlet) / P_stator", "3.4")
Pp("and re-applied with the measured resistance. R_th falls slightly as the temperature rise increases (Rev0 8.93 to "
   "8.20 K/W; Rev1-S 16.1 to 13.2 K/W per stator), so it is interpolated between the solved points in log(ΔT); the "
   "interpolation reproduces every solved point exactly. The winding current I satisfying T = 60 °C then follows from")
EQ("T_amb + R_th(ΔT) · [1.5 · Î² · R(60 °C) / n_st + P_eddy,st] = 60 °C", "3.5")
Pp("In Rev1-S the two series stators carry the same current, and their measured resistances agree within 1.6 %, so the "
   "copper heat is equal. S1, which sits between the stators, runs 2.9 K hotter than S2 in Icepak, so R_th is defined on "
   "the S1 hotspot with half the total heat. The limit is evaluated at 25 and 30 °C ambient under four stated cooling "
   "scenarios (Table 3.3). Lab-PC scripts that re-solve the limit points with the measured heat are provided as a "
   "confirmation step.")
TAB("Table 3.3. Cooling scenarios (R_th per stator at the 60 °C limit, 25 °C ambient).",
    ["Scenario", "Description", "Label", "Rev0 (K/W)", "Rev1-S (K/W)"], [
    ["A", "Icepak, hood fans on, rotor still, hypothetical housing", "THERMAL-FEM", "8.56", "14.76"],
    ["B", "As A with fans off (×1.11, lumped ratio; Icepak at 2 A gives ×1.05-1.07)", "THERMAL-FEM + inferred", "9.51", "16.39"],
    ["C", "Lumped network, rotor turning at 1000 rpm (optimistic; 1000 rpm only)", "THERMAL-LUMPED", "5.07", "8.74"],
    ["D", "Cautious planning basis for the unknown as-built cooling (×1.71 on A)", "ASSUMED", "15.0", "25.3"]],
    [0.7, 3.0, 1.2, 0.7, 0.7])

# ======================================================================= CHAPTER 4
H1("Chapter 4 material: Operating characterisation results")
H2("4.x.1 Motor constants")
TAB("Table 4.1. Comparative constants, original 1 mm-gap geometry.", ["Quantity", "Rev0", "Rev1-S (series)", "Label"], [
    ["Torque coefficient K (T = 1.5·K·Î), mN·m/A", f(k0["K_FEM_mNm_per_A"], 3), f(k1["K_FEM_mNm_per_A"], 2), "FEM"],
    ["K, analytical sheet-current model", f(k0["K_analytical_sheet"], 3), f(k1["K_analytical_sheet"], 2), "ANALYTICAL"],
    ["K, equivalent-coil current sweep", f(k0["K_EQ_sweep"], 2), f(k1["K_EQ_sweep"], 2), "FEM (calibrated)"],
    ["Torque per ampere peak, mN·m/A", f(k0["torque_per_A_pk_mNm"]), f(k1["torque_per_A_pk_mNm"]), "FEM"],
    ["Line back-EMF, V rms per 1000 rpm", f(k0["Ke_line_Vrms_per_krpm"], 3), f(k1["Ke_line_Vrms_per_krpm"], 3), "FEM"],
    ["Back-EMF THD, phase / line, %", "%s / %s" % (f(k0["E_phase_THD_pct"], 1), f(k0["E_line_THD_pct"], 1)),
     "%s / %s" % (f(k1["E_phase_THD_pct"], 1), f(k1["E_line_THD_pct"], 1)), "FEM"],
    ["Phase resistance at 20 °C, Ω", "1.89", "3.78", "MEASURED"],
    ["Synchronous inductance L − M, µH", "33.5-51.2", "74.4-112.6", "FEM (not measured)"],
    ["Motor constant K_m at 25 °C, mN·m/√W", f(k0["Km_mNm_per_sqrtW_25C"]), f(k1["Km_mNm_per_sqrtW_25C"]), "FEM + MEASURED"],
    ["Track eddy loss at 1000 rpm, mW", f(k0["eddy_1000rpm_mW"], 1), f(k1["eddy_1000rpm_mW"], 1), "FEM"],
    ["No-load voltage-limited speed, 12 / 24 V bus, rpm", "%.0f / %.0f" % (float(k0["no_load_speed_12V_rpm"]), float(k0["no_load_speed_24V_rpm"])),
     "%.0f / %.0f" % (float(k1["no_load_speed_12V_rpm"]), float(k1["no_load_speed_24V_rpm"])), "CIRCUIT"]],
    [3.0, 1.0, 1.2, 1.1])
Pp("The independent analytical model reproduces the FEM torque coefficient to within 0.03 % (Rev0) and 0.13 % (Rev1-S). "
   "Rev1-S has 2.13 times the torque per ampere of Rev0 but twice the resistance, so its motor constant K_m is "
   "1.51 times higher.")
H2("4.x.2 Torque against current")
FIG("sweeps/out/P1_torque_vs_current.png", "Fig. 4.1. Electromagnetic torque against phase current at i_d = 0. Lines: "
    "1.5·K·Î with the FEM K; points: FEM equivalent-coil current sweep normalised to K at 1 A; vertical lines: 60 °C "
    "thermal limit for scenarios A (dashed) and D (dotted), 25 °C, 1000 rpm.", 4.6)
Pp("Torque is linear in current to within 0.01 % up to 3 A peak on both machines. The armature field at 1 A is 25 mT "
   "peak (1.3-1.4 mT inside the magnets), and the steel peak flux density is unchanged from 0 to 3 A. Within this "
   "range the current limit is therefore thermal, not magnetic.")
H2("4.x.3 Back-EMF and speed")
FIG("sweeps/out/P2_backemf_waveform_harmonics.png", "Fig. 4.2. Back-EMF at 1000 rpm from the rotating FEM (scaled to "
    "the detailed-copper K): phase and line waveforms, and phase harmonic content.")
FIG("sweeps/out/P3_emf_eddy_vs_speed.png", "Fig. 4.3. Line back-EMF and track eddy loss against speed. The 1000 rpm "
    "point is a FEM solve; the other speeds are exact scaling (e ∝ n, P_eddy ∝ n²) pending the 500 and 2000 rpm FEM checks.")
Pp("The third harmonic (5.2-5.5 %% of the phase EMF) cancels in the star-connected line voltage, leaving a line THD of "
   "0.6-0.7 %%. The track eddy loss rises from %s mW (Rev0) and %s mW (Rev1-S) at 1000 rpm to 326 and 707 mW at "
   "4000 rpm, which is 8 %% (Rev0) and 15 %% (Rev1-S) of the copper loss at the scenario-A thermal current; the eddy drag is 0.78 and 1.69 mN·m."
   % (f(k0["eddy_1000rpm_mW"], 1), f(k1["eddy_1000rpm_mW"], 1)))
H2("4.x.4 Thermal limits")
FIG("thermal/out/T1_hotspot_vs_current.png", "Fig. 4.4. Predicted winding hotspot against current at 1000 rpm and "
    "25 °C ambient, with the measured resistance, for cooling scenarios A-D.")
rows = []
for m in ("Rev0", "Rev1-S"):
    for s in ("A", "B", "C", "D"):
        rows.append([m, s, f(tl(m, s, 25.0, 0), 3) if s != "C" else "-", f(tl(m, s, 25.0, 1000), 3), f(tl(m, s, 30.0, 1000), 3),
                     f(tl(m, s, 25.0, 4000), 3) if s != "C" else "-"])
TAB("Table 4.2. Thermally limited phase current (A peak) for a 60 °C winding, measured resistance.",
    ["Machine", "Scenario", "25 °C, 0 rpm", "25 °C, 1000 rpm", "30 °C, 1000 rpm", "25 °C, 4000 rpm"], rows,
    [1.0, 0.9, 1.1, 1.1, 1.1, 1.1])
Pp("At the same 1 A that the archived Icepak solves applied with the trace-model resistance, the measured resistance "
   "raises the heat from 2.32 to 3.26 W (Rev0) and from 2.42 to 3.51 W per stator (Rev1-S). The predicted hotspot then "
   "rises from 50.3 to 58.2 °C and from 65.7 to 80.6 °C at 30 °C inlet air. The resistance uncertainty "
   "(R_20 = 1.80-1.94 Ω) moves the limit by ±2.5 %, and a 30 °C ambient lowers it by 7-8 %. Stacking two stators raises "
   "R_th per stator by a factor of 1.72, so the thermally limited current of Rev1-S is 24 % lower than that of Rev0.")
H2("4.x.5 DC-bus voltage")
FIG("sweeps/out/P4_vdc_sweep.png", "Fig. 4.5. DC-bus sweep, SVPWM m = 0.95, 25 °C: maximum EM torque at 1000 rpm "
    "(thermal scenarios A and D) and voltage-limited speeds at no load and at the scenario-A thermal current.")
rows = []
for m in ("Rev0", "Rev1-S"):
    for r in E1:
        if r["machine"] == m and r["thermal_scenario"] == "A":
            rows.append([m, "%g" % float(r["Vdc_V"]), "%.0f" % float(r["no_load_speed_rpm"]), f(r["I_max_1000rpm_A"], 3),
                         r["limit_1000rpm"].replace("back-EMF exceeds the bus", "E > bus"), f(r["T_em_max_1000rpm_mNm"], 1),
                         "%.0f" % float(r["corner_speed_at_I_thermal_rpm"])])
TAB("Table 4.3. DC-bus sweep (thermal scenario A, 25 °C, L upper value).",
    ["Machine", "V_dc (V)", "No-load speed (rpm)", "Max Î at 1000 rpm (A)", "Limit", "T_em at 1000 rpm (mN·m)", "Corner speed at thermal Î (rpm)"],
    rows, [0.85, 0.65, 0.95, 1.0, 0.8, 1.0, 1.05])
Pp("Rev0 reaches its thermal current at 1000 rpm from about 8 V upwards. Rev1-S needs at least 12.7 V (scenario D) to "
   "14.3 V (scenario A). On a 12 V bus it is voltage-limited to %s A and %s mN·m at 1000 rpm, and it cannot reach "
   "1000 rpm at all on 6 V. Using the lower inductance changes these currents by less than 0.01 %%, because ω_e·L is only 0.04-0.09 Ω at 1000 rpm against 2-4 Ω of resistance."
   % (f([r for r in E1 if r["machine"] == "Rev1-S" and float(r["Vdc_V"]) == 12 and r["thermal_scenario"] == "A"][0]["I_max_1000rpm_A"], 2),
      f([r for r in E1 if r["machine"] == "Rev1-S" and float(r["Vdc_V"]) == 12 and r["thermal_scenario"] == "A"][0]["T_em_max_1000rpm_mNm"], 1)))
H2("4.x.6 Operating envelopes")
FIG("sweeps/out/P5_torque_speed_envelopes.png", "Fig. 4.6. Continuous electromagnetic torque-speed envelopes at 12 and "
    "24 V bus (25 °C, 60 °C winding; solid: scenario A, dashed: scenario D). Speeds above 4000 rpm lie outside the "
    "verified scaling range; no speed above 1000 rpm is mechanically qualified.")
FIG("sweeps/out/P6_efficiency_maps.png", "Fig. 4.7. Electromagnetic efficiency η_EM (excluding mechanical and inverter "
    "losses) over the voltage-feasible region at the nominal bus, with the scenario-A continuous envelope.")
H2("4.x.7 Proposed conditional operating specifications")
TAB("Table 4.4. Proposed simulation-based operating specifications at 1000 rpm, 25 °C ambient, 60 °C winding, star, "
    "i_d = 0 (D = cautious thermal basis / A = Icepak basis).", ["Item", "Rev0", "Rev1-S (series)", "Label"], [
    ["DC bus", "12 V", "24 V", "ASSUMED"],
    ["Continuous phase current, D / A", "%s / %s A pk" % (f(r0["D_25"]["I_pk"]), f(r0["A_25"]["I_pk"])),
     "%s / %s A pk" % (f(r1["D_25"]["I_pk"]), f(r1["A_25"]["I_pk"])), "thermally inferred"],
    ["Continuous EM torque, D / A", "%s / %s mN·m" % (f(r0["D_25"]["T_em_mNm"], 1), f(r0["A_25"]["T_em_mNm"], 1)),
     "%s / %s mN·m" % (f(r1["D_25"]["T_em_mNm"], 1), f(r1["A_25"]["T_em_mNm"], 1)), "FEM K × current"],
    ["EM output P_out,EM, D / A", "%s / %s W" % (f(r0["D_25"]["P_out_EM_W"]), f(r0["A_25"]["P_out_EM_W"])),
     "%s / %s W" % (f(r1["D_25"]["P_out_EM_W"]), f(r1["A_25"]["P_out_EM_W"])), "CIRCUIT"],
    ["Electrical input to the winding, D / A", "%s / %s W" % (f(r0["D_25"]["P_in_W"]), f(r0["A_25"]["P_in_W"])),
     "%s / %s W" % (f(r1["D_25"]["P_in_W"]), f(r1["A_25"]["P_in_W"])), "CIRCUIT"],
    ["EM efficiency η_EM, D / A", "%.0f / %.0f %%" % (r0["D_25"]["eta_EM_pct"], r0["A_25"]["eta_EM_pct"]),
     "%.0f / %.0f %%" % (r1["D_25"]["eta_EM_pct"], r1["A_25"]["eta_EM_pct"]), "CIRCUIT"],
    ["Terminal line voltage, D / A", "%s / %s V rms" % (f(r0["D_25"]["V_line_rms"]), f(r0["A_25"]["V_line_rms"])),
     "%s / %s V rms" % (f(r1["D_25"]["V_line_rms"]), f(r1["A_25"]["V_line_rms"])), "CIRCUIT"],
    ["Minimum DC bus, D / A", "%s / %s V" % (f(r0["D_25"]["Vdc_req"], 1), f(r0["A_25"]["Vdc_req"], 1)),
     "%s / %s V" % (f(r1["D_25"]["Vdc_req"], 1), f(r1["A_25"]["Vdc_req"], 1)), "CIRCUIT"],
    ["Voltage-limited speed at that current (not a rating)", "%.0f / %.0f rpm" % (r0["D_25"]["corner_rpm_nominal_bus"], r0["A_25"]["corner_rpm_nominal_bus"]),
     "%.0f / %.0f rpm" % (r1["D_25"]["corner_rpm_nominal_bus"], r1["A_25"]["corner_rpm_nominal_bus"]), "CIRCUIT"],
    ["Short-time current from cold (τ = 9.2 min)", "1.5 A ≤ 7.7 min; 2.0 A ≤ 3.6 min", "1.0 A ≤ 11.8 min; 1.5 A ≤ 3.7 min", "indicative"],
    ["Current range of the EM model", "≤ 3 A pk", "≤ 3 A pk", "FEM"]],
    [2.4, 1.45, 1.45, 1.0])
Pp("Shaft torque, shaft power, mechanical efficiency and a validated continuous rating are not available from these "
   "results; they require the measurements listed in Chapter 5.")

# ======================================================================= CHAPTER 5
H1("Chapter 5 material: Discussion")
H2("5.x.1 What the verification establishes")
Pp("Three numerically independent routes agree on the modelled machines. These are the detailed copper FEM, the "
   "analytical model with sheet currents in the real copper islands, and the calibrated equivalent-coil sweep. They "
   "agree to 0.03 % on K for Rev0 and 0.13 % for Rev1-S. The ±I differencing confirms the torque sign and removes a "
   "rotor-side numerical offset. The rotating and static solutions agree point by point within 1.6 % of K. The 5 % "
   "excess of the field-map method is fully explained by the centre-line current routing, not by the field or by "
   "Maxwell. This verification does not establish the real magnet remanence, the assembled gaps or any measured torque. "
   "It shows that the model is solved correctly, not that the model matches the hardware.")
H2("5.x.2 Comparison of Rev0 and Rev1-S")
Pp("Doubling the stator-rotor stages more than doubles the torque per ampere (×2.13), because stator S2 also benefits "
   "from R1's steel backplate (S2 alone is 13 %% stronger than S1). The thermal penalty of stacking, however, is large. "
   "S1 is enclosed between the two rotors, R_th per stator rises by about 1.7 times, and the continuous current falls "
   "from %s to %s A pk (scenario A). The continuous torque gain is therefore ×%.2f rather than ×2.13. Rev1-S also needs "
   "about twice the bus voltage at the same speed: 24 V is required for its thermal current at 1000 rpm, while 12 V "
   "suffices for Rev0. Rev1-S has the higher electromagnetic efficiency at the same speed (%.0f against %.0f %% at 1000 "
   "rpm, scenario A), because its back-EMF is a larger share of the terminal voltage."
   % (f(r0["A_25"]["I_pk"]), f(r1["A_25"]["I_pk"]), r1["A_25"]["T_em_mNm"] / r0["A_25"]["T_em_mNm"],
      r1["A_25"]["eta_EM_pct"], r0["A_25"]["eta_EM_pct"]))
H2("5.x.3 Assumptions that prevent a defensible continuous rating")
Pp("The specifications in Table 4.4 are conditional. Table 5.1 lists, in order of influence, the assumptions that "
   "currently prevent them from being stated as continuous ratings.")
TAB("Table 5.1. Remaining technical assumptions.", ["#", "Assumption", "Effect", "What closes it"], [
    ["1", "Thermal boundary conditions: hypothetical housing, fans, rotor still, radiation off; R_th not measured", "Scenarios A-D span 25-33 % in current", "Heat run on the built motor"],
    ["2", "60 °C winding limit (holder material unconfirmed)", "100 °C would raise the current by about 37 %", "Confirm holder material"],
    ["3", "Resistance measured 2-wire at an unrecorded temperature", "±2.5 % in current", "4-wire measurement with temperature"],
    ["4", "Location of the 36 % excess resistance over the trace model", "Local hotspots may exceed the model", "Thermocouples or thermal imaging at junctions"],
    ["5", "PWM ripple excluded; L simulated, not measured", "+%.0f-%.0f %% (Rev0) and +%.0f-%.0f %% (Rev1-S) copper loss at 50 kHz" % tuple(r0["pwm_extra_cu_loss_pct"] + r1["pwm_extra_cu_loss_pct"]), "Measure L and the ripple; set f_sw or add inductance"],
    ["6", "No mechanical or inverter loss model", "No shaft quantities; η_EM is an upper bound", "No-load drag and power measurements"],
    ["7", "Library magnet properties; nominal gaps", "K ∝ B_r; about 7 % per 0.25 mm of gap", "Open-circuit back-EMF test"],
    ["8", "Rev1-S has no full-motor FEM; ±I check pending", "< 0.5 %", "v12 diagnostic runs"],
    ["9", "Speed scaling from one 1000 rpm solve; eddy formula", "Eddy is 0.5-1 % of the loss at 1000 rpm, 8-15 % at 4000 rpm", "v12 500/2000 rpm runs"],
    ["10", "Thermal time constants from the lumped network only", "Short-time limits are indicative", "Heating curve from the heat run"],
    ["11", "Ambient 25-30 °C; speeds above 1000 rpm not mechanically qualified", "7-8 % per 5 K ambient", "Record ambient; mechanical check"]],
    [0.3, 2.6, 1.8, 1.6])
Pp("The dominant item is the thermal environment. The difference between scenarios A and D, which is the difference "
   "between the modelled hood and an unknown open frame, outweighs every electromagnetic uncertainty by an order of "
   "magnitude. The ripple estimate shows that the drive switching frequency belongs to the motor specification: at "
   "50 kHz without added inductance, the ripple can add a fifth or more to the copper loss, which would lower the "
   "continuous current by roughly a tenth.")
H2("5.x.4 Prototype and outstanding work")
Pp("The specifications apply to the original simulated geometry only. The constructed Rev0 differs in backplate size "
   "and air gap and must be characterised in its own right. The outstanding simulation work is the v12 HPC set "
   "(Rev1-S ±I, 500 and 2000 rpm rotating solves) and, optionally, the Icepak re-solve at the limit points with the "
   "measured heat. Neither is expected to change the specifications by more than about 0.5 %. The outstanding "
   "experimental work, which is postponed, is the open-circuit back-EMF test, the inductance and ripple measurement, the "
   "no-load drag measurement and the heat run.")

json.dump(B, open(os.path.join(HERE, "report_content.json"), "w"), indent=1)
print(len(B), "blocks")
