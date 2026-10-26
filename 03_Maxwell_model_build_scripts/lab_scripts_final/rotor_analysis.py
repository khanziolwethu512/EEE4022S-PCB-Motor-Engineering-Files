# -*- coding: utf-8 -*-
"""
Pure-Python post-processing of the rotor-angle magnetostatic sweep (no AEDT, no numpy).

Method (one phase excited, rotor at angle theta, current +I and -I):
    T(+I) = +I * dLam/dtheta + 1/2 I^2 dL/dtheta + Tcog
    T(-I) = -I * dLam/dtheta + 1/2 I^2 dL/dtheta + Tcog
=>  k(theta)   = dLam_PM/dtheta ~ (T(+I) - T(-I)) / (2 I)          [Wb/rad = N.m/A]
    Exact for a linear magnetic system. The rotor contains (possibly nonlinear) steel_1010, so this is a
    central-difference estimate of the PM torque / flux-linkage derivative around zero current
    (linearity to be confirmed with +-0.5 A vs +-1 A at one or two angles).
    c(theta)   = (T(+I) + T(-I)) / 2 = Tcog + 1/2 I^2 dL/dtheta    [N.m]   (expected ~0: coreless stator)
    e(theta)   = omega_m * k(theta)                                 [V]  MAGNITUDE is the back-EMF; the SIGN
                 follows the Maxwell winding/terminal convention (+I enters at <phase>_In; same convention as
                 Maxwell's InducedVoltage = +dLam/dt). Faraday's generated voltage is -dLam/dt; the physical
                 terminal polarity is fixed only after the rotor/terminal polarity check.
    Lam(theta) = integral of k dtheta (zero-mean, half-wave antisymmetric)
T is the torque ON THE ROTOR about +Z (virtual work on magnets + rotor steel). The Lorentz torque on the
stator copper is the reaction and should be equal and opposite; their mismatch is a mesh-quality metric.
"""
import math
import re

UNIT = {"newtonmeter": 1.0, "mnewtonmeter": 1e-3, "unewtonmeter": 1e-6, "nnewtonmeter": 1e-9,
        "knewtonmeter": 1e3, "deg": 1.0, "rad": 180.0 / math.pi, "a": 1.0, "ma": 1e-3}


def _scale(header):
    m = re.search(r"\[([^\]]+)\]", header)
    if not m:
        return 1.0
    return UNIT.get(m.group(1).strip().lower().replace(" ", ""), 1.0)


def read_report_csv(path):
    """AEDT rectangular-plot export -> {"theta": [...deg], "<quantity>": [... SI]} (first column = X)."""
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip()]
    head = [h.strip().strip('"') for h in lines[0].split(",")]
    cols = {}
    names = []
    for h in head:
        base = h.split("[")[0].strip()
        if base.lower().startswith(("theta", "rot_angle")):
            base = "theta"
        names.append(base)
        cols[base] = []
    scales = [_scale(h) for h in head]
    for row in lines[1:]:
        v = row.split(",")
        for i, name in enumerate(names):
            try:
                cols[name].append(float(v[i]) * scales[i])
            except (ValueError, IndexError):
                cols[name].append(float("nan"))
    return cols


def _pick(cols, key):
    for k in cols:
        if key.lower() in k.lower():
            return cols[k]
    return None


