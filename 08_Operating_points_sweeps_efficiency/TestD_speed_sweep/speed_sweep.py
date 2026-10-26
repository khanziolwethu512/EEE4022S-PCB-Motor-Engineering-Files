"""Test D: speed sweep (Rev0 vs Rev1-S), post-processing of the solved rotating models only.

No model change: the field-only rotating solutions (FMROT_REV0 job 1500352/1500707, FMROT_REV1S job 1502103)
are re-evaluated at other speeds. In a coreless machine with a field-only solution:
  - back-EMF waveform shape is speed independent, amplitude proportional to speed (e = w k(theta));
  - track eddy loss (thin-strip, every harmonic) scales with speed squared;
  - copper loss depends on current only (R_ac = R_dc while the skin depth >> 35 um, checked below).
Inputs: K on the full-FEM / board-by-board basis, measured R (1.89 ohm per stator), eddy loss at 1000 rpm.
"""
import json, math, csv, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCR = "/tmp/claude-0/-home-claude/1e7e0c0d-be12-5dae-890e-b89380ee8594/scratchpad"
OUT = os.path.join(SCR, "testsD", "out"); os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.3, "font.family": "DejaVu Sans"})
C0, C1, GREY, INK2 = "#2a78d6", "#eb6834", "#8a8a85", "#555550"

ALPHA, PP, M = 0.00393, 8, 0.95
L1 = 25e-6
def R_stator(T): return 1.89 * (1 + ALPHA * (T - 22.5))     # measured 1.87-1.90 ohm at ~15-30 C
MACH = {
    "Rev0":   dict(dir="fm0/RESULTS_FMROT_REV0",  K=18.534e-3, Kfm=19.475e-3, ns=1, Pe=0.0204, color=C0, ls="-"),
    "Rev1-S": dict(dir="fm1s/RESULTS_FMROT_REV1S", K=39.50e-3, Kfm=41.564e-3, ns=2, Pe=0.0442, color=C1, ls="--"),
}
ITP = 0.84   # candidate thermal test point, A pk per stator
# Stack-to-air thermal resistance per stator from the Icepak runs at 1 A pk (rotor still, fans on, 30 C air):
#   Rev0: 2.32 W, hottest board 50.3 C -> 20.3 K / 2.32 W = 8.75 K/W
#   Rev1-S: 4.84 W (2.42 W per stator), hottest board 65.7 C (S1) -> 35.7 K / 2.42 W = 14.8 K/W per stator
# Pessimistic values keep the same ratio as the 15 K/W used for Rev0's test point: x 15/8.75.
MACH["Rev0"]["Rth"] = 20.3 / 2.32
MACH["Rev1-S"]["Rth"] = 35.7 / 2.42
for _m in MACH.values(): _m["Rth_pess"] = _m["Rth"] * 15.0 / 8.75
for name, m in MACH.items():
    w = list(csv.DictReader(open(os.path.join(SCR, m["dir"], "fmrot_waveforms.csv"))))
    sc = m["K"] / m["Kfm"]
    eA = np.array([float(r["e_PHASE_A_V"]) for r in w]) * sc     # V at 1000 rpm
    eB = np.array([float(r["e_PHASE_B_V"]) for r in w]) * sc
    m["E_ph_rms"] = float(np.sqrt(np.mean(eA ** 2)))
    m["E_ll_rms"] = float(np.sqrt(np.mean((eA - eB) ** 2)))
    m["E_ll_pk"] = float(np.max(np.abs(eA - eB)))
    m["E_ph_pk1"] = m["K"] * 1000 * math.pi / 30                  # fundamental peak, V at 1000 rpm
    m["R60"] = R_stator(60) * m["ns"]; m["R25"] = R_stator(25) * m["ns"]; m["L"] = L1 * m["ns"]
    print(name, "check: E_ph_rms %.3f V, E_ll_rms %.3f V at 1000 rpm (report 1.372/2.377 and 2.925/5.066)" % (m["E_ph_rms"], m["E_ll_rms"]))

def w_of(n): return n * math.pi / 30
def eddy(m, n): return m["Pe"] * (n / 1000.0) ** 2
def v_req_pk(m, n, I, R):   # phase peak voltage, current on q-axis
    E = m["K"] * w_of(n); X = 2 * math.pi * n * PP / 60 * m["L"]
    return math.hypot(E + I * R, X * I)
