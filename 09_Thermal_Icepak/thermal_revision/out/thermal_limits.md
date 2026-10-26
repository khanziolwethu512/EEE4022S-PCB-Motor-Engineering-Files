# Revised thermal limits (Gate 2)

Winding limit 60 C (holder material unconfirmed); N35 magnets 80 C (not reached: Icepak magnets run below the winding). R_th per stator from the archived Icepak solves; heat from the MEASURED resistance.

## R_th extracted from Icepak (T_hood 30 C)

| Machine | I pk (A) | Fans | Icepak heat per stator (W) | Hotspot (C) | R_th per stator (K/W) |
|---|---|---|---|---|---|
| Rev0 | 0.737 | on | 1.220 | 40.9 | 8.93 |
| Rev0 | 1.000 | on | 2.317 | 50.3 | 8.76 |
| Rev0 | 2.000 | on | 11.569 | 124.9 | 8.20 |
| Rev0 | 2.000 | off | 11.870 | 134.5 | 8.80 |
| Rev1-S | 0.345 | on | 0.262 | 34.2 | 16.06 |
| Rev1-S | 1.000 | on | 2.421 | 65.7 | 14.75 |
| Rev1-S | 2.000 | on | 14.450 | 220.4 | 13.18 |
| Rev1-S | 2.000 | off | 14.970 | 236.8 | 13.81 |

Same current, archived heat vs measured-resistance heat (scenario A, 30 C hood, standstill):

| Machine | I pk | Icepak heat/stator (layout R) | Icepak hotspot | Heat/stator with measured R | Predicted hotspot |
|---|---|---|---|---|---|
| Rev0 | 1.0 A | 2.32 W | 50.3 C | 3.26 W | 58.2 C |
| Rev1-S | 1.0 A | 2.42 W | 65.7 C | 3.51 W | 80.6 C |

## Thermally limited current (A pk per stator; Rev1-S is the series terminal current), measured R 1.89 ohm

| Machine | Scenario | Evidence | Ta 25 C, 0 rpm | Ta 25 C, 1000 rpm | Ta 30 C, 1000 rpm | Ta 25 C, 4000 rpm | R_th at 25 C (K/W) |
|---|---|---|---|---|---|---|---|
| Rev0 | A: Icepak: hood fans on (1 m/s), rotor still, hypothetical acrylic housing | THERMAL-FEM | 1.116 | 1.113 | 1.027 | 1.071 | 8.56 |
| Rev0 | B: Icepak, fans off (natural convection), rotor still | THERMAL-FEM x inferred ratio 1.11 | 1.059 | 1.056 | 0.974 | 1.011 | 9.51 |
| Rev0 | C: Lumped network, rotor turning 1000 rpm, fans on (Rev1-S scaled by the Icepak Rev1-S/Rev0 ratio) | THERMAL-LUMPED (+ inferred for Rev1-S) | - | 1.448 | 1.341 | - | 5.07 |
| Rev0 | D: Cautious planning basis (as-built open frame / unknown cooling) | ASSUMED (x1.71 on Icepak) | 0.843 | 0.840 | 0.777 | 0.782 | 15.00 |
| Rev1-S | A: Icepak: hood fans on (1 m/s), rotor still, hypothetical acrylic housing | THERMAL-FEM | 0.850 | 0.846 | 0.780 | 0.779 | 14.76 |
| Rev1-S | B: Icepak, fans off (natural convection), rotor still | THERMAL-FEM x inferred ratio 1.11 | 0.807 | 0.802 | 0.740 | 0.731 | 16.39 |
| Rev1-S | C: Lumped network, rotor turning 1000 rpm, fans on (Rev1-S scaled by the Icepak Rev1-S/Rev0 ratio) | THERMAL-LUMPED (+ inferred for Rev1-S) | - | 1.102 | 1.020 | - | 8.74 |
| Rev1-S | D: Cautious planning basis (as-built open frame / unknown cooling) | ASSUMED (x1.71 on Icepak) | 0.649 | 0.644 | 0.595 | 0.553 | 25.30 |

Resistance sensitivity (scenario A, 25 C, 1000 rpm): Rev0 lower 1.80 -> 1.141 A; Rev0 measured 1.89 -> 1.113 A; Rev0 upper 1.94 -> 1.099 A; Rev1-S lower 1.80 -> 0.867 A; Rev1-S measured 1.89 -> 0.846 A; Rev1-S upper 1.94 -> 0.835 A

Short-time (first-order, scenario A, 25 C, from cold): see T2_short_time_limits.csv. The time constants are from the Rev0 lumped network (9.2 min at 1000 rpm, 24 min stalled); Icepak was solved steady-state only.
