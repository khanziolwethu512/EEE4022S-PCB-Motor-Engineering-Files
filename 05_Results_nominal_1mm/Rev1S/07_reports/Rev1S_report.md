---
title: "Rev1-S Maxwell Technical Report"
subtitle: "AK-07 PCB coreless axial-flux motor — Olwethu Khanzi — 19 October 2026, rev. 2 (measured resistance of both stators, inductance, measured stack)"
---

Rev1-S (two 5-board stators, two 16-magnet rotors, S1–R1–S2–R2) produces **59.2 mN·m per amp of peak phase current** (83.8 mN·m per amp rms) with the stators in series. It has **5.07 V rms line-to-line back-EMF at 1000 rpm**, 2.13 × Rev0, in the modelled geometry. Two independent routes give the torque constant within 0.5 %. The Rev1-S full-motor solve was lost to the disk quota, so the Rev0 full-motor result is the anchor. As with Rev0, the model geometry is not yet matched to the hardware, so these are predictions for the test bench, not a rating.

# Machine and simulation chain

| Item | Value used in the models |
|---|---|
| Stack order | S1 – R1 – S2 – R2 (two single-sided rotors on one shaft, aligned) |
| Stators | 2 × 5 boards, identical to Rev0 (6 layers, 1 oz, pitch 1.02 mm) |
| Rotors | 2 × 16 N35 magnets, 20 × 6 × 2 mm at 28 mm radius; 2 mm steel 1010 backplate each, OD 86 / ID 19 mm in the model |
| S1 environment | 1.0 mm gap to R1's magnets, nothing behind it (same as Rev0) |
| S2 environment | 1.0 mm gap to R2's magnets on one side; R1's bare steel backplate 1.0 mm (assumed) behind board 1 on the other |
| Winding connection in the models | Phase A of S1 in series with phase A of S2 (likewise B, C); parallel also assessed |

Models used:

1. **Board-by-board detailed FEM:** S2's five boards solved one at a time in their real environment; S1 taken as the Rev0 stack, which the full-motor Rev0 solve confirmed.
2. **Field map:** magnets and steel of the whole Rev1-S machine, B on the trace centre-lines.
3. **Equivalent-coil model (EQ):** all 10 boards, 3 phases, 8 rotor angles. The 8th angle was filled from the 7 solved ones by half-wave antisymmetry; the solved pairs obey it to 0.08 mN·m out of 7.3 mN·m.
4. **Rotating field-only transient (FMROT):** both rotors turning at 1000 rpm through one electrical period in 24 steps; two rotating bands; 32 cores, 122 GB.

The full-motor detailed static solve of Rev1-S ran for 47 h and was stopped by the 50 GB scratch quota before finishing one angle. It was not repeated.

# Torque constant

The board-by-board sum gives K = 39.50 mN·m/A. The equivalent-coil model, calibrated on Rev0 alone and not refitted to Rev1-S, gives 39.30 mN·m/A, 0.5 % lower.

| Method | S1 | S2 | Machine K (mN·m/A) | vs board sum |
|---|---|---|---|---|
| Board-by-board detailed sum | 18.54 | 20.96 | **39.50** | reference |
| Equivalent coils with the Rev0 calibration (×0.809) | 18.54 | 20.76 | 39.30 | −0.5 % |
| Field map (centre-line Lorentz) | 19.50 | 22.14 | 41.64 | +5.4 % |
| Rotating field-only transient | 19.47 | 22.10 | 41.56 | +5.2 % (field-map basis) |

| S2 board (1 = next to R1's steel, 5 = next to R2's magnets) | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Detailed K (mN·m/A) | 2.597 | 3.057 | 3.812 | 4.938 | 6.559 |

- **Stator 1** behaves exactly as in Rev0: the equivalent-coil model gives the same S1 value with and without S2 and R2 present (within 0.03 %).
- **Stator 2** gives about 12 % more torque than S1. Its boards far from R2's magnets sit next to R1's steel backplate, which pulls the field through the stack: S2 board 1 gives 2.60 mN·m/A against 1.83 for S1 board 5 at the same distance from its magnets.
- **Ratio to Rev0:** 2.13 × in torque per amp, for twice the copper.
- The rotating and field-map results are scaled by 39.50 / 41.564 = 0.950 below.

# Back-EMF, torque ripple and cogging

With the stators in series, the phase back-EMF at 1000 rpm is 2.925 V rms and the line back-EMF is 5.066 V rms. The line waveform is nearly sinusoidal (0.6 % THD).

![Rev1-S phase and line back-EMF at 1000 rpm, series connection](../out_rev1s/fig1_backemf_rev1s.png)

| Quantity | Phase | Line |
|---|---|---|
| Fundamental at 1000 rpm (series) | 2.925 V rms (4.137 V pk) | 5.066 V rms |
| THD | 5.2 % (H3 5.2, H5 0.6, H7 0.05 %) | 0.6 % |
| Per stator at 1000 rpm, phase | S1 1.372 V rms; S2 1.552 V rms (in phase) | — |
| Phase balance | K spread 0.02 %; displacement 120.0° | — |

