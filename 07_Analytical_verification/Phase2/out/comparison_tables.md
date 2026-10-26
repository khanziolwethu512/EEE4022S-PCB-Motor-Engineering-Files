## 1. Board by board, phase A (mN·m/A)

| Stator, board | Distance from its magnets (mm) | Analytical | FEM field map | FEM detailed | Analytical vs field map | Analytical vs detailed | Field map vs detailed |
|---|---|---|---|---|---|---|---|
| Rev0/Rev1-S S1 B1 | 1.000 | 6.3690 | 6.3697 | 6.2816 | -0.01 % | +1.39 % | +1.40 % |
| Rev0/Rev1-S S1 B2 | 2.020 | 4.8162 | 4.7962 | 4.5905 | +0.42 % | +4.92 % | +4.48 % |
| Rev0/Rev1-S S1 B3 | 3.041 | 3.6111 | 3.5881 | 3.3655 | +0.64 % | +7.30 % | +6.61 % |
| Rev0/Rev1-S S1 B4 | 4.061 | 2.6950 | 2.7268 | 2.4755 | -1.17 % | +8.87 % | +10.15 % |
| Rev0/Rev1-S S1 B5 | 5.081 | 2.0054 | 2.0154 | 1.8266 | -0.50 % | +9.79 % | +10.34 % |
| Rev1-S S2 B1 | 1.000 | 6.6710 | 6.6506 | 6.5593 | +0.31 % | +1.70 % | +1.39 % |
| Rev1-S S2 B2 | 2.020 | 5.1942 | 5.1866 | 4.9382 | +0.15 % | +5.18 % | +5.03 % |
| Rev1-S S2 B3 | 3.041 | 4.0987 | 4.0853 | 3.8115 | +0.33 % | +7.53 % | +7.18 % |
| Rev1-S S2 B4 | 4.061 | 3.3358 | 3.3286 | 3.0572 | +0.22 % | +9.11 % | +8.88 % |
| Rev1-S S2 B5 (next to R1 steel) | 5.081 | 2.8570 | 2.8842 | 2.5965 | -0.94 % | +10.03 % | +11.08 % |

## 2. Stators and machines (mN·m/A; T = 1.5·K·Î)

| Quantity | Analytical | FEM field map | FEM detailed / full motor | Analytical vs field map | Analytical vs detailed |
|---|---|---|---|---|---|
| Rev0 S1 phase A | 19.497 | 19.496 | 18.540 | +0.00 % | +5.16 % |
| Rev0 S1 phase B | 19.501 | 19.453 | — | +0.25 % | — |
| Rev0 S1 phase C | 19.497 | 19.491 | — | +0.03 % | — |
| **Rev0 machine, phase A** | **19.497** | 19.496 | 18.534 (full motor) | +0.00 % | **+5.19 %** |
| **Rev0 machine, phase B** | **19.501** | 19.453 | 18.534 (full motor) | +0.25 % | **+5.22 %** |
| **Rev0 machine, phase C** | **19.497** | 19.491 | 18.534 (full motor) | +0.03 % | **+5.20 %** |
| Rev1-S S1 phase A | 19.497 | 19.501 | 18.540 | -0.02 % | +5.16 % |
| Rev1-S S1 phase B | 19.501 | 19.452 | — | +0.25 % | — |
| Rev1-S S1 phase C | 19.497 | 19.502 | — | -0.03 % | — |
| Rev1-S S2 phase A | 22.157 | 22.135 | 20.963 | +0.10 % | +5.70 % |
| Rev1-S S2 phase B | 22.161 | 22.096 | — | +0.29 % | — |
| Rev1-S S2 phase C | 22.157 | 22.139 | — | +0.08 % | — |
| **Rev1-S machine, phase A** | **41.653** | 41.636 | 39.502 (board sum, phase A) | +0.04 % | **+5.45 %** |
| **Rev1-S machine, phase B** | **41.662** | 41.548 | 39.502 (board sum, phase A) | +0.27 % | **+5.47 %** |
| **Rev1-S machine, phase C** | **41.654** | 41.642 | 39.502 (board sum, phase A) | +0.03 % | **+5.45 %** |

## 3. Phase angle, harmonics and back-EMF at 1000 rpm

| Quantity | Analytical | FEM | Difference |
|---|---|---|---|
| Rev0 ψ phase A (deg elec) | -29.98 | -30.06 (field map), -30.18 (detailed board 1) | +0.08 deg |
| Rev0 phase back-EMF (V rms) | 1.444 | 1.372 (scaled from detailed K) | +5.19 % |
| Rev0 line back-EMF (V rms) | 2.501 | 2.38 (rotating FEM, scaled to detailed K) | +5.07 % |
| Rev0 3rd / 5th / 7th harmonic of phase EMF (%) | 5.79 / 0.64 / 0.14 | 5.5 / 0.7 / 0.1 (rotating FEM) | |
| Rev1-S ψ phase A (deg elec) | -29.99 | -30.08 (field map), -30.18 (detailed board 1) | +0.09 deg |
| Rev1-S phase back-EMF (V rms) | 3.084 | 2.925 (scaled from detailed K) | +5.45 % |
| Rev1-S line back-EMF (V rms) | 5.342 | 5.07 (rotating FEM, scaled to detailed K) | +5.37 % |
| Rev1-S 3rd / 5th / 7th harmonic of phase EMF (%) | 5.43 / 0.60 / 0.13 | — | |

## 4. Sensitivity of the analytical machine K (phase A)

| Case | Rev0 K | change | Rev1-S K | change |
|---|---|---|---|---|
| primary | 19.497 | +0.00 % | 41.653 | +0.00 % |
| width-averaged conductors | 19.483 | -0.07 % | 41.625 | -0.07 % |
| no recoil correction (mu_r = 1) | 20.539 | +5.34 % | 43.834 | +5.23 % |
| no steel (air only) | 12.250 | -37.17 % | 24.499 | -41.18 % |
| 32 rotor angles | 19.498 | +0.01 % | — | — |
| images n = 2 | — | — | 41.650 | -0.01 % |
| images n = 6 | — | — | 41.654 | +0.00 % |
| Br = 1.17 T (N35 range; K ∝ Br) | 18.546 | -4.88 % | 39.622 | -4.88 % |
| Br = 1.21 T (N35 range; K ∝ Br) | 19.180 | -1.63 % | 40.976 | -1.63 % |

Recoil correction: N_z = 0.536 (R1 on its plate), 0.515 (R2 between two plates); M_eff/M = 0.9493, 0.9511.
