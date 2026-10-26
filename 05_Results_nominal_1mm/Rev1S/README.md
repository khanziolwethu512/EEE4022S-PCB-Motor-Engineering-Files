# Rev1-S results

Rev1-S is two Rev0 stators and two Rev0 rotors in the order S1 – R1 – S2 – R2. S2 sits between R2's magnets (1.0 mm gap) and R1's bare steel backplate (1.0 mm, assumed). In the models the stators are connected in series per phase.

**Headline:** K = 39.50 mN·m/A from the board-by-board FEM (S1 18.54 + S2 20.96). The Rev0-calibrated equivalent-coil model, not refitted, gives 39.30 (−0.5 %). In series that is 59.2 mN·m per A pk, with 2.925 V rms phase and 5.066 V rms line back-EMF at 1000 rpm. The torque constant is defined by T = 1.5·K·I_pk.

The Rev1-S full-motor detailed static solve ran for 47 h on the HPC and was stopped by the scratch quota before finishing one angle. There is no full-motor Rev1-S result. Rev0's full-motor result (in the `rev0` branch) is the reference that validates the board-by-board method.

## Where to find what (for the report)

| Report topic | File |
|---|---|
| Torque constant, all methods | `07_reports/Rev1S_Maxwell_Technical_Report.pdf` (Torque constant section). Sources: `01_.../`, `02_.../`, `04_.../eq_calibration_summary.txt`, `03_.../fmrot_summary.txt` |
| Back-EMF waveforms and harmonics | `05_figures/fig1_backemf_rev1s.png`; data in `03_.../fmrot_waveforms.csv` |
| Torque ripple and cogging | `05_figures/fig2_torque_cogging_rev1s.png`; `03_.../FMR_Torque.csv` (two columns, one per rotor) |
| Field distribution | `05_figures/fig3_field_maps_rev1s.png`; animation `05_figures/anim_Bz_stator_face_rev1s.gif`; raw files in `03_.../B_S1`, `B_S2up` (S2 face toward R2's magnets), `B_S2low` (S2 face toward R1's steel), `Bsteel_R1_BackIron`, `Bsteel_R2_BackIron` |
| Current density | Same boards as Rev0: use the Rev0 figure, or `03_.../current_density_board1_per_A.csv` |
| Losses and efficiency | `05_figures/fig5_efficiency_rev1s.png`; `06_tables/efficiency_rev1s_measuredR.csv`; `06_tables/loss_table_for_icepak.csv` |
| Predicted operating points for both motors | `07_reports/Rev0_Rev1S_Predicted_Operating_Points.pdf` (rev. C) |
| Part C report (whole project, 16 pages) | `07_reports/PartC_Report_AK07.pdf` |

## Folder contents

**01_lab_board_by_board_fem_S2**: detailed single-board solves of S2's five boards in the Rev1-S environment (lab PCs).
- `REV1S_S2_J1…J5_P20`: board j counted from R1's steel side. K = 2.597, 3.057, 3.812, 4.938, 6.559 mN·m/A; sum 20.96.
- `REV1_S2ENV_G100_T20`: setup check of the S2 environment.
- S1 is the Rev0 stack (18.54 mN·m/A).

**02_lab_field_maps**: Rev1-S field-only full-motor runs. `FIELDMAP_REV1S_P20` is the reference: K = 41.64 mN·m/A on the field-map basis.

**03_rotating_field_only_fmrot**: both rotors turning at 1000 rpm, one electrical period in 24 steps, two rotating bands, 32 cores, 122 GB peak (UCT HPC, job 1502103).
- `fmrot_summary.txt`:
  - check against the field map: PASS, worst 1.59 % over 240 points;
  - K per phase, board and stator: S1 19.47 and S2 22.10 on the field-map basis;
  - harmonics, ripple, cogging, eddy loss (44 mW) and field statistics.
  - Multiply field-map-basis values by **0.950** (39.50 / 41.564); the figures already do this.
  - The efficiency table in this file uses the trace-model resistance; use `06_tables/` instead.
- Other files have the same meaning as in Rev0.

**03b_rotating_short_check**: the first 6 time steps only, the earlier validation run (job 1500415). PASS, 1.51 %.

**04_equivalent_coil_calibration**: all 10 boards, 3 phases, 8 rotor angles.
- 7 angles were solved on the HPC before the disk quota corrupted the project. The 8th (39.375°) was filled by half-wave antisymmetry (T(θ + 22.5°) = −T(θ), checked to 0.08 mN·m on the solved pairs) and calibrated offline with `analysis/calibrate_eq_offline.py`.
- Result: Ncoil 1.631 (× 0.813), board spread 9.0 %, phase spread 0.87 %. Verdict: USABLE.
- With Rev0's factor (0.809) instead, the machine K is 39.30 mN·m/A.
- Files: `eq_progress.json` (raw solved torques), `EQ_Torques.csv`, `eq_calibration_summary.txt`, `EQ_REV1S_CALIBRATION.json`.

**05_figures**: report figures (made with `analysis/figs_generic.py`, using `KREF=39.50 KCL=41.564 TAG=rev1s NAME=Rev1-S RPH=4.118 PEDD=0.0442`).

**06_tables**:
- `efficiency_rev1s_measuredR.csv`: series connection, R = 4.32 Ω at 60 °C, from both stators' measured 1.87–1.90 Ω (1.89 Ω used).
- `loss_table_for_icepak.csv`: per-board losses.
- `fig_numbers.json`: caption numbers.

**07_reports**:
- `Rev1S_Maxwell_Technical_Report` (PDF, Word, Markdown).
- `Rev0_Rev1S_Predicted_Operating_Points` (PDF, Word; source `Ratings.md`), rev. C: bench-test baseline, not continuous ratings.
- `PartC_Report_AK07` (PDF, Word): the full Part C report.

## Caveats

These are the same as for Rev0, plus:
- the S2-to-R1 clearance is assumed (1 mm);
- both stators' resistance is measured (1.87–1.90 Ω); in parallel, S2's 13 % higher back-EMF unbalances the current sharing (see the operating-points sheet);
- there is no completed full-motor Rev1-S solve.
