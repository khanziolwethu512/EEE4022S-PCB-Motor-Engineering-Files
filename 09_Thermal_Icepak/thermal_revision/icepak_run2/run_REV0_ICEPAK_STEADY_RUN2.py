"""
run_REV0_ICEPAK_STEADY.py  -  v1 (2026-10-08)
=============================================
Test script: copies REV0_ICEPAK_FROZEN.aedt, then for each case
  sets T_hood / V_fan, sets P_board1..5 from I_pk and copper R(T),
  solves steady state, reads board/magnet temperatures, updates
  R(T) and re-solves until the losses change by < 1 %.
Saves the project and icepak_progress.json after every solve, so a
crash resumes at the next unfinished case (finished cases are skipped).

Geometry is never rebuilt. The rotor is still: results are the
no-stirring (stalled-air) bound; compare with rev0_thermal_lumped.py.
"""
import os, json, shutil, time

def _pick_work_dir():
    # Local run folder, never OneDrive (sync locks corrupt AEDT projects).
    # Uses D:/New folder on PCs that have it, otherwise C:/Users/Student/Rev0_work.
    if os.path.isdir(r"D:\New folder"):
        return r"D:\New folder\Motor run\thermal"
    return os.path.join(os.path.expanduser("~"), "Rev0_work", "thermal")
WORK_DIR    = _pick_work_dir()
OUT_DIR     = r"C:\Users\Student\OneDrive - University of Cape Town\EEE4022S Ansys files\Thermal\results"
FROZEN      = os.path.join(WORK_DIR, "REV0_ICEPAK_FROZEN.aedt")
RUN_NAME    = "REV0_ICEPAK_STEADY_RUN2"
AEDT_VERSION = "2025.2"

R20, ALPHA = 1.89 / 5, 0.00393         # ohm per board-phase at 20 C - MEASURED 1.89 ohm per stator (RUN2)
CASES = [   # name, I_pk (A), T_hood (C), V_fan (m/s)  - RUN2 (22 Oct): measured R, revised limit points
    ("I1p116_Ta25_fans_on",  1.116, 25.0, 1.0),
    ("I1p030_Ta30_fans_on",  1.030, 30.0, 1.0),
    ("I1p116_Ta25_fans_off", 1.116, 25.0, 0.0),
    ("I1p0_Ta25_fans_on", 1.0, 25.0, 1.0),
]
MAX_ITERS, TOL = 4, 0.01

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

_FS_OK = {}   # remembers which (quantity, function) spelling worked

def field_stat(ipk, obj, func):
    """Volume Mean/Maximum of temperature on one object (PyAEDT 1.8 calculator)."""
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
        return v - 273.15 if v > 200 else v      # Kelvin -> C if the calculator returns K
    raise RuntimeError("could not read temperature %s on %s; tried %s" % (func, obj, "; ".join(errs)))

def main():
    try:
        from ansys.aedt.core import Icepak
    except ImportError:
        from pyaedt import Icepak
    proj = os.path.join(WORK_DIR, RUN_NAME + ".aedt")
    os.makedirs(WORK_DIR, exist_ok=True)
    print("Work folder: " + WORK_DIR)
    if not os.path.exists(proj):
        src = FROZEN if os.path.exists(FROZEN) else os.path.join(OUT_DIR, os.path.basename(FROZEN))
        if not os.path.exists(src):
            raise SystemExit("No frozen build found in %s or %s.\n"
                             "Run REV0_ICEPAK_BUILD.py first and check it ends with 'FROZEN:'." % (WORK_DIR, OUT_DIR))
        shutil.copy2(src, proj); log("copied frozen build %s -> %s" % (src, proj))
    prog = json.load(open(PROG)) if os.path.exists(PROG) else {}
    try:
        ipk = Icepak(project=proj, design="Rev0_thermal", version=AEDT_VERSION, new_desktop=False)
    except TypeError:
        ipk = Icepak(projectname=proj, designname="Rev0_thermal", specified_version=AEDT_VERSION,
                     new_desktop_session=False)
    for name, I, Th, V in CASES:
        if prog.get(name, {}).get("done"):
            log("skip %s (done)" % name); continue
        ipk["T_hood"] = "%gcel" % Th; ipk["V_fan"] = "%gm_per_sec" % V
        T = prog.get(name, {}).get("T_win", [Th + 10] * 5)
        hist = prog.get(name, {}).get("hist", [])
        for it in range(len(hist), MAX_ITERS):
            P = [p_board(I, t) for t in T]
            for k in range(5): ipk["P_board%d" % (k + 1)] = "%.5fW" % P[k]
            t0 = time.time()
            ok = ipk.analyze_setup("SteadyRev0")
            ipk.save_project()
            if not ok: raise RuntimeError("solve failed: " + name)
            T_mean = [field_stat(ipk, "Win%d" % k, "Mean") for k in range(1, 6)]
            T_max = [field_stat(ipk, "Win%d" % k, "Maximum") for k in range(1, 6)]
            # magnet temperature = hottest magnet VOLUME MEAN. Volume "Maximum" on the thin magnets
            # picks up interpolated interface nodes (RUN1 check: max ~128 C vs mean ~96 C and centre
            # monitor 98 C at 2 A fans off), so it is not used.
            T_mag = max(field_stat(ipk, "Mag%02d" % i, "Mean") for i in range(16))
            hist.append(dict(P=P, T_mean=T_mean, T_max=T_max, T_mag=T_mag, s=round(time.time() - t0)))
            dP = max(abs(p_board(I, a) - b) / b for a, b in zip(T_mean, P))
            prog[name] = dict(T_win=T_mean, hist=hist, done=dP < TOL)
            json.dump(prog, open(PROG, "w"), indent=1)
            copy_out([PROG, LOG])
            log("%s it%d  P=%.3f W total  Tmean B1..B5=%s  Tmax=%.1f  Tmag=%.1f  dP=%.2f%%"
                % (name, it + 1, sum(P), [round(t, 1) for t in T_mean], max(T_max), T_mag, 100 * dP))
            T = T_mean
            if dP < TOL: break
        prog[name]["done"] = True; json.dump(prog, open(PROG, "w"), indent=1)
    # summary CSV
    with open(os.path.join(WORK_DIR, RUN_NAME + "_summary.csv"), "w") as f:
        f.write("case,I_pk,P_total_W,T_mean_B1,T_mean_B3,T_mean_B5,T_hotspot,T_magnet\n")
        for name, I, Th, V in CASES:
            h = prog[name]["hist"][-1]
            f.write("%s,%g,%.3f,%.1f,%.1f,%.1f,%.1f,%.1f\n" % (name, I, sum(h["P"]), h["T_mean"][0],
                    h["T_mean"][2], h["T_mean"][4], max(h["T_max"]), h["T_mag"]))
    log("summary written")
    copy_out([PROG, LOG, os.path.join(WORK_DIR, RUN_NAME + "_summary.csv")])
    ipk.release_desktop(close_projects=False, close_desktop=False)

if __name__ == "__main__":
    main()
