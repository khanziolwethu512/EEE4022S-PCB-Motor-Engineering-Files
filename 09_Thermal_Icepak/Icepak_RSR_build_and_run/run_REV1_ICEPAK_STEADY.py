"""
run_REV1_ICEPAK_STEADY.py  -  v1 (2026-10-08)
=============================================
Usage:   python run_REV1_ICEPAK_STEADY.py Rev1D     (or Rev1S)

Same method as run_REV0_ICEPAK_STEADY.py: copies <DESIGN>_ICEPAK_FROZEN.aedt, then per case
sets T_hood / V_fan and P_S1B1..P_S2B5 from I_pk and copper R(T), solves, reads the winding
temperatures, updates R(T), re-solves until the losses change by < 1 %. Checkpoint after
every solve; re-running continues where it stopped. Rotors are still (no stirring).

Magnet temperature = hottest magnet VOLUME MEAN (volume Maximum is not used: it picks up
interpolated interface nodes on the thin magnets - see the Rev0 RUN1 check).
"""
import os, sys, json, shutil, time

DESIGN = (sys.argv[1] if len(sys.argv) > 1 else "Rev1D").replace("-", "")
if DESIGN not in ("Rev1D", "Rev1S", "Rev2S", "RSR"):
    raise SystemExit("Usage: python run_REV1_ICEPAK_STEADY.py Rev1D|Rev1S|Rev2S|RSR")

def _pick_work_dir():
    if os.path.isdir(r"D:\New folder"):
        return r"D:\New folder\Motor run\thermal"
    return os.path.join(os.path.expanduser("~"), "Rev0_work", "thermal")
WORK_DIR = _pick_work_dir()
OUT_DIR  = r"C:\Users\Student\OneDrive - University of Cape Town\EEE4022S Ansys files\Thermal\results"
FROZEN   = os.path.join(WORK_DIR, DESIGN.upper() + "_ICEPAK_FROZEN.aedt")
RUN_NAME = DESIGN.upper() + "_ICEPAK_STEADY_RUN1"
AEDT_VERSION = "2025.2"

R20, ALPHA = 0.2777, 0.00393          # ohm per board-phase at 20 C [AEDT Gate 1]
K_STACK = {"Rev1D": 56.68, "Rev1S": 38.48, "Rev2S": 60.46, "RSR": 39.0}[DESIGN]   # Rev2S: estimate S1 + 2 x S2 (21 Oct)   # mN.m/A (MATLAB/stack_sum, FEM inputs)
I_20MNM = 0.737 * 18.02 / K_STACK                    # same 20 mN.m point as Rev0
CASES = [   # name, I_pk (A), T_hood (C), V_fan (m/s)
    ("T20mNm_fans_on", round(I_20MNM, 3), 30.0, 1.0),
    ("I1p0_fans_on",   1.0, 30.0, 1.0),
    ("I2p0_fans_on",   2.0, 30.0, 1.0),
    ("I2p0_fans_off",  2.0, 30.0, 0.0),
]
MAX_ITERS, TOL = 5, 0.01
MAGS_PER_LAYER = (0, 4, 8, 12)        # sample 4 magnets per layer (read-out time)

PROG = os.path.join(WORK_DIR, RUN_NAME + "_progress.json")
LOG = os.path.join(WORK_DIR, RUN_NAME + "_log.txt")
def log(m):
    line = time.strftime("%H:%M:%S ") + m; print(line)
    open(LOG, "a").write(line + "\n")

def copy_out(paths):
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        for p in paths:
            if os.path.isfile(p): shutil.copy2(p, OUT_DIR)
    except Exception as e:
        print("WARN copy to OneDrive failed: %r" % e)

def p_board(I_pk, T):
    return 1.5 * I_pk ** 2 * R20 * (1 + ALPHA * (T - 20.0))

_FS_OK = {}
def field_stat(ipk, obj, func):
    names = {"Mean": ["Mean", "Average"], "Maximum": ["Maximum", "Max"]}[func]
    combos = [_FS_OK[func]] if func in _FS_OK else [(q, f) for q in ("Temp", "Temperature") for f in names]
    errs = []
    for q, f in combos:
        try:
            v = ipk.post.get_scalar_field_value(q, f, ipk.existing_analysis_sweeps[0], object_name=obj)
        except Exception as e:
            errs.append("%s/%s: %r" % (q, f, e)); continue
        if v is None or v is False:
            errs.append("%s/%s: returned %r" % (q, f, v)); continue
        _FS_OK[func] = (q, f)
        v = float(v)
        return v                     # the field calculator returns degC here (checked on Rev0)
    raise RuntimeError("could not read temperature %s on %s; tried %s" % (func, obj, "; ".join(errs)))

def board_monitors(ipk, names, match):
    """Per-board point-monitor temperatures for the variation just solved (None if not found)."""
    res = {}
    try: mons = ipk.monitor.all_monitors
    except Exception: return {n: None for n in names}
    for n in names:
        res[n] = None
        try:
            data = mons[n].value()
            for entry in data.values():
                var = entry.get("Variation", {})
                if all(k in var and abs(float(var[k][0]) - float(v)) < 1e-3 for k, v in match.items()):
                    res[n] = float(entry["Temperature"]["Value"][-1])
        except Exception:
            pass
    return res

