"""Report-ready material (Chapters 3, 4, 5, 7) for the Rev0 as-built study. Numbers from out/asbuilt_summary.json and
the HPC fieldmap summaries; rendered by ../finalop/report/render.js. python content_asbuilt.py -> asbuilt_content.json"""
import json, math, os
HERE = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(HERE, "out", "asbuilt_summary.json")))
C = dict((r["case"], r) for r in S["cases"])
an = S["analytical_independent"]
chk = S["detailed_checks"]
f = lambda x, n=3: ("%%.%df" % n) % x
K_A_REF = 18.534
e = lambda K, n: math.sqrt(3) * K * 1e-3 * n * 2 * math.pi / 60 / math.sqrt(2)
B = []
H1 = lambda t: B.append({"t": "h1", "x": t})
H2 = lambda t: B.append({"t": "h2", "x": t})
Pp = lambda t: B.append({"t": "p", "x": t})
EQ = lambda t, n: B.append({"t": "eq", "x": t, "n": n})
NOTE = lambda t: B.append({"t": "note", "x": t})


def TAB(cap, head, rows, w):
    B.append({"t": "table", "cap": cap, "head": head, "rows": rows, "w": w})


def FIG(p, cap, w=4.8):
    B.append({"t": "fig", "path": os.path.join(HERE, "out", p), "cap": cap, "w": w})


KB, KC = C["B"]["K_mNm_per_A"], C["C"]["K_mNm_per_A"]
K35, K45 = C["C350"]["K_mNm_per_A"], C["C450"]["K_mNm_per_A"]
band = S["uncertainty"]["E_LL_100rpm"]
c1, c5 = chk[0], chk[1]
d_rot = [100 * (c["detailed_rotor"] / c["detailed_copper"] - 1) for c in chk]
d_an = [100 * (c1["detailed_copper"] / 2.5206 - 1), 100 * (c5["detailed_copper"] / 0.7607 - 1)]
diag_txt = ("The detailed-copper boards of Case C (jobs 1526907/1526908; one real-copper board at the board-1 and board-5 "
            "positions, ±1 A) close the verification. In both, the copper Lorentz torque and the rotor virtual-work torque "
            "agree (%+.2f %% and %+.2f %%), and the copper result agrees with the independent analytical sheet-current "
            "value (%+.2f %% and %+.2f %%), confirming the sheet-current correction at 4.0 and 8.1 mm. The corrected field "
            "map agrees with the detailed copper at board 5 (%+.2f %%) but is %.2f %% low at board 1, outside the 1 %% "
            "criterion. The cause is the field map's flux density, not the correction: on the centre-line basis board 1 "
            "of the field map is 1.2 %% below both the detailed model's own magnet field (2.710 against 2.743 mN·m/A) and "
            "the analytical value. Per board the field map scatters by −1.2 to +3.4 %% about the analytical centre-line "
            "values (mesh resolution of the five-board region at a 4 mm gap), but these deviations cancel in the sum "
            "(+0.12 %% and +0.21 %% for the whole stack in Cases B and C). Substituting the two detailed boards for their field-map values "
            "would raise K for Case C from %s to %s mN·m/A (%+.2f %%, +0.5 mV at 100 rpm). The as-built K is therefore "
            "taken as %s mN·m/A with a method uncertainty of about ±0.5 %%, which is small against the gap and remanence "
            "band of Fig. 4.D." % (d_rot[0], d_rot[1], d_an[0], d_an[1], c5["diff_pct"], -c1["diff_pct"],
                                    f(KC), f(KC + c1["detailed_copper"] - c1["fieldmap_x_ratio"] + c5["detailed_copper"] - c5["fieldmap_x_ratio"]),
                                    100 * (c1["detailed_copper"] - c1["fieldmap_x_ratio"] + c5["detailed_copper"] - c5["fieldmap_x_ratio"]) / KC,
                                    f(KC)))

NOTE("Supplementary as-built material. It supports the experimental validation of Rev0 and does not change the main "
     "Rev0 versus Rev1-S comparison, which uses the nominal 1 mm geometry throughout. Numbering is local.")

