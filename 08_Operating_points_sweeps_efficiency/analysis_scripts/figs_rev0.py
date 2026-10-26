import csv, glob, math, os, re, sys, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
D = sys.argv[1]; OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
C = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}; LS = {"A": "-", "B": "--", "C": "-."}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 2,
                     "figure.facecolor": "white", "savefig.dpi": 200, "savefig.bbox": "tight"})
SCALE = 18.534 / 19.475          # centre-line rotating model -> full-motor FEM torque constant
rows = list(csv.DictReader(open(os.path.join(D, "fmrot_waveforms.csv"))))
th = np.array([float(r["theta_mech_deg"]) for r in rows]) * 8.0     # electrical degrees
E = {p: np.array([float(r["e_PHASE_%s_V" % p]) for r in rows]) * SCALE for p in "ABC"}
T = np.array([float(r["T_load_Nm"]) for r in rows]) * 1e3 * SCALE
def fourier(x_deg, y, nmax=11, n_out=721):
    x = np.radians(x_deg); xx = np.linspace(0, 2 * np.pi, n_out)
    out = np.full_like(xx, y.mean())
    for n in range(1, nmax + 1):
        a = 2 * np.mean(y * np.cos(n * x)); b = 2 * np.mean(y * np.sin(n * x))
        out += a * np.cos(n * xx) + b * np.sin(n * xx)
    return np.degrees(xx), out
# 1 back-EMF
fig, axs = plt.subplots(1, 2, figsize=(10, 3.8))
for p in "ABC":
    xs, ys = fourier(th, E[p]); axs[0].plot(xs, ys, color=C[p], ls=LS[p], label="Phase " + p)
    axs[0].plot(th % 360, E[p], "o", ms=3.5, color=C[p])
axs[0].set(xlabel="Rotor position (electrical degrees)", ylabel="Phase back-EMF (V)", xlim=(0, 360),
           title="Phase back-EMF, 1000 rpm")
axs[0].set_xticks(range(0, 361, 60)); axs[0].legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, fontsize=8)
for (a, b), c in ((("A", "B"), "AB"), (("B", "C"), "BC"), (("C", "A"), "CA")):
    y = E[a] - E[b]; xs, ys = fourier(th, y)
    axs[1].plot(xs, ys, color=C[a], ls=LS[a], label="Line " + c)
axs[1].set(xlabel="Rotor position (electrical degrees)", ylabel="Line back-EMF (V)", xlim=(0, 360),
           title="Line-to-line back-EMF, 1000 rpm"); axs[1].set_xticks(range(0, 361, 60))
axs[1].legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, fontsize=8)
def harm(y):
    x = np.radians(th); h = []
    for n in range(1, 12):
        a = 2 * np.mean(y * np.cos(n * x)); b = 2 * np.mean(y * np.sin(n * x)); h.append(math.hypot(a, b))
    return h
hA = harm(E["A"]); hL = harm(E["A"] - E["B"])
info = {"E_ph_rms": hA[0] / math.sqrt(2), "E_ll_rms": hL[0] / math.sqrt(2),
        "THD_ph": 100 * math.sqrt(sum(v * v for v in hA[1:])) / hA[0], "THD_ll": 100 * math.sqrt(sum(v * v for v in hL[1:])) / hL[0],
        "H3_ph": 100 * hA[2] / hA[0], "H5_ph": 100 * hA[4] / hA[0], "H7_ph": 100 * hA[6] / hA[0]}
fig.text(0.01, -0.1, "Scaled to the full-motor torque constant (K = 18.53 mN·m/A). Points: Maxwell time steps; lines: "
         "Fourier fit to the 11th harmonic. Phase %.3f V rms, THD %.1f %%; line %.3f V rms, THD %.1f %%."
         % (info["E_ph_rms"], info["THD_ph"], info["E_ll_rms"], info["THD_ll"]), fontsize=8, color=INK2)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig1_backemf_rev0.png")); plt.close(fig)
# 2 torque: loaded + cogging
cg = list(csv.reader(open(os.path.join(D, "FMR_Torque.csv"))))[1:]
tc = np.array([float(r[0]) for r in cg]); qc = np.array([float(r[1]) for r in cg]) * 1e3
the = tc * 1e-3 * 1000 / 60 * 360 * 8
fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
xs, ys = fourier(th, T, 11)
axs[0].plot(xs, ys, color=C["A"]); axs[0].plot(th % 360, T, "o", ms=3.5, color=C["A"])
axs[0].axhline(T.mean(), color=INK2, lw=1, ls=":")
axs[0].set(xlabel="Rotor position (electrical degrees)", ylabel="Torque (mN·m)", xlim=(0, 360),
           ylim=(T.mean() * 0.97, T.mean() * 1.03), title="Torque at 1 A pk, sinusoidal currents")