def vmax_pk(Vdc): return M * Vdc / math.sqrt(3)               # SVPWM linear range, phase peak
def i_volt(m, n, Vdc, R):   # largest q-axis current the bus can drive at speed n
    lo, hi = 0.0, 20.0
    if v_req_pk(m, n, 0, R) >= vmax_pk(Vdc): return 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if v_req_pk(m, n, mid, R) <= vmax_pk(Vdc): lo = mid
        else: hi = mid
    return lo
def i_therm(m, n, Rth, Tlim=60.0, Tamb=25.0):
    # per stator: 1.5 I^2 R_stator(Tlim) + P_eddy_per_stator = (Tlim - Tamb)/Rth
    pe = eddy(m, n) / m["ns"]
    head = (Tlim - Tamb) / Rth - pe
    return math.sqrt(max(head, 0) / (1.5 * R_stator(Tlim)))

speeds = np.arange(0, 4001, 25)
# ---------- D1: back-EMF vs speed with supply limits ----------
fig, ax = plt.subplots(figsize=(7.2, 4.0))
for name, m in MACH.items():
    ax.plot(speeds, m["E_ll_rms"] * speeds / 1000, color=m["color"], ls=m["ls"], lw=2, label=name + (" (series)" if m["ns"] == 2 else ""))
for V in (12, 24):
    lim = M * V / math.sqrt(2)      # SVPWM: line peak = m Vdc -> line rms = m Vdc / sqrt2
    ax.axhline(lim, color=GREY, lw=1, ls=":")
    ax.text(4000, lim + 0.3, "%d V bus limit (SVPWM, m = 0.95): %.1f V rms" % (V, lim), ha="right", fontsize=8, color=INK2)
for name, m in MACH.items():
    for V in (12, 24):
        n0 = M * V / math.sqrt(2) / m["E_ll_rms"] * 1000
        if n0 < 4000: ax.plot([n0], [M * V / math.sqrt(2)], "o", color=m["color"], ms=5)
ax.set_xlabel("Speed (rpm)"); ax.set_ylabel("Line back-EMF (V rms)"); ax.set_xlim(0, 4000); ax.set_ylim(0, 22)
ax.legend(loc="upper left", fontsize=9, frameon=False)
fig.text(0.01, -0.04, "Open-circuit line back-EMF from the rotating models, scaled to K (Rev0 18.53, Rev1-S 39.50 mN·m/A). Dots: no-load speed at which the "
         "back-EMF alone reaches the bus limit.", fontsize=7.5, color=INK2, wrap=True)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "D1_backemf_vs_speed.png"), dpi=200, bbox_inches="tight"); plt.close(fig)

# ---------- D2: losses vs speed at the test point ----------
fig, axs = plt.subplots(1, 2, figsize=(10, 3.9))
for name, m in MACH.items():
    pcu = 1.5 * (ITP ** 2) * R_stator(60) * m["ns"]
    pe = np.array([eddy(m, n) for n in speeds])
    axs[0].plot(speeds, pe * 1e3, color=m["color"], ls=m["ls"], lw=2, label=name + " track eddy")
    axs[0].axhline(pcu * 1e3, color=m["color"], ls=m["ls"], lw=1, alpha=0.6)
    axs[0].text(60, pcu * 1e3 * 1.08, "%s copper loss at 0.84 A pk, 60 °C: %.2f W" % (name, pcu), fontsize=7.5, color=INK2)
    td = np.where(speeds > 0, pe / np.maximum(speeds * math.pi / 30, 1e-9), 0) * 1e3
    axs[1].plot(speeds, td, color=m["color"], ls=m["ls"], lw=2, label=name)
axs[0].set_yscale("log"); axs[0].set_ylim(1, 8000)
axs[0].set_xlabel("Speed (rpm)"); axs[0].set_ylabel("Loss (mW, log scale)"); axs[0].set_title("Copper and track-eddy loss", fontsize=10)
axs[0].legend(loc="lower right", fontsize=8, frameon=False)
axs[1].set_xlabel("Speed (rpm)"); axs[1].set_ylabel("Eddy drag torque (mN·m)"); axs[1].set_title("Braking torque from track eddy currents", fontsize=10)
axs[1].legend(loc="upper left", fontsize=8, frameon=False)
fig.text(0.01, -0.05, "Eddy loss from the rotating model at 1000 rpm (Rev0 20.4 mW, Rev1-S 44.2 mW), scaled with speed squared; drag torque = P_eddy/ω, "
         "so it grows linearly with speed. Copper loss: measured 1.89 Ω per stator corrected to 60 °C.", fontsize=7.5, color=INK2, wrap=True)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "D2_losses_vs_speed.png"), dpi=200, bbox_inches="tight"); plt.close(fig)

