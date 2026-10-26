---
title: "Rev0 and Rev1-S Predicted Operating Points"
subtitle: "AK-07 PCB coreless axial-flux motor — bench-test baseline — 19 October 2026 (rev. C)"
---

These are **predicted operating points for planning the bench tests**, not continuous ratings. The continuous ratings will be set by testing.

The predictions come from the Maxwell simulations, the measured winding resistance (1.87–1.90 Ω on every phase of both stators) and the measured stator stack thickness (5.1 mm maximum). They supersede rev. B (19 October) and all earlier tables, including the 1.8 Ω / 0.85 A values in the 17 October technical report.

**Changes from rev. B**

- **Current.** 0.84 A pk per stator is now labelled a candidate thermal test point, not a continuous rating.
- **Speed.** 1000 rpm is the target test speed. The higher speeds are voltage limits only.
- **Rev1-S parallel.** Re-worked for the unequal back-EMF of S1 and S2.
- **Inductance.** Corrected from 110 µH to about 25 µH per stator, so the PWM ripple estimates are about 4.4 times higher.
- **Mechanical loss.** The method for measuring it has been corrected.
- **Drive.** The guidance is re-worded as checks.
- **Stack thickness.** Recorded as measured.

# Predicted operating points at the 1000 rpm target test speed

All values are for **star (Y)** connection at 133.3 Hz electrical. The current is the **candidate thermal test point**, 0.84 A pk in any one stator. It has not been shown to keep the real winding below 60 °C (see "Thermal").

| Quantity | Rev0 | Rev1-S series | Rev1-S parallel |
|---|---|---|---|
| Supply for the test | 12 V | 24 V | 12 V |
| Equivalent phase resistance (measured, about 20 °C) | 1.89 Ω | 3.78 Ω | 0.945 Ω |
| Terminal (line) current | 0.84 A pk (0.59 A rms) | 0.84 A pk (0.59 A rms) | **1.54 A pk** (1.09 A rms) |
| Current in each stator | 0.84 A pk | 0.84 A pk | S1 0.84 / S2 0.70 A pk (unequal; see below) |
| Torque constant, terminal | 27.8 mN·m/A pk | 59.2 mN·m/A pk | 29.5 mN·m/A pk (at this current) |
| Electromagnetic torque | 23.4 mN·m | 49.8 mN·m | 45.5 mN·m |
| Estimated shaft torque¹ | 18.2–21.2 mN·m | 44.3–47.3 mN·m | 40.0–43.0 mN·m |
| Shaft power | 1.9–2.2 W | 4.6–5.0 W | 4.2–4.5 W |
| Back-EMF at 1000 rpm, phase / line | 1.37 / 2.38 V rms | 2.93 / 5.07 V rms | 1.46 / 2.53 V rms² |
| Required DC bus, SVPWM (m = 0.95; 25–100 °C winding) | 6.4–7.4 V | 13.2–15.3 V | 6.4–7.3 V |
| Copper loss (25–60 °C) | 2.0–2.4 W | 3.9–4.7 W | 3.3–4.0 W |
| Electromagnetic efficiency, 60 °C | about 51 % | about 53 % | about 54 % |
| Calculated voltage-limited speed, 12 V³ | 2300–2590 rpm | 570–840 rpm | 2240–2490 rpm |
| Calculated voltage-limited speed, 24 V³ | 5690–5980 rpm | 2160–2430 rpm | 5420–5670 rpm |

¹ Electromagnetic torque minus the predicted track-eddy drag (0.19 mN·m for Rev0, 0.42 mN·m for Rev1-S at 1000 rpm), minus an **assumed** 2–5 mN·m of mechanical loss. For example, 49.8 − 0.4 − (2 to 5) = 44.3–47.3 mN·m. The mechanical loss is not yet measured.

² Mean of S1 (1.37 V) and S2 (1.55 V) phase back-EMF. The terminal voltage of the parallel pair at no load is this mean.

³ These are the speeds at which the inverter runs out of voltage at this current. **They are not speed ratings.** The rotor assembly, bearings and magnet retention have not been qualified for speeds above the 1000 rpm target. Do not exceed 1000 rpm until the mechanical assembly has been checked.

