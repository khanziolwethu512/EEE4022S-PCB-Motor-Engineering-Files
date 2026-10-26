# EEE4022S — PCB Axial-Flux Motor Engineering Evidence

Supporting technical evidence for the UCT 2026 final-year project *Design, Analysis and Prototyping of a PCB Motor: Evaluating a Two-Stage Coreless Axial-Flux Configuration*.

## Authorship

The original PCB winding and Altium design are the work of **Paul Gould**: https://github.com/gouldpa00/magnetless_motor . They are not original EEE4022S designs. Preserve their upstream license and provenance with redistributed originals or derivatives. See [ATTRIBUTION.md](ATTRIBUTION.md).

## Evidence folders

- `01_PCB_source_Altium_Gerber_ODB` — PCB source and fabrication outputs
- `02_PCB_geometry_extraction_and_reconstruction` — connectivity and geometry reconstruction
- `03_Maxwell_model_build_scripts` — electromagnetic model scripts
- `04_HPC_UCT_cluster` — HPC runner and logs
- `05_Results_nominal_1mm` — nominal Rev0 and Rev1-S outputs
- `06_Results_asbuilt_Rev0_4mm` — as-built model exports
- `07_Analytical_verification` — analytical model and cross-checks
- `08_Operating_points_sweeps_efficiency` — predicted operating points
- `09_Thermal_Icepak` — thermal model evidence
- `10_AEDT_projects_early_exploration` — early exploratory models
- `11_Experimental_measurements` — measured data and oscilloscope captures
- `12_Mechanical_drawings_BOM_procurement` — mechanical CAD, drawings and parts
- `13_Technical_records_and_reports` — supporting reports

## Verification and limitations

Some large solved HPC databases are unavailable. The three October 23 oscilloscope captures read 101.71, 103.37 and 98.78 mV AC RMS (mean 101.29 mV); exact handheld-probe terminal connections remain undocumented. Refer to the main report for the scope of validation.

**Upload status:** evidence files are being staged from the prepared archive. Missing folders in the online repository should not be interpreted as published evidence.