# ---------- D3: torque-speed envelopes ----------
cases = [("Rev0", 12), ("Rev0", 24), ("Rev1-S", 12), ("Rev1-S", 24)]
fig, axs = plt.subplots(1, 2, figsize=(10.5, 4.0), sharey=True)
env = {}
for k, V in enumerate((12, 24)):
    ax = axs[k]
    for name, m in MACH.items():
        R = m["R60"]
        T_th = []; T_v = []; T = []; Tsh = []
        for n in speeds:
            it = ITP
            iv = i_volt(m, n, V, R)
            i = min(it, iv)
            tem = 1.5 * m["K"] * i * 1e3
            td = (eddy(m, n) / w_of(n) * 1e3) if n > 0 else 0
            T.append(tem); Tsh.append(max(tem - td, 0))
        T = np.array(T); Tsh = np.array(Tsh)
        env[(name, V)] = (T, Tsh)
        ax.plot(speeds, T, color=m["color"], ls=m["ls"], lw=2, label=name + (" series" if m["ns"] == 2 else ""))
        ax.fill_between(speeds, 0, T, color=m["color"], alpha=0.07, lw=0)
        nmax = speeds[np.nonzero(T > 0)[0][-1]] if np.any(T > 0) else 0
        lab = ("> 4000 rpm" if nmax >= 4000 else "%d rpm" % nmax)
        ax.annotate(lab, (min(nmax, 3990), 0), textcoords="offset points", xytext=(-4, 6), ha="right", fontsize=7.5, color=INK2)
    ax.set_title("%d V bus (SVPWM, m = 0.95), winding at 60 °C" % V, fontsize=10)
    ax.set_xlabel("Speed (rpm)"); ax.set_xlim(0, 4000)
axs[0].set_ylabel("Electromagnetic torque (mN·m)")
axs[0].legend(loc="upper right", fontsize=8, frameon=False)
fig.text(0.01, -0.06, "Envelope at the 0.84 A pk per-stator test current (drive current limit) until the bus voltage runs out (q-axis current, "
         "L = 25 µH per stator). Thermal limits are in Fig. D5. Prescribed-speed electromagnetic torque; mechanical loss not included.",
         fontsize=7.5, color=INK2, wrap=True)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "D3_torque_speed_envelopes.png"), dpi=200, bbox_inches="tight"); plt.close(fig)

# ---------- D4: efficiency maps ----------
fig, axs = plt.subplots(1, 2, figsize=(10.5, 4.2))
levels = [30, 40, 50, 60, 70, 80, 85, 90]
for k, (name, m) in enumerate(MACH.items()):
    ax = axs[k]; V = 24
    n = np.linspace(50, 4000, 160); Tmax = 1.5 * m["K"] * 1.0 * 1e3
    Tg = np.linspace(0.5, Tmax, 140)
    NN, TT = np.meshgrid(n, Tg)
    I = TT / 1e3 / (1.5 * m["K"])
    Pout = TT / 1e3 * NN * math.pi / 30
    Pcu = 1.5 * I ** 2 * m["R60"]
    Pe = m["Pe"] * (NN / 1000) ** 2
    eta = 100 * Pout / (Pout + Pcu + Pe)
    T24i = np.interp(NN, speeds, env[(name, 24)][0])
    eta = np.where(TT <= T24i + 1e-9, eta, np.nan)      # outside the 24 V envelope: not reachable
    cs = ax.contourf(NN, TT, eta, levels=[0] + levels + [100], cmap="Blues", alpha=0.85)
    cl = ax.contour(NN, TT, eta, levels=levels, colors="#1f3864", linewidths=0.6)
    ax.clabel(cl, fmt="%d %%", fontsize=7)
    T24, _ = env[(name, 24)]; T12, _ = env[(name, 12)]
    ax.plot(speeds, T24, color="k", lw=1.6, label="24 V envelope"); ax.plot(speeds, T12, color="k", lw=1.2, ls=":", label="12 V envelope")
    ax.plot([1000], [1.5 * m["K"] * ITP * 1e3], "o", color=m["color"], ms=7, mec="white", label="Test point (1000 rpm, 0.84 A pk)")
    ax.set_xlim(0, 4000); ax.set_ylim(0, Tmax)
    ax.set_title(name + (" (stators in series)" if m["ns"] == 2 else ""), fontsize=10)
    ax.set_xlabel("Speed (rpm)"); ax.set_ylabel("Electromagnetic torque (mN·m)")
    ax.legend(loc="upper right", fontsize=7, frameon=True, framealpha=0.9)
    ax.text(3950, Tmax*0.62, "unreachable\n(above envelope)", ha="right", fontsize=7.5, color=INK2) if name=="Rev1-S" else None