def lstsq_harmonics(theta_deg, y, p, orders):
    """Least-squares fit y ~ sum_n a_n cos(n p th) + b_n sin(n p th). Returns {n: (a, b, amplitude, phase_deg)}."""
    basis = []
    for n in orders:
        basis.append(lambda t, n=n: math.cos(n * p * math.radians(t)))
        basis.append(lambda t, n=n: math.sin(n * p * math.radians(t)))
    m = len(basis)
    A = [[sum(basis[i](t) * basis[j](t) for t in theta_deg) for j in range(m)] for i in range(m)]
    rhs = [sum(basis[i](t) * yy for t, yy in zip(theta_deg, y)) for i in range(m)]
    # Gauss-Jordan with partial pivoting
    for c in range(m):
        piv = max(range(c, m), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-14:
            raise ValueError("harmonic fit is singular - not enough distinct angles")
        A[c], A[piv] = A[piv], A[c]
        rhs[c], rhs[piv] = rhs[piv], rhs[c]
        for r in range(m):
            if r != c:
                f = A[r][c] / A[c][c]
                A[r] = [A[r][k] - f * A[c][k] for k in range(m)]
                rhs[r] -= f * rhs[c]
    x = [rhs[i] / A[i][i] for i in range(m)]
    out = {}
    for i, n in enumerate(orders):
        a, b = x[2 * i], x[2 * i + 1]
        out[n] = (a, b, math.hypot(a, b), math.degrees(math.atan2(b, a)))
    return out


def analyse(plus, minus, current, poles, rpm):
    """plus/minus: dicts from read_report_csv for +I and -I (minus=None: +I only, which assumes the
    cogging/reluctance term is ~0 - established by a +/-I baseline). Returns (rows, summary, warnings)."""
    p = poles // 2
    th = plus["theta"]
    single = minus is None
    if single:
        minus = {"theta": th}
    elif [round(t, 6) for t in th] != [round(t, 6) for t in minus["theta"]]:
        raise ValueError("+I and -I reports do not have the same rotor angles")
    tr_p, tc_p = _pick(plus, "Torque_Rotor"), _pick(plus, "Torque_Cu")
    if single:
        # T(-I) = -T(+I) when cogging/reluctance ~ 0 -> the formulas below reduce to k = T(+I)/I, c = 0
        tr_m = [-x for x in tr_p] if tr_p else None
        tc_m = [-x for x in tc_p] if tc_p else None
    else:
        tr_m, tc_m = _pick(minus, "Torque_Rotor"), _pick(minus, "Torque_Cu")
    if tr_p is None or tr_m is None:
        raise ValueError("Torque_Rotor column missing from the export")
    wm = rpm * 2 * math.pi / 60.0
    rows, warn = [], []
    # Single-current runs: the rotor (virtual-work) torque carries a current-even bias that only the +/-I
    # difference removes (smoke test 2026-10-05: ~0.47 mN.m = ~9% of the 1 A PM torque), whereas the Lorentz
    # torque on the copper was linear in I to 2e-6. So with +I only, k is taken from the copper torque.
    use_cu = single and tc_p is not None
    for i, t in enumerate(th):
        if use_cu:
            k = -tc_p[i] / current
        else:
            k = (tr_p[i] - tr_m[i]) / (2.0 * current)
        c = (tr_p[i] + tr_m[i]) / 2.0
        r = {"theta_mech_deg": t, "theta_elec_deg": t * p, "T_rotor_plus_Nm": tr_p[i], "T_rotor_minus_Nm": tr_m[i],
             "dLam_dtheta_Wb_per_rad": k, "cogging_plus_reluctance_Nm": c, "emf_V_at_rpm_maxwell_sign": wm * k}
        if use_cu:
            kr = tr_p[i] / current
            r["dLam_dtheta_from_rotor_single_I"] = kr
            r["action_reaction_mismatch_pct"] = 100.0 * abs(kr - k) / max(abs(k), 1e-12)
            r["cogging_plus_reluctance_Nm"] = float("nan")
        elif tc_p is not None and tc_m is not None:
            kc = -(tc_p[i] - tc_m[i]) / (2.0 * current)
            r["dLam_dtheta_from_copper"] = kc
            r["action_reaction_mismatch_pct"] = 100.0 * abs(kc - k) / max(abs(k), 1e-12)
            r["copper_torque_nonlinearity_pct"] = 100.0 * abs(tc_p[i] + tc_m[i]) / max(abs(tc_p[i] - tc_m[i]), 1e-15)
        rows.append(r)
    ks = [r["dLam_dtheta_Wb_per_rad"] for r in rows]
    # extend by half-wave antisymmetry k(theta + 180 elec) = -k(theta) (magnet pattern N/S alternation;
    # checked below wherever both angles were solved)
    half = 180.0 / p
    fx, fy = list(th), list(ks)
    for t, k in zip(th, ks):
        if not any(abs(((u - t - half) * p + 180.0) % 360.0 - 180.0) < 1e-6 for u in th):
            fx.append(t + half)
            fy.append(-k)
    n_unique = len(set(round(t * p % 360.0, 6) for t in fx))
    orders = [1] if n_unique < 8 else ([1, 3] if n_unique < 12 else [1, 3, 5])
    fit = lstsq_harmonics(fx, fy, p, orders)
    K1 = fit[1][2]
    s = {"pole_pairs": p, "angles": len(th), "harmonics_fitted": orders,
         "currents_solved": "+I only" if single else "+I and -I",
         "k_source": ("Lorentz torque on the copper (+I only; linear in I)" if use_cu else
                      "rotor virtual torque, (T(+I) - T(-I))/2I" if not single else
                      "rotor virtual torque at +I only (biased by the current-even term)"),
         "K1_dLam_dtheta_peak_Wb_per_rad": K1,
         "Lam1_PM_flux_linkage_peak_Wb": K1 / p,
         "kt_peak_Nm_per_A_one_phase": K1,
         "E1_peak_V_at_rpm": wm * K1, "E1_rms_V_at_rpm": wm * K1 / math.sqrt(2), "rpm": rpm,
         "Tavg_ideal_fundamental_3ph_optimum_phasing_Nm_per_Apk": 1.5 * K1,
         "phase_of_k_elec_deg": fit[1][3],
         "fit_coeffs": dict((n, [fit[n][0], fit[n][1]]) for n in orders),
         "cogging_plus_reluctance_max_abs_Nm": (float("nan") if single else
                                                max(abs(r["cogging_plus_reluctance_Nm"]) for r in rows)),
         "emf_sign_convention": "Maxwell winding/terminal convention (+I into _In, e = +dLam/dt); physical "
                                "generator polarity (Faraday e = -dLam/dt) to be fixed by the rotor/terminal "
                                "polarity check",
         "polarity_maxwell_convention": ("+I into the _In terminal with the rotor turning +Z gives %s dLam/dtheta "
                                         "at theta = %g deg" % ("POSITIVE" if ks[0] > 0 else "NEGATIVE", th[0]))}
    for n in orders[1:]:
        s["H%d_over_H1_pct" % n] = 100.0 * fit[n][2] / max(K1, 1e-15)
    if "copper_torque_nonlinearity_pct" in rows[0]:
        s["copper_torque_nonlinearity_max_pct"] = max(r["copper_torque_nonlinearity_pct"] for r in rows)
    if "action_reaction_mismatch_pct" in rows[0]:
        s["action_reaction_mismatch_max_pct"] = max(r["action_reaction_mismatch_pct"] for r in rows)
        if s["action_reaction_mismatch_max_pct"] > 10 and not use_cu:
            warn.append("Rotor (virtual) and copper (Lorentz) torques differ by up to %.0f%% - mesh too coarse"
                        % s["action_reaction_mismatch_max_pct"])
    # half-wave antisymmetry check (k(theta + 180 elec) = -k(theta)) where both angles were solved
    errs = []
    for i, t in enumerate(th):
        for j, u in enumerate(th):
            if abs((u - t) - half) < 1e-6:
                errs.append(abs(ks[j] + ks[i]) / max(K1, 1e-15))
    per = []
    for i, t in enumerate(th):
        for j, u in enumerate(th):
            if abs((u - t) - 2 * half) < 1e-6:
                per.append(abs(ks[j] - ks[i]) / max(K1, 1e-15))
    if per:
        s["full_period_repeat_error_pct"] = 100.0 * max(per)
        if s["full_period_repeat_error_pct"] > 10:
            warn.append("k(theta + %.3g deg) != k(theta) by %.0f%% of K1 - periodicity not reproduced"
                        % (2 * half, s["full_period_repeat_error_pct"]))
    if errs:
        s["half_wave_antisymmetry_pairs_checked"] = len(errs)
        s["half_wave_antisymmetry_error_pct"] = 100.0 * max(errs)
        if s["half_wave_antisymmetry_error_pct"] > 10:
            warn.append("k(theta + %.3g deg) != -k(theta) by %.0f%% of K1 - check mesh/convergence"
                        % (half, s["half_wave_antisymmetry_error_pct"]))
    if not single and s["cogging_plus_reluctance_max_abs_Nm"] > 0.2 * K1 * current:
        warn.append("(T+ + T-)/2 reaches %.3g N.m (> 20%% of the PM torque at %g A) - a coreless stator should give "
                    "~0: mesh noise or an unexpected reluctance effect" % (s["cogging_plus_reluctance_max_abs_Nm"], current))
    return rows, s, warn


def write_csv(path, rows):
    keys = list(rows[0].keys())
    with open(path, "w") as f:
        f.write(",".join(keys) + "\n")
        for r in rows:
            f.write(",".join("%.8g" % r[k] for k in keys) + "\n")


# ------------------------------------------------------------------------- three-phase synchronous check
def _literal(v):
    """Parse a summary value. ast.literal_eval first; AEDT's IronPython 2.7 ast does not fold negative numbers
    ('-0.003' is a UnaryOp there, so literal_eval rejects it), hence a JSON fallback for dicts/lists of numbers
    (int dict keys quoted for JSON, then converted back) and float() for plain numbers."""
    import ast
    import json
    import re
    try:
        return ast.literal_eval(v)
    except Exception:
        pass
    try:
        return float(v)
    except Exception:
        pass
    if v[:1] in "{[":
        try:
            j = json.loads(re.sub(r"([{,]\s*)(-?\d+)\s*:", r'\1"\2":', v))
            if isinstance(j, dict):
                return dict((int(k) if re.match(r"^-?\d+$", k) else k, x) for k, x in j.items())
            return j
        except Exception:
            pass
    return v


def read_summary(path):
    out = {}
    with open(path) as f:
        for line in f:
            if " = " in line and not line.startswith("WARNING"):
                k, v = line.split(" = ", 1)
                out[k.strip()] = _literal(v.strip())
    return out


def k_from_fit(fit, p, theta_deg):
    """dLam_A/dtheta at mechanical angle theta from the baseline harmonic fit {n: [a, b]}."""
    x = math.radians(p * theta_deg)
    return sum(ab[0] * math.cos(int(n) * x) + ab[1] * math.sin(int(n) * x) for n, ab in fit.items())


def analyse_sync(cols, fit, psi_deg, ipk, poles, phase_deg, phase_rot, tol_pct=5.0):
    """cols: export with Torque_Rotor, Torque_Cu (all copper) and Torque_Cu_A/B/C. Torque ON THE ROTOR is
    -Torque_Cu (reaction). Prediction: sum_X I_X(theta) * k_A(theta - rot_X) from the Phase-A baseline."""
    p = poles // 2
    th = cols["theta"]
    tr = _pick(cols, "Torque_Rotor")
    tcs = {}
    for k in cols:
        for n in ("A", "B", "C"):
            if k.lower().startswith(("torque_cu_%s" % n).lower()):
                tcs[n] = cols[k]
    tot = None
    for k in cols:
        if k.lower().startswith("torque_cu.") or k.lower() == "torque_cu":
            tot = cols[k]
    rows, warn = [], []
    for i, t in enumerate(th):
        r = {"theta_mech_deg": t, "theta_elec_deg": t * p}
        pred = 0.0
        for net in ("PHASE_A", "PHASE_B", "PHASE_C"):
            n = net[-1]
            cur = ipk * math.cos(math.radians(p * t - psi_deg + phase_deg[net]))
            kx = k_from_fit(fit, p, t - phase_rot[net])
            r["I_%s_A" % n] = cur
            r["T_%s_pred_Nm" % n] = cur * kx
            pred += cur * kx
            if n in tcs:
                r["T_%s_solved_Nm" % n] = -tcs[n][i]
        r["T_pred_Nm"] = pred
        if tot is not None:
            r["T_solved_copper_Nm"] = -tot[i]
        elif tcs:
            r["T_solved_copper_Nm"] = sum(-tcs[n][i] for n in tcs)
        if tr is not None:
            r["T_solved_rotor_Nm"] = tr[i]
        rows.append(r)
    mean = lambda xs: sum(xs) / float(len(xs))
    Ts = [r["T_solved_copper_Nm"] for r in rows]
    Tp = [r["T_pred_Nm"] for r in rows]
    K1 = math.hypot(*fit.get(1, fit.get("1")))
    s = {"angles": len(th), "Ipk_A": ipk, "psi_baseline_elec_deg": psi_deg,
         "T_ideal_1p5_K1_Ipk_Nm": 1.5 * K1 * ipk,
         "T_pred_mean_Nm": mean(Tp), "T_solved_copper_mean_Nm": mean(Ts),
         "mean_torque_error_pct": 100.0 * (mean(Ts) - mean(Tp)) / max(abs(mean(Tp)), 1e-15),
         "ripple_solved_pct": 100.0 * (max(Ts) - min(Ts)) / max(abs(mean(Ts)), 1e-15),
         "ripple_pred_pct": 100.0 * (max(Tp) - min(Tp)) / max(abs(mean(Tp)), 1e-15)}
    if "T_solved_rotor_Nm" in rows[0]:
        s["T_solved_rotor_mean_Nm"] = mean([r["T_solved_rotor_Nm"] for r in rows])
    per = []
    for n in tcs:
        per.append(max(abs(r["T_%s_solved_Nm" % n] - r["T_%s_pred_Nm" % n]) for r in rows) / max(K1 * ipk, 1e-15))
    if per:
        s["per_phase_max_error_pct_of_K1_Ipk"] = 100.0 * max(per)
    ok = abs(s["mean_torque_error_pct"]) <= tol_pct and (not per or 100.0 * max(per) <= 2 * tol_pct)
    s["superposition_check"] = "PASSED" if ok else "FAILED"
    if not ok:
        warn.append("Three-phase torque does not match the Phase-A superposition prediction (mean error %.1f%%%s) "
                    "- check the current angle / phase sequence / linearity before using the DOE"
                    % (s["mean_torque_error_pct"], (", per-phase %.1f%%" % s["per_phase_max_error_pct_of_K1_Ipk"])
                                                     if per else ""))
    return rows, s, warn
