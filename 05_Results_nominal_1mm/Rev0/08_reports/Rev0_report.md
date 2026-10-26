---
title: "Rev0 Maxwell Technical Report"
subtitle: "AK-07 PCB coreless axial-flux motor — Olwethu Khanzi — 17 October 2026, revised 19 October 2026 (measured resistance of both stators, inductance, measured stack)"
---

Rev0 (one 5-board PCB stator, one 16-magnet rotor) produces **27.8 mN·m per amp of peak phase current** (39.3 mN·m per amp rms), with **2.38 V rms line-to-line back-EMF at 1000 rpm**, in the modelled geometry. The full-motor solve and the board-by-board sum agree within 0.03 %; the field map reads 5 % high. The model's backplate, stack spacing and air gap still differ from, or are unconfirmed against, the hardware, so these are predictions for the test bench, not a rating.

# Machine and simulation chain

Rev0 is a single-sided coreless axial-flux machine: five 6-layer PCBs stacked as one stator, facing one rotor of 16 magnets on a steel backplate.

| Item | Value used in the models |
|---|---|
| Stator | 5 boards, 6 layers each, 1 oz copper, 1.0 mm FR-4, board pitch 1.02 mm; 3 phases, 8 coils per phase per board |
| Rotor | 16 × N35, 20 × 6 × 2 mm, centred at 28 mm radius, alternating polarity (8 pole pairs) |
| Backplate | 2 mm steel 1010, OD 86 / ID 19 mm (hardware is 80 / 25 mm: correction pending) |
| Air gap | 1.0 mm, magnet face to board-1 surface |
| Shaft | 19 mm steel |
| Reference speed | 1000 rpm = 133.3 Hz electrical |

The results come from five Ansys Maxwell 2025 R2 models, each checking the next:

1. **Board-by-board detailed FEM:** each board solved alone with its real traces and vias, then summed (lab PCs).
2. **Field map:** magnets and steel only, with B sampled on the trace centre-lines and Lorentz force integrated (lab PCs).
3. **Full-motor detailed static:** all five boards meshed together, all three phases at 1 A synchronous, two rotor angles, 6 adaptive passes, 110 GB per angle (UCT HPC, 40 cores).
4. **Rotating field-only transient (FMROT):** the rotor turns at 1000 rpm through one electrical period in 24 steps, with B exported on the traces at every step (UCT HPC).
5. **Equivalent-coil model (EQ):** each phase per board is replaced by 8 stranded sector coils calibrated to model 3; 8 rotor angles (UCT HPC).

The torque constant K is defined by T = 1.5 · K · I_pk. The phase back-EMF peak equals K · ω_mech.

# Torque constant

The full-motor solve gives K = 18.534 mN·m/A from the copper (Lorentz) torque. This matches the sum of the single-board solves to 0.03 %. The field map reads 4.9 % high.

| Method | K (mN·m/A) | vs full motor |
|---|---|---|
| Full-motor static, copper torque (2-angle mean) | 18.534 | reference |
| Full-motor static, rotor virtual work | 18.470 | −0.3 % |
| Board-by-board detailed sum | 18.540 | +0.03 % |
| Field map (centre-line Lorentz) | 19.496 | +5.2 % |
| Rotating field-only transient | 19.475 | +5.1 % (same basis as the field map) |

| Board (1 = next to the magnets) | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Full motor, K (mN·m/A) | 6.282 | 4.590 | 3.364 | 2.474 | 1.825 |
| Field map vs full motor | +1.4 % | +4.5 % | +6.7 % | +10.2 % | +10.4 % |

- Copper and rotor torque agree within 0.51 % (0°) and 0.18 % (3.75°), which confirms the mesh.
- K falls by about 26 % per board: the field decays at 0.30 per mm through the stack.
- The field map's excess grows with distance from the magnets. The likely cause is that centre-line sampling differs from the volume force on the meshed copper. Mesh, padding and shaft stub were each ruled out.
- Torque is linear in current: 2 A gives exactly twice the torque of 1 A, within 0.002 %.
- Results from the field map and the rotating model are scaled by 18.534 / 19.475 = 0.952 to the full-motor value.

# Back-EMF, torque ripple and cogging

At 1000 rpm the phase back-EMF is 1.372 V rms and the line back-EMF is 2.377 V rms. The line waveform is close to sinusoidal at 0.7 % THD, because the phase waveform's 3rd harmonic cancels between phases.

