# -*- coding: utf-8 -*-
"""
REV0 phase_check.py - three-phase synchronous check BY SUPERPOSITION of single-phase FEM runs.

Why: the full single-board three-phase model (REF_ROTOR_MS_3PH, all 3 phases of copper + rotor, 4 passes) exceeded
16 GB at its first matrix solve and crashed the lab PC (2026-10-07). The stator has no iron and the response is
linear in current (baseline: copper torque linear to 0.005 %, +/-I rotor torques antisymmetric), so the
synchronous torque is exactly the sum of the single-phase contributions:
    T(theta) = sum_X I_X(theta) * k_X(theta),   I_X = Ipk*cos(theta_e + phi_sync + PHASE_DEG[X]), phi_sync = -psi_A
with k_X(theta) = K_X*cos(theta_e - psi_X) solved separately for each phase (Phase A = baseline, B and C = the
REV0_CHECK_PHB / _PHC runs). Mean torque = 0.5*Ipk*sum_X K_X*cos(psi_X - psi_A + PHASE_DEG[X])  (pass: within 2 %
of 1.5*K_A*Ipk and every phase within 2 % / 2 deg of the geometric expectation psi_B = psi_A + 120, psi_C = psi_A - 120).

Run with plain Python or AEDT Tools > Run Script, after run_PHASE_BC.py. Reads Motor run\results.
"""
from __future__ import print_function

import math
import os
import sys

PHASE_DEG = {"A": 0.0, "B": -120.0, "C": 120.0}
RUNS = {"A": "REV0_REF_ROTOR_MS_SWEEP", "B": "REV0_CHECK_PHB", "C": "REV0_CHECK_PHC"}
IPK = 1.0


def _here():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def main():
    sys.path.insert(0, _here())
    import rotor_analysis
    res = os.path.join(os.path.dirname(_here()), "results")
    K, psi = {}, {}
    for ph, name in sorted(RUNS.items()):
        p = os.path.join(res, name + "_results", "rotor_sweep_summary.txt")
        if not os.path.isfile(p):
            raise SystemExit("Missing %s - run run_PHASE_BC.py first (or the baseline)" % p)
        s = rotor_analysis.read_summary(p)
        K[ph], psi[ph] = float(s["K1_dLam_dtheta_peak_Wb_per_rad"]), float(s["phase_of_k_elec_deg"])
    lines = ["Three-phase synchronous check by superposition of single-phase FEM (Ipk = %g A):" % IPK]
    ok = True
    expect = {"A": psi["A"], "B": psi["A"] + 120.0, "C": psi["A"] - 120.0}
    for ph in "ABC":
        dk = 100.0 * (K[ph] / K["A"] - 1.0)
        dp = _wrap(psi[ph] - expect[ph])
        good = abs(dk) <= 2.0 and abs(dp) <= 2.0
        ok = ok and good
        lines.append("  Phase %s: K1 = %.4f mN.m/A (%+.2f %% vs A), psi = %+.2f deg (expected %+.2f, error %+.2f deg) %s"
                     % (ph, 1e3 * K[ph], dk, _wrap(psi[ph]), _wrap(expect[ph]), dp, "OK" if good else "CHECK"))
    tmean = 0.5 * IPK * sum(K[ph] * math.cos(math.radians(psi[ph] - psi["A"] + PHASE_DEG[ph])) for ph in "ABC")
    ideal = 1.5 * K["A"] * IPK
    err = 100.0 * (tmean / ideal - 1.0)
    ok = ok and abs(err) <= 2.0
    lines.append("  Mean synchronous torque = %.4f mN.m vs ideal 1.5*K1_A*Ipk = %.4f mN.m (%+.2f %%)"
                 % (1e3 * tmean, 1e3 * ideal, err))
    for wrong, sgn in (("reversed sequence (A-C-B)", -1),):
        t_bad = 0.5 * IPK * sum(K[ph] * math.cos(math.radians(psi[ph] - psi["A"] + sgn * PHASE_DEG[ph])) for ph in "ABC")
        lines.append("  (for comparison, %s would give %.4f mN.m)" % (wrong, 1e3 * t_bad))
    lines.append("THREE-PHASE CHECK: %s" % ("PASS" if ok else "CHECK - send this output"))
    out = os.path.join(res, "THREE_PHASE_CHECK.txt")
    open(out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    try:
        oDesktop.AddMessage("", "", 0 if ok else 2, "[phase_check] " + lines[-1] + " - " + lines[-3].strip())  # noqa: F821
    except Exception:
        pass


main()