- The rotating model agrees with the static field map within 1.59 % of K1 at all 240 board-phase-angle points, and within 0.42 % and 0.27° on board 1. S1 and S2 are in phase to within 0.02°.
- With sinusoidal currents at 1 A pk, mean torque is 59.25 mN·m with 1.16 % pk-pk ripple. The back-EMF harmonics predict 2·(H5 − H7) = 1.15 %, consistent. The loaded waveform is reconstructed from the field, not solved under load.
- The no-load rotor torque (both rotors) varies 0.78 mN·m pk-pk without periodicity: cogging is below the solver noise floor, as for Rev0.

![Rev1-S torque at 1 A pk and no-load rotor torque](../out_rev1s/fig2_torque_cogging_rev1s.png)

# Field distribution

Both magnet-facing stator faces see the same field as Rev0 (0.44 T peak). S2's face toward R1's bare steel sees only 0.11 T, and neither backplate saturates (0.83 and 0.93 T peak).

![Rev1-S air-gap field and backplate field](../out_rev1s/fig3_field_maps_rev1s.png)

| Location | Peak | Mean field magnitude |
|---|---|---|
| 0.25 mm off S1, facing R1's magnets | 0.445 T | 0.226 T |
| 0.25 mm off S2, facing R2's magnets | 0.444 T | 0.226 T |
| 0.25 mm off S2, facing R1's steel | 0.108 T | 0.041 T |
| R1 backplate | 0.835 T (99th percentile 0.795) | 0.287 T |
| R2 backplate | 0.931 T (99th percentile 0.872) | 0.336 T |

Current density is the same as Rev0 (identical boards): 9.2–9.4 A/mm² per amp in the tracks, 57 A/mm² per amp at local necks.

# Losses and efficiency

Copper loss again dominates. Track eddy loss is 44 mW at 1000 rpm (S1 20.3, S2 23.9 mW), twice Rev0's. Copper loss per stator is the same as Rev0 at the same current.

| Quantity | Value | Notes |
|---|---|---|
| Phase resistance, series | 3.70–3.92 Ω at 25 °C; 4.20–4.44 Ω at 60 °C | Both stators measured 1.87–1.90 Ω per phase |
| Copper loss at 1 A pk, 60 °C | 6.5 W (both stators) | 1.5 · I² · R |
| Track eddy loss at 1000 rpm | 44.2 mW | ∝ speed² |
| Phase inductance, series | about 50 µH (25 µH per stator; measure it) | Parallel: about 12.5 µH |

![Rev1-S electromagnetic efficiency, series, 60 °C](../pc1/fig5_efficiency_rev1s.png)

| Speed | 0.5 A pk (29.6 mN·m) | 1.0 A pk (59.2 mN·m) | 1.5 A pk (88.9 mN·m) |
|---|---|---|---|
| 500 rpm | 48.7 % | 32.3 % | 24.2 % |
| 1000 rpm | 65.1 % | 48.7 % | 38.9 % |
| 2000 rpm | 77.5 % | 65.1 % | 55.8 % |

At equal torque Rev1-S needs about half Rev0's current per stator, so at 28 mN·m it loses about half the copper power of Rev0. Electromagnetic efficiency only: bearing and windage loss are not included.

# Connection, thermal and limitations

**Connection.** The two stators can be joined per phase in series or in parallel; the choice must be stated for every test.

| Per phase, star | Series | Parallel |
|---|---|---|
| Terminal torque constant (T = 1.5·K·I) | 39.50 mN·m/A | 19.75 mN·m/A |
| Phase back-EMF at 1000 rpm | 2.925 V rms | 1.462 V rms |
| Resistance at 60 °C | 4.20–4.44 Ω | 1.05–1.11 Ω |
| Inductance | about 50 µH | about 12.5 µH |

In parallel, the 0.18 V rms back-EMF difference between S1 and S2 drives about 40 mA rms of circulating current at 1000 rpm, about 25 mW. That figure assumes the stators are angularly aligned; each 1° of mechanical misalignment adds roughly 50 mA. Under load the same difference makes S1 carry more current than S2 (0.84 against 0.70 A pk at 1.54 A pk terminal current), so in parallel the terminal current must be limited by S1, and each stator's current must be measured separately.

**Thermal.** An earlier Icepak model of Rev1-S ran S1 2–15 K hotter than S2, with an assumed acrylic hood and fans. No model of the as-built assembly exists. Use the 0.84 A pk per stator candidate test point as a ceiling for supervised testing and expect the closely stacked Rev1-S to run warmer than Rev0.

Limitations, in addition to those listed for Rev0 (backplate 80 / 25 mm against 86 / 19 mm, unmeasured air gaps; the 5.1 mm measured stack matches the model):

- **Full-motor check:** the Rev1-S full-motor solve was not completed. The torque constant rests on the board-by-board sum, confirmed within 0.5 % by the Rev0-calibrated equivalent-coil model.
- **S2 to R1 clearance:** the 1 mm gap between S2 and R1's bare backplate is assumed. It sets S2's far-board torque.
- **Resistance:** both stators measured 1.87–1.90 Ω per phase.
- **Cogging and ripple:** as for Rev0, cogging is below the solver noise and the ripple is reconstructed, not solved under load.

**Expected simulation-to-hardware gap and recommendation.** As for Rev0, measured values are expected to differ by more than the agreement between the simulation methods, because the hardware geometry differs from the model. The fix is the same: measure the assembled motor, rebuild the equivalent-coil model to those dimensions using the Rev0 calibration, and compare like with like.