![Phase and line back-EMF at 1000 rpm](../out_rev0/fig1_backemf_rev0.png)

| Quantity | Phase | Line |
|---|---|---|
| Fundamental at 1000 rpm | 1.372 V rms (1.941 V pk) | 2.377 V rms |
| Back-EMF constant | 1.372 V rms per 1000 rpm | 2.377 V rms per 1000 rpm |
| THD | 5.5 % (H3 5.5, H5 0.7, H7 0.05 %) | 0.7 % |
| Phase balance | K spread 0.04 %; displacement 120.0° | — |

- The rotating model turns the magnets and steel only: no stator current is solved. It agrees with the static field map within 1.49 % of K1 at all 120 board-phase-angle points, so the back-EMF predictions are sound. Its waveforms are scaled by 0.952 to the full-motor K.
- The loaded torque waveform is reconstructed by applying ideal sinusoidal currents to the exported field, not solved as a loaded transient. Mean torque at 1 A pk is 27.80 mN·m with 1.26 % pk-pk (0.35 mN·m) ripple at 6× electrical frequency. As a consistency check, the back-EMF harmonics predict 2·(H5 − H7) = 1.23 % pk-pk for sinusoidal drive, so the ripple follows from the field shape rather than numerical noise. It still needs a resolution check with finer time steps.
- The no-load rotor torque comes from Maxwell's rotor force (volume integration), a separate calculation from the Lorentz torque above. It varies 0.61 mN·m pk-pk without periodicity, and the static board solves showed the same (below 0.47 mN·m, not periodic). Cogging is therefore below this solver noise floor, as expected with no stator iron; the noise floor is larger than the predicted ripple, so neither is resolved by the rotor-torque output.
- Zero magnet and steel eddy loss is a consequence of the model scope (no armature field, no PWM ripple), not proof of zero loss under inverter drive.

![Torque at 1 A pk and no-load rotor torque](../out_rev0/fig2_torque_cogging_rev0.png)

# Field distribution and current density

The air-gap field peaks at 0.44 T just off the stator face, and the backplate peaks at 0.90–0.92 T. That is well below the 1.5–1.6 T knee of 1010 steel, so the 2 mm plate is not saturated.

![Axial field at the stator face and field magnitude in the steel backplate](../out_rev0/fig3_field_maps_rev0.png)

| Quantity | Value | Source |
|---|---|---|
| Bz 0.25 mm off the stator face | max 0.448 T; mean field magnitude 0.227 T | Rotating model, 8 instants |
| Fundamental Bz on the tracks, board 1 / board 5 | 0.174 / 0.051 T | Field map |
| Field decay through the stack | 0.30 per mm (26 % lost per board) | Field map |
| Backplate field magnitude, max / 99th percentile / mean | 0.907 / 0.869 / 0.332 T | Rotating model |
| Backplate field magnitude, max, static | 0.92 T | Full-motor static |

Current density per 1 A of phase current is 9.2–9.4 A/mm² in the tracks, with a whole-board mean of 8.6 A/mm² and a 95th percentile of 10.3 A/mm². Each phase splits over parallel tracks on all six layers. Local peaks reach 57 A/mm² per A at narrow necks near the terminals and vias; these are short hot-spot candidates but carry little of the total loss. Skin depth at 1000 rpm is 5.7 mm (164× the copper thickness), so the distribution is effectively DC.

![Current density in board 1, layer L1, per 1 A](../out_rev0/fig4_current_density_rev0.png)

# Losses, efficiency and thermal limit

Copper I²R loss dominates: 3.2 W at 1 A pk and 60 °C against 20 mW of track eddy loss at 1000 rpm. Electromagnetic efficiency at the 1000 rpm, 1 A pk point is therefore about 47 % (about 51 % at the 0.84 A pk test point), rising with speed and falling with current.

| Loss | Value | Notes |
|---|---|---|
| Phase resistance, measured | 1.87–1.90 Ω per phase (complete stator), every phase of S1 and S2; temperature not recorded | Model (traces only): 1.33–1.39 Ω; the difference is joints, leads and contact |
| Resistance used | 1.85–1.96 Ω at 25 °C; 2.10–2.22 Ω at 60 °C (2.16 Ω used) | Measurement at an assumed 15–30 °C; 0–0.1 Ω of it treated as contact resistance and not temperature-corrected |
| Copper loss at 1 A pk, 60 °C | 3.24 W (1.5 · I² · R) | Includes contact loss; scales with I² and winding temperature |
| Track eddy loss at 1000 rpm | 20.4 mW (boards 1–5: 10.8 / 4.8 / 2.5 / 1.5 / 0.8 mW) | Thin-strip estimate, ∝ speed²; 0.33 W at 4000 rpm |
| Magnet and steel eddy loss | not modelled under load | Zero in the field-only model by construction |
| Phase inductance | about 25 µH (from the Maxwell single-board value and board coupling; measure it) | ωL = 0.02 Ω at 1000 rpm, negligible against R; too small to filter PWM ripple (see the operating-points sheet) |