H1("Chapter 3 material: As-built geometry modelling")
Pp("The manufactured Rev0 differs from the simulated design in two respects that affect the magnetic field at the "
   "winding: the magnet-to-board gap is approximately 4.0 mm rather than 1.0 mm, and the rotor uses an 80 mm OD, "
   "25 mm bore, 2 mm ferromagnetic steel backplate instead of the 86/19 mm plate with a 19 mm steel shaft. Three cases "
   "separate the two effects (Table 3.A). Every other quantity (magnets, magnet radius, boards, layers, connection) is "
   "unchanged.")
Pp("The prototype photographs show how the manufactured machine is supported. The central shaft/support tube, the hub "
   "ring that locates the backplate on it, the bore ring on the magnet face and the end plates that carry the stator "
   "stack are 3D-printed PLA. PLA is non-magnetic and practically non-conducting, so it is represented as air "
   "(μr ≈ 1, σ ≈ 0). It is distinct from the metallic parts of the assembly: the backplate, which remains "
   "ferromagnetic steel and is modelled; the steel screws and nuts that fix the backplate to the PLA hub (a ring at "
   "r ≈ 12-14 mm, inside the magnet ring) and at the rim; and the threaded rods and nuts that clamp the stator stack "
   "outside the active winding region. These fasteners are small, lie outside the magnet track (r = 18-38 mm), and "
   "are not modelled; their effect is expected to be minor but has not been quantified. The dynamometer shaft and "
   "coupling are outside the model region.")
Pp("The solved Case C geometry contains an 8 mm steel shaft at r ≤ 4 mm, separate from the backplate, with the hub "
   "region as air. The manufactured support at that position is PLA, i.e. the model holds slightly more steel than "
   "the prototype. Because the whole change from the nominal to the as-built rotor (plate size, bore and shaft "
   "together) alters K by only +0.09 % (Chapter 4), a PLA shaft in place of the 8 mm steel one cannot change the "
   "result measurably, and no separate PLA-shaft solution was run. Case C is therefore taken as the as-built model.")
TAB("Table 3.A. Rev0 cases of the as-built study.", ["Case", "Gap (mm)", "Backplate OD / ID (mm)", "Shaft", "Purpose"], [
    ["A nominal", "1.0", "86 / 19", "19 mm steel, fills bore", "Reference (reused, not re-solved)"],
    ["B gap only", "4.0", "86 / 19", "19 mm steel, fills bore", "Isolates the gap"],
    ["C as built", "4.0", "80 / 25 (steel)", "8 mm steel modelled (bounds the PLA support); PLA hub = air", "Adds the manufactured rotor"],
    ["C, gap band", "3.5 and 4.5", "80 / 25", "as C", "Gap uncertainty"]], [1.0, 0.8, 1.3, 1.6, 1.6])
Pp("Each case was solved with the field-only Maxwell model used for the nominal machine: magnets, steel and air are "
   "meshed (20 mm region padding, four adaptive passes), the copper is not, and the magnetic flux density is exported "
   "on the centre-lines of every track of the five boards at twelve rotor positions spanning half an electrical "
   "period (1.875° steps; the second half follows from half-wave antisymmetry). The same run gives the back-EMF "
   "waveform and harmonics, the track eddy loss and flux-density maps 0.25 mm from the board-1 face, at the "
   "mid-planes of boards 1, 3 and 5 and in the backplate. The method was first applied to the nominal geometry "
   "(Case A), where it reproduced the archived rotating solution: K 19.478 against 19.470 mN·m/A on the centre-line "
   "basis, phase back-EMF 1.4423 against 1.4418 V rms at 1000 rpm, third harmonic 5.5 %, ripple 1.30 against 1.26 %.")
Pp("Centre-line integration over-predicts the torque of the real copper by a distance-dependent amount (1.4-10 % per "
   "board at the nominal positions) because the current spreads across the copper islands. Each board's field-map "
   "value was therefore multiplied by the ratio of the sheet-current to the centre-line torque computed for the same "
   "distance with the independent analytical model:")
