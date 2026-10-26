"""Rev0 as-built study (v14) - reproducible post-processing of the HPC field maps + detailed-board checks + the
independent analytical prediction. Produces the comparison CSV, report figures and a provenance record.

  python asbuilt_post.py --results <folder holding RESULTS_FIELDMAP_REV0_HW, RESULTS_FIELDMAP_REV0_B_G400, ...>
                         [--analytical asbuilt_analytical.json] [--out out]

Cases (all star connection, 16 poles, five boards in series per phase):
  A  nominal: gap 1.0 mm, backplate 86/19 x 2 mm, 19 mm shaft            (reference K 18.534 from the full-motor FEM)
  B  gap only: gap 4.0 mm, everything else as A
  C  as built: gap 4.0 mm, backplate 80/25 x 2 mm, 8 mm steel shaft, hub non-magnetic (air)
  C350 / C450: Case C at 3.5 / 4.5 mm (gap uncertainty band)

K (T = 1.5 K I_pk, e_ph,pk = K w_m) for every case is taken as
  K = sum over boards k of  K_FM,k  x  r(d_k),     r(d) = K_sheet(d) / K_centre-line(d)  (analytical, same distance)
i.e. the Maxwell field map (centre-line integration of the Maxwell field, case geometry incl. backplate) corrected
board by board for the centre-line current-routing bias with the validated sheet-current ratio. Check at 1 mm:
this route vs the full-motor detailed FEM; at 4 mm: vs the detailed single boards (DIAG_REV0_C_B1/B5).
Back-EMF at speed n is K x w_m (the field-only solution depends on rotor position only: verified 500/1000/2000 rpm);
these are SPEED-SCALED values, not separate transient solutions.
"""
import argparse, csv, json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
P = 8
PITCH = 1.02032
SPEEDS = [50, 100, 150, 1000]
REF_A = {"K": 18.534, "source": "full-motor detailed FEM, SLURM 1470376"}
CASES = [  # key, label, results folder, gap, OD, ID, shaft
    ("A", "A nominal (1 mm, 86/19)", "RESULTS_FIELDMAP_REV0_HW", 1.0, 86.0, 19.0, 19.0),
    ("B", "B gap only (4 mm, 86/19)", "RESULTS_FIELDMAP_REV0_B_G400", 4.0, 86.0, 19.0, 19.0),
    ("C", "C as built (4 mm, 80/25, 8 mm shaft)", "RESULTS_FIELDMAP_REV0_C_ASBUILT", 4.0, 80.0, 25.0, 8.0),
    ("C350", "C at 3.5 mm", "RESULTS_FIELDMAP_REV0_C350", 3.5, 80.0, 25.0, 8.0),
    ("C450", "C at 4.5 mm", "RESULTS_FIELDMAP_REV0_C450", 4.5, 80.0, 25.0, 8.0),
]
PROBE_A = "RESULTS_FIELDMAP_REV0_A_PROBE"
DIAG = {"C_B1": ("RESULTS_DIAG_REV0_C_B1", 4.0), "C_B5": ("RESULTS_DIAG_REV0_C_B5", 4.0 + 4 * PITCH)}
MEASURED = {"rpm": 100, "E_LL_rms": 0.096, "note": "preliminary bench value, ~4 mm gap, NOT used for calibration"}
BR_LIB, BR_N35 = 1.23, (1.17, 1.22)       # library value used by every model / N35 datasheet range


def wm(n):
    return n * 2 * math.pi / 60.0


def e_ll(K, n):
    return math.sqrt(3) * K * wm(n) / math.sqrt(2)


def ratio_fn(an):
    """r(d) interpolated (linear in d) from every analytical board point."""
    pts = sorted((b["distance_mm"], b["ratio_sheet_over_cl"]) for c in an["cases"].values() for b in c["boards"].values())
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return lambda d: float(np.interp(d, xs, ys))


