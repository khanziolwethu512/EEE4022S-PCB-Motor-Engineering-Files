# Operating sweeps and envelopes (Gate 3) - circuit model on verified FEM / measured inputs

## Comparative constants

| Quantity | Rev0 | Rev1-S (series) | Evidence |
|---|---|---|---|
| K (mN·m/A), T = 1.5 K Î | 18.534 | 39.500 | FEM |
| K, analytical sheet-current | 18.539 | 39.550 | ANALYTICAL |
| K, equivalent-coil sweep | 18.52 | 39.43 | FEM (calibrated) |
| Torque per A pk (mN·m) | 27.80 | 59.25 | FEM |
| Line back-EMF (V rms per 1000 rpm) | 2.377 | 5.066 | FEM |
| Back-EMF THD phase / line (%) | 5.5 / 0.7 | 5.2 / 0.6 | FEM |
| Phase resistance, 20 °C (Ω) | 1.89 | 3.78 | MEASURED |
| Phase inductance L−M (µH) | 33.5–51.2 | 74.4–112.6 | FEM (not measured) |
| Characteristic current ψ/L (A pk) | 45 | 44 | CIRCUIT |
| Motor constant K_m at 25 °C (mN·m/√W) | 16.35 | 24.64 | FEM + MEASURED |
| Track eddy loss at 1000 rpm (mW) | 20.4 | 44.2 | FEM-post |
| Thermal current, scenario A, 25 °C, 1000 rpm (A pk) | 1.113 | 0.846 | THERMAL-FEM |
| Thermal current, scenario D (A pk) | 0.840 | 0.644 | ASSUMED R_th |
| EM torque at those currents (mN·m) | 31.0 (A) / 23.3 (D) | 50.1 (A) / 38.1 (D) | CIRCUIT |
| No-load speed 12 / 24 V bus (rpm) | 3391 / 6782 | 1591 / 3182 | CIRCUIT |

## C1 - current sweep at 1000 rpm, 25 °C (scenario A thermal; L upper)

| Machine | I pk (A) | T_em FEM (mN·m) | T_em analytical (mN·m) | Winding A / D (°C) | Bus needed (V) | η_EM (%) |
|---|---|---|---|---|---|---|
| Rev0 | 0.00 | 0.00 | 0.00 | 25 / 25 | 3.54 | 0 |
| Rev0 | 0.25 | 6.95 | 6.95 | 27 / 28 | 4.42 | 78 |
| Rev0 | 0.50 | 13.90 | 13.90 | 32 / 37 | 5.34 | 65 |
| Rev0 | 0.75 | 20.85 | 20.86 | 40 / 52 | 6.33 | 55 |
| Rev0 | 1.00 | 27.80 | 27.81 | 53 / 77 | 7.43 | 47 |
| Rev0 | 1.50 | 41.70 | 41.71 | 94 / 182 | 10.20 | 35 |
| Rev0 | 2.00 | 55.60 | 55.62 | 175 / >200 | 14.62 | 24 |
| Rev0 | 3.00 | 83.41 | 83.43 | >200 / >200 | 37.44 | 9 |
| Rev1-S | 0.00 | 0.00 | 0.00 | 25 / 26 | 7.54 | 0 |
| Rev1-S | 0.25 | 14.81 | 14.83 | 28 / 30 | 9.32 | 79 |
| Rev1-S | 0.50 | 29.62 | 29.66 | 37 / 45 | 11.22 | 66 |
| Rev1-S | 0.75 | 44.44 | 44.49 | 52 / 75 | 13.36 | 56 |
| Rev1-S | 1.00 | 59.25 | 59.33 | 75 / 128 | 15.93 | 47 |
| Rev1-S | 1.50 | 88.88 | 88.99 | 158 / >200 | 23.50 | 32 |
| Rev1-S | 2.00 | 118.50 | 118.65 | >200 / >200 | 41.63 | 18 |
| Rev1-S | 3.00 | 177.76 | 177.98 | >200 / >200 | 75.35 | 10 |

Winding temperatures above 200 C are outside the thermal model (no steady state below the 600 C cap); they mark currents that are not continuous.

## E1 - DC-bus sweep (25 °C)

