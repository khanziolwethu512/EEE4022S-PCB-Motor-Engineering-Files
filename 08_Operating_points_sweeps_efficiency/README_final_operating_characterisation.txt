EEE4022S final operating characterisation - Rev0 and Rev1-S, ORIGINAL 1 mm-gap simulation geometry (22 Oct 2026)
Constructed Rev0 prototype NOT covered. Experimental testing postponed. Only winding resistance is measured.

0_provenance/            Gate 0: provenance_inventory.csv/.md (sources, job IDs, labels), test_matrix_status.csv
1_EM_checks_HPC_v12/     Gate 1: hpc_motor.py (sha 680501337171) + HPC_RUN_STEPS_v12.txt - Rev1-S +/-I, 500/2000 rpm
                         rotating solves, optional 0.25/0.75 A; acceptance criteria stated in the steps file
2_thermal/               Gate 2: thermal_revision.py; out/ (R_th extraction, limits for scenarios A-D, Ta 25/30 C,
                         short-time limits, T0/T1 plots); icepak_run2/ lab-PC scripts re-solving the limit points with
                         the measured heat (optional confirmation)
3_sweeps_envelopes/      Gate 3: sweeps.py; out/ K0 constants, C1 current, S1 speed, E1 DC-bus, F1 envelopes,
                         F2 efficiency grids (CSV) and plots P1-P6
4_report/                Gate 4: Ch3-5 material (.docx, TNR 11 pt, 1.5 spacing; .pdf preview), specs.md (conditional
                         specifications + blocking assumptions), verification_evidence.md
Rerun order: python 0_provenance/audit.py; python 2_thermal/thermal_revision.py; python 3_sweeps_envelopes/sweeps.py;
python 4_report/specs.py; python 4_report/content.py; node 4_report/render.js report_content.json out.docx
(sweeps.py reads the archived HPC results from the session's arch/ folder; the CSV outputs are included.)
Labels: FEM / FEM (calibrated) / ANALYTICAL / THERMAL-FEM / THERMAL-LUMPED / CIRCUIT / MEASURED / ASSUMED.
"P_out,EM" and "eta_EM" are electromagnetic quantities, NOT shaft output or mechanical efficiency.