EQ("K = Σ_k K_FM,k · [K_sheet(d_k) / K_cl(d_k)],   d_k = g + (k − 1)·1.0203 mm", "3.A")
Pp("Applied to Case A this gives %s mN·m/A, %+.2f %% from the full-motor detailed FEM (18.534). The ratio is 0.91-0.92 "
   "at every board position of the 4 mm cases. The analytical model treats the backplate as an infinite steel plane "
   "and so cannot represent the 80/25 mm plate; that effect is taken from the field maps alone." %
   (f(C["A"]["K_mNm_per_A"]), C["A"]["dK_vs_A_ref18534_pct"]))
Pp("Before any of these solutions, and without reference to the bench measurement, the analytical model predicted "
   "K = %s mN·m/A at a 4.0 mm gap (%s / %s mN·m/A at 3.5 / 4.5 mm). The geometry of every case was checked in the "
   "build logs (gap, plate size, bore, shaft, no additional steel), all phase angles are within 0.3° of −30° and the "
   "phase steps are 120.0°, confirming polarity and rotor coordinates. Back-EMF at 50, 100 and 150 rpm is obtained "
   "as e = K·ω_m from the position-dependent solution (verified at 500, 1000 and 2000 rpm for the nominal machine); "
   "these are speed-scaled values, not separate transient solutions." % (f(an["gap_4.00"]), f(an["gap_3.50"]), f(an["gap_4.50"])))

H1("Chapter 4 material: Nominal, gap-only and as-built Rev0")
rows = []
for k, lab in (("A", "A nominal"), ("B", "B gap only"), ("C", "C as built"), ("C350", "C, 3.5 mm"), ("C450", "C, 4.5 mm")):
    r = C[k]
    K = K_A_REF if k == "A" else r["K_mNm_per_A"]
    rows.append([lab, f(K), "-" if k == "A" else "%+.1f" % (100 * (K / K_A_REF - 1)), "%.2f" % (1.5 * K),
                 "%.3f" % (K / 8), "%.1f / %.1f / %.1f" % (1e3 * e(K, 50), 1e3 * e(K, 100), 1e3 * e(K, 150)),
                 "%.3f" % e(K, 1000), "%.1f / %.2f" % (r["THD_phase_pct"], r["THD_line_pct"])])
TAB("Table 4.A. Rev0 electromagnetic coefficients (FEM field map, sheet-current corrected; Case A = full-motor FEM). "
    "Electrical frequency 6.67 / 13.33 / 20.0 / 133.3 Hz at 50 / 100 / 150 / 1000 rpm.",
    ["Case", "K (mN·m/A)", "vs A (%)", "T per A pk (mN·m)", "ψ_pm (mWb)", "E_LL 50/100/150 rpm (mV rms)",
     "E_LL 1000 rpm (V rms)", "THD phase / line (%)"], rows, [0.9, 0.7, 0.55, 0.7, 0.65, 1.3, 0.75, 0.8])
FIG("X2_K_vs_gap.png", "Fig. 4.A. Torque coefficient against gap: field maps (corrected) and the independent analytical "
    "prediction made before the field maps were solved.")
Pp("Increasing the gap from 1.0 to 4.0 mm lowers K by %.1f %% (Case B). Changing the rotor to the manufactured 80/25 mm "
   "steel backplate (with the PLA support represented as air and an 8 mm steel shaft) changes K by a further %+.2f %%, which is within the numerical scatter of the method: "
   "the magnets occupy r = 18-38 mm, inside both plates, and the plate carries at most 0.92-0.95 T, so neither its outer "
   "diameter nor its bore affects the field at the winding. The as-built prediction is therefore governed by the gap "
   "alone. Over the 3.5-4.5 mm band K varies from %s to %s mN·m/A (+%.0f / −%.0f %%), about 30 %% per millimetre." %
   (-S["contributions"]["gap_effect_B_over_A_pct"], S["contributions"]["rotor_effect_C_over_B_pct"], f(K35), f(K45),
    100 * (K35 / KC - 1), 100 * (1 - K45 / KC)))
