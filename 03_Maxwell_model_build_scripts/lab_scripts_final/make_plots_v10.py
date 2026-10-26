"""Report figures from a finished FMROT run (your own PC, needs numpy + matplotlib):
    python make_plots_v10.py "<...>\\Motor run\\results\\FMROT_REV0_results"
Writes PNGs into that folder: back-EMF waveforms, loaded torque, Bz map at the stator face (8 instants -> also a GIF if
Pillow is installed), rotor-steel |B| map, current density map of board 1."""
import csv, glob, math, os, re, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

d = sys.argv[1] if len(sys.argv) > 1 else "."


def fld(path):
    rows = []
    for line in open(path):
        p = line.replace(",", " ").split()
        if len(p) >= 6:
            try:
                rows.append([float(v) for v in p[:6]])
            except ValueError:
                pass
    a = np.array(rows)
    if a.size:
        a = a[np.isfinite(a).all(axis=1)]              # field export writes NaN outside the solved objects
    if a.size and np.abs(a[:, :3]).max() < 1.0:      # coordinates exported in metres
        a[:, :3] *= 1e3
    return a


# back-EMF and torque
wf = os.path.join(d, "fmrot_waveforms.csv")
if os.path.isfile(wf):
    r = list(csv.DictReader(open(wf)))
    th = np.array([float(x["theta_mech_deg"]) for x in r]) * 8          # electrical degrees
    fig, ax = plt.subplots(figsize=(7, 4))
    for ph, c in (("A", "C3"), ("B", "C2"), ("C", "C0")):
        ax.plot(th, [float(x["e_PHASE_%s_V" % ph]) for x in r], c, label="phase %s" % ph)
    ax.set_xlabel("rotor position (electrical degrees)"); ax.set_ylabel("back-EMF (V) at the simulated speed")
    ax.grid(alpha=0.3); ax.legend(); fig.tight_layout(); fig.savefig(os.path.join(d, "fig_backemf.png"), dpi=150)
    if "T_load_Nm" in r[0]:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        ax.plot(th, [1e3 * float(x["T_load_Nm"]) for x in r], "k")
        ax.set_xlabel("rotor position (electrical degrees)"); ax.set_ylabel("torque (mN.m)"); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(os.path.join(d, "fig_torque_load.png"), dpi=150)

# Bz maps at the stator face
frames = []
for name in sorted(set(re.sub(r"_t[0-9.]+ms\.fld$", "", os.path.basename(f)) for f in glob.glob(os.path.join(d, "B_*_t*ms.fld")))):
    files = sorted(glob.glob(os.path.join(d, name + "_t*ms.fld")))
    vmax = max(np.abs(fld(f)[:, 5]).max() for f in files)
    for i, f in enumerate(files):
        a = fld(f)
        fig, ax = plt.subplots(figsize=(5.5, 5))
        sc = ax.tricontourf(a[:, 0], a[:, 1], a[:, 5], 60, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
        fig.colorbar(sc, ax=ax, label="Bz (T)")
        t = re.search(r"_t([0-9.]+)ms", f).group(1)
        ax.set_title("%s  Bz, t = %s ms" % (name, t)); ax.set_aspect("equal")
        out = os.path.join(d, "fig_%s_%02d.png" % (name, i))
        fig.tight_layout(); fig.savefig(out, dpi=110); plt.close(fig)
        frames.append(out)
    try:
        from PIL import Image
        ims = [Image.open(x) for x in frames[-len(files):]]
        ims[0].save(os.path.join(d, "anim_%s.gif" % name), save_all=True, append_images=ims[1:], duration=250, loop=0)
    except Exception:
        pass

# steel |B|
for f in sorted(glob.glob(os.path.join(d, "Bsteel_*_t*ms.fld")))[:1]:
    a = fld(f)
    b = np.sqrt((a[:, 3:6] ** 2).sum(1))
    fig, ax = plt.subplots(figsize=(5.5, 5))
    sc = ax.tricontourf(a[:, 0], a[:, 1], b, 60, cmap="viridis")
    fig.colorbar(sc, ax=ax, label="|B| (T)"); ax.set_aspect("equal"); ax.set_title(os.path.basename(f)[:-4])
    fig.tight_layout(); fig.savefig(os.path.join(d, "fig_steel_B.png"), dpi=150)

# current density, board 1
cd = os.path.join(d, "current_density_board1_per_A.csv")
if os.path.isfile(cd):
    r = list(csv.DictReader(open(cd)))
    fig, axs = plt.subplots(1, 3, figsize=(16, 5.2))
    for ax, ph in zip(axs, ("PHASE_A", "PHASE_B", "PHASE_C")):
        seg = [((float(x["x0_mm"]), float(x["y0_mm"])), (float(x["x1_mm"]), float(x["y1_mm"]))) for x in r if x["phase"] == ph]
        J = np.array([float(x["J_A_per_mm2"]) for x in r if x["phase"] == ph])
        lc = LineCollection(seg, array=J, cmap="inferno", linewidths=0.8)
        ax.add_collection(lc); ax.set_xlim(-47, 47); ax.set_ylim(-47, 47); ax.set_aspect("equal")
        fig.colorbar(lc, ax=ax, label="J (A/mm2) per 1 A"); ax.set_title("%s, board 1 (all layers)" % ph)
    fig.tight_layout(); fig.savefig(os.path.join(d, "fig_current_density.png"), dpi=150)
print("figures written to", d)
