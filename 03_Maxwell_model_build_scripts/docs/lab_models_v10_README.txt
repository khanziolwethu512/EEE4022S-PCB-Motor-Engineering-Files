REV0 PIPELINE v10.0 (2026-10-14) - two SIMPLIFIED ROTATING full-motor models for the lab PCs
================================================================================================
Why: the detailed trace-level motor cannot be meshed for a rotating run (HPC smoke test: one board + rotor did
not finish meshing in 3.6 h on one core; the mesher is single-threaded). These two models remove the traces from
the mesh in two different ways. Both are validated against the static field map you already have
(FIELDMAP_REV0_P20 / FIELDMAP_REV1S_P20, gate passed 8 Oct).

INSTALL
  Copy every file in this folder into your existing rev0 folder (OneDrive ...\EEE4022S Ansys files\Motor run\rev0),
  replacing config.py (the new one only ADDS profiles; nothing old changes). New modules: fm_rotating.py, eqcoil.py,
  transient.py. Check that ...\Motor run\results\FIELDMAP_REV0_P20_results\fieldmap_results.json exists (and the
  REV1S_P20 one for Rev1-S) - both models validate against it.
  Every model is the COMPLETE motor: all 5 boards x 3 phases of every stator + rotor(s); every result is
  given per phase (A, B, C), per board, per stator and for the machine, and checked phase by phase.
  Run a runner with AEDT 2025 R2: Tools > Run Script > run_....py. Each runner is restartable (run it again after a
  crash/freeze; finished parts are skipped). Results are copied to ...\Motor run\results\<PROJECT>_results.

MODEL A - FIELD-ONLY ROTATING TRANSIENT (fm_rotating.py)  "FMROT"
  Maxwell: magnets (eddy ON) + rotor steel + air, rotor turning at 1000 rpm in a band (Rev1-S: two bands). NO copper
  in the mesh. At every time step B is exported on the real trace centre-lines (180 775 points for Rev0) and the
  torque / back-EMF are integrated there (the validated field-map method), plus a thin-conductor copper eddy-loss
  estimate. Maxwell gives magnet eddy loss and cogging. Armature reaction is neglected (as in the field map).
    1. run_FMROT_REV0_SHORT.py   6 steps (rotor 0 -> 5.625 deg). Look in fmrot_summary.txt for
                                 "SHORT-RUN CHECK ... PASS" and in rev0_run_log.txt for the solve time per step.
    2. run_FMROT_REV0.py         one electrical period, 48 steps -> fmrot_summary.txt (K, back-EMF + harmonics,
                                 loaded torque + ripple, losses, GATE vs field map), fmrot_waveforms.csv.
    3. run_FMROT_REV1S_SHORT.py, then run_FMROT_REV1S.py  (same for Rev1-S)
  Disk: fields are saved every step (maybe 5-10 GB per full run on D:). The B files are deleted after reading.

MODEL B - EQUIVALENT-COIL STATOR (eqcoil.py)  "EQ"   (see EQ_coil_layout.png)
  Each phase of each board = 8 closed sector coils placed where the traces carry their radial current (measured from
  traces_board.json), on two layers symmetric about the board mid-plane (A: L1+L6, B: L2+L5, C: L3+L4), stranded,
  all in series. The copper IS in Maxwell -> armature reaction included, Maxwell computes torque, EMF, flux.
  Because the coils are an idealisation they are CALIBRATED against the field map first:
    1. run_EQ_REV0_CAL.py        magnetostatic, all 3 phases at 1 A, 8 rotor angles -> eq_calibration_summary.txt
                                 (K per board AND phase vs field map, psi errors, phase balance) and
                                 results\EQ_REV0_CALIBRATION.json (calibrated turns). Must say "USABLE".
    2. run_EQ_REV0_ROT_SHORT.py  6 steps no-load + 6 steps loaded (timing / sanity)
    3. run_EQ_REV0_ROT.py        one period no-load (back-EMF) + one period loaded 1 A (torque WITH armature
                                 reaction) -> eq_rot_summary.txt
    4. Rev1-S: run_EQ_REV1S_CAL.py, then _ROT_SHORT, then _ROT.

SUGGESTED USE OF THE LAB PCs (in parallel)
  PC1: FMROT_REV0_SHORT -> FMROT_REV0 -> FMROT_REV1S_SHORT -> FMROT_REV1S
  PC2: EQ_REV0_CAL -> EQ_REV0_ROT_SHORT -> EQ_REV0_ROT
  If a SHORT run takes more than ~3 min per time step, or a PC freezes, stop and move that model to the HPC.

WHAT EACH MODEL GIVES (project brief: Maxwell measurements)
                                        Model A (FMROT)                    Model B (EQ)
  magnetic flux / field distribution   B maps at each stator face +       (use model A)
                                        rotor steel, 8 instants/period,
                                        steel |B| max (saturation)
  back-EMF waveforms + harmonics       yes (all phases, per board)        yes (Maxwell, all phases)
  torque production + ripple           yes (no armature reaction)         yes (WITH armature reaction)
  cogging torque                        yes (Maxwell, rotor)               yes (no-load run)
  current density                       per track of board 1, per amp     uniform in the coils (idealised)
  coreless behaviour                    cogging ~0, linear K, A vs B = armature-reaction effect
  EM losses                             copper DC, copper eddy (est.),     copper DC, magnet eddy
                                        magnet eddy (Maxwell)
  efficiency                            table: 500/1000/2000 rpm x         at 1000 rpm, 1 A
                                        0.5/1/2 A (scaled)
  thermal                               NOT here - loss_table_for_icepak.csv is the input for the Icepak model
  Plots: python make_plots_v10.py "<...>\results\FMROT_REV0_results" on your own PC (numpy + matplotlib).

WHAT TO SEND BACK after each run: <PROJECT>_results\rev0_run_log.txt and the *_summary.txt file
(fmrot_summary.txt / eq_calibration_summary.txt / eq_rot_summary.txt).

NOT TESTED IN AEDT YET: the scripts were run end to end against a mock of the AEDT API (geometry flow, band and
shaft split, exports, post-processing, gates), not in real Maxwell. The things most likely to need a fix on the first
real run: the field export at a time step (two time formats are tried automatically), the equivalent-coil terminal
sheets (AssignCoilTerminal on a sheet object) and the coil-terminal direction (a reversed polarity is detected by the
calibration and corrected automatically).