axs[0].set_xticks(range(0, 361, 60))
axs[0].annotate("mean %.2f mN·m\nripple %.2f %% pk-pk" % (T.mean(), 100 * (T.max() - T.min()) / T.mean()),
                xy=(0.03, 0.08), xycoords="axes fraction", fontsize=8, color=INK)
m = tc > 0
axs[1].plot(the[m], qc[m], color=C["B"], marker="o", ms=3.5)
axs[1].axhline(0, color=INK2, lw=1)
axs[1].set(xlabel="Rotor position (electrical degrees)", ylabel="Torque (mN·m)", xlim=(0, 360),
           title="No-load rotor torque (cogging + solver noise)", ylim=(qc[m].min() - 0.25, 0.05)); axs[1].set_xticks(range(0, 361, 60))
cpp = qc[m].max() - qc[m].min()
axs[1].annotate("%.2f mN·m pk-pk = %.1f %% of the 1 A torque\nmean %.2f mN·m; not periodic -> at the noise level" % (cpp, 100 * cpp / T.mean(), qc[m].mean()), xy=(0.03, 0.04),
                xycoords="axes fraction", fontsize=8, color=INK)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig2_torque_cogging_rev0.png")); plt.close(fig)
info.update({"T_mean": T.mean(), "ripple_pct": 100 * (T.max() - T.min()) / T.mean(), "cogging_pkpk": cpp})
# 3 field maps
def fld(p):
    a = []
    for l in open(p):
        s = l.split()
        if len(s) < 6: continue
        try: v = [float(x) for x in s[:6]]
        except ValueError: continue
        if all(math.isfinite(x) for x in v): a.append(v)
    return np.array(a)