FIG("X3_board_contributions.png", "Fig. 4.B. Board-by-board contribution to K. At 4 mm the field decays more slowly "
    "relative to its value at board 1, so the boards share the torque more evenly.")
Pp("The larger gap also filters the field: higher spatial harmonics decay faster with distance, so the phase back-EMF "
   "THD falls from 5.6 %% (Case A) to %.1f %% (Case C) and the line THD from 0.68 %% to %.2f %%. The peak axial flux "
   "density 0.25 mm from the board-1 face falls from 0.38 T to 0.16 T, and at the board-5 mid-plane from 0.084 T to "
   "0.040 T (Fig. 4.C). The track eddy loss at 1000 rpm falls from about 21 mW to %.1f mW." %
   (C["C"]["THD_phase_pct"], C["C"]["THD_line_pct"], C["C"]["eddy_1000rpm_mW"]))
FIG("X5_Bz_radial.png", "Fig. 4.C. Peak axial flux density against radius, 0.25 mm from the board-1 face and at the "
    "board-5 mid-plane (rotor at 0°).")
FIG("X1_backemf_vs_speed.png", "Fig. 4.D. Predicted open-circuit line back-EMF of the as-built Rev0 (Case B lies under "
    "Case C), with the band for a 3.5-4.5 mm gap and N35 remanence 1.17-1.22 T, and the preliminary bench value at "
    "100 rpm, which was not used in the model.")
TAB("Table 4.B. Model checks.", ["Check", "Result", "Criterion"], [
    ["Case A: corrected field map vs full-motor detailed FEM", "%+.2f %%" % C["A"]["dK_vs_A_ref18534_pct"], "±0.5 %"],
    ["Case A: method vs archived rotating solution (K, E, H3, ripple)", "+0.04 %, +0.03 %, 5.5 %, 1.30 %", "0.5 % / 0.3 pt / 0.2 pt"],
    ["Case A: static-field eddy loss vs rotating solution", "21.6 vs 20.35 mW (+6.2 %)", "5 % (not met; loss only)"],
    ["Case B: field map vs analytical, centre-line basis", "8.270 vs 8.260 (+0.12 %)", "-"],
    ["Case B: corrected vs analytical sheet-current", "%s vs %s (%+.2f %%)" % (f(KB), f(an["gap_4.00"]), 100 * (KB / an["gap_4.00"] - 1)), "-"],
    ["Polarity / phase", "ψ −29.80 to −30.29°, steps 120.0°", "±1°"],
    ["Case C detailed boards 1 / 5: copper vs rotor virtual work", "%+.2f %% / %+.2f %%" % tuple(d_rot), "±3 %"],
    ["Case C detailed boards 1 / 5: copper vs analytical sheet-current", "%+.2f %% / %+.2f %%" % tuple(d_an), "-"],
    ["Case C boards 1 / 5: corrected field map vs detailed copper", "%+.2f %% / %+.2f %%" % (c1["diff_pct"], c5["diff_pct"]), "±1 % (board 1 not met)"]],
    [3.0, 2.0, 1.3])
Pp(diag_txt)

H1("Chapter 5 material: Air-gap sensitivity and the as-built prototype")
Pp("For this coreless winding the gap is the only geometric quantity of consequence. The field above a single-sided "
   "magnet array decays approximately as exp(−πz/τ) with the pole pitch τ, giving about 0.30 /mm here, so every "
   "additional millimetre of gap costs roughly a quarter of the torque coefficient. The manufactured backplate size "
   "and the shaft have no measurable effect. A gap of 4 mm instead of 1 mm therefore reduces the torque per "
   "ampere and the back-EMF of the prototype to 41 % of the design value; for the same torque the prototype needs "
   "2.45 times the current and dissipates six times the copper loss, so the simulated thermal limits of the nominal "
   "machine do not apply to it.")
