# Offline check (plain Python): trace integration in an analytic magnet field -> K1 6.110 vs FEM 6.092 mN.m/A
"""Offline check of the trace-integration code with an ANALYTIC magnet field (surface magnetic charges of the 16
magnets + their images in an ideal iron plane at the back of the magnets). Not a substitute for Maxwell: it only
proves the sign, phase and magnitude of the torque integration before the lab-PC run."""
import json, math, numpy as np
D = json.load(open('traces_board.json'))
ZC = D['_meta']['z_layer_board1_mm']
mu0 = 4e-7 * math.pi
M = 1.23 / mu0 / 1.0997            # NdFe35: Br ~1.23 T, mu_r 1.0997 -> M = Hc
g, top1, tm = 1.0, 0.51016, 2.0
zm0, zm1 = top1 + g, top1 + g + tm
h = 0.5
def sources(theta_deg):
    xs, qs = [], []
    us = np.arange(18 + h / 2, 38, h); vs = np.arange(-3 + h / 2, 3, h)
    U, V = np.meshgrid(us, vs); U = U.ravel(); V = V.ravel()
    for k in range(16):
        a = math.radians(k * 22.5 + theta_deg); ca, sa = math.cos(a), math.sin(a)
        x = U * ca - V * sa; y = U * sa + V * ca
        s = 1.0 if k % 2 == 0 else -1.0           # +Z magnetised: N face (+charge) on top
        for z, sign in ((zm1, s), (zm0, -s)):
            for zz, im in ((z, 1.0), (2 * zm1 - z, -1.0)):   # image in the ideal-iron plane at zm1 (opposite sign:
                if abs(zz - zm1) < 1e-9: continue                  #  iron surface = magnetic equipotential); the top
                xs.append(np.stack([x, y, np.full_like(x, zz)], 1))   # face and its image cancel exactly
                qs.append(np.full(x.size, im * sign * M * (h * 1e-3) ** 2))
    return np.concatenate(xs), np.concatenate(qs)
def Bfield(P, S, Q):
    out = np.zeros_like(P)
    for i in range(0, len(P), 150):
        d = (P[i:i + 150, None, :] - S[None, :, :]) * 1e-3
        r3 = np.linalg.norm(d, axis=2) ** 3
        out[i:i + 150] = mu0 / (4 * math.pi) * np.einsum('ijk,ij->ik', d, Q[None, :] / r3)
    return out
def k_board(ph, theta, zoff=0.0):
    t = np.array([[r[1], r[2], r[3], r[4], r[5]] for r in D[ph]['tracks']])
    zl = np.array([ZC[r[0]] for r in D[ph]['tracks']]) + zoff
    mid = np.stack([(t[:, 0] + t[:, 2]) / 2, (t[:, 1] + t[:, 3]) / 2, zl], 1)
    dl = np.stack([t[:, 2] - t[:, 0], t[:, 3] - t[:, 1], 0 * zl], 1) * 1e-3
    S, Q = sources(theta)
    B = Bfield(mid, S, Q)
    F = t[:, 4:5] * np.cross(dl, B)
    T = np.sum(mid[:, 0] * 1e-3 * F[:, 1] - mid[:, 1] * 1e-3 * F[:, 0])
    v = np.array(D[ph]['vias'])
    if len(v):
        za = np.array([ZC[x] for x in v[:, 2]]) + zoff; zb = np.array([ZC[x] for x in v[:, 3]]) + zoff
        vm = np.stack([v[:, 0].astype(float), v[:, 1].astype(float), (za + zb) / 2], 1)
        vdl = np.stack([0 * za, 0 * za, (zb - za)], 1) * 1e-3
        Bv = Bfield(vm, S, Q); Fv = v[:, 4:5].astype(float) * np.cross(vdl, Bv)
        T += np.sum(vm[:, 0] * 1e-3 * Fv[:, 1] - vm[:, 1] * 1e-3 * Fv[:, 0])
    return -T                                         # k = torque on rotor per amp = -(copper torque)
th = [0, 5.625, 11.25, 16.875, 22.5, 28.125, 33.75, 39.375]
for ph in ('PHASE_A',):
    k = np.array([k_board(ph, t) for t in th])
    c = np.fft.rfft(k) / len(k) * 2
    K1, psi = abs(c[1]), math.degrees(math.atan2(-c[1].imag, c[1].real))
    print(ph, 'k(theta) mWb/rad', np.round(1e3 * k, 3))
    print('K1 = %.3f mN.m/A, psi = %.1f deg elec, H3/H1 = %.1f %%' % (1e3 * K1, psi, 100 * abs(c[3]) / K1))
print('FEM baseline: K1 6.092, psi -30.18, k(0..16.875) = 5.317 1.018 -2.347 -6.359 mWb/rad')
