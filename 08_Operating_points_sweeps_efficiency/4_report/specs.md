# Proposed simulation-based operating specifications (conditional)

Original simulation geometry only (86 mm OD / 19 mm bore / 2 mm backplates, 1.0 mm gaps); star connection; FOC i_d = 0; SVPWM m = 0.95; 1000 rpm target speed. Two thermal bases: **D** = cautious planning basis (assumed R_th 15 / 25.3 K/W per stator) and **A** = Icepak (hypothetical housing, fans on, rotor still). Ambient 25 C, winding limit 60 C. Electromagnetic values only: shaft torque, shaft power, mechanical efficiency and a validated continuous rating are NOT available without measurements.

| Item | Rev0 | Rev1-S (series) | Label |
|---|---|---|---|
| DC bus (nominal) | 12 V | 24 V | assumed (drive) |
| Target speed / electrical frequency | 1000 rpm / 133.3 Hz | 1000 rpm / 133.3 Hz | test plan |
| Line back-EMF | 2.377 V rms per 1000 rpm | 5.066 V rms per 1000 rpm | FEM |
| Continuous phase current, D / A | 0.84 / 1.11 A pk (0.59 / 0.79 A rms) | 0.64 / 0.85 A pk (0.46 / 0.60 A rms) | thermally inferred |
| Same at 30 C ambient, D / A | 0.78 / 1.03 A pk | 0.60 / 0.78 A pk | thermally inferred |
| Continuous EM torque, D / A | 23.3 / 31.0 mN·m | 38.1 / 50.1 mN·m | FEM K x current |
| EM output at 1000 rpm (T_em ω − eddy), D / A | 2.42 / 3.22 W | 3.95 / 5.20 W | circuit model |
| Electrical input to the winding, D / A | 4.76 / 7.31 W | 6.71 / 9.94 W | circuit model |
| EM efficiency (no mechanical / inverter loss), D / A | 51 / 44 % | 59 / 52 % | circuit model |
| Line voltage at the terminals, D / A (60 C) | 4.63 / 5.36 V rms | 8.52 / 9.60 V rms | circuit model |
| Minimum DC bus at 1000 rpm, D / A | 6.9 / 8.0 V | 12.7 / 14.3 V | circuit model |
| Voltage-limited speed at that current, nominal bus, D / A | 2439 / 2133 rpm | 2493 / 2283 rpm | circuit model (not a speed rating) |
| No-load voltage-limited speed, nominal bus | 3391 rpm | 3182 rpm | circuit model |
| Short-time current from cold (τ 9.2 min, conservative) | 1.5 A pk ≤ 7.7 min; 2.0 A pk ≤ 3.6 min | 1.0 A pk ≤ 11.8 min; 1.5 A pk ≤ 3.7 min | thermally inferred, indicative |
| Maximum current of the EM model | 3 A pk (K linear within 0.01 %) | 3 A pk | FEM |
| PWM ripple at 50 kHz (excluded above) | 0.8–1.2 A pk-pk (+8–19 % copper loss) | 0.7–1.1 A pk-pk (+12–27 %) | circuit estimate |

# Remaining assumptions that prevent a defensible continuous rating

| # | Assumption | What is assumed now | Effect on the rating | What would close it |
|---|---|---|---|---|
| 1 | Thermal boundary conditions | Icepak modelled a HYPOTHETICAL acrylic housing in a bench hood with 1 m/s fans, the rotor still and radiation off. The as-built motor runs in an open frame. No thermal resistance has been measured. | Scenario A vs D (1.71 x R_th) moves the continuous current by 25-33 %. | Heat run: constant current to steady state, R_th = dT / P from the resistance rise and thermocouples on S1 boards 1 and 5. |
| 2 | Winding temperature limit | 60 C is a placeholder for the unconfirmed holder material (FR-4 itself and N35 magnets allow more). | 100 C instead of 60 C raises the continuous current by about 37 % (allowed rise x 2.1, less the higher R at 100 C). | Confirm the holder material and its service temperature. |
| 3 | Resistance basis | 1.87-1.90 ohm per stator phase measured 2-wire at an unrecorded temperature; 0-0.1 ohm may be contact resistance. | R20 1.80-1.94 ohm: +/-2.5 % in current. | 4-wire measurement with the temperature recorded. |
| 4 | Heat distribution | The measured R is 36 % above the trace model. Where the extra resistance sits (vias, rim bridges, junctions or tracks) is unknown; Icepak spread the heat over the tracks. | Local hotspots could exceed the modelled hotspot. | Thermal camera / thermocouples at junctions in the heat run. |
| 5 | PWM current ripple | Excluded from all loss and thermal figures (sinusoidal currents assumed). L is small (34-51 uH per stator, simulated, not measured). | At 50 kHz the ripple adds an estimated 8-19 % (Rev0, 12 V) and 12-27 % (Rev1-S, 24 V) to the copper loss at the scenario-A current. | Measure L; measure ripple at low current; choose f_sw or add series inductance. |
| 6 | Mechanical and inverter losses | Bearing, windage and inverter losses are not modelled, so no shaft torque, shaft power or mechanical efficiency is available; eta_EM is an upper bound. | - | No-load drag (FOC current method or spin-down) and input/output power measurement. |
| 7 | Magnet properties and assembly | Br 1.23 T and mu_r 1.0998 are library N35 values; the 1.0 mm gap and 1.02 mm board pitch are nominal. | K scales with Br; about 7 % per extra 0.25 mm of gap. | Open-circuit back-EMF test on the built machine (outside this simulation scope). |
| 8 | Rev1-S electromagnetic reference | No full-motor detailed FEM (job 1486831 lost to the disk quota); K = board-by-board sum, confirmed by the independent sheet-current model (+0.13 %) and the EQ model (-0.17 %). +/-I check in the S2 environment pending (v12). | Small (< 0.5 %). | v12 DIAG_REV1S_S2_B1/B5. |
| 9 | Speed scaling and eddy loss | e ~ n and track eddy ~ n^2 from the single 1000 rpm FEM solve; eddy by the thin-conductor formula on the centre-line field, vias excluded. | Eddy is 0.5-1 % of the loss at 1000 rpm, 8 % (Rev0) / 15 % (Rev1-S) at 4000 rpm. | v12 FMROT 500/2000 rpm. |
| 10 | Transient thermal behaviour | Time constants (9.2 min turning, 24 min stalled) come from the Rev0 lumped network; Icepak was steady-state only; Rev1-S assumed equal (conservative). | Short-time ratings are indicative only. | Heating curve from the heat run. |
| 11 | Ambient and speed | 25 C (and 30 C) still lab air; no rotor stirring credited except scenario C (1000 rpm only). No speed above 1000 rpm is mechanically qualified. | 30 C ambient lowers the current by 7-8 %. | Record ambient; mechanical check before any run above 1000 rpm. |

The constructed Rev0 prototype (4 mm gap, 80 / 25 mm backplates) is a different geometry; none of the values above transfer to it.
