# -*- coding: utf-8 -*-
"""
Rev0 configuration - every engineering value lives here.

Authority: PCB_MAXWELL_SOURCE_PACKAGE + the Rev0 specification (2026-10-04).
Values marked ASSUMPTION are modelling choices that are logged on every run.
Pick what to run with PROFILE (in main.py) - profiles only override values below.
"""

BASE = dict(
    # ---------------------------------------------------------------- project
    PROJECT_NAME="REV0_MODEL",
    DESIGN_NAME="Rev0",
    SAVE_DIR=r"D:\New folder",         # projects + results live here (main.py v8.3 sets it to the local WORK folder)
    SHARED_RESULTS_DIR=None,
    REAR_STEEL_GAP=None,               # Rev1 S2 environment: steel plate (R1 back iron) this far below board 1's
    REAR_STEEL_THICK=None,             #   bottom surface, this thick, OD = BACK_IRON_OD, solid (shaft fills the bore)
    # Rev1-D stator-2 environment (v9.4): a second, LOWER PM rotor below the board = rotor R1 of Rev1-D seen from S2:
    #   board bottom - LOWER_PM_GAP - [face-B magnets (toward S2)] - [R1 plate, LOWER_PLATE_THICK] - [face-A magnets (toward S1)]
    LOWER_PM_GAP=None,                 # mm, board bottom surface -> face-B magnet face; None = no lower PM rotor
    LOWER_PLATE_THICK=2.0,             # mm, R1 shared steel plate (a parameter to verify: both faces load it)
    LOWER_POLARITY="additive",         # face B vs the upper rotor at the same angle: "additive" = same magnetisation
                                       #   vector (opposite poles face each other across S2) | "opposed" (wrong way, check only)
    R1_FACE_RELATION="through",        # face A vs face B at the same angle: "through" = same magnetisation vector (flux
                                       #   passes straight through the plate) | "mirror" = reversed (plate carries 2x flux)
    LOWER_BACK_ARRAY=True,             # model face A (behind the plate): plate loading + leakage
    # field-only full-motor model with trace-resolved winding post-processing (fieldmap.py, v9.5)
    FM_DESIGN="Rev0",                  # "Rev0" | "Rev1S" | "Rev1D"
    FM_THETAS=[0.0, 5.625, 11.25, 16.875, 22.5, 28.125, 33.75, 39.375],   # deg mech: one full electrical period
    FM_ZONE_MESH=0.8,                  # mm, max element length in the air annulus around each stator
    FM_ZONE_MAX_ELEMS=500000,
    FM_ZONE_R0=13.5,                   # mm, zone inner / outer radius (traces 15.2..42.6 mm, terminal pads to ~46.5)
    FM_ZONE_R1=47.5,
    # field-only ROTATING transient (fm_rotating.py, v10.0) and equivalent-coil model (eqcoil.py, v10.0)
    FMR_SPP=48,                        # time steps per electrical period (48 -> every 6th step is a field-map angle)
    FMR_PERIODS=1.0,                   # electrical periods simulated
    FMR_STEPS=None,                    # int -> SHORT run of exactly this many steps (validation / timing)
    FMR_BAND_MESH=1.0,                 # mm, fixed transient mesh: band, magnets, rotor steel
    FMR_MAG_MESH=1.0,
    FMR_STEEL_MESH=2.5,
    FMR_IPK=1.0,                       # A peak, synchronous load evaluated in post-processing (FMROT)
    FM_REF_PROJECT=None,               # static field-map project the rotating run is validated against
    CU_SIGMA=5.8e7,                    # S/m, copper (eddy-loss estimate)
    EQ_SLAB_T=0.08,                    # mm, thickness of each equivalent half-coil slab (one per phase per layer pair)
                                       #   (0.1 left a 0.05 mm sliver between the L5/L6 and L1/L2 slabs -> mesh failure)
    EQ_SIDE_TRIM=0.8,                  # deg taken off each coil side width (centre kept): adjacent phases' sides
                                       #   overlapped by 0.26 deg on neighbouring layers -> bad tetrahedra (16 Oct HPC)
    EQ_DETAILED_K={"Rev0": {"S1": [6.2817, 4.5898, 3.3637, 2.4736, 1.8254]},      # mN.m/A per board, full-motor FEM
                   "Rev1S": {"S1": [6.2817, 4.5898, 3.3637, 2.4736, 1.8254],     #   (Rev0 HPC) / detailed single-board
                             "S2": [6.5593, 4.9382, 3.8115, 3.0572, 2.5965]}},   #   FEM (Rev1-S S2, model order: B1 next to R2's
                                                                                 #   magnets); calibration target
    EQ_ARC_W=1.5,                      # mm, radial width of the coil end arcs (inside / outside the active radius)
    EQ_MIN_SIDE_W=3.0,                 # deg, minimum angular width of a coil side
    EQ_COIL_MESH=1.5,                  # mm, max element length inside the equivalent coils
    EQ_POINT_OUT=False,                # coil-terminal direction flag (a reversed polarity is detected and corrected)
    EQ_FORCE=False,                    # run the rotating EQ model even if the calibration is marked not usable
    R1_DOUBLE=False,                   # final build: R1 carries magnets on both faces (Rev1-D)
    S2_REVERSED=False,                 # final Rev1 builds: S2 coil terminals reversed relative to S1 (set from FEM phase)
    N_STAGES=1,
    FULL_SOURCE="REV0_FINAL_G100_T20_FROZEN.aedt",   # full-motor solve attempt: copied from Motor run\frozen
    FULL_THETA=0.0,                    # deg mech, the one rotor angle of the full-motor attempt                        # final builds: 1 = Rev0 (S-R), 2 = Rev1 (S-R-S-R)
    FROZEN_STATOR="REV0_STATOR_FROZEN.aedt",   # source of every final build (copied, never modified)           # main.py sets it to <SHARED>\results (OneDrive); baseline is looked up there too

    # ---------------------------------------------------------------- stator / PCB
    N_BOARDS=1,                       # detailed boards actually built (5 detailed boards exceed 16 GB)
    N_BOARDS_REV0=5,                  # physical Rev0 stack - reserved for the future five-board field-map stage
    PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
    PCB_THICKNESS=1.0,                # mm copper + dielectric (spec)
    MASK_T=0.01016,                   # mm solder mask on each outer face (source stack-up, spec)
    INTERBOARD_GAP=0.0,               # mm extra gap between boards (spec: nominally 0, mask-to-mask)
    # stack-up: "scaled" keeps the Altium copper thicknesses and scales the 5 Altium dielectrics
    # (symmetric 0.0711/0.0711/0.1000/0.0711/0.0711 ratio) to fill PCB_THICKNESS.
    # ASSUMPTION until the real JLCPCB 1.0 mm stack-up is supplied ("manual" + DIELECTRIC_MANUAL).
    STACKUP_MODE="scaled",
    DIELECTRIC_MANUAL=[0.142, 0.142, 0.200, 0.142, 0.142],
    BUILD_FR4=True,                   # FR-4 dielectrics + solder masks (non-magnetic; mesh cost)
    MASK_MATERIAL="SolderResist",     # created per project: non-conductive, mu_r 1, eps_r 3.5 (source stack-up)
    MASK_EPS_R=3.5,
    # vias: solid copper cylinders. ASSUMPTION valid for conduction/field; NOT for final resistance
    VIA_DIAMETER=0.30,
    VIA_SIDES=8,

    # terminals: explicit, verified map (L1 island = In, L6 island = Out); see build_pcb.py
    TERMINAL_MAP={
        "PHASE_A": {"in": ("L1", -22.75, 39.40416), "out": ("L6", -22.75, 39.40416)},
        "PHASE_B": {"in": ("L1", 0.0, 45.50000), "out": ("L6", 0.0, 45.50000)},
        "PHASE_C": {"in": ("L1", 22.75, 39.40416), "out": ("L6", 22.75, 39.40416)},
    },
    EXCITE_STATOR=True,
    STACK_SERIES=False,               # N_BOARDS > 1: series strings A1->..->AN via inter-board bridges (see build_pcb)
    BUILD_ONLY=False,                 # build + validate + frozen copy; no solver setup, no solve               # leads + coil terminals + windings (only for N_BOARDS == 1)
    LEAD_WIDTH=1.0,
    LEAD_HEIGHT=0.5,
    LEAD_RISE=0.3,                    # mm, lead bar clearance above/below the board surface

    # ---------------------------------------------------------------- rotor
    BUILD_ROTOR=True,
    POLES=16,
    AIR_GAP=1.0,                      # mm, stator surface (top solder mask of PCB1) -> magnet face
    MAG_CENTRE_R=28.0,                # mm
    MAG_LENGTH=20.0,                  # mm radial
    MAG_WIDTH=6.0,                    # mm tangential
    MAG_THICK=2.0,                    # mm axial (magnetised through this)
    MAG_MATERIAL="NdFe35",            # N35
    MAG_ANGLE_OFFSET=0.0,             # deg, centre of magnet 1
    BACK_IRON_OD=86.0,
    BACK_IRON_ID=19.0,                # bore = shaft (spec)
    BACK_IRON_THICK=2.0,
    BACK_IRON_MATERIAL="steel_1010",  # commissioning material (spec)
    SHAFT_D=19.0,
    SHAFT_MATERIAL="steel_1010",      # ASSUMPTION: exact shaft alloy not characterised (spec)
    SHAFT_ABOVE_ROTOR=5.0,            # mm of shaft modelled beyond the back iron
    # ASSUMPTION: shaft modelled on the rotor side only (from the band floor up). A shaft through the
    # stator bore would need a non-cylindrical rotating band; enable only if required.
    SHAFT_THROUGH_STATOR=False,
    UNITE_SHAFT_BACK_IRON=True,       # shaft and 19 mm bore are coincident steel_1010 -> one rotating steel body
    BAND_CLEARANCE=0.5,               # mm, band radius beyond the largest rotor part
    REGION_PADDING=15.0,

    # ---------------------------------------------------------------- solve
    SOLUTION_TYPE="Transient",        # "Transient" or "Magnetostatic"
    # Transient formulation. AEDT 2025 R2: A-Phi does NOT support motion (band) -> any rotating model
    # must be T-Omega. A-Phi is used for stationary PCB conduction/electrical checks only.
    TRANSIENT_FORMULATION="T-Omega",  # "T-Omega" or "A-Phi"
    RPM=1000.0,
    IPK=0.0,                          # A peak per phase; 0 = no-load
    MAGNETOSTATIC_I=1.0,              # A in phase A; B, C get -I/2 (only phases present)
    PHASE_DEG={"PHASE_A": 0.0, "PHASE_B": -120.0, "PHASE_C": 120.0},   # working A->C->B; to be verified
    ELECTRICAL_PERIODS=1.0,
    TRANSIENT_STEPS=None,             # int -> stop after exactly this many time steps (overrides periods)
    SAVE_FIELDS=True,                 # False -> no field data stored (lighter, reports still work)
    STEPS_PER_PERIOD=90,
    SAVE_FIELDS_EVERY=10,
    COPPER_EDDY=False,
    MAGNET_EDDY=False,
    MS_MAX_PASSES=10,
    MS_MATRIX=False,                  # inductance matrix at last pass; froze the 16 GB lab PC at 'Start Matrix'
    MS_PERCENT_REFINE=30,
    MESH_BAND_MAX=2.0,
    MESH_MAGNET_MAX=2.0,
    MESH_COPPER_MAX=0.0,
    # ---------------------------------------------------------------- rotor-angle magnetostatic sweep
    # One phase excited with DC current Iamp; rotor (magnets) rotated by design variable theta;
    # Optimetrics sweeps theta (and Iamp = +I, -I). Torque on the rotor (virtual work) and on the
    # copper (Lorentz, reaction) -> dLam/dtheta, back-EMF, k_t, cogging (rotor_analysis.py).
    ROTOR_SWEEP=False,
    THETA_START=0.0,                  # deg mech; 16 poles -> 45 deg mech = one electrical period
    THETA_STOP=22.5,                  # half an electrical period is enough (half-wave antisymmetry, checked)
    THETA_STEP=2.5,
    SWEEP_I=1.0,                      # A, DC in the excited phase
    SWEEP_MINUS_I=True,               # also solve -I: separates PM torque from cogging/reluctance exactly
    SWEEP_SAVE_FIELDS=False,
    # "stepwise": one Analyze per (angle, current), project + sweep_progress.json saved after each solve, a
    # crash costs one variation and START_AT="analyze" continues where it stopped. "optimetrics": one
    # ParametricSetup1 solve (saves only at the end).
    SWEEP_MODE="stepwise",
    SWEEP_REOPEN_EVERY=1,             # stepwise: close + reopen the project after every N solves (frees RAM); 0 = never          # True -> field results kept per variation (B in gap / steel), more disk
    # three-phase synchronous check (REF_ROTOR_MS_3PH): I_X = Isync*cos(p*rot_angle + phi_sync + PHASE_DEG[X]),
    # phi_sync = -psi, psi = phase of dLam_A/dtheta from the Phase-A baseline sweep (never a provisional value)
    SYNC_3PH=False,
    SYNC_IPK=1.0,                     # A peak
    SYNC_PHI_DEG=None,                # None -> read from BASELINE_PROJECT's rotor_sweep_summary.txt
    BASELINE_PROJECT="REV0_REF_ROTOR_MS_SWEEP",
    # mechanical rotation of each phase's copper relative to Phase A (verified from the source geometry:
    # B = A rotated -30 deg, C = A rotated -60 deg, on every layer) -> k_X(theta) = k_A(theta - rot)
    PHASE_ROT_MECH={"PHASE_A": 0.0, "PHASE_B": -30.0, "PHASE_C": -60.0},
    MESH_GAP_MAX=None,                # mm, length op on the air-gap vacuum layer; None -> AIR_GAP/2
    MESH_GAP_MAX_ELEMS=300000,        # element cap for that op (RAM guard: 0.25 mm over the whole annulus
                                      # would be ~2.3M tetrahedra at a 1 mm gap - beyond the 16 GB PC)
    EXPORT_DIR="",                    # "" -> <project dir>/<project>_results
)

