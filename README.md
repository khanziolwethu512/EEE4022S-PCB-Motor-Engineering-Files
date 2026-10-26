# EEE4022S — PCB Axial-Flux Motor Engineering Evidence

Supporting engineering material for *Design, Analysis and Prototyping of a PCB Motor: Evaluating a Two-Stage Coreless Axial-Flux Configuration* (UCT, 2026).

**Read the report first.** This repository supports reproduction and audit; some large solved Ansys project databases are unavailable or excluded. Numerical predictions are distinguished from measured results in the report.

## Provenance and credits
**The PCB winding was originally designed by Paul Gould**: https://github.com/gouldpa00/magnetless_motor . See [ATTRIBUTION.md](ATTRIBUTION.md) and the unchanged upstream licence and originals within `01_PCB_source_Altium_Gerber_ODB/Gould_original_magnetless_motor/`. The author's original contributions are in modelling, comparison, verification, mechanical fabrication and testing, not invention of Gould's winding.

## Evidence map

| Folder | What the marker can inspect | Report sections |
|---|---|---|
| 01_PCB_source_Altium_Gerber_ODB | Original source, extracted PCB manufacturing and connection files | 3.2, 3.4 |
| 02_PCB_geometry_extraction_and_reconstruction | Geometry scripts and connectivity validation | 3.4 |
| 03_Maxwell_model_build_scripts | Ansys Maxwell model-generation code | 3.4–3.6 |
| 04_HPC_UCT_cluster | HPC runner, job setup and logs | 3.6, 4.2 |
| 05_Results_nominal_1mm | Rev0 and Rev1-S nominal simulation exports and evidence | 4.2–4.8 |
| 06_Results_asbuilt_Rev0_4mm | As-built Maxwell outputs, logs and provenance | 3.10, 4.9, Appendix F |
| 07_Analytical_verification | Independent calculations and model comparisons | 4.2, Appendix F |
| 08_Operating_points_sweeps_efficiency | Derived operating-point and speed sweep calculations | 4.8, Appendix E |
| 09_Thermal_Icepak | Thermal model scripts and available outputs | 3.7, 4.7 |
| 10_AEDT_projects_early_exploration | Early AEDT projects; not final solved verification | 3.4 |
| 11_Experimental_measurements | Laboratory workbook, oscilloscope screenshots and prototype photos | 3.9, 4.10 |
| 12_Mechanical_drawings_BOM_procurement | Drawings, fabrication instructions, BOM | 3.8 |
| 13_Technical_records_and_reports | Supporting technical reports, assumptions and logs | Appendices D–G |

## Important limitations
- The original archived evidence was curated for marker navigation. It is not a complete backup of all solver scratch files or deleted Maxwell databases.
- The screenshots include **three** 23 October 2026 oscilloscope captures. They display AC RMS values of 101.71, 103.37, and 98.78 mV, whose mean is **101.29 mV**; the report version using the earlier two-capture mean must be updated separately. The oscilloscope probe connection was handheld and the exact terminals remain undocumented.
- Drawings include earlier iterations as well as final 80 mm OD/25 mm ID templates. Check filenames and revision status before fabrication.
- `FILE_INDEX.csv` contains SHA-256 checksums for all files in this prepared package.

## Publication status
This is a *repository-ready file package*, not proof of a published GitHub repository. Upload to a new repository and add its final URL to Appendix B.
