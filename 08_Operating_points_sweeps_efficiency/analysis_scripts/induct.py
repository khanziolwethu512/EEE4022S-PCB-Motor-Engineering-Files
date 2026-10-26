"""Phase inductance of the 5-board PCB stack: current-weighted Neumann sum over the solved track pieces
(traces_board.json: per-piece DC current for 1 A), softened kernel r_eff = sqrt(r^2 + a^2), a = GMD of the
0.5 x 0.035 mm trace. Air only, and with an ideal high-mu image plane (steel backplate) as an upper bound."""
import json, math, sys, time
import numpy as np
T = json.load(open(sys.argv[1]))
meta = T["_meta"]; zl = meta["z_layer_board1_mm"]; pitch = meta["pitch_mm"]
a = 0.2235 * (0.5 + 0.035)          # mm, GMD of a rectangle
MU = 1e-7                           # mu0/4pi, H/m
def seg(ph):
    t = T[ph]["tracks"]
    x0 = np.array([r[1] for r in t]); y0 = np.array([r[2] for r in t]); x1 = np.array([r[3] for r in t]); y1 = np.array([r[4] for r in t])
    I = np.array([r[5] for r in t]); z = np.array([zl[r[0]] for r in t])
    P = np.c_[(x0 + x1) / 2, (y0 + y1) / 2, z]
    D = np.c_[(x1 - x0) * I, (y1 - y0) * I, np.zeros_like(I)]     # current-weighted dl (A.mm), 1 A terminal
    return P, D
def M(P1, D1, P2, D2, dz, mirror=None):
    """sum_ij D1i.D2j / |r| with board-2 shifted by dz (mm); mirror: z of an image plane (image = reflected, same sign of
    in-plane current for a high-mu plane)."""
    P2 = P2.copy(); P2[:, 2] += dz
    if mirror is not None:
        P2[:, 2] = 2 * mirror - P2[:, 2]
    s = 0.0
    for i in range(0, len(P1), 800):
        p = P1[i:i + 800]; d = D1[i:i + 800]
        r = np.sqrt(((p[:, None, :] - P2[None, :, :]) ** 2).sum(-1) + a * a)
        s += ((d @ D2.T) / r).sum()
    return MU * s * 1e-3          # mm^2/mm -> m  => H
t0 = time.time()
PA, DA = seg("PHASE_A"); PB, DB = seg("PHASE_B")
n = 5
# board k (0 = next to the magnets) centre at z = -k*pitch; magnet face at +top + gap; plate surface at gap+2 mm magnet
top = zl["L1"] + 0.035 / 2 + 0.0204 / 2      # ~ board top (mask) relative to board centre
res = {}
for name, P2, D2 in (("Laa", PA, DA), ("Mab", PB, DB)):
    m = {dk: M(PA, DA, P2, D2, -dk * pitch) for dk in range(n)}
    air = sum(m[abs(i - j)] for i in range(n) for j in range(n))
    res[name] = {"air": air, "per_offset": m}
    print(name, "offsets", {k: "%.3f uH" % (v * 1e6) for k, v in m.items()}, "stack air %.3f uH" % (air * 1e6), "%.0fs" % (time.time() - t0), flush=True)
# image plane at the steel surface: board-1 top + 1 mm gap + 2 mm magnet
zp = top + 1.0 + 2.0
for name, P2, D2 in (("Laa", PA, DA), ("Mab", PB, DB)):
    im = 0.0
    for i in range(n):
        for j in range(n):
            # board i at z=-i*p ; image of board j about zp
            Pj = P2.copy(); Pj[:, 2] += -j * pitch
            Pi = PA.copy(); Pi[:, 2] += -i * pitch
            im += M(Pi, DA, Pj, D2, 0.0, mirror=zp)
    res[name]["image"] = im
    print(name, "image term %.3f uH" % (im * 1e6), "%.0fs" % (time.time() - t0), flush=True)
json.dump({k: {kk: (vv if not isinstance(vv, dict) else {str(a): b for a, b in vv.items()}) for kk, vv in v.items()} for k, v in res.items()},
          open("induct_results.json", "w"), indent=1)
for case in ("air", "air+image"):
    Laa = res["Laa"]["air"] + (res["Laa"]["image"] if "image" in case else 0)
    Mab = res["Mab"]["air"] + (res["Mab"]["image"] if "image" in case else 0)
    print("%-10s Laa %.2f uH  Mab %.2f uH  Ls = Laa - Mab %.2f uH (one 5-board stator)" % (case, Laa * 1e6, Mab * 1e6, (Laa - Mab) * 1e6))
