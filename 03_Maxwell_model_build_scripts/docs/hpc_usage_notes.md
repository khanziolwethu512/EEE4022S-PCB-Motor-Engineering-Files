# hpc_motor.py — full-motor static and transient Maxwell runs on the UCT HPC (2026-10-13, v5)

One self-contained file (about 2 MB). It carries the rev0_v9 pipeline, the board geometry, traces_board.json, the reference results and the PCB source-package extract. You submit it on its own with sbatch; it needs no other files.

## Account (granted 13 October 2026)
- User: khnolw003.
  - Home: /home/khnolw003, 10 GB, backed up. The script lives here.
  - Scratch: /scratch/khnolw003, 50 GB, volatile, not backed up. The work folder is /scratch/khnolw003/pcbmotor_hpc.
- Limits: 40 cores per job, 1 node per job, 200 running cores in total. Use at most 8 GB per core (the script asks for 7800M).
- Off campus you need the VPN. Log in with `ssh khnolw003@hpc.uct.ac.za` (or PuTTY) and move files with scp (or WinSCP).
- The report must include the eResearch acknowledgement: https://ucthpc.uct.ac.za/index.php/acknowledge-eresearch

## Priorities (decided 13 October)
1. **Rev0 (the original motor)** — static at 2 angles, the mesh gates, then the no-load and loaded rotating runs. 32 cores, about 250 GB.
2. **Rev1-S** — static at 2 angles, the split-shaft check, two rotating bands, the mesh gates, then the no-load and loaded rotating runs. 40 cores, about 312 GB.
3. **Rev2-S** (S-R-S-R-S-R), only if there is time — static at 2 angles. 40 cores. Estimated references: K 63.77 (field map) and 60.47 (detailed) mN·m/A.
4. Rev1-D is dropped. It is future work, and its earlier static results stand.

Friday mode, for each motor: angles 0° and 3.75° (the 6th-harmonic ripple cancels in the mean); the static ladder starts at L2; the rotating runs use 45 steps over 1 electrical period at 1000 rpm.

## v5 changes (after the account email)
- **Cores:** at most 40 per job; anything higher is capped. Rev0 has 32 in the header. A Rev1-S or Rev2-S job started with too few cores resubmits itself at 40.
- **Disk guard (`--disk-gb`, default 45):**
  - The supervisor checks the size of the work folder every 2 min and stops AEDT cleanly before the 50 GB quota is reached.
  - It won't start a task with less than 2 GB left.
  - After the gate, it deletes the short-step gate projects; their CSVs are kept.
  - It sizes the production field frames from the short-step project size: up to 15 frames, and none if fewer than 4 fit. The torque, back-EMF, current and loss waveforms are always kept.
- **AEDT TMPDIR:** goes on the node's local disk when it has more than 30 GB free; otherwise it goes in the work folder.
- **Rev2-S build (rev2.py):**
  - S2 and S3 are exact copies of S1, moved by 11.1016 and 22.2032 mm, and junction-probed.
  - Three Rev0 rotors on one shaft.
  - Every stator's terminals are added to the PhaseA/B/C windings in series.
  - Transient (three bands, from `--mode transient --motor Rev2S`): bands at z 1.010–6.010, 12.112–17.112 and 23.213–33.713 mm.

## Setup and run order
1. Connect: VPN if you are off campus, then `ssh khnolw003@hpc.uct.ac.za`.
2. Look around:
   - `cat ~/example-script.sh` — note its `--account` and `--partition` lines;
   - `quota`;
   - `module avail 2>&1 | grep -i ansys` — expect `software/ansys-2025R2-v252`;
   - `sinfo -s`.
3. Upload: `scp hpc_motor.py khnolw003@hpc.uct.ac.za:~/` (or WinSCP).
4. Edit the header: `nano ~/hpc_motor.py`.
   - Line 3, partition: keep `ada` unless the example script says otherwise.
   - Line 8, account: remove one `#` and use the example script's account. If the example has no account line, leave it commented.
   - Line 9, email: optional.
5. Smoke test: `cd ~ && sbatch hpc_motor.py --mode smoke`, then `squeue -u $USER`. Afterwards, `cat /scratch/khnolw003/pcbmotor_hpc/SMOKE_RESULT.txt`.
6. Rev0: `sbatch hpc_motor.py --mode friday --motor Rev0`.
7. Rev1-S, once Rev0's first static solve reports its peak memory (`python3 hpc_motor.py --mode status`): `sbatch --ntasks=40 hpc_motor.py --mode friday --motor Rev1S`.
8. Optional: `sbatch --ntasks=40 hpc_motor.py --mode friday --motor Rev2S`.
9. Monitor:
   - `squeue -u $USER`;
   - `python3 hpc_motor.py --mode status`;
   - `tail -f /scratch/khnolw003/pcbmotor_hpc/Rev0/supervisor.log`.
10. Results:
    - The main outputs are `/scratch/khnolw003/pcbmotor_hpc/RESULTS.txt` / `RESULTS.json` and `<motor>/results/`.
    - Copy them to home (`cp -r`) and to your laptop with WinSCP; scratch is not backed up.

## Formulations and resources
| | Static sweep | Rev0 transient | Rev1-S transient (2 bands) | Rev2-S transient (3 bands, optional) |
|---|---|---|---|---|
| Solver | Magnetostatic, non-linear steel | T-Ω, 1 band, 1000 rpm | T-Ω, Band_R1 + Band_R2 | T-Ω, 3 bands |
| Mesh | adaptive ladder L0–L5 (friday starts at L2) | MT0/1/2 fixed length ops | same | same |
| Excitation | 3-phase DC per angle | Ipk·cos(ωt − ψ + phase), ψ = −30.181°; 0 A and 1 A runs | same, S1 + S2 in series | same, S1 + S2 + S3 in series |
| Cores / RAM | 32–40 / 250–312 GB | 32 / 250 GB | 40 / 312 GB | 40 / 312 GB |
| Wall time (estimate) | 3–8 h per angle | 10–35 h per run | 25–90 h per run | longer than Rev1-S |

## Gates (unchanged)
- **Split-shaft equivalence:** PASS ≤ 0.5 %, MARGINAL ≤ 1.5 %.
- **Short-step (t = 0 copper torque vs static):** ≤ 3 % passes; at MT2, ≤ 6 % passes as "mesh-limited". The production plan must fit within 100 h.
- **Failures in transient runs:**
  - out of memory: no retry;
  - crash: one retry, then the solved steps are salvaged;
  - disk full: no retry; free some space, then rerun with `--retry-failed`.

## Tested here (mock AEDT running the real code)
- All the gate pass and fail paths.
- Transient chains for Rev0, Rev1-S and Rev2-S (three bands), and Friday ALL (Rev0 here plus Rev1-S fanned out at 40 cores).
- Smoke, crash salvage, out of memory, wall-time resubmission, the disk-budget stop, field-frame sizing, and the core-count self-resubmit.

Not testable here: the real AEDT calls, and the real memory, time and disk sizes. The smoke run and the short-step gates exist to find these first.
