# -*- coding: utf-8 -*-
"""
REV0 fix_baseline_summary.py - re-run ONLY the analysis of the finished Phase-A baseline sweep
(REV0_REF_ROTOR_MS_SWEEP) so its rotor_sweep_summary.txt gains the harmonic fit (fit_coeffs) that the
three-phase check needs. No AEDT project is opened and nothing is solved: it re-reads the exported
Torque_Iplus.csv / Torque_Iminus.csv of the baseline and runs the current rotor_analysis on them.

Run with plain Python, or AEDT Tools > Run Script (no project needs to be open). Takes seconds.
The old summary is kept as rotor_sweep_summary_pre_v65.txt.
"""
from __future__ import print_function

import os
import shutil
import sys

BASELINE = "REV0_REF_ROTOR_MS_SWEEP"
RESULTS_DIR = ""        # "" = auto: the results folder next to this script's folder (Motor run\results)
POLES, RPM, SWEEP_I = 16, 1000.0, 1.0
GEOMETRY = "Geometry: air gap 1.000 mm, back iron 2.00 mm, magnet centre radius 28.00 mm"


def _here():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def _results_dir():
    if RESULTS_DIR:
        return RESULTS_DIR
    cands = [os.path.join(os.path.dirname(_here()), "results")]
    sub = os.path.join("EEE4022S Ansys files", "Motor run", "results")
    for env in ("OneDriveCommercial", "OneDrive"):
        if os.environ.get(env):
            cands.append(os.path.join(os.environ[env], sub))
    cands += [os.path.join(os.path.expanduser("~"), "OneDrive - University of Cape Town", sub), r"D:\New folder"]
    for c in cands:
        if os.path.isdir(os.path.join(c, BASELINE + "_results")):
            return c
    raise SystemExit("Cannot find %s_results. Set RESULTS_DIR at the top of this file. Tried: %s" % (BASELINE, cands))


def main():
    sys.path.insert(0, _here())
    import rotor_analysis
    d = os.path.join(_results_dir(), BASELINE + "_results")
    plus_p, minus_p = os.path.join(d, "Torque_Iplus.csv"), os.path.join(d, "Torque_Iminus.csv")
    for p in (plus_p, minus_p):
        if not os.path.isfile(p):
            raise SystemExit("Missing %s - files present: %s" % (p, sorted(os.listdir(d))))
    plus, minus = rotor_analysis.read_report_csv(plus_p), rotor_analysis.read_report_csv(minus_p)
    rows, s, warn = rotor_analysis.analyse(plus, minus, SWEEP_I, POLES, RPM)
    if "fit_coeffs" not in s:
        raise SystemExit("rotor_analysis did not return fit_coeffs - wrong rotor_analysis.py version?")
    summ = os.path.join(d, "rotor_sweep_summary.txt")
    old = rotor_analysis.read_summary(summ) if os.path.isfile(summ) else {}
    backup = os.path.join(d, "rotor_sweep_summary_pre_v65.txt")
    if os.path.isfile(summ) and not os.path.isfile(backup):
        shutil.copyfile(summ, backup)
    with open(summ, "w") as f:
        f.write("Profile REF_ROTOR_MS_SWEEP  project %s  (re-analysed by fix_baseline_summary.py, no re-solve)\n"
                % BASELINE)
        f.write(GEOMETRY + "\n")
        for k in s:
            f.write("%s = %s\n" % (k, s[k]))
        for w in warn:
            f.write("WARNING: %s\n" % w)
    rotor_analysis.write_csv(os.path.join(d, "rotor_sweep_table.csv"), rows)
    k1 = s["K1_dLam_dtheta_peak_Wb_per_rad"]
    print("Re-analysed %d angles: K1 = %.4f mN.m/A, psi = %.2f deg elec, fit_coeffs = %s"
          % (s.get("angles", len(rows)), 1e3 * k1, s["phase_of_k_elec_deg"], s["fit_coeffs"]))
    if old.get("K1_dLam_dtheta_peak_Wb_per_rad"):
        k_old = float(old["K1_dLam_dtheta_peak_Wb_per_rad"])
        dev = 100.0 * (k1 / k_old - 1.0)
        print("Previous summary K1 = %.4f mN.m/A -> difference %+.3f %%  (%s)"
              % (1e3 * k_old, dev, "OK" if abs(dev) < 0.5 else "CHECK - send this output"))
    print("Written: %s (old copy: %s)" % (summ, backup))
    try:
        oDesktop.AddMessage("", "", 0, "[fix_baseline_summary] K1 %.4f mN.m/A, psi %.2f deg; fit_coeffs written to %s"  # noqa: F821
                            % (1e3 * k1, s["phase_of_k_elec_deg"], summ))
    except Exception:
        pass


main()
