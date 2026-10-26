# EEE4022S — Analytical verification phase 1 (22 October 2026)

## Purpose
Independent *spatial harmonic attenuation* calculation using only pole count and mean magnet radius. It checks relative changes across PCB boards in Rev0; it is **not** an independent absolute torque, EMF, or field-amplitude prediction. The CSV contains FEM data from the existing `AK07_Final_Simulation_Results.zip` archive and serves only as the comparison dataset.

## Assumptions and derivation
16 poles = 8 pole pairs. Mean magnet radius r = 28 mm. The tangential fundamental field wavenumber for a locally planar periodic pole array is k = p/r = 8/28 = 0.285714 mm^-1. In the source-free region, a harmonic field amplitude falls approximately as exp(-k Δz). Thus relative board response (assuming similar conductor geometry on all PCBs) is K_j/K_1 ≈ exp[-k(z_j-z_1)]. The approximation ignores finite magnet shape, high harmonics, steel returns, and flux through the complete conductor path.

## Result
- Board 5 / board 1: analytical 0.3116; detailed FEM 0.2908.
- Sum of 5 PCB coefficients / PCB 1 coefficient: analytical 3.0340; detailed FEM 2.9514.
- Fitted FEM endpoint decay k = 0.30266 mm^-1, compared with geometry-only 0.28571 mm^-1.
- These are relative checks; DO NOT use FEM Board 1 amplitude as 'analytical' K amplitude.
- Rev1-S S2 faces a different return-path environment; a separate two-rotor/two-backplate analytical boundary-value model or explicit field model is needed.

## Next phase for Claude
1. Recover original mini_wave-bb winding coordinates/copper trace paths (or authentic extracted path data) and magnet positions/magnetization; record provenance.
2. Derive Bz(r,theta,z) independently using a segmented magnet surface-charge/Coulomb or Fourier harmonic representation with stated steel approximation. Do not import Maxwell B-field values into analytical prediction.
3. Integrate dT_z = [r × (I dl × B)]_z along all conductor paths and layers, retaining winding polarity and PCB rotations for Rev0 and Rev1-S.
4. Compute flux linkage and emf from independent flux-linkage or reciprocity derived from the analytical winding and field (not FEM-derived K).
5. Report error to validated FEM per board, by phase and for both machine totals. Include sensitivity to steel return and finite magnet dimensions; differentiate independent predictions from calibrated models.
6. Provide phase R based on measured or layout conductor lengths and widths (ideal copper R analytically, measured R separately), copper loss, simple magnetostatic energy inductance estimate, and a clearly conditional thermal resistance model.
7. Then proceed to FEM verification and subsequent circuit, current, speed, voltage, Icepak sweeps. Current, speed, and voltage cannot be independent degrees of freedom in a voltage-controlled PMSM steady state: specify load/commutation/controller and solve consistent operating points.

## Reproduce
`python analytical_verification.py` (Python 3 standard library only).
