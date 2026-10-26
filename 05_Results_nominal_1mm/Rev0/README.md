# Rev0 results

Rev0 is one stator of 5 PCBs and one rotor of 16 N35 magnets on a 2 mm steel backplate. The modelled geometry has a 1.0 mm air gap, a 1.02 mm board pitch and an 86 / 19 mm backplate.

**Headline:** K = 18.534 mN·m/A from the full-motor FEM. That is 27.8 mN·m per A pk, with 1.372 V rms phase and 2.377 V rms line back-EMF at 1000 rpm. The torque constant is defined by T = 1.5·K·I_pk.

## Where to find what (for the report)

| Report topic | File |
|---|---|
| Torque constant, all methods compared | `01_full_motor_static_hpc/RESULTS.txt` (top table and per-board table) |
| Per-board torque constant | `01_full_motor_static_hpc/Rev0_boards.csv` |
| Back-EMF waveforms and harmonics | `06_figures/fig1_backemf_rev0.png`; data in `02_rotating_field_only_fmrot/fmrot_waveforms.csv`; harmonics in `fmrot_summary.txt` |
| Torque ripple and cogging | `06_figures/fig2_torque_cogging_rev0.png`; `02_.../FMR_Torque.csv` (no-load rotor torque) |
| Field distribution (air gap and steel) | `06_figures/fig3_field_maps_rev0.png`; animation `06_figures/anim_Bz_stator_face_rev0.gif`; raw field files in `02_.../B_S1_t*.fld` and `Bsteel_BackIron_t*.fld` |
| Current density | `06_figures/fig4_current_density_rev0.png`; data in `02_.../current_density_board1_per_A.csv` |
| Losses and efficiency | `06_figures/fig5_efficiency_rev0.png`; `07_tables/efficiency_rev0_measuredR.csv`; per-board eddy loss in `02_.../loss_table_for_icepak.csv` |
| Equivalent-coil model | `03_equivalent_coil_calibration/eq_calibration_summary.txt` |
| Lab field map and board-by-board FEM | `04_lab_field_maps/`, `05_lab_board_by_board_fem/` |
| Full write-up | `08_reports/Rev0_Maxwell_Technical_Report.pdf` (Word and Markdown versions alongside) |
| Predicted operating points for the test bench | `08_reports/Rev0_Rev1S_Predicted_Operating_Points.pdf` (rev. C) |
| Part C report (whole project, 16 pages) | `08_reports/PartC_Report_AK07.pdf` |

## Folder contents

**01_full_motor_static_hpc**: all 5 boards and the rotor meshed together. Magnetostatic, 3-phase synchronous current at 1 A pk, rotor angles 0° and 3.75°, 6 adaptive passes, about 110 GB and 17.5 h per angle on 40 cores (UCT HPC, job 1466609).
- `RESULTS.txt` / `RESULTS.json`: summary. Copper (Lorentz) torque against rotor virtual-work torque, which agree within 0.51 % and 0.18 %; comparison with the field map and the board-by-board sum; steel field.
- `Rev0_angles.csv`: torque per angle. `Rev0_boards.csv`: K per board. `Rev0_summary.json`: everything in machine-readable form.
- `hpc_supervisor_rev0.log`: run log.
- The Rev1-S rows in `RESULTS.txt` show "no solved angle". That run was stopped by the disk quota; see the `rev1s` branch.

**02_rotating_field_only_fmrot**: the rotor turns at 1000 rpm through one electrical period (7.5 ms) in 24 steps, with magnets and steel only. B is exported on 180 775 trace centre-line points per step. (UCT HPC, jobs 1500352 and 1500707.)
- `fmrot_summary.txt`: K per phase, board and stator; back-EMF and harmonics; balance; check against the field map (PASS, worst 1.49 %); torque ripple; cogging; eddy loss; field statistics; current density; efficiency.
  - Values are on the field-map basis, K = 19.475 mN·m/A. Multiply by **0.952** (18.534 / 19.475) for the full-motor basis; the figures already do this.
  - The efficiency table in this file uses the trace-model resistance (1.33 Ω). Use `07_tables/` instead, which uses the measured value.
