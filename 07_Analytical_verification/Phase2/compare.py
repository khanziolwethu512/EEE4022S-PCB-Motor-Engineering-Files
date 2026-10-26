"""Run the analytical model (primary + sensitivity cases) and compare with the archived FEM results.
FEM numbers are read ONLY here, for comparison; they never enter analytical_em.py.

python compare.py <fem_results_dir>     (folder with FIELDMAP_REV0_P20_results / FIELDMAP_REV1S_P20_results)
"""
import csv, json, math, os, sys, time
import numpy as np
import analytical_em as A

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
# detailed FEM (archived, Board_by_board_K_mNm_per_A.csv + final results): phase A, mN.m/A
DET = {"S1": [6.2816, 4.5905, 3.3655, 2.4755, 1.8266],                 # Rev0 S1 detailed single-board (= Rev1-S S1)
       "S2": [6.5593, 4.9382, 3.8115, 3.0572, 2.5965]}                 # Rev1-S S2, board 1 = next to R2's magnets
DET_PSI = -30.18                                                        # detailed single-board baseline, deg elec
FULL_MOTOR_REV0 = 18.534                                                # Rev0 full-motor detailed FEM (HPC)
FMROT = {"Rev0": {"E_line": 2.38, "THD_ph": 5.5, "H3": 5.5}, "Rev1S": {"E_line": 5.07}}


def fem_fieldmap(d, design):
    p = os.path.join(d, "FIELDMAP_%s_P20_results" % design.upper(), "fieldmap_results.json")
    with open(p) as f:
        return json.load(f)


def pct(a, b):
    return 100.0 * (a / b - 1.0)


def run_case(label, design, T, **kw):
    t0 = time.time()
    r = A.solve(design, T, log=lambda s: None, **kw)
    print("  case %-28s %-5s K %.3f mN.m/A  (%.0f s)" % (label, design, r["machine"]["PHASE_A"]["K1_mNm_per_A"],
                                                            time.time() - t0))
    return r