![Rev0 electromagnetic efficiency, winding at 60 °C](../pc0/fig5_efficiency_rev0.png)

| Speed | 0.5 A pk (13.9 mN·m) | 1.0 A pk (27.8 mN·m) | 1.5 A pk (41.7 mN·m) |
|---|---|---|---|
| 500 rpm | 47.2 % | 31.0 % | 23.0 % |
| 1000 rpm | 63.7 % | 47.2 % | 37.4 % |
| 2000 rpm | 76.6 % | 63.7 % | 54.2 % |

These efficiencies are electromagnetic only. Bearing and windage loss are not modelled, and they will lower the measured shaft efficiency at these small power levels.

Thermal limit: no thermal model of the as-built assembly exists yet. The earlier 1.75 A pk limit is withdrawn. It used the model resistance and an assumed acrylic hood with fans and aluminium end plates (Icepak, 8.75 K/W from the hottest board to air). A candidate thermal test point of **0.84 A pk** (about 23 mN·m) assumes a 60 °C board limit and a pessimistic 15 K/W. It is a candidate for supervised testing, not an approved continuous rating, until the holder material is confirmed and the temperature rise is measured. N35 magnets are limited to 80 °C.

# Equivalent-coil model, limitations and open items

The equivalent-coil model is calibrated, not independently predictive. Each phase per board is 8 stranded sector coils on two layer slabs, which keeps the angular and radial position of the coil sides, the board heights and the phase polarity. With geometric turns (Ncoil = 2.006) it gives K ≈ 23.0 mN·m/A, 24 % high. One factor of 0.809 (Ncoil = 1.623) matches the full-motor value, so agreement after calibration is not a further validation of the absolute torque. It is useful for fast sensitivity studies (geometry changes, Rev1-S). After calibration:

- every board agrees within about ±4 % (spread 7.1 %);
- the phases agree within 1.1 %;
- the phase angle is within 0.4° and the phase displacement is 120.0°.

Copper resistance and loss are handled outside the field model, with no bulk conducting block.

Limitations:

- **Backplate:** modelled at OD 86 / ID 19 mm, but the hardware is 80 / 25 mm. A correction run is pending; the effect is expected but not shown to be small.
- **Stack spacing:** modelled with a 1.02 mm board pitch, giving a 5.10 mm stack. The assembled stack measured 5.1 mm maximum, so the spacing matches the model.
- **Air gap:** a 1.0 mm target, unmeasured. Each extra 0.25 mm lowers K by about 7 %.
- **Resistance:** measured on both stators (1.87–1.90 Ω), temperature not recorded; contact and copper parts not separated.
- **Rotating model:** field only. The loaded waveform is reconstructed with ideal sinusoidal currents. Armature reaction is neglected, which is valid for a coreless stator (mT armature field against 0.2–0.4 T from the magnets). Inverter ripple losses are not included.
- **Eddy-loss estimate:** samples B at track mid-points and may be 10–20 % high. Pads, pours and vias are not included.
- **Thermal:** no model of the as-built assembly yet.

**Expected simulation-to-hardware gap.** The models were built before the hardware was finalised. The prototype differs in backplate size (80 / 25 mm against 86 / 19 mm), and possibly in stack spacing and air gap. Measured torque and back-EMF are therefore expected to differ from these predictions by more than the 0.03–5 % agreement between the simulation methods. The sensitivities above give the likely size: about 7 % per extra 0.25 mm of air gap and about 4 % per 0.1 mm of inter-board gap. The backplate change is expected to be smaller but is not quantified.

**Recommendation.** In future work, build and measure the hardware first: backplate, holders, stack thickness and assembled air gap. Then rebuild the simulation model to those measured dimensions before testing. The equivalent-coil model, already calibrated here, is the fast route for that rebuild. Simulation and test would then compare like with like, and the remaining differences would show modelling error rather than geometry mismatch.