- `fmrot_waveforms.csv`: per step, rotor angle, k(θ) and back-EMF of each phase (V at 1000 rpm), and torque at 1 A pk with sinusoidal currents.
- `fmrot_results.json`: all of the above in machine-readable form.
- `FMR_Torque.csv`: Maxwell rotor torque at no load (cogging plus solver noise). `FMR_Loss.csv`: magnet solid loss, zero because there is no armature field in this model.
- `B_S1_t*.fld`: B on a polar grid 0.25 mm off the stator face, at 8 instants (x, y, z in mm; Bx, By, Bz in T).
- `Bsteel_BackIron_t*.fld`: B at the backplate mid-thickness. NaN rows are points outside the steel.
- `current_density_board1_per_A.csv`: every track piece of board 1 with its current share and J per 1 A.
- `loss_table_for_icepak.csv`: per-board copper and eddy loss at 1000 rpm and 1 A pk.
- `rev0_run_log.txt`: the model's own log. `*.pts` / `probe.*`: export point lists.
- Removed: `B_on_traces_step001.fld` (25 MB raw export) and the progress file.

**03_equivalent_coil_calibration**: 8 stranded sector coils per phase per board, magnetostatic, all 3 phases at 1 A DC, 8 rotor angles (job 1500351).
- Result: geometric turns give K 24 % high. Calibrated Ncoil is 1.623 (× 0.809), with board spread 7.1 %, phase spread 1.1 % and phase error ≤ 0.4°. Verdict: USABLE.
- `EQ_REV0_CALIBRATION.json`: per-board correction factors. `EQ_Torques.csv`: raw torques per coil group and angle.

**04_lab_field_maps**: field-only full-motor magnetostatic runs on the lab PCs, 8 rotor angles.
- `fieldmap_results.json`: K per board and phase. `*_summary.txt`: readable summary.
- `FIELDMAP_REV0_P20` (20 mm region padding) is the reference used everywhere. The other folders are mesh and padding checks.

**05_lab_board_by_board_fem**: detailed single-board solves (real traces and vias) on the lab PCs.
- `REV0_DOE_D100…D508_P20`: boards 1–5 at their distances from the magnets. Their sum gives 18.540 mN·m/A.
- `REV0_LIN_D100_P20_2A`: linearity check at 2 A.
- `REV0_REF_ROTOR_MS_SWEEP` / `_3PH`: reference rotor-angle sweeps.
- `REV0_CHECK_PHB/PHC`: phase B and C checks.
- `REV0_STACK_JUNCTION_TEST`: board-to-board junction resistance.
- `REV0_FULL_SOLVE_ATTEMPT`: lab-PC full-motor attempt (ran out of memory).
- `REV0_DOE_D050`, `D500*`, `BI50`: early design-of-experiments points.

**06_figures**: report figures at 200 dpi. Back-EMF values are scaled to K = 18.534. Made with `analysis/figs_rev0.py`.

**07_tables**:
- `efficiency_rev0_measuredR.csv`: efficiency at 500, 1000 and 2000 rpm for 0.5–2 A pk, using R = 2.16 Ω at 60 °C from the measured 1.87–1.90 Ω (1.89 Ω used).
- `fig_numbers.json`: the numbers quoted in the figure captions.

**08_reports**:
- `Rev0_Maxwell_Technical_Report` (PDF, Word, Markdown).
- `Rev0_Rev1S_Predicted_Operating_Points` (PDF, Word; source `Ratings.md`), rev. C: bench-test baseline, not continuous ratings.
- `PartC_Report_AK07` (PDF, Word): the full Part C report.
- `earlier_Rev0_modelling_report_2026-10-07.pdf`: the earlier lab-PC modelling report.

## Caveats

- The modelled geometry differs from the hardware: backplate 86 / 19 mm in the model against 80 / 25 mm built; the air gap and stack spacing are not yet measured.
- The rotating model is field-only. The loaded torque waveform is reconstructed with ideal sinusoidal currents.
- Efficiencies are electromagnetic only; bearing and windage losses are not included.
