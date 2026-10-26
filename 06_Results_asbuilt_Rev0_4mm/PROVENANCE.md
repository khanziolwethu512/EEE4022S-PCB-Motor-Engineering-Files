# Rev0 as-built study - provenance and validation record (24 Oct 2026; geometry provenance updated 25 Oct 2026)

Solver: Ansys Electronics Desktop 2025 R2, Maxwell 3D magnetostatic, UCT HPC (partition ada, account eleceng).
Runner: hpc_motor.py sha 4e7fbd6fee7d (code_946d6dcedc); submitted with submit_v14.sh.

| Case | Profile | SLURM job | Status |
|---|---|---|---|
| A nominal (reused) | FIELDMAP_REV0_HW | 1521344 (23 Oct) | complete |
| A field maps | FIELDMAP_REV0_A_PROBE | 1526909 | complete (1 angle; its K line is not used) |
| B gap only | FIELDMAP_REV0_B_G400 | 1526905 | complete |
| C as built | FIELDMAP_REV0_C_ASBUILT | 1526906 | complete |
| C at 3.5 mm | FIELDMAP_REV0_C350 | 1526910 | complete |
| C at 4.5 mm | FIELDMAP_REV0_C450 | 1526911 | complete |
| C detailed board 1 | DIAG_REV0_C_B1 | 1526907 | complete (25 Oct) |
| C detailed board 5 | DIAG_REV0_C_B5 | 1526908 | complete (25 Oct) |

Reference results: the 4.0 mm-gap field maps (Cases B, C and the 3.5/4.5 mm band) are the reference, K(C) = 7.554
mN.m/A with a method uncertainty of about +/-0.5 % from the detailed-copper verification (below).

As-built geometry and materials (confirmed from the prototype photographs and video, 25 Oct 2026):
- Rotor backplate: steel, 80 mm OD / 25 mm ID / 2 mm, ferromagnetic - MODELLED (steel_1010).
- Shaft/support tube, hub ring locating the backplate, bore ring on the magnet face, stator end plates: 3D-printed
  PLA - non-magnetic and non-conducting (mu_r ~ 1, sigma ~ 0), represented as AIR.
- Metallic fasteners: steel screws/nuts fixing the backplate to the PLA hub (ring at r ~ 12-14 mm) and at the rim;
  threaded rods and nuts clamping the stator stack outside the active winding region - NOT MODELLED (small, outside
  the magnet track r = 18-38 mm; effect expected minor, not quantified).
- Dynamometer shaft and blue coupling: outside the model region.
- The solved Case C (FIELDMAP_REV0_C_ASBUILT) contains an 8 mm steel shaft at r <= 4 mm, separate from the plate,
  hub = air. This is slightly MORE steel than the PLA prototype, so it bounds it. The whole nominal-to-as-built rotor
  change is +0.09 % in K, so no separate PLA-shaft run was made (decision confirmed by the user, 25 Oct 2026).

Independent analytical prediction (asbuilt_analytical.py, no Maxwell input, no measurement) was computed BEFORE the
HPC runs: K(4.0 mm) = 7.539 mN.m/A, 96.7 mV rms line-to-line at 100 rpm.

Source classification of the reported values:
- K, harmonics, field maps: FEM (field map), corrected board by board with the ANALYTICAL sheet/centre-line ratio.
- Back-EMF at 50/100/150/1000 rpm: FEM coefficient x speed (speed-scaled, not separate transient solutions).
- Uncertainty band: FEM at 3.5/4.5 mm combined with the N35 remanence range 1.17-1.22 T (datasheet; the model uses
  the AEDT library value 1.23 T).
- 0.096 V at 100 rpm: preliminary MEASURED value, not used for calibration.

Checks (criteria fixed before the runs): Case A corrected K -0.11 % vs full-motor FEM (pass, 0.5 %); method vs
archived rotating solution K +0.04 %, E +0.03 %, H3 5.5 %, ripple 1.30 vs 1.26 % (pass); static-field eddy loss
21.6 vs 20.35 mW (+6.2 %, outside the 5 % criterion - affects only the eddy-loss figure); all psi within 0.3 deg of
-30 deg, phase steps 120.0 deg (pass).
Detailed-copper verification, Case C (DIAG_REV0_C_B1 at 4.000 mm, DIAG_REV0_C_B5 at 8.081 mm):
- copper (+I - -I)/2 2.5270 / 0.7643 mN.m/A; rotor virtual work 2.5273 / 0.7741 -> +0.01 % / +1.28 % (pass, 3 %).
- copper vs analytical sheet-current 2.5206 / 0.7607 -> +0.25 % / +0.48 % (correction confirmed at 4 and 8 mm).
- corrected field map 2.4908 / 0.7607 vs copper -> -1.43 % (board 1, FAILS the 1 % criterion) / -0.48 % (pass).
  Cause: field-map flux density at board 1 is 1.2 % below the detailed model's own magnet field (centre-line
  2.710 vs 2.743); field-map per-board scatter -1.2 to +3.4 % vs analytical, cancelling to +0.12 / +0.21 % in the
  stack total (B / C). Substituting both detailed boards: K(C) 7.554 -> 7.594 (+0.53 %, +0.5 mV at 100 rpm).
  Reported values NOT changed; recorded as +/-0.5 % method uncertainty.
Conventions: T = 1.5 K I_pk (balanced sinusoidal currents in phase with the back-EMF), e_ph,pk = K w_m,
psi_pm = K / p (p = 8), E_LL,rms = sqrt3 K w_m / sqrt2, f_e = n/60 x 8.