# Rev1-S parallel connection

The simulations predict different torque constants for the two stators. S1 is 18.54 mN·m/A. S2 is 20.96 mN·m/A, higher because R1's steel backplate sits next to it. Their phase back-EMFs are therefore in phase but differ by about 13 % (1.37 against 1.55 V rms at 1000 rpm).

Connected in parallel, this difference drives a circulating current between S1 and S2:

- **At no load** it is about 0.06–0.07 A pk per phase at 1000 rpm, about 22–26 mW of extra loss.
- **Under load** it adds to S1's share and subtracts from S2's.

At 1.68 A pk terminal current, S1 would carry about 0.91 A pk and S2 0.77 A pk, so S1 would exceed the 0.84 A test point. The terminal current is therefore reduced to 1.54 A pk, which keeps S1 at 0.84 A pk. S1 is also the hotter stator in the Icepak model, so it sets the limit.

Terminal current alone cannot show either stator's current. If the parallel connection is used:

- measure the current of S1 and S2 separately (one current probe on each stator's phase A lead);
- confirm the back-EMF difference with the open-circuit test first.

Parallel remains an alternative that needs verification. Series connection on 24 V avoids the problem.

# Connection

All values are for **star (Y)** connection. Each winding's start and finish are brought out (A1–A2, B1–B2, C1–C2), so delta is possible, but it is not covered here. In delta, the 5.5 % third-harmonic back-EMF drives about 40 mA rms circulating current at 1000 rpm.

The simulations excite the windings with balanced sinusoidal currents (I_A + I_B + I_C = 0), so they correspond directly to star.

# Basis of each number

| Input | Value | Status |
|---|---|---|
| Torque constant K (T = 1.5·K·I pk) | Rev0 18.53 mN·m/A. Rev1-S 39.50 mN·m/A (S1 18.54 + S2 20.96) | Simulated. Rev0 from the full-motor FEM. Rev1-S from the board-by-board sum, confirmed within 0.5 % by the Rev0-calibrated equivalent-coil model |
| Back-EMF | Phase peak = K·ω. THD 5.5 % phase, 0.7 % line | Simulated, rotating model |
| Phase resistance per stator | 1.87–1.90 Ω, every phase of S1 and S2 (1.89 Ω used) | Measured. Temperature not recorded (15–30 °C assumed); 0–0.1 Ω treated as contact resistance |
| Resistance with temperature | 1.85–1.96 Ω at 25 °C; 2.10–2.22 Ω at 60 °C; 2.38–2.52 Ω at 100 °C, per stator | Derived (α = 0.00393 /K) |
| Stator stack thickness | 5.1 mm maximum | **Measured.** Matches the modelled 5.10 mm (5 × 1.02 mm), so stack spacing is no longer a significant uncertainty |
| Inductance | About 25 µH per stator (Rev1-S 50 µH series, 12.5 µH parallel) | Estimate from the Maxwell single-board value (≈ 2 µH) and the board-to-board coupling. Measure it before power-up |
| Mechanical loss | 2–5 mN·m | **Assumed.** See "Measuring mechanical loss" |
| Thermal test point | 0.84 A pk per stator | From an assumed 60 °C board limit and an assumed 15 K/W. Not established |
| Geometry | Backplate 86 / 19 mm, 1.0 mm air gaps | Model. Hardware backplates are 80 / 25 mm; air gaps not yet measured |

Required voltage is E + I·R with the current on the q-axis. The winding reactance at 133 Hz is about 0.02 Ω, which is negligible. Each extra 0.25 mm of air gap lowers K and back-EMF by about 7 %, raising the current needed for a given torque.

# Thermal

The 0.84 A pk test point comes from an assumed 15 K/W stack-to-air thermal resistance and an assumed 60 °C board limit. Neither is measured, so the test point does not establish that the real winding stays below 60 °C. The continuous rating must come from the heat run.

| Thermal resistance, stack to air | 60 °C board limit | 100 °C board limit |
|---|---|---|
| 8.75 K/W (earlier Icepak, hood with fans) | 1.09 A pk per stator | 1.51 A pk |
| 15 K/W (pessimistic, used here) | 0.84 A pk | 1.15 A pk |

- Run the heat test at constant current until the temperature settles. Hold 60 °C as the limit until the material of the yellow holders is confirmed. N35 magnets are limited to 80 °C.
- Log boards 1 and 5 with thermocouples. Take the mean winding temperature from the resistance rise: ΔT = (R/R0 − 1)/0.00393.
- The measured thermal resistance then sets the continuous current: I pk = √(ΔT_allowed / (1.5·R_hot·R_th)).
- Rev1-S stacks two stators closely, and S1 runs hotter than S2. Instrument S1.

# Drive checks

With about 25 µH per stator, the winding inductance is too small to filter the PWM. Ripple is roughly V_dc / (6·L·f_sw), peak to peak. These estimates are uncertain by about ±50 %:

| Winding | 12 V, 20 kHz | 12 V, 50 kHz | 24 V, 50 kHz | 12 V, 50 kHz, + 0.5 mH per phase |
|---|---|---|---|---|
| Rev0 (25 µH) | 4.0 A | 1.6 A | 3.2 A | 0.08 A |
| Rev1-S series (50 µH) | 2.0 A | 0.8 A | 1.6 A | 0.07 A |
| Rev1-S parallel (12.5 µH) | 8.0 A | 3.2 A | 6.4 A | 0.08 A |

These are proposals to check against the available inverter, not an established drive setup:

1. Measure the phase inductance with an LCR meter (1–10 kHz) on each stator.
2. Check the inverter's switching frequency range, current-sense bandwidth and over-current trip against the table above.
3. At low current (0.2–0.3 A pk), measure the phase-current ripple with a current probe before increasing current.
4. If the ripple is more than about 20 % of the test current, raise the switching frequency if the inverter allows, or add series inductance of 0.5–1 mH per phase.
5. Set the driver's current limit on **peak** current, including ripple.

# Measuring mechanical loss

A powered no-load input-power measurement cannot isolate mechanical loss: it also contains inverter loss, copper loss and eddy loss. Use one of these instead:

- **No-load current method (preferred with an FOC drive).** At a steady no-load speed, the electromagnetic torque equals the drag torque: T_drag = 1.5·K·I_q,pk. Here K comes from the open-circuit back-EMF test (K = E_ph,pk / ω) and I_q comes from the drive or a current probe. Subtract the predicted eddy drag (0.19 / 0.42 mN·m at 1000 rpm) to get the mechanical part. This excludes copper and inverter losses by construction.
- **Spin-down.** Spin the rotor to speed, disconnect it, and record speed against time. T_drag = −J·dω/dt, which needs the rotor inertia J from CAD.
- **External drive with a torque sensor.** Drive the motor open-circuit from a second motor through an in-line torque sensor.

# First-test sequence

1. **Measure before connecting.** Each stator's phase resistance, with room temperature noted. The phase inductance. The assembled air gaps.
2. **Open-circuit back-EMF (main model check).** Spin each motor externally at known speeds up to 1000 rpm and record the line back-EMF.
   - Expected at 1000 rpm: Rev0 2.38 V rms; Rev1-S 5.07 V rms (series).
   - For Rev1-S, also record S1 and S2 separately: about 2.38 and 2.69 V rms line. This confirms they are in phase and quantifies their difference before any parallel connection.
   - A value more than a few percent low points to a larger air gap than modelled.
3. **First powered run.** Power Rev0 at 0.2–0.3 A pk and 300–500 rpm and check the current ripple (Drive checks). Then step up towards 0.84 A pk at 1000 rpm, logging temperature.
4. **Mechanical loss.** Measure the no-load drag with one of the methods above, then torque against current.
5. **Heat run.** Run at constant current until temperatures settle, to measure the thermal resistance and set the continuous rating.
6. **Rev1-S.** Repeat in series. Use parallel only with per-stator current measurement.