def load_json(p):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--analytical", default=os.path.join(HERE, "asbuilt_analytical.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    an = load_json(a.analytical)
    if not an:
        sys.exit("analytical json missing: " + a.analytical)
    r_of = ratio_fn(an)
    rows, boards, prov, warn = [], {}, [], []
    for key, label, folder, gap, od, idd, sh in CASES:
        fm = load_json(os.path.join(a.results, folder, "fieldmap_results.json"))
        if not fm:
            warn.append("%s: %s/fieldmap_results.json not found - case NOT solved / not retrieved" % (key, folder))
            continue
        kb = [fm["boards"]["S1_B%d_PHASE_A" % (k + 1)]["K1"] * 1e3 for k in range(5)]
        rk = [r_of(gap + k * PITCH) for k in range(5)]
        kcorr = [x * y for x, y in zip(kb, rk)]
        # phase sum of the corrected boards (boards are in phase within 0.2 deg -> scalar sum within 0.002 %)
        K_fm = fm["machine"]["PHASE_A"]["K1"] * 1e3
        K = sum(kcorr) * (K_fm / sum(kb))                 # keeps the vector-sum factor of the field map
        wf = fm.get("waveform", {})
        thd_ph = wf.get("PHASE_A", {}).get("THD_pct", float("nan"))
        thd_ll = wf.get("line_AB", {}).get("THD_pct", float("nan"))
        h = wf.get("PHASE_A", {}).get("H_pct", {})
        psi = fm["machine"]["PHASE_A"]["psi"]
        bal = [fm["machine"][ph]["K1"] for ph in ("PHASE_A", "PHASE_B", "PHASE_C")]
        anc = an["cases"].get("gap_%.2f" % gap) if abs(od - 86.0) < 1e-9 else None
        row = {"case": key, "label": label, "gap_mm": gap, "backplate_OD_mm": od, "backplate_ID_mm": idd,
               "shaft_mm": sh, "K_mNm_per_A": K, "K_fieldmap_centreline": K_fm,
               "K_analytical_sheet_independent": anc["K_sheet"] if anc else "",
               "torque_per_Apk_mNm": 1.5 * K, "psi_pm_mWb": K / P, "Ke_Vs_per_rad": K * 1e-3,
               "psi_A_deg": psi, "phase_K_spread_pct": 100 * (max(bal) - min(bal)) / (sum(bal) / 3),
               "THD_phase_pct": thd_ph, "THD_line_pct": thd_ll, "H3_pct": h.get("H3", ""), "H5_pct": h.get("H5", ""),
               "H7_pct": h.get("H7", ""), "ripple_pct": wf.get("ripple_pct", ""),
               "eddy_1000rpm_mW": 1e3 * fm["eddy"]["total_W"] if fm.get("eddy") else ""}
        for n in SPEEDS:
            row["f_e_%drpm_Hz" % n] = n / 60.0 * P
            row["E_LL_rms_%drpm_V" % n] = e_ll(K * 1e-3, n)
            row["E_LL_rms_%drpm_V_incl_harm" % n] = e_ll(K * 1e-3, n) * math.sqrt(1 + (thd_ll / 100) ** 2) if thd_ll == thd_ll else ""
        st = fm.get("steel", {})
        for pn in ("PCB_face_plus0p25mm", "PCB_B1_mid", "PCB_B3_mid", "PCB_B5_mid", "R1_BackIron"):
            if pn in st:
                row["Bz_abs_max_%s_T" % pn] = st[pn].get("Bz_abs_max", "")
                row["B_max_%s_T" % pn] = st[pn]["max"]
        rows.append(row)
        boards[key] = {"fm": kb, "ratio": rk, "corrected": kcorr}
        prov.append("%s: %s (fieldmap_results.json), %d angles%s" % (key, folder, len(fm["thetas"]),
                    ", half-wave" if len(fm["thetas"]) == 12 else ""))
    if not rows:
        sys.exit("no solved case found under " + a.results + "\n" + "\n".join(warn))
    byk = dict((r["case"], r) for r in rows)
    for r in rows:
        r["dK_vs_A_pct"] = 100 * (r["K_mNm_per_A"] / byk["A"]["K_mNm_per_A"] - 1) if "A" in byk else ""
        r["dK_vs_A_ref18534_pct"] = 100 * (r["K_mNm_per_A"] / REF_A["K"] - 1)
    contrib = {}
    if all(k in byk for k in "ABC"):
        KA, KB, KC = (byk[k]["K_mNm_per_A"] for k in "ABC")
        contrib = {"gap_effect_B_over_A_pct": 100 * (KB / KA - 1), "rotor_effect_C_over_B_pct": 100 * (KC / KB - 1),
                   "total_C_over_A_pct": 100 * (KC / KA - 1)}
    # Br band and gap band for Case C
    band = {}
    if "C" in byk:
        lo = byk["C450"]["K_mNm_per_A"] if "C450" in byk else None
        hi = byk["C350"]["K_mNm_per_A"] if "C350" in byk else None
        KC = byk["C"]["K_mNm_per_A"]
        band = {"K_C": KC, "K_gap4p5": lo, "K_gap3p5": hi,
                "Br_factor_range": [BR_N35[0] / BR_LIB, BR_N35[1] / BR_LIB]}
        for n in (50, 100, 150):
            kmin = (lo if lo else KC) * band["Br_factor_range"][0]
            kmax = (hi if hi else KC) * band["Br_factor_range"][1]
            band["E_LL_%drpm" % n] = [e_ll(KC * 1e-3, n), e_ll(kmin * 1e-3, n), e_ll(kmax * 1e-3, n)]
    # detailed-board checks
    checks = []
    for name, (folder, d) in DIAG.items():
        dj = load_json(os.path.join(a.results, folder, "diag_results.json"))
        if not dj:
            warn.append("%s: %s not found" % (name, folder))
            continue
        kcu = dj["routes"]["copper Lorentz, (+I - -I)/2"]["K1_mNm_per_A"]
        krot = dj["routes"]["rotor virtual work, (+I - -I)/2"]["K1_mNm_per_A"]
        kb_i = 0 if name.endswith("B1") else 4
        pred = boards["C"]["corrected"][kb_i] if "C" in boards else float("nan")
        checks.append({"check": name, "distance_mm": d, "detailed_copper": kcu, "detailed_rotor": krot,
                       "fieldmap_x_ratio": pred, "diff_pct": 100 * (pred / kcu - 1)})
    # --------------------------------------------------------------------------------------- write CSV / JSON
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(os.path.join(a.out, "asbuilt_comparison.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(dict((k, round(v, 6) if isinstance(v, float) else v) for k, v in r.items()))
    with open(os.path.join(a.out, "asbuilt_boards.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "board", "distance_mm", "K_fieldmap_centreline", "ratio_sheet_over_cl", "K_corrected"])
        for key, label, folder, gap, od, idd, sh in CASES:
            if key in boards:
                for k in range(5):
                    w.writerow([key, k + 1, round(gap + k * PITCH, 5), round(boards[key]["fm"][k], 5),
                                round(boards[key]["ratio"][k], 5), round(boards[key]["corrected"][k], 5)])
    summary = {"cases": rows, "contributions": contrib, "uncertainty": band, "detailed_checks": checks,
               "analytical_independent": {k: v["K_sheet"] for k, v in an["cases"].items()},
               "measured": MEASURED, "warnings": warn, "provenance": prov}
    json.dump(summary, open(os.path.join(a.out, "asbuilt_summary.json"), "w"), indent=1)
    # --------------------------------------------------------------------------------------- figures
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
    col = {"A": "#1f4e79", "B": "#b03a2e", "C": "#2e8b57", "C350": "#2e8b57", "C450": "#2e8b57"}
    # F1 back-EMF vs speed
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    ns = np.linspace(0, 200, 50)
    for k in ("B", "C"):
        if k in byk:
            ax.plot(ns, [e_ll(byk[k]["K_mNm_per_A"] * 1e-3, n) for n in ns], "-" if k == "C" else "--", color=col[k],
                    lw=1.4 if k == "C" else 2.4, label=byk[k]["label"] + (" (under C)" if k == "B" else ""), zorder=3 if k == "C" else 2)
    if band.get("E_LL_100rpm"):
        lo_k = (byk["C450"]["K_mNm_per_A"] if "C450" in byk else byk["C"]["K_mNm_per_A"]) * band["Br_factor_range"][0]
        hi_k = (byk["C350"]["K_mNm_per_A"] if "C350" in byk else byk["C"]["K_mNm_per_A"]) * band["Br_factor_range"][1]
        ax.fill_between(ns, [e_ll(lo_k * 1e-3, n) for n in ns], [e_ll(hi_k * 1e-3, n) for n in ns], color=col["C"],
                        alpha=0.15, label="C: gap 3.5-4.5 mm, Br 1.17-1.22 T")
    for n in (50, 100, 150):
        if "C" in byk:
            ax.plot([n], [e_ll(byk["C"]["K_mNm_per_A"] * 1e-3, n)], "o", color=col["C"], ms=4)
    ax.plot([MEASURED["rpm"]], [MEASURED["E_LL_rms"]], "kx", ms=7, mew=1.5, label="preliminary measurement (not used)")
    ax.set_xlabel("Speed (rpm)"); ax.set_ylabel("Line-to-line back-EMF (V rms)")
    ax.legend(fontsize=6.5, loc="upper left"); fig.tight_layout()
    fig.savefig(os.path.join(a.out, "X1_backemf_vs_speed.png"), dpi=220); plt.close(fig)
    # F2 K vs gap
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    gs = sorted((c["gap_mm"], c["K_sheet"]) for c in an["cases"].values())
    gx = np.linspace(0.8, 4.8, 60)
    lam = math.log(gs[0][1] / gs[-1][1]) / (gs[-1][0] - gs[0][0]) if len(gs) > 1 else 0.3
    ax.plot([g for g, _ in gs], [k for _, k in gs], "s", mfc="white", color="0.3", label="analytical, 86 mm plate (independent)")
    for k in ("A", "B", "C", "C350", "C450"):
        if k in byk:
            ax.plot([byk[k]["gap_mm"]], [byk[k]["K_mNm_per_A"]], "o" if k in "AB" else "^", color=col[k], ms=6,
                    label=byk[k]["label"] if k in ("A", "B", "C") else None)
    ax.axhline(REF_A["K"], color="0.6", lw=0.8, ls=":"); ax.text(1.15, REF_A["K"] + 0.5, "full-motor detailed FEM 18.534", fontsize=7, color="0.4")
    gfit = [(c["gap_mm"], c["K_sheet"]) for c in an["cases"].values()]
    if len(gfit) >= 3:
        cf = np.polyfit([g for g, _ in gfit], np.log([k for _, k in gfit]), 2)
        ax.plot(gx, np.exp(np.polyval(cf, gx)), "-", color="0.75", lw=0.9, zorder=0)
    ax.set_ylim(0, 20.5)
    ax.set_xlabel("Magnet to board-1 gap (mm)"); ax.set_ylabel("K (mN·m/A)"); ax.legend(fontsize=6.5, loc="center right")
    fig.tight_layout(); fig.savefig(os.path.join(a.out, "X2_K_vs_gap.png"), dpi=220); plt.close(fig)
    # F3 board-by-board
    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    wdt = 0.26
    for j, k in enumerate(("A", "B", "C")):
        if k in boards:
            ax.bar(np.arange(1, 6) + (j - 1) * wdt, boards[k]["corrected"], wdt, color=col[k], label=byk[k]["label"])
    ax.set_xlabel("Board (1 = nearest the magnets)"); ax.set_ylabel("Board K (mN·m/A)"); ax.legend(fontsize=6.5)
    fig.tight_layout(); fig.savefig(os.path.join(a.out, "X3_board_contributions.png"), dpi=220); plt.close(fig)
    # F4 field maps 0.25 mm off the board-1 face (Bz)
    planes = [("A", PROBE_A), ("B", "RESULTS_FIELDMAP_REV0_B_G400"), ("C", "RESULTS_FIELDMAP_REV0_C_ASBUILT")]
    have = [(k, os.path.join(a.results, f, "B_PCB_face_plus0p25mm.fld")) for k, f in planes]
    have = [(k, p) for k, p in have if os.path.isfile(p)]
    if have:
        fig, axs = plt.subplots(1, len(have), figsize=(2.6 * len(have) + 0.6, 2.7))
        axs = np.atleast_1d(axs)
        for ax, (k, p) in zip(axs, have):
            d = np.array([[float(v) for v in l.replace(",", " ").split()[:6]] for l in open(p)
                          if len(l.split()) >= 6 and l.strip()[0] in "-0123456789."])
            sc = 1e3 if np.nanmax(np.abs(d[:, 0])) < 1.0 else 1.0
            im = ax.scatter(d[:, 0] * sc, d[:, 1] * sc, c=d[:, 5], s=2, cmap="RdBu_r", vmin=-0.5, vmax=0.5)
            ax.set_aspect("equal"); ax.set_title("%s: Bz 0.25 mm off board 1" % k, fontsize=7.5); ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=list(axs), shrink=0.8, label="Bz (T)")
        fig.savefig(os.path.join(a.out, "X4_Bz_board1_face.png"), dpi=220); plt.close(fig)
    # F5 radial |Bz| profile at the board-1 face and board mid-planes
    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    for k, f in planes:
        for pn, ls in (("PCB_face_plus0p25mm", "-"), ("PCB_B5_mid", ":")):
            p = os.path.join(a.results, f, "B_%s.fld" % pn)
            if not os.path.isfile(p):
                continue
            d = np.array([[float(v) for v in l.replace(",", " ").split()[:6]] for l in open(p)
                          if len(l.split()) >= 6 and l.strip()[0] in "-0123456789."])
            sc = 1e3 if np.nanmax(np.abs(d[:, 0])) < 1.0 else 1.0
            r = np.round(np.hypot(d[:, 0], d[:, 1]) * sc)
            ur = np.unique(r)
            ax.plot(ur, [np.nanmax(np.abs(d[r == x, 5])) for x in ur], ls, color=col[k],
                    label="%s, %s" % (k, "0.25 mm off board 1" if ls == "-" else "board 5 mid-plane"))
    ax.set_xlabel("Radius (mm)"); ax.set_ylabel("Peak |Bz| (T)"); ax.legend(fontsize=6)
    fig.tight_layout(); fig.savefig(os.path.join(a.out, "X5_Bz_radial.png"), dpi=220); plt.close(fig)
    # --------------------------------------------------------------------------------------- markdown summary
    L = ["# Rev0 as-built study - results", "", "| Case | K (mN·m/A) | vs A | T per A pk (mN·m) | E_LL 50 / 100 / 150 rpm (mV rms) | "
         "E_LL 1000 rpm (V rms) | THD ph / line (%) |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %.3f | %s | %.2f | %.1f / %.1f / %.1f | %.4f | %s / %s |" % (
            r["label"], r["K_mNm_per_A"], ("%+.1f %%" % r["dK_vs_A_pct"]) if r["dK_vs_A_pct"] != "" else "-",
            r["torque_per_Apk_mNm"], 1e3 * r["E_LL_rms_50rpm_V"], 1e3 * r["E_LL_rms_100rpm_V"], 1e3 * r["E_LL_rms_150rpm_V"],
            r["E_LL_rms_1000rpm_V"], ("%.1f" % r["THD_phase_pct"]) if r["THD_phase_pct"] == r["THD_phase_pct"] else "-",
            ("%.2f" % r["THD_line_pct"]) if r["THD_line_pct"] == r["THD_line_pct"] else "-"))
    if contrib:
        L += ["", "Contributions: gap 1 -> 4 mm %+.1f %%; manufactured rotor (80/25 plate, 8 mm shaft) %+.1f %%; total %+.1f %%"
              % (contrib["gap_effect_B_over_A_pct"], contrib["rotor_effect_C_over_B_pct"], contrib["total_C_over_A_pct"])]
    if band.get("E_LL_100rpm"):
        L += ["Case C at 100 rpm: %.1f mV rms (band %.1f-%.1f mV for gap 3.5-4.5 mm and Br 1.17-1.22 T); preliminary "
              "measurement %.0f mV (not used for calibration)" % tuple([1e3 * x for x in band["E_LL_100rpm"]] + [1e3 * MEASURED["E_LL_rms"]])]
    for c in checks:
        L.append("Detailed-copper check %s (%.3f mm): detailed %.4f, rotor %.4f, field map x ratio %.4f mN.m/A (%+.2f %%)"
                 % (c["check"], c["distance_mm"], c["detailed_copper"], c["detailed_rotor"], c["fieldmap_x_ratio"], c["diff_pct"]))
    if "A" in byk:
        L.append("Method check, Case A: field map x ratio %.3f vs full-motor detailed FEM 18.534 (%+.2f %%)"
                 % (byk["A"]["K_mNm_per_A"], byk["A"]["dK_vs_A_ref18534_pct"]))
    if warn:
        L += ["", "NOT AVAILABLE:"] + ["- " + x for x in warn]
    L += ["", "Back-EMF values are speed-scaled from the position-dependent field solution (e = K w_m), not separate "
          "transient solutions. Electrical frequency f = n/60 x 8."]
    open(os.path.join(a.out, "asbuilt_results.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
