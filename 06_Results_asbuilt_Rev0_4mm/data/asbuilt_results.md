# Rev0 as-built study - results

| Case | K (mN·m/A) | vs A | T per A pk (mN·m) | E_LL 50 / 100 / 150 rpm (mV rms) | E_LL 1000 rpm (V rms) | THD ph / line (%) |
|---|---|---|---|---|---|---|
| A nominal (1 mm, 86/19) | 18.514 | +0.0 % | 27.77 | 118.7 / 237.5 / 356.2 | 2.3745 | 5.6 / 0.68 |
| B gap only (4 mm, 86/19) | 7.547 | -59.2 % | 11.32 | 48.4 / 96.8 / 145.2 | 0.9679 | 1.1 / 0.08 |
| C as built (4 mm, 80/25, 8 mm shaft) | 7.554 | -59.2 % | 11.33 | 48.4 / 96.9 / 145.3 | 0.9688 | 1.0 / 0.11 |
| C at 3.5 mm | 8.754 | -52.7 % | 13.13 | 56.1 / 112.3 / 168.4 | 1.1227 | 1.4 / 0.09 |
| C at 4.5 mm | 6.518 | -64.8 % | 9.78 | 41.8 / 83.6 / 125.4 | 0.8360 | 0.9 / 0.11 |

Contributions: gap 1 -> 4 mm -59.2 %; manufactured rotor (80/25 plate, 8 mm shaft) +0.1 %; total -59.2 %
Case C at 100 rpm: 96.9 mV rms (band 79.5-111.4 mV for gap 3.5-4.5 mm and Br 1.17-1.22 T); preliminary measurement 96 mV (not used for calibration)
Detailed-copper check C_B1 (4.000 mm): detailed 2.5270, rotor 2.5273, field map x ratio 2.4908 mN.m/A (-1.43 %)
Detailed-copper check C_B5 (8.081 mm): detailed 0.7643, rotor 0.7741, field map x ratio 0.7607 mN.m/A (-0.48 %)
Method check, Case A: field map x ratio 18.514 vs full-motor detailed FEM 18.534 (-0.11 %)

Back-EMF values are speed-scaled from the position-dependent field solution (e = K w_m), not separate transient solutions. Electrical frequency f = n/60 x 8.