def main(femdir):
    os.makedirs(OUT, exist_ok=True)
    T = A.load_traces()
    fm = {d: fem_fieldmap(femdir, d) for d in ("Rev0", "Rev1S")}
    cases = [("primary", {}), ("width-averaged conductors", {"width_avg": True}),
             ("no recoil correction (mu_r = 1)", {"recoil": False}), ("no steel (air only)", {"steel": False}),
             ("32 rotor angles", {"n_ang": 32})]
    res = {}
    for label, kw in cases:
        for d in ("Rev0", "Rev1S"):
            if label == "32 rotor angles" and d == "Rev1S":
                continue
            res[(label, d)] = run_case(label, d, T, **kw)
    for n in (2, 6):
        res[("images n = %d" % n, "Rev1S")] = run_case("images n = %d" % n, "Rev1S", T, n_img=n)
    json.dump({"%s|%s" % k: v for k, v in res.items()}, open(os.path.join(OUT, "analytical_all_cases.json"), "w"), indent=1)

    rows, lines = [], []
    P = {d: res[("primary", d)] for d in ("Rev0", "Rev1S")}
    # ---- 1. board by board (phase A)
    lines += ["## 1. Board by board, phase A (mN·m/A)", "",
              "| Stator, board | Distance from its magnets (mm) | Analytical | FEM field map | FEM detailed | Analytical vs field map | Analytical vs detailed | Field map vs detailed |",
              "|---|---|---|---|---|---|---|---|"]
    for st, design in (("S1", "Rev0"), ("S2", "Rev1S")):
        for kb in range(5):
            an = P[design]["boards"]["%s_B%d_PHASE_A" % (st, kb + 1)]["K1_mNm_per_A"]
            f = 1e3 * fm[design]["boards"]["%s_B%d_PHASE_A" % (st, kb + 1)]["K1"]
            de = DET[st][kb]
            dist = A.GAP + kb * A.PITCH
            lines.append("| %s B%d%s | %.3f | %.4f | %.4f | %.4f | %+.2f %% | %+.2f %% | %+.2f %% |" % (
                "Rev0/Rev1-S S1" if st == "S1" else "Rev1-S S2", kb + 1,
                " (next to R1 steel)" if (st == "S2" and kb == 4) else "", dist, an, f, de, pct(an, f), pct(an, de),
                pct(f, de)))
            rows.append({"item": "%s board %d phase A" % (st, kb + 1), "analytical": an, "fieldmap": f, "detailed": de})
    # ---- 2. stators and machines, all phases
    lines += ["", "## 2. Stators and machines (mN·m/A; T = 1.5·K·Î)", "",
              "| Quantity | Analytical | FEM field map | FEM detailed / full motor | Analytical vs field map | Analytical vs detailed |",
              "|---|---|---|---|---|---|"]
    for design, st_list in (("Rev0", ["S1"]), ("Rev1S", ["S1", "S2"])):
        for st in st_list:
            for ph in ("PHASE_A", "PHASE_B", "PHASE_C"):
                an = P[design]["stators"][st][ph]["K1_mNm_per_A"]
                f = 1e3 * fm[design]["stators"]["%s_%s" % (st, ph)]["K1"]
                de = sum(DET[st]) if ph == "PHASE_A" else None
                lines.append("| %s %s phase %s | %.3f | %.3f | %s | %+.2f %% | %s |" % (
                    "Rev0" if design == "Rev0" else "Rev1-S", st, ph[-1], an, f, "%.3f" % de if de else "—",
                    pct(an, f), "%+.2f %%" % pct(an, de) if de else "—"))
        for ph in ("PHASE_A", "PHASE_B", "PHASE_C"):
            an = P[design]["machine"][ph]["K1_mNm_per_A"]
            f = 1e3 * fm[design]["machine"][ph]["K1"]
            de = FULL_MOTOR_REV0 if design == "Rev0" else sum(DET["S1"]) + sum(DET["S2"])
            lines.append("| **%s machine, phase %s** | **%.3f** | %.3f | %.3f%s | %+.2f %% | **%+.2f %%** |" % (
                "Rev0" if design == "Rev0" else "Rev1-S", ph[-1], an, f, de,
                " (full motor)" if design == "Rev0" else " (board sum, phase A)", pct(an, f), pct(an, de)))
    # ---- 3. phase angle, harmonics, back-EMF
    lines += ["", "## 3. Phase angle, harmonics and back-EMF at 1000 rpm", "",
              "| Quantity | Analytical | FEM | Difference |", "|---|---|---|---|"]
    for design in ("Rev0", "Rev1S"):
        m = P[design]["machine"]["PHASE_A"]
        nm = "Rev0" if design == "Rev0" else "Rev1-S"
        lines.append("| %s ψ phase A (deg elec) | %.2f | %.2f (field map), %.2f (detailed board 1) | %+.2f deg |" % (
            nm, m["psi_deg"], fm[design]["machine"]["PHASE_A"]["psi"], DET_PSI, m["psi_deg"] - fm[design]["machine"]["PHASE_A"]["psi"]))
        lines.append("| %s phase back-EMF (V rms) | %.3f | %.3f (scaled from detailed K) | %+.2f %% |" % (
            nm, m["E_ph_rms_1000rpm_V"], (FULL_MOTOR_REV0 if design == "Rev0" else 39.50) * 1e-3 * 104.72 / math.sqrt(2),
            pct(m["E_ph_rms_1000rpm_V"], (FULL_MOTOR_REV0 if design == "Rev0" else 39.50) * 1e-3 * 104.72 / math.sqrt(2))))
        lines.append("| %s line back-EMF (V rms) | %.3f | %.2f (rotating FEM, scaled to detailed K) | %+.2f %% |" % (
            nm, m["E_line_rms_1000rpm_V"], FMROT[design]["E_line"], pct(m["E_line_rms_1000rpm_V"], FMROT[design]["E_line"])))
        lines.append("| %s 3rd / 5th / 7th harmonic of phase EMF (%%) | %.2f / %.2f / %.2f | %s | |" % (
            nm, m["H3_pct"], m["H5_pct"], m["H7_pct"], "5.5 / 0.7 / 0.1 (rotating FEM)" if design == "Rev0" else "—"))
    # ---- 4. sensitivity
    lines += ["", "## 4. Sensitivity of the analytical machine K (phase A)", "",
              "| Case | Rev0 K | change | Rev1-S K | change |", "|---|---|---|---|---|"]
    base = {d: P[d]["machine"]["PHASE_A"]["K1_mNm_per_A"] for d in P}
    labels = [c[0] for c in cases] + ["images n = 2", "images n = 6"]
    for lab in labels:
        cells = []
        for d in ("Rev0", "Rev1S"):
            r = res.get((lab, d))
            if r is None:
                cells += ["—", "—"]
            else:
                k = r["machine"]["PHASE_A"]["K1_mNm_per_A"]
                cells += ["%.3f" % k, "%+.2f %%" % pct(k, base[d])]
        lines.append("| %s | %s |" % (lab, " | ".join(cells)))
    for br in (1.17, 1.21):
        lines.append("| Br = %.2f T (N35 range; K ∝ Br) | %.3f | %+.2f %% | %.3f | %+.2f %% |" % (
            br, base["Rev0"] * br / A.BR, pct(br, A.BR), base["Rev1S"] * br / A.BR, pct(br, A.BR)))
    st = P["Rev0"]["stators"]["S1"]
    st2 = P["Rev1S"]["stators"]["S2"]
    lines += ["", "Recoil correction: N_z = %.3f (R1 on its plate), %.3f (R2 between two plates); M_eff/M = %.4f, %.4f."
              % (st["demag_Nz"], st2["demag_Nz"], st["M_eff_over_M"], st2["M_eff_over_M"])]
    md = "\n".join(lines) + "\n"
    open(os.path.join(OUT, "comparison_tables.md"), "w").write(md)
    print(md)
    with open(os.path.join(OUT, "boards_phaseA.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    figures(P, fm)


def figures(P, fm):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, (st, design, title) in zip(axs, (("S1", "Rev0", "Rev0 stator (and Rev1-S S1)"),
                                             ("S2", "Rev1-S".replace("-", ""), "Rev1-S S2 (R1 steel below, R2 magnets above)"))):
        x = np.arange(1, 6)
        an = [P[design]["boards"]["%s_B%d_PHASE_A" % (st, i)]["K1_mNm_per_A"] for i in x]
        f = [1e3 * fm[design]["boards"]["%s_B%d_PHASE_A" % (st, i)]["K1"] for i in x]
        ax.bar(x - 0.27, an, 0.27, label="Analytical (this work)")
        ax.bar(x, f, 0.27, label="FEM field map")
        ax.bar(x + 0.27, DET[st], 0.27, label="FEM detailed copper")
        ax.set_xticks(x)
        ax.set_xticklabels(["B%d" % i for i in x])
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("Board (B1 nearest its rotor's magnets)")
        ax.grid(axis="y", alpha=0.3)
    axs[0].set_ylabel("Torque constant per board, phase A (mN·m/A)")
    axs[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "A1_board_K_analytical_vs_FEM.png"), dpi=200)
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    for design, c in (("Rev0", "C0"), ("Rev1S", "C1")):
        th = P[design]["thetas"]
        k = 1e3 * np.array(P[design]["machine"]["PHASE_A"].get("k", [])) if "k" in P[design]["machine"]["PHASE_A"] else None
        tot = np.sum([P[design]["stators"][s]["PHASE_A"]["k"] for s in P[design]["stators"]], axis=0) * 1e3
        thf = np.linspace(0, 45, 181)
        K1, psi, _ = A.fourier(th, tot / 1e3)
        ax.plot(np.array(th) * 8, tot, "o", color=c, ms=4, label="%s analytical" % design.replace("Rev1S", "Rev1-S"))
        fth = fm[design]["thetas"]
        fk = 1e3 * np.array(fm[design]["machine"]["PHASE_A"].get("k", [])) if "k" in fm[design]["machine"]["PHASE_A"] else None
        if fk is None:
            fk = np.sum([np.array(fm[design]["stators"][s]["k"]) for s in fm[design]["stators"] if s.endswith("PHASE_A")], axis=0) * 1e3
        ax.plot(np.array(fth) * 8, fk, "x", color=c, ms=7, label="%s FEM field map" % design.replace("Rev1S", "Rev1-S"))
    ax.set_xlabel("Rotor position (deg electrical)")
    ax.set_ylabel("k = dλ/dθ, phase A (mN·m/A)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "A2_k_theta_analytical_vs_fieldmap.png"), dpi=200)


if __name__ == "__main__":
    main(sys.argv[1])
