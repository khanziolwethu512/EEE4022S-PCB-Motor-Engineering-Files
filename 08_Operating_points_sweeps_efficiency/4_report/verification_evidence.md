# Verification evidence (Gate 1 and cross-checks)

Each row compares two routes that do not share the quantity being checked. Labels: FEM (Maxwell), ANALYTICAL
(no Maxwell input), FEM (calibrated) (equivalent-coil model calibrated on FEM), CIRCUIT. Source IDs refer to the
provenance inventory.

| # | Check | Route 1 | Route 2 | Difference | Status |
|---|---|---|---|---|---|
| 1 | Rev0 machine K | Full detailed motor FEM 18.534 mN·m/A (S01, job 1470376) | Analytical field + 2D sheet currents 18.539 (S12) | +0.03 % | PASS |
| 2 | Rev0 machine K | Full detailed motor FEM 18.534 | Detailed single-board sum 18.540 (S03) | +0.03 % | PASS |
| 3 | Rev0 machine K | Full detailed motor FEM 18.534 | EQ current sweep at 1 A, exact per-board correction 18.52 (S08) | −0.08 % | PASS (calibrated, not independent) |
| 4 | Rev1-S machine K | Board-sum FEM 39.50 (S03 + S04) | Analytical sheet currents 39.55 (S12) | +0.13 % | PASS |
| 5 | Rev1-S S2 stator K | Board-sum FEM 20.963 | Analytical sheet currents 21.011 | +0.23 % | PASS |
| 6 | Board 1 (1.000 mm), Rev0 | Detailed FEM copper 6.2818 | Sheet currents 6.2814 | −0.01 % | PASS |
| 7 | Board 5 (5.081 mm), Rev0 | Detailed FEM copper 1.8264 | Sheet currents 1.8262 | −0.01 % | PASS |
| 8 | Torque sign / numerical offset, Rev0 (V2) | Copper Lorentz (+I − −I)/2: 6.2818 / 1.8264 | Rotor virtual work (+I − −I)/2: 6.2777 / 1.8342 (jobs 1517777 / 1517602) | −0.07 % / +0.43 % | PASS |
| 9 | Magnet field at the tracks | Field of the detailed model on the centre-lines (filament 6.3618 / 2.0029) | Field map 6.3697 / 2.0154; analytical 6.3690 / 2.0054 | ≤ 0.7 % | PASS |
| 10 | Field-map +5 % gap | Centre-line network current routing | Real copper sheet currents | closes 1.4–10 % per board to 0.02 % | RESOLVED |
| 11 | Rotating vs static (Rev0) | FMROT 1000 rpm, 120 board-phase-angle points (job 1500352) | Static field map | ≤ 1.49 % of K1 | PASS |
| 12 | Rotating vs static (Rev1-S) | FMROT 1000 rpm, 240 points | Static field map | ≤ 1.59 % of K1 | PASS |
| 13 | Series polarity, Rev1-S | S1 ψ −29.98° | S2 ψ −30.00° | 0.02° | PASS (additive) |
| 14 | Phase balance / sequence | ψ_A −30.0°, ψ_B +90.0°, ψ_C −150.0° | 120.0° steps, K spread ≤ 0.04 % | — | PASS |
| 15 | Torque linearity (C1) | K at 0.5 A | K at 3 A (EQ sweep, jobs 1504750 / 1504792) | +0.008 % / +0.004 % | PASS |
| 16 | Armature reaction | Armature field at 1 A: 25 mT peak, 1.3–1.4 mT in the magnets | Steel peak 1.432 → 1.431 T from 0 to 3 A | negligible | PASS |
| 17 | Rotor vs coil torque (EQ) | Virtual work on the rotor | Coil Lorentz torque | Rev0 ≤ 0.4 %, Rev1-S ≤ 1.7 % | PASS |
| 18 | Field weakening | Characteristic current ψ/L | 44–45 A pk vs ≤ 3 A operating range | — | i_d = 0 is the only useful strategy |
| 19 | Rev1-S ±I in the S2 environment (V2) | — | v12 DIAG_REV1S_S2_B1 / B5 | — | PENDING (HPC) |
| 20 | Speed scaling (S1) | 1000 rpm FEM | v12 FMROT 500 / 2000 rpm | — | PENDING (HPC) |
| 21 | Thermal interpolation | R_th(dT) interpolation | Reproduces every solved Icepak fans-on point exactly; RUN2 scripts re-solve the limit points with the measured heat | — | Lab-PC confirmation optional |

Acceptance criteria for the pending runs were fixed before the runs (HPC_RUN_STEPS_v12.txt): DIAG copper ±I within
1 % of the archived and sheet-current values; FMROT K1 within 0.5 % of 1000 rpm, E/rpm constant within 0.5 %, eddy
within 5 % of the n² law.

What the verification does NOT establish: actual magnet remanence, assembly tolerances, the real thermal
environment, or any measured torque. It shows that three independent numerical routes agree on the modelled geometry.