PROFILES = {
    # commissioning gates (same content as the standalone gate scripts)
    "GATE1": dict(PROJECT_NAME="REV0_GATE1_MS_PHASEA", PHASES=["PHASE_A"], BUILD_FR4=False,
                  BUILD_ROTOR=False, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=2, MS_PERCENT_REFINE=15),
    # Gate 2 is split: the earlier conduction-path failure happened in T-Omega (the motion solver the
    # rotating reference model needs), and A-Phi is a separate solver with its own terminal rules.
    # Short form after the 2026-10-04 run (PC ran out of 16 GB RAM after step 1): 2 time steps,
    # no field storage, 5 mm air padding. Step 1 alone proves the conduction-path calculation.
    "GATE2_TOMEGA": dict(PROJECT_NAME="REV0_GATE2_TOMEGA_PHASEA_SHORT", PHASES=["PHASE_A"], BUILD_FR4=False,
                         BUILD_ROTOR=False, SOLUTION_TYPE="Transient", TRANSIENT_FORMULATION="T-Omega",
                         IPK=1.0, TRANSIENT_STEPS=2, SAVE_FIELDS=False, REGION_PADDING=5.0),
    "GATE2_APHI": dict(PROJECT_NAME="REV0_GATE2_APHI_PHASEA_SHORT", PHASES=["PHASE_A"], BUILD_FR4=False,
                       BUILD_ROTOR=False, SOLUTION_TYPE="Transient", TRANSIENT_FORMULATION="A-Phi",
                       IPK=1.0, TRANSIENT_STEPS=2, SAVE_FIELDS=False, REGION_PADDING=5.0),
    # per-phase validation of B and C (magnetostatic, like gate 1)
    "GATE1_B": dict(PROJECT_NAME="REV0_GATE1_MS_PHASEB", PHASES=["PHASE_B"], BUILD_FR4=False,
                    BUILD_ROTOR=False, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=2, MS_PERCENT_REFINE=15),
    "GATE1_C": dict(PROJECT_NAME="REV0_GATE1_MS_PHASEC", PHASES=["PHASE_C"], BUILD_FR4=False,
                    BUILD_ROTOR=False, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=2, MS_PERCENT_REFINE=15),
    # all three phases on one board, DC balanced (I_A = 1 A, I_B = I_C = -0.5 A), FR-4 + masks, no rotor:
    # phase isolation, 3x3 inductance matrix, field of the complete winding
    "BOARD_3PH_MS": dict(PROJECT_NAME="REV0_BOARD_3PH_MS", BUILD_ROTOR=False, SOLUTION_TYPE="Magnetostatic",
                         MS_MAX_PASSES=3, MS_PERCENT_REFINE=15, REGION_PADDING=5.0),
    # same, with FR-4/solder mask left as air (mu_r = 1 either way; geometry, pitch, gap unchanged).
    # USE ONLY WITH OLWETHU'S APPROVAL - it removes the thin mask layers that dominate the mesh.
    "BOARD_3PH_MS_AIR": dict(PROJECT_NAME="REV0_BOARD_3PH_MS_AIR", BUILD_ROTOR=False, BUILD_FR4=False,
                             SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=3, MS_PERCENT_REFINE=15,
                             REGION_PADDING=5.0),
    # rotor only, spinning (motion/band commissioning, torque noise floor)
    "ROTOR_MOTION": dict(PROJECT_NAME="REV0_ROTOR_MOTION", PHASES=[], N_BOARDS=0, BUILD_FR4=False,
                         SAVE_FIELDS_EVERY=1),
    # ---- rotor-angle magnetostatic reference model (detailed board 1 + real rotor) ----
    # Only the excited phase's copper is built (B, C copper is mu_r = 1 and carries no current in these
    # solves -> no effect on the field; B and C follow by symmetry, checked with PHASES=["PHASE_B"]).
    # Baseline: ONE FULL electrical period, theta 0..45 deg mech in 5.625 deg (45 deg elec) steps
    # (9 angles) x (+1 A, -1 A) = 18 solves, fields saved. Verifies 45 deg periodicity, 22.5 deg half-wave
    # antisymmetry, polarity and the torque waveform before any symmetry reduction is used.
    "REF_ROTOR_MS_SWEEP": dict(PROJECT_NAME="REV0_REF_ROTOR_MS_SWEEP", PHASES=["PHASE_A"], BUILD_FR4=False,
                               BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                               MS_PERCENT_REFINE=20, REGION_PADDING=5.0, ROTOR_SWEEP=True,
                               THETA_START=0.0, THETA_STOP=45.0, THETA_STEP=5.625, SWEEP_MINUS_I=True,
                               SWEEP_SAVE_FIELDS=True),
    # Smoke / timing test: 2 angles 90 deg ELECTRICAL apart (0 and 11.25 deg mech; 8 pole pairs)
    # x (+1 A, -1 A) = 4 solves.
    "REF_ROTOR_MS_SMOKE": dict(PROJECT_NAME="REV0_REF_ROTOR_MS_SMOKE", PHASES=["PHASE_A"], BUILD_FR4=False,
                               BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                               MS_PERCENT_REFINE=20, REGION_PADDING=5.0, ROTOR_SWEEP=True,
                               THETA_START=0.0, THETA_STOP=11.25, THETA_STEP=11.25, SWEEP_MINUS_I=True,
                               SWEEP_SAVE_FIELDS=False),
    # Design-of-experiments point (air gap / back iron / magnet radius via OVERRIDES or RUNS in main.py):
    # 4 angles 45 deg elec apart, +1 A only (valid once the baseline shows cogging ~ 0) = 4 solves.
    "REF_ROTOR_MS_DOE": dict(PROJECT_NAME="REV0_REF_ROTOR_MS_DOE", PHASES=["PHASE_A"], BUILD_FR4=False,
                             BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                             MS_PERCENT_REFINE=20, REGION_PADDING=5.0, ROTOR_SWEEP=True,
                             THETA_START=0.0, THETA_STOP=16.875, THETA_STEP=5.625, SWEEP_MINUS_I=False,
                             SWEEP_SAVE_FIELDS=False),
    # Same, keeping field results per variation (back-iron sweep: steel |B|max, mid-gap |Bz| -> saturation
    # and diminishing returns, not torque alone).
    "REF_ROTOR_MS_DOE_STEEL": dict(PROJECT_NAME="REV0_REF_ROTOR_MS_DOE_STEEL", PHASES=["PHASE_A"],
                                   BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic",
                                   MS_MAX_PASSES=4, MS_PERCENT_REFINE=20, REGION_PADDING=5.0, ROTOR_SWEEP=True,
                                   THETA_START=0.0, THETA_STOP=16.875, THETA_STEP=5.625, SWEEP_MINUS_I=False,
                                   SWEEP_SAVE_FIELDS=True),
    # Three-phase synchronous magnetostatic check: all 3 phases, currents follow the rotor angle with the
    # current angle taken from the baseline; 5 angles over one torque-ripple period (60 deg elec = 7.5 mech).
    "REF_ROTOR_MS_3PH": dict(PROJECT_NAME="REV0_REF_ROTOR_MS_3PH", PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                             BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                             MS_PERCENT_REFINE=20, REGION_PADDING=5.0, ROTOR_SWEEP=True, SYNC_3PH=True,
                             THETA_START=0.0, THETA_STOP=7.5, THETA_STEP=1.875, SWEEP_MINUS_I=False,
                             SWEEP_SAVE_FIELDS=False),
    # ---- the actual Rev0 STATOR: build only (rotor added after the optimisation) ----
    # Starts from an empty project: PCB1..PCB5 built ONE AT A TIME (each validated + saved + checkpointed),
    # then the boards are electrically connected (rim bridges board k L6 Out -> board k+1 L1 In, string-end
    # leads), junction contacts checked in AEDT, windings assigned, validated, frozen copy saved.
    # Star point NOT made (six string ends exposed). No rotor, no solver setup, no solve.
    "REV0_STATOR_BUILD": dict(PROJECT_NAME="REV0_STATOR", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                              BUILD_FR4=False, BUILD_ROTOR=False, SOLUTION_TYPE="Magnetostatic", STACK_SERIES=True,
                              BUILD_ONLY=True, REGION_PADDING=5.0),
    # Rev1 stator-2 environment: one board (Phase A) between R2's magnets (AIR_GAP away) and R1's back iron
    # (REAR_STEEL_GAP below the board). Set by run_REV1_S2_ENV.py for S2's board nearest R1 (AIR_GAP = g + 4*pitch).
    "REV1_S2_ENV": dict(PROJECT_NAME="REV1_S2ENV", PHASES=["PHASE_A"], BUILD_FR4=False, BUILD_ROTOR=True,
                        SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4, MS_PERCENT_REFINE=20, REGION_PADDING=5.0,
                        ROTOR_SWEEP=True, THETA_START=0.0, THETA_STOP=16.875, THETA_STEP=5.625, SWEEP_MINUS_I=False,
                        SWEEP_SAVE_FIELDS=False, REAR_STEEL_GAP=1.0, REAR_STEEL_THICK=2.0),
    # Rev1-D (S1 - [16 mag | shared plate | 16 mag] - S2 - [16 mag | plate], 48 magnets) stator-2 environment: one board
    # (Phase A) between rotor R2 (AIR_GAP above) and R1's face-B magnets (LOWER_PM_GAP below), R1 plate and face-A
    # magnets behind. Set by run_REV1D_S2_K1.py / _K3.py for S2 board k: AIR_GAP = g + (5-k)p, LOWER_PM_GAP = g + (k-1)p.
    # Fields kept per angle: max |B| in R2 steel and in the R1 shared plate, mid-gap Bz, axial-force estimate.
    "REV1D_S2": dict(PROJECT_NAME="REV1D_S2", PHASES=["PHASE_A"], BUILD_FR4=False, BUILD_ROTOR=True,
                     SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4, MS_PERCENT_REFINE=20, REGION_PADDING=5.0,
                     ROTOR_SWEEP=True, THETA_START=0.0, THETA_STOP=16.875, THETA_STEP=5.625, SWEEP_MINUS_I=False,
                     SWEEP_SAVE_FIELDS=True, LOWER_PM_GAP=1.0, LOWER_PLATE_THICK=2.0),
    # ---- final motor models (build only, from a COPY of the frozen stator; set AIR_GAP / BACK_IRON_THICK) ----
    "REV0_FINAL_BUILD": dict(PROJECT_NAME="REV0_FINAL", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                             BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", STACK_SERIES=True,
                             BUILD_ONLY=True, REGION_PADDING=5.0, N_STAGES=1),
    "REV1_FINAL_BUILD": dict(PROJECT_NAME="REV1_FINAL", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                             BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", STACK_SERIES=True,
                             BUILD_ONLY=True, REGION_PADDING=5.0, N_STAGES=2),
    # ---- FULL-MOTOR field-only models (no copper) + trace-resolved winding post-processing (fieldmap.py) ----
    "FIELDMAP_REV0": dict(PROJECT_NAME="FIELDMAP_REV0", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                          BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                          MS_PERCENT_REFINE=20, REGION_PADDING=5.0, FM_DESIGN="Rev0"),
    "FIELDMAP_REV1D": dict(PROJECT_NAME="FIELDMAP_REV1D", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                           BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                           MS_PERCENT_REFINE=20, REGION_PADDING=5.0, FM_DESIGN="Rev1D", LOWER_PLATE_THICK=2.0),
    "FIELDMAP_REV1S": dict(PROJECT_NAME="FIELDMAP_REV1S", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                           BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                           MS_PERCENT_REFINE=20, REGION_PADDING=5.0, FM_DESIGN="Rev1S"),
    # ---- v10.0 FIELD-ONLY ROTATING TRANSIENT (fm_rotating.py): full motor, band + motion, no copper in the mesh ----
    # --- 17 Oct hardware-sensitivity checks (field map, P20 basis; compare K per board with FIELDMAP_REV0_P20) ---
    "FIELDMAP_REV0_BP80": dict(PROJECT_NAME="FIELDMAP_REV0_BP80", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                               BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                               MS_PERCENT_REFINE=20, REGION_PADDING=20.0, FM_DESIGN="Rev0",
                               BACK_IRON_OD=80.0, BACK_IRON_ID=25.0, UNITE_SHAFT_BACK_IRON=False),   # hardware backplate; 19 mm shaft separate, 3 mm air annulus (hub not modelled)
    "FIELDMAP_REV0_G125": dict(PROJECT_NAME="FIELDMAP_REV0_G125", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                               BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                               MS_PERCENT_REFINE=20, REGION_PADDING=20.0, FM_DESIGN="Rev0", AIR_GAP=1.25),
    "FIELDMAP_REV0_IB022": dict(PROJECT_NAME="FIELDMAP_REV0_IB022", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                                BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                                MS_PERCENT_REFINE=20, REGION_PADDING=20.0, FM_DESIGN="Rev0", INTERBOARD_GAP=0.22),   # ~6 mm stack
    "EQ_REV0_CAL_FINE": dict(PROJECT_NAME="EQ_REV0_CAL_FINE", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                             BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                             MS_PERCENT_REFINE=20, REGION_PADDING=20.0, EXCITE_STATOR=False, FM_DESIGN="Rev0",
                             FM_REF_PROJECT="FIELDMAP_REV0_P20", EQ_COIL_MESH=1.0),   # one-step mesh refinement of EQ_REV0_CAL
    "FMROT_REV0": dict(PROJECT_NAME="FMROT_REV0", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                       BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Transient", TRANSIENT_FORMULATION="T-Omega",
                       EXCITE_STATOR=False, MAGNET_EDDY=True, REGION_PADDING=20.0, FM_DESIGN="Rev0",
                       FM_REF_PROJECT="FIELDMAP_REV0_P20", FMR_SPP=24),   # 24 steps/period: fields at every step cost ~0.5 GB each (disk quota)
    "FMROT_REV0_SHORT": dict(PROJECT_NAME="FMROT_REV0_SHORT", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                             BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Transient",
                             TRANSIENT_FORMULATION="T-Omega", EXCITE_STATOR=False, MAGNET_EDDY=True,
                             REGION_PADDING=20.0, FM_DESIGN="Rev0", FM_REF_PROJECT="FIELDMAP_REV0_P20", FMR_STEPS=6),
    "FMROT_REV1S": dict(PROJECT_NAME="FMROT_REV1S", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                        BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Transient", TRANSIENT_FORMULATION="T-Omega",
                        EXCITE_STATOR=False, MAGNET_EDDY=True, REGION_PADDING=20.0, FM_DESIGN="Rev1S",
                        FM_REF_PROJECT="FIELDMAP_REV1S_P20", FMR_SPP=24),   # 24 steps/period: fields at every step cost ~0.5 GB each (disk quota)
    "FMROT_REV1S_SHORT": dict(PROJECT_NAME="FMROT_REV1S_SHORT", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                              BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Transient",
                              TRANSIENT_FORMULATION="T-Omega", EXCITE_STATOR=False, MAGNET_EDDY=True,
                              REGION_PADDING=20.0, FM_DESIGN="Rev1S", FM_REF_PROJECT="FIELDMAP_REV1S_P20", FMR_STEPS=6),
    # ---- v10.0 EQUIVALENT-COIL STATOR (eqcoil.py): copper in Maxwell as calibrated stranded coils ----
    "EQ_REV0_CAL": dict(PROJECT_NAME="EQ_REV0_CAL", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"], BUILD_FR4=False,
                        BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4, MS_PERCENT_REFINE=20,
                        REGION_PADDING=20.0, EXCITE_STATOR=False, FM_DESIGN="Rev0", FM_REF_PROJECT="FIELDMAP_REV0_P20"),
    "EQ_REV0_ROT": dict(PROJECT_NAME="EQ_REV0_ROT", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"], BUILD_FR4=False,
                        BUILD_ROTOR=True, SOLUTION_TYPE="Transient", TRANSIENT_FORMULATION="T-Omega", MAGNET_EDDY=True,
                        REGION_PADDING=20.0, FM_DESIGN="Rev0", FM_REF_PROJECT="FIELDMAP_REV0_P20"),
    "EQ_REV0_ROT_SHORT": dict(PROJECT_NAME="EQ_REV0_ROT_SHORT", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                              BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Transient", TRANSIENT_FORMULATION="T-Omega",
                              MAGNET_EDDY=True, REGION_PADDING=20.0, FM_DESIGN="Rev0", FM_REF_PROJECT="FIELDMAP_REV0_P20",
                              FMR_STEPS=6),
    "EQ_REV1S_CAL": dict(PROJECT_NAME="EQ_REV1S_CAL", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                         BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", MS_MAX_PASSES=4,
                         MS_PERCENT_REFINE=20, REGION_PADDING=20.0, EXCITE_STATOR=False, FM_DESIGN="Rev1S",
                         FM_REF_PROJECT="FIELDMAP_REV1S_P20"),
    "EQ_REV1S_ROT": dict(PROJECT_NAME="EQ_REV1S_ROT", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                         BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Transient", TRANSIENT_FORMULATION="T-Omega",
                         MAGNET_EDDY=True, REGION_PADDING=20.0, FM_DESIGN="Rev1S", FM_REF_PROJECT="FIELDMAP_REV1S_P20"),
    "EQ_REV1S_ROT_SHORT": dict(PROJECT_NAME="EQ_REV1S_ROT_SHORT", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                               BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Transient",
                               TRANSIENT_FORMULATION="T-Omega", MAGNET_EDDY=True, REGION_PADDING=20.0,
                               FM_DESIGN="Rev1S", FM_REF_PROJECT="FIELDMAP_REV1S_P20", FMR_STEPS=6),
    "REV1D_FINAL_BUILD": dict(PROJECT_NAME="REV1D_FINAL", N_BOARDS=5, PHASES=["PHASE_A", "PHASE_B", "PHASE_C"],
                              BUILD_FR4=False, BUILD_ROTOR=True, SOLUTION_TYPE="Magnetostatic", STACK_SERIES=True,
                              BUILD_ONLY=True, REGION_PADDING=5.0, N_STAGES=2, R1_DOUBLE=True, LOWER_PLATE_THICK=2.0),
    # Deliberate feasibility test: the COMPLETE detailed Rev0 motor (copy of REV0_FINAL frozen) at ONE rotor angle,
    # synchronous 3-phase currents, magnetostatic, 2 passes, matrix OFF. Expected to exceed 16 GB; documented either way.
    "REV0_FULL_ATTEMPT": dict(PROJECT_NAME="REV0_FULL_SOLVE_ATTEMPT", N_BOARDS=5,
                              PHASES=["PHASE_A", "PHASE_B", "PHASE_C"], BUILD_FR4=False, BUILD_ROTOR=True,
                              SOLUTION_TYPE="Magnetostatic", STACK_SERIES=True, BUILD_ONLY=False, MS_MAX_PASSES=2,
                              MS_PERCENT_REFINE=20, REGION_PADDING=5.0, SYNC_IPK=1.0, FULL_THETA=0.0),
    # Cheap electrical proof of the inter-board junction: 2 boards, Phase A only, one bridge, DC 1 A
    # magnetostatic (2 passes). Pass = Maxwell conduction path accepted + R ~ 2 x 0.2777 ohm (postprocess_ms.py).
    "STACK_JUNCTION_TEST": dict(PROJECT_NAME="REV0_STACK_JUNCTION_TEST", N_BOARDS=2, PHASES=["PHASE_A"],
                                BUILD_FR4=False, BUILD_ROTOR=False, SOLUTION_TYPE="Magnetostatic", STACK_SERIES=True,
                                BUILD_ONLY=False, MS_MAX_PASSES=2, MS_PERCENT_REFINE=15, REGION_PADDING=5.0),
    # detailed single-board reference model + rotor (transient; NOT runnable on the 16 GB lab PC)
    "REF_BOARD_NOLOAD": dict(PROJECT_NAME="REV0_REF_BOARD_NOLOAD", IPK=0.0),
    "REF_BOARD_LOAD_1A": dict(PROJECT_NAME="REV0_REF_BOARD_LOAD_1A", IPK=1.0),
}


