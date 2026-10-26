#!/usr/bin/env python3
r"""
Process open-circuit back-EMF measurements for the as-built Rev0 PCB motor.

Input: a CSV with one row per reading:
    speed_cmd_rpm, f_e_Hz, V_AB_mV, V_BC_mV, V_CA_mV
  - f_e_Hz  : electrical frequency read from the scope (leave blank if not measured;
              the commanded speed is then used and flagged)
  - V_xx_mV : line-to-line RMS voltages in mV (leave blank if not measured)

Outputs (in the output folder):
  backemf_results.csv   per-reading speed, mean line voltage, unbalance, K, implied gap
  backemf_vs_model.pdf  measured points over the Case C prediction band
  backemf_table.tex     booktabs table ready for \input{} in the report

Model values come from Table F.1 of the report (Case C, as built).
Usage:
  python process_backemf.py measurements.csv --out results --v-unc 1.0 --f-unc 0.1
"""
import argparse
import csv
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

P = 8                      # pole pairs
K_C = 7.554e-3             # N m/A, Case C at 4.0 mm (field-map reference)
K_GAP = {3.5: 8.754e-3, 4.0: 7.554e-3, 4.5: 6.518e-3}   # Case C gap band
DECAY = math.log(K_GAP[3.5] / K_GAP[4.5]) / 1.0          # 1/mm, log-linear fit
BR_BAND = (1.17, 1.22)     # T, remanence band used for Fig 4.8
BR_NOM = 1.23              # T, library NdFe35 value used in the model


def e_ll_rms(K, rpm):
    """Open-circuit line-to-line RMS back-EMF (V) for per-phase coefficient K (N m/A)."""
    w = 2 * math.pi * rpm / 60
    return math.sqrt(1.5) * K * w


def k_from(e_ll_v, rpm):
    w = 2 * math.pi * rpm / 60
    return e_ll_v / (math.sqrt(1.5) * w)


def gap_from(K):
    """Effective magnet-to-board-1 gap (mm) implied by K, nominal remanence."""
    return 4.0 + math.log(K_C / K) / DECAY


