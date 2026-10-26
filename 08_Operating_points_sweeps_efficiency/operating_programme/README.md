# EEE4022S — Final operating characterisation handover (22 Oct 2026)

**Scope:** Original 1 mm-gap, 86 mm OD / 19 mm ID simulated Rev0 (S–R, five series PCBs/phase) and Rev1-S (S–R–S–R, ten series PCBs/phase), both 16 poles and star-connected. The manufactured 4 mm-gap Rev0 hardware is documented separately and is **not** the geometry for this campaign. No new FEM or Icepak solves are claimed in this package.

## Verified baseline from prior work

| Quantity | Rev0 | Rev1-S series | Basis |
|---|---:|---:|---|
| K (mN m/A peak-phase coefficient) | 18.534 | 39.50 | Detailed-copper FEM reference |
| T at 1 A peak (mN m) | 27.80 | 59.25 | 1.5 K Ipk |
| E line-line at 1000 rpm (V rms) | 2.377 | 5.066 | Rotating field with detailed-copper scaling |
| Rph (ohm) | 1.89 | 3.78 | Measured five-board stator and series assumption |
| Lph estimate (microhenry) | 34–51 | 74–113 | Armature-only FEM (not measured, not independent analytical) |
| f_e at 1000 rpm (Hz) | 133.333 | 133.333 | Eight pole pairs |

Analytical sheet-current model K approximately 18.54 (Rev0) and 39.55 (Rev1-S); prior diagnostic indicates close agreement with detailed FEM. Independent FEM work remains source-record dependent.

## Execution gates

**Gate 0 — Provenance:** inventory existing AEDT/HPC projects and raw CSVs; retain previous results; verify series electrical connection polarity and all terminal assignments. Do not launch expensive jobs simply to replicate solved cases.

**Gate 1 — EM:** confirm reference operating point at 1000 rpm, then run only missing targeted current and rotating-speed checks; verify speed scaling and dynamic-current assumptions.

**Gate 2 — thermal:** revisit Icepak with measured 1.89-ohm/stat or assumed 3.78-ohm series winding, temperature adjustment, actual two-stator heat distribution and selected ambient/cooling conditions. The thermal model housing remains hypothetical, not as-built.

**Gate 3 — circuit:** dq current constraints at id=0 and SVPWM voltage limits. Vdc is not motor line voltage. Compute current at each requested speed, bus voltage and thermal constraint. Use actual L uncertainty range; do not silently use the old 25 microhenry assumption.

**Gate 4 — report:** label all outputs as measured / analytical / FEM / circuit-model / thermally inferred. State that mechanical shaft power/efficiency and validated continuous rating are unavailable without measurements. Include plots, raw tables and solver/job identifiers.

## Existing baseline software audit

`operating_baseline_phase2.py` is an archived reference, not a newly validated final tool. It assumes id=0, SVPWM m=0.95, 25 C ambient, 60 C winding, 12V Rev0 / 24V Rev1-S, 51/113 microhenry L, shared per-stator heat in Rev1-S, and 1000-rpm eddy loss scaled as speed squared. Its ``P_mech_W`` is **electromagnetic conversion power** T_em * omega, not verified shaft output; ``eff_pct`` excludes mechanical and inverter losses. For Rev1-S, equal thermal-loss allocation must be checked against the Icepak stator asymmetry. Adjust naming before using its output in the thesis.

## Deliverables

1. Provenance inventory and completion status for the test-matrix rows.
2. Archived-versus-new status for each numerical series with settings and HPC job IDs.
3. Raw results and figures for torque-current, EMF-speed, voltage-limited torque-speed, temperature-current, and comparative motor constants.
4. Tabulated *conditional* current and voltage limits including input assumptions and uncertainties.
5. Concise methods/results/discussion content for Chapters 3–5, preserving report formatting (11 pt Times New Roman, 1.5 spacing, Chapters 1–7 ≤50 pages).

**Important:** The final numerical verification diagnostic does not independently establish actual magnet remanence, assembly tolerances or experimental motor torque. Avoid claiming physical validation.