Pp("At 100 rpm the as-built model predicts %.1f mV rms line-to-line (band %.1f-%.1f mV for a 3.5-4.5 mm gap and "
   "N35 remanence 1.17-1.22 T). The preliminary measurement of about 96 mV lies within 1 %% of the central value. "
   "Because remanence and gap act on the same quantity, the measurement alone cannot separate them: with the library "
   "remanence of 1.23 T it corresponds to an effective gap of 4.03 mm, and with 1.17 T to 3.86 mm. The agreement is "
   "therefore consistent with the model and the measured geometry, but it is not yet an independent validation: the "
   "measurement is preliminary, and the gap must be measured directly before the comparison can be used to infer "
   "either quantity." % (1e3 * band[0], 1e3 * band[1], 1e3 * band[2]))
Pp("The support arrangement bears directly on that gap. In the prototype the rotor is carried on a PLA tube and hub "
   "and the stator stack on PLA end plates clamped by threaded rods, without a bearing that locates the rotor axially "
   "or radially in the machine itself. The gap is therefore set by assembly rather than by a machined datum, and it "
   "can differ around the rotor (tilt and face run-out) and change during a test: PLA is compliant, creeps under "
   "sustained load and softens well below the temperatures a loaded winding can reach (its glass transition is "
   "around 55-60 °C), while the threaded-rod stack can shift if a nut loosens. Because K falls by about 30 % per "
   "millimetre of gap, a few tenths of a millimetre of movement is enough to change the back-EMF and torque per "
   "ampere by several per cent. This does not affect the electromagnetic model, in which the PLA parts are "
   "non-magnetic as in the real machine, but it limits how precisely a bench result can be compared with it and "
   "is the main reason the gap must be measured at the time of each test.")

H1("Chapter 7 material: Mechanical improvements and simulation-matched testing")
Pp("Recommendations for the mechanical design:")
for t in ("Set the magnet-to-board gap mechanically, not by assembly: a machined spacer or shim stack between the stator "
          "holder and a shaft shoulder, with a target of 1.0-1.5 mm. Recovering 2.5-3 mm of gap roughly doubles the "
          "torque per ampere and the back-EMF at no cost in copper.",
          "Control axial play and run-out: bearing preload or a locating collar so that the rotor cannot move towards the "
          "stator; measure face run-out of the backplate, because the minimum gap, not the mean, limits how close the "
          "rotor can be set.",
          "Replace the PLA support with a rigid, accurately aligned, bearing-supported assembly for future controlled "
          "testing: a metal shaft running in a pair of preloaded bearings housed in a stiff frame that also locates "
          "the stator, so that the shaft axis is square to the boards and concentric with the winding and the gap is "
          "fixed by machined faces rather than by the printed parts. A steel shaft does not degrade the machine: "
          "Case C includes an 8 mm steel shaft and the as-built rotor changes K by less than 0.1 %.",
          "Retain the rotor positively on the shaft: a keyed or clamped hub (or set screws on a flat) for torque, and "
          "a shoulder with a locking collar or circlip for axial position, so that the rotor cannot slip under "
          "dynamometer torque or be drawn towards the stator by the magnet attraction.",
          "Keep the 80/25 mm steel backplate: the simulations show its size and bore do not reduce performance."):
    Pp("• " + t)
Pp("Recommended test sequence matched to the simulations:")
for t in ("Measure the gap with feeler gauges at four or more positions around the rotor, and the face run-out, before testing.",
          "Open-circuit back-EMF at 50, 100 and 150 rpm with the drive disconnected: line-to-line rms and waveform, speed "
          "confirmed from the electrical frequency (6.67, 13.33, 20.0 Hz). Expected for a 4.0 mm gap: 48, 97 and 145 mV "
          "rms, nearly sinusoidal (line THD about 0.1 %).",
          "Compute K_exp = √2·E_LL / (√3·ω_m) and compare with K(g) at the measured gap; the remaining difference is a "
          "measure of the magnet remanence.",
          "Torque against current at low current with the dynamometer: expected 11.3 mN·m per A peak at 4 mm. Limit "
          "the current to the thermal capability of the prototype, which is lower in torque terms than the nominal design "
          "by the factor 0.41.",
          "Repeat after reducing the gap to confirm the predicted exponential dependence."):
    Pp("• " + t)

json.dump(B, open(os.path.join(HERE, "asbuilt_content.json"), "w"), indent=1)
print(len(B), "blocks")