def main():
    from ansys.aedt.core import Icepak
    os.makedirs(WORK_DIR, exist_ok=True)
    print("Work folder: " + WORK_DIR)
    info_p = FROZEN.replace(".aedt", "_info.json")
    if not os.path.exists(info_p):
        alt = os.path.join(OUT_DIR, os.path.basename(info_p))
        if os.path.exists(alt): shutil.copy2(alt, info_p)
    proj = os.path.join(WORK_DIR, RUN_NAME + ".aedt")
    # a frozen build repaired after this run started makes the old run invalid: start over
    if os.path.exists(proj) and os.path.exists(FROZEN) and os.path.getmtime(FROZEN) > os.path.getmtime(proj):
        import glob
        for p in glob.glob(os.path.join(WORK_DIR, RUN_NAME) + "*"):
            if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
            else: os.remove(p)
        print("frozen build is newer than the old run - old run files removed, starting fresh")
    if not os.path.exists(proj):
        src = FROZEN if os.path.exists(FROZEN) else os.path.join(OUT_DIR, os.path.basename(FROZEN))
        if not os.path.exists(src) or not os.path.exists(info_p):
            raise SystemExit("No frozen %s build found. Run: python REV1_ICEPAK_BUILD.py %s" % (DESIGN, DESIGN))
        shutil.copy2(src, proj); log("copied frozen build %s -> %s" % (src, proj))
    info = json.load(open(info_p))
    if "UNITS" not in info:
        raise SystemExit("This frozen build is the old 10-body version. Rebuild: python REV1_ICEPAK_BUILD.py " + DESIGN)
    units, wins, layers = info["UNITS"], info["WINS"], info["MAG_LAYERS"]
    nb, mons = info["N_BOARDS"], info["BOARD_MONITORS"]
    prog = json.load(open(PROG)) if os.path.exists(PROG) else {}
    # v1 read-out bug: winding temperatures above 200 C were wrongly "converted from Kelvin"
    # (e.g. 229 C logged as -43.9 C). Any case holding a temperature below the hood air is
    # invalid and is solved again.
    for name, I, Th, V in CASES:
        h = prog.get(name, {}).get("hist", [])
        if any(t < Th - 5 for e in h for t in e["T_mean"] + e["T_max"]):
            log("re-solving %s: stored temperatures are invalid (Kelvin read-out bug)" % name)
            prog.pop(name)
    ipk = Icepak(project=proj, design=info["DESIGN_NAME"], version=AEDT_VERSION, new_desktop=True)
    log("%s: 20 mN.m point = %.3f A_pk (K_stack %.2f mN.m/A)" % (DESIGN, I_20MNM, K_STACK))
    for name, I, Th, V in CASES:
        if prog.get(name, {}).get("done"):
            log("skip %s (done)" % name); continue
        ipk["T_hood"] = "%gcel" % Th; ipk["V_fan"] = "%gm_per_sec" % V
        T = prog.get(name, {}).get("T_win", [Th + 10] * len(units))
        hist = prog.get(name, {}).get("hist", [])
        for it in range(len(hist), MAX_ITERS):
            P = [nb * p_board(I, t) for t in T]          # per stator (5 boards)
            for lab, p in zip(units, P): ipk["P_" + lab] = "%.5fW" % p
            t0 = time.time()
            if not ipk.analyze_setup(info["SETUP"]): raise RuntimeError("solve failed: " + name)
            ipk.save_project()
            T_mean = [field_stat(ipk, w, "Mean") for w in wins]
            T_max = [field_stat(ipk, w, "Maximum") for w in wins]
            T_mag = {ly: max(field_stat(ipk, names[i], "Mean") for i in MAGS_PER_LAYER)
                     for ly, names in layers.items()}
            T_brd = board_monitors(ipk, mons, {"V_fan": V, "P_" + units[0]: P[0]})
            dP = max(abs(nb * p_board(I, a) - b) / b for a, b in zip(T_mean, P))
            hist.append(dict(P=P, T_mean=T_mean, T_max=T_max, T_mag=T_mag, T_brd=T_brd,
                             s=round(time.time() - t0)))
            prog[name] = dict(T_win=T_mean, hist=hist, done=dP < TOL)
            json.dump(prog, open(PROG, "w"), indent=1)
            log("%s it%d  P=%.3f W  winding mean per stator=%s  hotspot=%.1f  boards=%s  magnets=%s  dP=%.2f%%"
                % (name, it + 1, sum(P), [round(t, 1) for t in T_mean], max(T_max),
                   {k: (round(v, 1) if v is not None else None) for k, v in T_brd.items()},
                   {k: round(v, 1) for k, v in T_mag.items()}, 100 * dP))
            copy_out([PROG, LOG])
            T = T_mean
            if dP < TOL: break
        prog[name]["done"] = True; json.dump(prog, open(PROG, "w"), indent=1)
    out = os.path.join(WORK_DIR, RUN_NAME + "_summary.csv")
    with open(out, "w") as f:
        f.write("case,I_pk,P_total_W,%s,T_hotspot,%s,%s\n" % (",".join("Twin_mean_" + u for u in units),
                ",".join(mons), ",".join("T_" + k for k in layers)))
        for name, I, Th, V in CASES:
            h = prog[name]["hist"][-1]
            f.write("%s,%g,%.3f,%s,%.1f,%s,%s\n" % (name, I, sum(h["P"]),
                    ",".join("%.1f" % t for t in h["T_mean"]), max(h["T_max"]),
                    ",".join("" if h["T_brd"].get(m) is None else "%.1f" % h["T_brd"][m] for m in mons),
                    ",".join("%.1f" % h["T_mag"][k] for k in layers)))
    log("summary written")
    copy_out([PROG, LOG, out])
    ipk.release_desktop(close_projects=True, close_desktop=True)

if __name__ == "__main__":
    main()