gaps = sorted(glob.glob(os.path.join(D, "B_S1_t*.fld"))); steels = sorted(glob.glob(os.path.join(D, "Bsteel_BackIron_t*.fld")))
g0 = fld(gaps[0]); s0 = fld(steels[0])
fig, axs = plt.subplots(1, 2, figsize=(10.5, 4.6))
vmax = np.abs(g0[:, 5]).max()
tc1 = axs[0].tricontourf(g0[:, 0], g0[:, 1], g0[:, 5], 40, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
fig.colorbar(tc1, ax=axs[0], label="Bz (T)", shrink=0.85)
axs[0].set(aspect="equal", title="Axial field Bz, 0.25 mm off the stator face", xlabel="x (mm)", ylabel="y (mm)")
bm = np.sqrt((s0[:, 3:6] ** 2).sum(1))
tc2 = axs[1].tricontourf(s0[:, 0], s0[:, 1], bm, 40, cmap="viridis")
fig.colorbar(tc2, ax=axs[1], label="|B| (T)", shrink=0.85)
axs[1].set(aspect="equal", title="|B| in the steel backplate (mid-thickness)", xlabel="x (mm)", ylabel="y (mm)")
for ax in axs: ax.grid(False)
fig.text(0.01, -0.02, "Rev0 rotating model at t = %s ms (1000 rpm). Gap |B| max %.3f T; steel |B| max %.3f T (no point above 1.6 T)."
         % ("%g" % float(re.search(r"_t([0-9.]+)ms", gaps[0]).group(1)), np.sqrt((g0[:, 3:6] ** 2).sum(1)).max(), bm.max()), fontsize=8, color=INK2)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig3_field_maps_rev0.png")); plt.close(fig)
frames = []
for f in gaps:
    a = fld(f); fig, ax = plt.subplots(figsize=(5, 4.6))
    t = ax.tricontourf(a[:, 0], a[:, 1], a[:, 5], 40, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    fig.colorbar(t, ax=ax, label="Bz (T)", shrink=0.85); ax.set_aspect("equal"); ax.grid(False)
    ax.set_title("Bz at the stator face, t = %g ms" % float(re.search(r"_t([0-9.]+)ms", f).group(1)))
    p = os.path.join(OUT, "_frame%02d.png" % len(frames)); fig.savefig(p, dpi=100); plt.close(fig); frames.append(p)
try:
    from PIL import Image
    ims = [Image.open(p) for p in frames]
    ims[0].save(os.path.join(OUT, "anim_Bz_stator_face_rev0.gif"), save_all=True, append_images=ims[1:], duration=300, loop=0)
except Exception as e:
    print("gif skipped", e)
for p in frames: os.remove(p)
# 4 current density, board 1, layer L1 (the six layers carry the same pattern: medians 9.2-9.4 A/mm2 per A)
r = list(csv.DictReader(open(os.path.join(D, "current_density_board1_per_A.csv"))))
fig, axs = plt.subplots(1, 3, figsize=(14, 4.8))
Jall = np.array([float(x["J_A_per_mm2"]) for x in r]); vmax = np.percentile(Jall, 99.5)
for ax, ph in zip(axs, ("PHASE_A", "PHASE_B", "PHASE_C")):
    sel = sorted([x for x in r if x["phase"] == ph and x["layer"] == "L1"], key=lambda x: float(x["J_A_per_mm2"]))
    seg = [((float(x["x0_mm"]), float(x["y0_mm"])), (float(x["x1_mm"]), float(x["y1_mm"]))) for x in sel]
    J = np.array([float(x["J_A_per_mm2"]) for x in sel])
    lc = LineCollection(seg, array=J, cmap="Blues", linewidths=1.2, norm=matplotlib.colors.Normalize(0, vmax))
    ax.add_collection(lc); ax.set(xlim=(-42, 42), ylim=(-42, 42), aspect="equal", xlabel="x (mm)",
                                  title="%s, board 1, layer L1" % ph.replace("_", " ").title())
    ax.grid(False)
axs[0].set_ylabel("y (mm)")
fig.colorbar(lc, ax=axs, label="J (A/mm²) per 1 A phase current", shrink=0.85)
fig.text(0.01, -0.02, "DC current share from the nodal solve over a 0.5 mm × 35 µm track, all six layers similar (median 9.2–9.4 A/mm² per A). "
         "Whole board: mean %.1f, 95th percentile %.1f, max %.1f A/mm² per A (local necks; colour scale clipped at the 99.5th percentile)."
         % (Jall.mean(), np.percentile(Jall, 95), Jall.max()), fontsize=8, color=INK2)
fig.savefig(os.path.join(OUT, "fig4_current_density_rev0.png")); plt.close(fig)
# 5 efficiency with the measured resistance
K = 18.534e-3
R = 2.059; Pedd1000 = 0.0204   # S1 measured 1.8 ohm/phase at 15-30 C (assumed), contact 0-0.1 ohm not T-corrected -> 2.00-2.12 ohm at 60 C
fig, ax = plt.subplots(figsize=(6.5, 4))
rowsE = []
cols = {500: C["A"], 1000: C["B"], 2000: C["C"]}; lss = {500: "-", 1000: "--", 2000: "-."}
I = np.linspace(0.05, 2.0, 200)
for n in (500, 1000, 2000):
    w = n * math.pi / 30; Te = 1.5 * K * I; Pout = Te * w; Pcu = 1.5 * I * I * R; Pe = Pedd1000 * (n / 1000) ** 2
    eta = 100 * Pout / (Pout + Pcu + Pe)
    ax.plot(Te * 1e3, eta, color=cols[n], ls=lss[n]); ax.annotate("%d rpm" % n, xy=(Te[-1] * 1e3, eta[-1]), xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK, va="center")
    for i0 in (0.5, 1.0, 1.5, 2.0):
        te = 1.5 * K * i0; po = te * w; pc = 1.5 * i0 * i0 * R
        rowsE.append([n, i0, round(te * 1e3, 2), round(po, 3), round(pc, 3), round(Pe, 4), round(100 * po / (po + pc + Pe), 1)])
ax.set(xlabel="Electromagnetic torque (mN·m)", ylabel="Efficiency, electromagnetic (%)", ylim=(0, 100), xlim=(0, 62),
       title="Rev0 electromagnetic efficiency, winding at 60 °C")
fig.text(0.01, -0.06, "R = %.2f Ω per phase at 60 °C (range 2.00–2.12 Ω), from the S1 measurement of 1.8 Ω at an unrecorded 15–30 °C, with 0–0.1 Ω contact not temperature-corrected.\nCopper and track-eddy loss only — bearing and windage loss not included." % R, fontsize=8, color=INK2)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig5_efficiency_rev0.png")); plt.close(fig)
with open(os.path.join(OUT, "efficiency_rev0_measuredR.csv"), "w", newline="") as f:
    w_ = csv.writer(f); w_.writerow(["rpm", "Ipk_A", "Tem_mNm", "Pout_W", "Pcu_W", "Peddy_W", "eta_pct"]); w_.writerows(rowsE)
info["R_used"] = R
json.dump(info, open(os.path.join(OUT, "fig_numbers.json"), "w"), indent=1)
print(json.dumps(info, indent=1)); print(rowsE)