def fnum(s):
    s = (s or "").strip()
    return float(s) if s else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="backemf_out")
    ap.add_argument("--v-unc", type=float, default=1.0,
                    help="voltage uncertainty, %% of reading (instrument spec)")
    ap.add_argument("--f-unc", type=float, default=0.1,
                    help="frequency uncertainty, %% of reading")
    ap.add_argument("--speed-unc", type=float, default=2.0,
                    help="speed uncertainty, %%, used only when f_e is blank")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows = []
    with open(a.csv, newline="") as fh:
        for r in csv.DictReader(fh):
            cmd = fnum(r.get("speed_cmd_rpm"))
            fe = fnum(r.get("f_e_Hz"))
            v = [fnum(r.get(k)) for k in ("V_AB_mV", "V_BC_mV", "V_CA_mV")]
            v = [x for x in v if x is not None]
            if cmd is None or not v:
                continue
            rpm = 60 * fe / P if fe else cmd
            s_unc = a.f_unc if fe else a.speed_unc
            vm = sum(v) / len(v)
            unbal = (max(v) - min(v)) / vm * 100 if len(v) > 1 else float("nan")
            K = k_from(vm / 1000, rpm)
            k_unc = math.hypot(a.v_unc, s_unc)          # % (1-sigma style, combined)
            pred = e_ll_rms(K_C, rpm) * 1000
            rows.append(dict(cmd=cmd, rpm=rpm, speed_src="scope f_e" if fe else "commanded",
                             n=len(v), v=vm, unbal=unbal, pred=pred,
                             dev=(vm - pred) / pred * 100,
                             K=K * 1000, K_unc=K * 1000 * k_unc / 100,
                             gap=gap_from(K),
                             gap_unc=(k_unc / 100) / DECAY))

    if not rows:
        raise SystemExit("No usable rows in the CSV.")

    with open(os.path.join(a.out, "backemf_results.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["speed_cmd_rpm", "speed_rpm", "speed_source", "lines_measured",
                    "V_LL_mean_mV", "unbalance_pct", "V_LL_model_mV", "deviation_pct",
                    "K_mNm_per_A", "K_unc_mNm_per_A", "implied_gap_mm", "gap_unc_mm"])
        for r in rows:
            w.writerow([r["cmd"], f"{r['rpm']:.2f}", r["speed_src"], r["n"], f"{r['v']:.2f}",
                        f"{r['unbal']:.2f}", f"{r['pred']:.2f}", f"{r['dev']:+.2f}",
                        f"{r['K']:.3f}", f"{r['K_unc']:.3f}", f"{r['gap']:.2f}",
                        f"{r['gap_unc']:.2f}"])

    # Weighted mean K across readings
    wts = [1 / r["K_unc"] ** 2 for r in rows]
    Kbar = sum(r["K"] * w for r, w in zip(rows, wts)) / sum(wts)
    Kbar_unc = 1 / math.sqrt(sum(wts))

    # Figure: prediction band + measurements
    nmax = max(200, 1.15 * max(r["rpm"] for r in rows))
    ns = [nmax * i / 100 for i in range(101)]
    lo = [e_ll_rms(K_GAP[4.5] * BR_BAND[0] / BR_NOM, n) * 1000 for n in ns]
    hi = [e_ll_rms(K_GAP[3.5] * BR_BAND[1] / BR_NOM, n) * 1000 for n in ns]
    mid = [e_ll_rms(K_C, n) * 1000 for n in ns]
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    ax.fill_between(ns, lo, hi, color="tab:green", alpha=0.18,
                    label="Model band: gap 3.5–4.5 mm, $B_r$ 1.17–1.22 T")
    ax.plot(ns, mid, color="tab:green", lw=1.6, label="Model, as built (4.0 mm)")
    for src, mk in (("scope f_e", "o"), ("commanded", "s")):
        pts = [r for r in rows if r["speed_src"] == src]
        if pts:
            ax.errorbar([r["rpm"] for r in pts], [r["v"] for r in pts],
                        yerr=[r["v"] * a.v_unc / 100 for r in pts], fmt=mk, color="k",
                        ms=5, capsize=3,
                        label="Measured (speed from " + ("scope frequency)" if src == "scope f_e" else "command)"))
    ax.set_xlabel("Shaft speed (rpm)")
    ax.set_ylabel("Line-to-line back-EMF (mV RMS)")
    ax.set_xlim(0, nmax)
    ax.set_ylim(0, None)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "backemf_vs_model.pdf"))
    fig.savefig(os.path.join(a.out, "backemf_vs_model.png"), dpi=200)

    # LaTeX table
    with open(os.path.join(a.out, "backemf_table.tex"), "w") as fh:
        fh.write("\\begin{table}[htbp]\n\\centering\n")
        fh.write("\\caption{Measured open-circuit line-to-line back-EMF of the as-built Rev0 "
                 "compared with the Case C prediction ($K = 7.554$\\,mN\\,m\\,A$^{-1}$ at 4.0\\,mm).}\n")
        fh.write("\\label{tab:backemf_meas}\n\\begin{tabular}{rrrrrr}\n\\toprule\n")
        fh.write("Speed (rpm) & $V_{LL}$ meas. (mV) & $V_{LL}$ model (mV) & Dev. (\\%) & "
                 "Unbal. (\\%) & $K$ (mN\\,m\\,A$^{-1}$) \\\\\n\\midrule\n")
        for r in rows:
            ub = "--" if math.isnan(r["unbal"]) else f"{r['unbal']:.1f}"
            fh.write(f"{r['rpm']:.1f} & {r['v']:.1f} & {r['pred']:.1f} & {r['dev']:+.1f} & "
                     f"{ub} & ${r['K']:.2f} \\pm {r['K_unc']:.2f}$ \\\\\n")
        fh.write("\\midrule\n")
        fh.write(f"\\multicolumn{{5}}{{l}}{{Weighted mean}} & ${Kbar:.2f} \\pm {Kbar_unc:.2f}$ \\\\\n")
        fh.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")

    print(f"{'rpm':>7} {'src':>10} {'V_LL mV':>8} {'model':>7} {'dev %':>6} {'unbal%':>6} "
          f"{'K mNm/A':>12} {'gap mm':>11}")
    for r in rows:
        print(f"{r['rpm']:7.1f} {r['speed_src']:>10} {r['v']:8.2f} {r['pred']:7.2f} "
              f"{r['dev']:+6.1f} {r['unbal']:6.1f} {r['K']:6.3f}±{r['K_unc']:.3f} "
              f"{r['gap']:5.2f}±{r['gap_unc']:.2f}")
    print(f"\nWeighted mean K = {Kbar:.3f} ± {Kbar_unc:.3f} mN·m/A "
          f"(model 7.554; implied gap {gap_from(Kbar / 1000):.2f} mm at nominal Br)")
    print(f"Outputs written to {os.path.abspath(a.out)}")


if __name__ == "__main__":
    main()