| Machine | Vdc (V) | Thermal | No-load speed (rpm) | Max I at 1000 rpm (A pk) | Limited by | T_em at 1000 rpm (mN·m) | Corner speed at thermal I (rpm) | Bus use at thermal I, 1000 rpm |
|---|---|---|---|---|---|---|---|---|
| Rev0 | 6 | A | 1696 | 0.669 | voltage | 18.6 | 442 | 133 % |
| Rev0 | 6 | D | 1696 | 0.650 | voltage | 18.1 | 750 | 115 % |
| Rev0 | 9 | A | 2543 | 1.113 | thermal | 31.0 | 1288 | 89 % |
| Rev0 | 9 | D | 2543 | 0.840 | thermal | 23.3 | 1595 | 77 % |
| Rev0 | 12 | A | 3391 | 1.113 | thermal | 31.0 | 2133 | 66 % |
| Rev0 | 12 | D | 3391 | 0.840 | thermal | 23.3 | 2439 | 57 % |
| Rev0 | 15 | A | 4239 | 1.113 | thermal | 31.0 | 2977 | 53 % |
| Rev0 | 15 | D | 4239 | 0.840 | thermal | 23.3 | 3281 | 46 % |
| Rev0 | 18 | A | 5087 | 1.113 | thermal | 31.0 | 3820 | 44 % |
| Rev0 | 18 | D | 5087 | 0.840 | thermal | 23.3 | 4122 | 38 % |
| Rev0 | 24 | A | 6782 | 1.113 | thermal | 31.0 | 5503 | 33 % |
| Rev0 | 24 | D | 6782 | 0.840 | thermal | 23.3 | 5799 | 29 % |
| Rev1-S | 6 | A | 796 | 0.000 | back-EMF exceeds the bus | 0.0 | 0 | 238 % |
| Rev1-S | 6 | D | 796 | 0.000 | back-EMF exceeds the bus | 0.0 | 116 | 211 % |
| Rev1-S | 9 | A | 1193 | 0.206 | voltage | 12.2 | 300 | 159 % |
| Rev1-S | 9 | D | 1193 | 0.205 | voltage | 12.1 | 514 | 141 % |
| Rev1-S | 12 | A | 1591 | 0.595 | voltage | 35.3 | 697 | 119 % |
| Rev1-S | 12 | D | 1591 | 0.574 | voltage | 34.0 | 911 | 106 % |
| Rev1-S | 15 | A | 1989 | 0.846 | thermal | 50.1 | 1094 | 95 % |
| Rev1-S | 15 | D | 1989 | 0.644 | thermal | 38.1 | 1307 | 85 % |
| Rev1-S | 18 | A | 2387 | 0.846 | thermal | 50.1 | 1491 | 79 % |
| Rev1-S | 18 | D | 2387 | 0.644 | thermal | 38.1 | 1703 | 70 % |
| Rev1-S | 24 | A | 3182 | 0.846 | thermal | 50.1 | 2283 | 60 % |
| Rev1-S | 24 | D | 3182 | 0.644 | thermal | 38.1 | 2493 | 53 % |

## S1 - speed sweep at the scenario-A thermal current (25 °C)

| Machine | rpm | E line (V rms) | Eddy (mW) | Eddy drag (mN·m) | T_em (mN·m) | Winding (°C) | Bus needed (V) | η_EM (%) |
|---|---|---|---|---|---|---|---|---|
| Rev0 | 250 | 0.594 | 1.3 | 0.049 | 31.0 | 59.8 | 5.32 | 17 |
| Rev0 | 500 | 1.189 | 5.1 | 0.097 | 31.0 | 59.9 | 6.21 | 28 |
| Rev0 | 750 | 1.783 | 11.4 | 0.146 | 31.0 | 59.9 | 7.09 | 37 |
| Rev0 | 1000 | 2.377 | 20.4 | 0.194 | 31.0 | 60.0 | 7.98 | 44 |
| Rev0 | 1500 | 3.566 | 45.8 | 0.291 | 31.0 | 60.2 | 9.75 | 54 |
| Rev0 | 2000 | 4.754 | 81.4 | 0.389 | 31.0 | 60.6 | 11.53 | 61 |
| Rev0 | 3000 | 7.131 | 183.2 | 0.583 | 31.0 | 61.5 | 15.08 | 69 |
| Rev0 | 4000 | 9.508 | 325.6 | 0.777 | 31.0 | 62.8 | 18.64 | 74 |
| Rev1-S | 250 | 1.267 | 2.8 | 0.105 | 50.1 | 59.6 | 8.62 | 22 |
| Rev1-S | 500 | 2.533 | 11.0 | 0.211 | 50.1 | 59.7 | 10.51 | 36 |
| Rev1-S | 750 | 3.800 | 24.9 | 0.316 | 50.1 | 59.8 | 12.40 | 45 |
| Rev1-S | 1000 | 5.066 | 44.2 | 0.422 | 50.1 | 60.0 | 14.29 | 52 |
| Rev1-S | 1500 | 7.599 | 99.4 | 0.633 | 50.1 | 60.5 | 18.07 | 62 |
| Rev1-S | 2000 | 10.132 | 176.7 | 0.844 | 50.1 | 61.1 | 21.86 | 68 |
| Rev1-S | 3000 | 15.198 | 397.6 | 1.266 | 50.1 | 63.0 | 29.44 | 75 |
| Rev1-S | 4000 | 20.264 | 706.9 | 1.688 | 50.1 | 65.6 | 37.04 | 79 |