class Config(object):
    def __init__(self, profile, overrides=None):
        if profile not in PROFILES:
            raise KeyError("Unknown PROFILE '%s'. Choose one of: %s" % (profile, ", ".join(sorted(PROFILES))))
        d = dict(BASE)
        d.update(PROFILES[profile])
        d.update(overrides or {})
        d["PROFILE"] = profile
        self.__dict__.update(d)
        if self.SOLUTION_TYPE not in ("Transient", "Magnetostatic"):
            raise ValueError("SOLUTION_TYPE must be 'Transient' or 'Magnetostatic'")
        if self.TRANSIENT_FORMULATION not in ("T-Omega", "A-Phi"):
            raise ValueError("TRANSIENT_FORMULATION must be 'T-Omega' or 'A-Phi'")
        if self.is_aphi() and self.BUILD_ROTOR:
            raise ValueError("Profile %s: Transient A-Phi does not support motion in AEDT 2025 R2 - a rotating "
                             "rotor needs TRANSIENT_FORMULATION='T-Omega'" % profile)
        if self.STACK_SERIES and (self.N_BOARDS < 2 or self.ROTOR_SWEEP):
            raise ValueError("STACK_SERIES needs N_BOARDS >= 2 and is a build profile (no ROTOR_SWEEP)")
        if self.ROTOR_SWEEP:
            if self.SOLUTION_TYPE != "Magnetostatic" or not self.BUILD_ROTOR:
                raise ValueError("ROTOR_SWEEP needs SOLUTION_TYPE='Magnetostatic' and BUILD_ROTOR=True")
            if self.SYNC_3PH:
                if sorted(self.PHASES) != ["PHASE_A", "PHASE_B", "PHASE_C"] or self.SWEEP_MINUS_I:
                    raise ValueError("SYNC_3PH needs all three phases and SWEEP_MINUS_I=False")
                p = self.POLES // 2
                for n in self.PHASES:   # current phase must match the winding's electrical position
                    if abs(((-p * self.PHASE_ROT_MECH[n] - self.PHASE_DEG[n]) + 180.0) % 360.0 - 180.0) > 1e-6:
                        raise ValueError("PHASE_DEG[%s]=%g does not match the winding rotation %g deg mech"
                                         % (n, self.PHASE_DEG[n], self.PHASE_ROT_MECH[n]))
            elif len(self.PHASES) != 1:
                raise ValueError("ROTOR_SWEEP excites exactly one phase (PHASES=['PHASE_A'] etc.)")
            if self.THETA_STEP <= 0 or self.THETA_STOP < self.THETA_START:
                raise ValueError("THETA_START/STOP/STEP invalid")
        if self.LOWER_POLARITY not in ("additive", "opposed") or self.R1_FACE_RELATION not in ("through", "mirror"):
            raise ValueError("LOWER_POLARITY must be additive/opposed and R1_FACE_RELATION through/mirror")
        if self.LOWER_PM_GAP and self.REAR_STEEL_GAP:
            raise ValueError("LOWER_PM_GAP (Rev1-D) and REAR_STEEL_GAP (Rev1-S) are alternative S2 environments")

    def is_aphi(self):
        return self.SOLUTION_TYPE == "Transient" and self.TRANSIENT_FORMULATION == "A-Phi"

    def aedt_solution_type(self):
        """String for InsertDesign / SetSolutionType (AEDT 2025 R2 scripting guide)."""
        if self.SOLUTION_TYPE == "Magnetostatic":
            return "Magnetostatic"
        return "Transient APhi" if self.is_aphi() else "Transient"

    def gap_mesh_max(self):
        return self.MESH_GAP_MAX if self.MESH_GAP_MAX else self.AIR_GAP / 2.0

    def board_pitch(self):
        return self.PCB_THICKNESS + 2 * self.MASK_T + self.INTERBOARD_GAP

    def assumptions(self):
        a = ["Stack-up mode '%s'%s" % (self.STACKUP_MODE,
             " - Altium dielectric ratios scaled to %.3f mm copper+dielectric; NOT the JLCPCB stack-up"
             % self.PCB_THICKNESS if self.STACKUP_MODE == "scaled" else ""),
             "Solder mask %.5f mm each face (source stack-up); board pitch %.5f mm" % (self.MASK_T, self.board_pitch()),
             "Vias = solid %.2f mm copper (%d-sided): fine for conduction/field, low for final resistance"
             % (self.VIA_DIAMETER, self.VIA_SIDES),
             "Air gap %.3f mm measured from PCB1 top solder-mask surface to magnet face" % self.AIR_GAP]
        if self.PHASES and not self.BUILD_FR4:
            a.append("FR-4 and solder mask modelled as air (mu_r = 1, non-conductive either way); "
                     "board geometry, pitch and air gap unchanged")
        if self.SOLUTION_TYPE == "Magnetostatic" and not self.MS_MATRIX:
            a.append("Inductance matrix not computed (lab-PC freeze at 'Start Matrix')")
        if self.BUILD_ROTOR:
            a.append("Shaft %s, %.1f mm dia, rotating; %s%s" % (self.SHAFT_MATERIAL, self.SHAFT_D,
                     "through stator bore" if self.SHAFT_THROUGH_STATOR else
                     "simplified EM representation: rotor side only (band floor to %.1f mm beyond back iron); "
                     "section through the stator bore omitted; NOT the physical shaft length" % self.SHAFT_ABOVE_ROTOR,
                     "; shaft + back iron united as one steel body" if self.UNITE_SHAFT_BACK_IRON else ""))
        if self.STACK_SERIES:
            a.append("%d identical boards, same orientation, touching mask-to-mask (pitch %.5f mm); each phase a "
                     "%d-board series string: 1 x 1 mm copper bridges at the rim terminal spanning the 0.02032 mm "
                     "mask-to-mask gap and touching board k L6 Out / board k+1 L1 In pad faces (represents the edge "
                     "solder joint; boards are separate touching conductors, not one united solid); external raised "
                     "leads only on the string ends; star point NOT connected (six ends exposed)"
                     % (self.N_BOARDS, self.board_pitch(), self.N_BOARDS))
        if self.SYNC_3PH:
            a.append("Three-phase synchronous magnetostatic check: I_X = %g A * cos(%d*rot_angle + phi_sync + "
                     "PHASE_DEG[X]); phi_sync from the Phase-A baseline (%s); prediction by superposition of the "
                     "baseline dLam_A/dtheta rotated to each phase (B = A rotated -30 deg, C = -60 deg mech)"
                     % (self.SYNC_IPK, self.POLES // 2, self.BASELINE_PROJECT if self.SYNC_PHI_DEG is None
                        else "override %g deg" % self.SYNC_PHI_DEG))
        elif self.ROTOR_SWEEP:
            a.append("Rotor-angle magnetostatic sweep: %s excited with DC %s; theta %g..%g deg step %g; "
                     "dLam/dtheta from torque reciprocity k = (T(+I) - T(-I))/2I%s - a central-difference estimate "
                     "around zero current (exact only if the rotor steel is linear); back-EMF sign in the Maxwell "
                     "terminal convention; 3-phase torque = ideal fundamental with optimum phasing; no eddy currents"
                     % (self.PHASES[0], "+/-%g A" % self.SWEEP_I if self.SWEEP_MINUS_I else "+%g A" % self.SWEEP_I,
                        self.THETA_START, self.THETA_STOP, self.THETA_STEP,
                        "" if self.SWEEP_MINUS_I else " with T(-I) = -T(+I), i.e. cogging assumed ~0"))
            if not self.SYNC_3PH:
                a.append("Only the excited phase's copper is modelled (other phases are mu_r = 1, unexcited)")
        if self.REAR_STEEL_GAP:
            a.append("Rev1 S2 environment: solid steel plate (%s, OD %.1f mm, %.2f mm thick) %.3f mm below the "
                     "board's bottom surface = rotor-1 back iron + shaft seen by stator 2; rotor-1 magnets behind that "
                     "plate NOT modelled (their leakage through the steel neglected)"
                     % (self.BACK_IRON_MATERIAL, self.BACK_IRON_OD, self.REAR_STEEL_THICK, self.REAR_STEEL_GAP))
        if self.PROFILE.startswith("FIELDMAP"):
            a.append("Field-only full-motor model (%s): magnets + steel + air solved in Maxwell, NO PCB copper (mu_r = 1, "
                     "no current -> no effect on the magnet field); B sampled on the ODB++ trace centre-lines of every "
                     "board; torque by Lorentz integration; armature reaction and copper eddy effects neglected"
                     % self.FM_DESIGN)
        if self.PROFILE.startswith("EQ_"):
            a.append("Equivalent-coil stator (%s): each phase of each board = 8 closed stranded sector coils at the measured "
                     "radial-current positions, split over two layers symmetric about the board mid-plane (A L1+L6, B L2+L5, "
                     "C L3+L4), %.2f mm slabs; turns calibrated against the field map %s; no eddy currents in the copper"
                     % (self.FM_DESIGN, self.EQ_SLAB_T, self.FM_REF_PROJECT))
        if self.PROFILE.startswith("FMROT"):
            a.append("Field-only ROTATING transient (%s): magnets (eddy %s) + steel + air in Maxwell, rotor turning at %g "
                     "rpm in cylindrical band(s); NO PCB copper meshed; B exported on the trace centre-lines of every board "
                     "at every step; torque/back-EMF by Lorentz integration; armature reaction neglected; copper eddy "
                     "loss by the thin-conductor formula" % (self.FM_DESIGN, "ON" if self.MAGNET_EDDY else "OFF", self.RPM))
        if self.LOWER_PM_GAP:
            a.append("Rev1-D S2 environment: lower PM rotor (R1) %.3f mm below the board's bottom surface: %d face-B magnets "
                     "(%s with the upper rotor), %s steel plate %.2f mm (OD %.1f, solid), %s; lower magnets rotate with "
                     "rot_angle (common shaft, rotors aligned)"
                     % (self.LOWER_PM_GAP, self.POLES, self.LOWER_POLARITY, self.BACK_IRON_MATERIAL,
                        self.LOWER_PLATE_THICK, self.BACK_IRON_OD,
                        ("%d face-A magnets behind the plate (%s)" % (self.POLES, self.R1_FACE_RELATION))
                        if self.LOWER_BACK_ARRAY else "face-A magnets NOT modelled"))
        if self.R1_DOUBLE:
            a.append("Rev1-D: R1 = %d face-A magnets (toward S1) | steel plate %.2f mm | %d face-B magnets (toward S2), "
                     "face relation %s; R2 single-sided; face B / R2 magnetised additively across S2"
                     % (self.POLES, self.LOWER_PLATE_THICK, self.POLES, self.R1_FACE_RELATION))
        if self.SOLUTION_TYPE == "Transient":
            a.append("Transient formulation %s (%s)" % (self.TRANSIENT_FORMULATION,
                     "stationary only - no motion" if self.is_aphi() else "supports motion/band"))
        if self.PHASES and self.SOLUTION_TYPE == "Transient" and self.EXCITE_STATOR:
            a.append("Stator excitation = balanced current sources per phase (EM characterisation), "
                     "not the physical 5-board series-Y circuit")
        return a