fig.text(0.01, -0.05, "Electromagnetic efficiency = Tω / (Tω + copper loss + track eddy loss), winding at 60 °C, measured resistance. Shading only inside the 24 V envelope; "
         "torque axis up to 1 A pk per stator. Bearing, windage and inverter losses not included.", fontsize=7.5, color=INK2, wrap=True)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "D4_efficiency_maps.png"), dpi=200, bbox_inches="tight"); plt.close(fig)

# ---------- D5: thermal current limit vs speed ----------
fig, ax = plt.subplots(figsize=(7.2, 3.9))
for name, m in MACH.items():
    for key, lw, al, tag in (("Rth", 2.0, 1.0, "Icepak"), ("Rth_pess", 1.3, 0.75, "pessimistic")):
        ax.plot(speeds, [i_therm(m, n, m[key]) for n in speeds], color=m["color"], ls=m["ls"], lw=lw, alpha=al,
                label="%s, %s %.3g K/W per stator" % (name, tag, m[key]))
ax.axhline(ITP, color=GREY, lw=1, ls=":"); ax.text(3990, ITP + 0.012, "0.84 A pk test point", ha="right", fontsize=7.5, color=INK2)
ax.set_xlabel("Speed (rpm)"); ax.set_ylabel("Current per stator for 60 °C (A pk)"); ax.set_xlim(0, 4000); ax.set_ylim(0.5, 1.2)
ax.legend(fontsize=7.5, frameon=False, ncol=2, loc="lower left")
fig.text(0.01, -0.06, "Steady-state current that keeps the hottest board at 60 °C (25 °C air), copper loss at 60 °C plus track eddy loss. Thermal "
         "resistance per stator from the Icepak models at 1 A pk: Rev0 8.75 K/W; Rev1-S 14.8 K/W, because its two stacked stators share "
         "the cooling. Pessimistic = × 15/8.75. Rotor still (no stirring).", fontsize=7.5, color=INK2, wrap=True)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "D5_thermal_current_vs_speed.png"), dpi=200, bbox_inches="tight"); plt.close(fig)

# ---------- Table and skin-depth check ----------
rho = 1.72e-8; mu0 = 4e-7 * math.pi
rows = []
for n in (250, 500, 1000, 2000, 3000, 4000):
    fe = n * PP / 60
    d1 = math.sqrt(2 * rho / (2 * math.pi * fe * mu0)); d11 = math.sqrt(2 * rho / (2 * math.pi * 11 * fe * mu0))
    for name, m in MACH.items():
        R = m["R60"]
        Pcu = 1.5 * ITP ** 2 * R
        Pe = eddy(m, n); Tem = 1.5 * m["K"] * ITP * 1e3; Td = Pe / w_of(n) * 1e3
        Pout = Tem / 1e3 * w_of(n)
        rows.append(dict(rpm=n, f_e_Hz=round(fe, 1), machine=name, E_ll_rms_V=round(m["E_ll_rms"] * n / 1000, 3),
                         eddy_mW=round(Pe * 1e3, 1), eddy_drag_mNm=round(Td, 3), Pcu_W_60C=round(Pcu, 3),
                         eddy_pct_of_Pcu=round(100 * Pe / Pcu, 2), eta_EM_pct_at_0p84A=round(100 * Pout / (Pout + Pcu + Pe), 1),
                         Vdc_needed_SVPWM_V=round(math.sqrt(3) * v_req_pk(m, n, ITP, R) / M, 2),
                         I_therm_Icepak_A=round(i_therm(m, n, m['Rth']), 3), I_therm_pess_A=round(i_therm(m, n, m['Rth_pess']), 3),
                         skin_depth_fund_mm=round(d1 * 1e3, 2), skin_depth_H11_mm=round(d11 * 1e3, 2)))
with open(os.path.join(OUT, "D_speed_sweep_table.csv"), "w", newline="") as f:
    wtr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wtr.writeheader(); wtr.writerows(rows)
for r in rows: print(r)
for name, m in MACH.items():
    for V in (12, 24):
        print(name, V, "V: no-load speed limit %.0f rpm" % (M * V / math.sqrt(3) / (m["K"] * math.pi / 30)))
json.dump({k: {kk: vv for kk, vv in v.items() if kk not in ("color", "ls")} for k, v in MACH.items()},
          open(os.path.join(OUT, "D_inputs.json"), "w"), indent=1)
