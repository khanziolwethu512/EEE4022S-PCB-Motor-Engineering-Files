"""EEE4022S AK-07 - INDEPENDENT ANALYTICAL ELECTROMAGNETIC MODEL (Phase 2, 22 Oct 2026)

Original design geometry only: 86 mm OD / 19 mm bore / 2 mm steel backplates, 16 N35 magnets 20 x 6 x 2 mm on
r = 28 mm, 1.0 mm magnet-to-PCB gap, five 1.02032 mm boards per stator (Rev0: S1 + R1; Rev1-S: S1 + R1 + S2 + R2).

Nothing from Maxwell enters this model: no Maxwell field, torque, K, flux or EMF. Inputs are
  * geometry (design values above; layer z positions from the PCB stack-up),
  * the copper paths of one board: traces_board.json, extracted from the ODB++ manufacturing export with a DC nodal
    solve of the copper network (make_traces_board.py, numpy/scipy, no Ansys) -> every track piece and via step with
    its share of 1 A,
  * magnet material: N35, Br and recoil permeability (input data, see BR / MU_R below).

Method
  1. Magnets: uniformly magnetised blocks (axial M) = two charged sheets +-sigma (sigma = Br/mu0) on their faces;
     closed-form field of a uniformly charged rectangle (verified against quadrature, sheet_test.py).
  2. Steel: infinitely permeable planes (mu -> inf, no saturation) -> method of images. A magnet on a backplate
     becomes the doubled-thickness magnet. Rev1-S S2 lies between R1's BARE steel (below) and R2's magnets on R2's
     steel (above): two parallel planes -> infinite image series (truncated, convergence checked). R1's own magnets
     are on the far side of R1's steel and are screened by the mu -> inf plane.
  3. Recoil permeability (mu_r > 1): the magnet's effective magnetisation is reduced by its own demagnetising field,
     M_eff = M / (1 + (mu_r - 1) N_z), with N_z the volume-average demagnetising factor of the image-equivalent
     (doubled) block, computed from the same sheet formula.
  4. Lorentz torque on every track piece / via step at its share of 1 A (centre-line, or averaged over the track
     cross-section), T_z = r x (I dl x B); k(theta) = dLambda/dtheta = -T_copper/I (reciprocity), fundamental K1 and
     phase psi from k over one electrical period (same definitions as the FEM post-processing so the numbers compare).
  5. Back-EMF: e = omega_m * k(theta); E_ph,rms = K1 omega_m / sqrt2; harmonics from k(theta).

python analytical_em.py [--fast]       (numpy only)
"""
import json, math, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MU0 = 4e-7 * math.pi
# --- magnet material (input data, not a Maxwell result). N35 grade: Br 1.17-1.22 T (manufacturer range);
#     the value of the material assigned in the original design (NdFe35, AEDT library) is 1.23 T, mu_r 1.0998.
BR = 1.23
MU_R = 1.0998
# --- design geometry (mm)
POLES, R_IN, R_OUT, MAG_W, MAG_T = 16, 18.0, 38.0, 6.0, 2.0
GAP, BI_T, RS_GAP = 1.0, 2.0, 1.0           # magnet gap, backplate thickness, R1 steel -> S2 clearance
PITCH = 1.02032                              # board pitch (1.0 mm PCB + 2 x 0.01016 mm mask)
TOP1 = 0.51016                               # board-1 top surface (L1 copper top 0.5 mm + mask)
N_BOARDS = 5


def load_traces():
    with open(os.path.join(HERE, "traces_board.json")) as f:
        return json.load(f)


# ------------------------------------------------------------------------------------------------ field kernel
def sheet_H(a1, a2, b1, b2, c):
    """Field of a unit-density charged rectangle (without sigma/4pi), local frame; verified in sheet_test.py."""
    def G(a):
        s = np.sqrt(a * a + c * c)
        return np.arcsinh(b1 / s) - np.arcsinh(b2 / s)

    def Gp(b):
        s = np.sqrt(b * b + c * c)
        return np.arcsinh(a1 / s) - np.arcsinh(a2 / s)

    def F(a, b):
        R = np.sqrt(a * a + b * b + c * c)
        return np.arctan(a * b / (c * R))
    return G(a2) - G(a1), Gp(b2) - Gp(b1), F(a1, b1) - F(a1, b2) - F(a2, b1) + F(a2, b2)


class Rotor(object):
    """A 16-magnet array: magnet faces at z0 (gap side) and z1 (backplate side); polarity +1 = magnet 1 north
    towards +z (as built: even magnets +z, odd -z)."""

    def __init__(self, z0, z1, polarity=+1):
        self.z0, self.z1, self.pol = z0, z1, polarity


def sheets(rotors, planes, n_img):
    """List of (zs, sign, magnet sign pattern owner) charge sheets incl. images.
    rotors: list of Rotor; planes: sorted list of plane z (mu -> inf) bounding the region where B is wanted,
    [] (none), [zp] (one plane) or [zA, zB] (two planes)."""
    out = []
    for ro in rotors:
        for zq, q in ((ro.z1, +1.0), (ro.z0, -1.0)):     # +z magnetised block: +sigma on top face, -sigma on bottom
            q *= ro.pol
            if not planes:
                out.append((zq, q))
            elif len(planes) == 1:
                zp = planes[0]
                out += [(zq, q), (2 * zp - zq, -q)]
            else:
                A, B = planes
                L = B - A
                for n in range(-n_img, n_img + 1):
                    out.append((zq + 2 * n * L, q))
                    out.append((2 * A - zq + 2 * n * L, -q))
    # sheets that coincide with equal and opposite charge cancel exactly (faces on a mu -> inf plane)
    acc = {}
    for z, q in out:
        k = round(z, 9)
        acc[k] = acc.get(k, 0.0) + q
    return [(z, q) for z, q in sorted(acc.items()) if abs(q) > 1e-12]


def field(P, theta_deg, sh, m_eff):
    """B (T) at points P (N x 3, mm) with the magnets turned by theta (deg mech, CCW about +z)."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    Bx = np.zeros(len(P)); By = np.zeros(len(P)); Bz = np.zeros(len(P))
    pref = MU0 * m_eff / (4 * math.pi)                       # sigma = m_eff (A/m); B = mu0 H in air
    for k in range(POLES):
        al = math.radians(k * 360.0 / POLES + theta_deg)
        ca, sa = math.cos(al), math.sin(al)
        u = x * ca + y * sa
        v = -x * sa + y * ca
        sgn_k = 1.0 if k % 2 == 0 else -1.0
        a1, a2, b1, b2 = u - R_IN, u - R_OUT, v + MAG_W / 2, v - MAG_W / 2
        hu = np.zeros(len(P)); hv = np.zeros(len(P)); hz = np.zeros(len(P))
        for zs, q in sh:
            Hu, Hv, Hz = sheet_H(a1, a2, b1, b2, z - zs)
            hu += q * Hu; hv += q * Hv; hz += q * Hz
        Bx += pref * sgn_k * (hu * ca - hv * sa)
        By += pref * sgn_k * (hu * sa + hv * ca)
        Bz += pref * sgn_k * hz
    return np.stack([Bx, By, Bz], axis=1)


def demag_factor(sh_self, z0, z1, n=9):
    """Volume-average demagnetising factor N_z of ONE magnet (with its images) from its own field: N = -<Hz>/M."""
    us = R_IN + (np.arange(n) + 0.5) * (R_OUT - R_IN) / n
    vs = -MAG_W / 2 + (np.arange(n) + 0.5) * MAG_W / n
    zs = z0 + (np.arange(n) + 0.5) * (z1 - z0) / n
    U, V, Z = np.meshgrid(us, vs, zs, indexing="ij")
    a1, a2, b1, b2 = U.ravel() - R_IN, U.ravel() - R_OUT, V.ravel() + MAG_W / 2, V.ravel() - MAG_W / 2
    hz = np.zeros(U.size)
    for zq, q in sh_self:
        hz += q * sheet_H(a1, a2, b1, b2, Z.ravel() - zq)[2]
    return -hz.mean() / (4 * math.pi)


# ------------------------------------------------------------------------------------------------ conductors
def conductor_set(T, z_top_board1, width_avg=False):
    """Points and Lorentz weights for every board (kb = 0 nearest the magnets) and phase of a stator whose board-1
    top surface is at z_top_board1. Returns dict (kb, phase) -> (P, wt_track, kind, dl...) arrays."""
    zc = T["_meta"]["z_layer_board1_mm"]
    dz0 = z_top_board1 - TOP1
    wid = T["_meta"].get("width_mm", 0.5)
    out = {}
    for kb in range(N_BOARDS):
        for ph in ("PHASE_A", "PHASE_B", "PHASE_C"):
            tr = np.array([[0, x0, y0, x1, y1, I] for L, x0, y0, x1, y1, I in T[ph]["tracks"]], float)
            zt = np.array([zc[L] for L, *_ in T[ph]["tracks"]]) + dz0 - kb * PITCH
            mx, my = 0.5 * (tr[:, 1] + tr[:, 3]), 0.5 * (tr[:, 2] + tr[:, 4])
            dlx, dly, I = tr[:, 3] - tr[:, 1], tr[:, 4] - tr[:, 2], tr[:, 5]
            if width_avg:          # 3 x 2 sub-filaments over the 0.5 mm x 35 um cross-section
                dl = np.hypot(dlx, dly); dl[dl == 0] = 1.0
                nx, ny = -dly / dl, dlx / dl
                offs = [(s * wid / 3.0, t * 0.035 / 4.0) for s in (-1, 0, 1) for t in (-1, 1)]
            else:
                nx = ny = np.zeros_like(mx)
                offs = [(0.0, 0.0)]
            P = np.concatenate([np.stack([mx + s * nx, my + s * ny, zt + t], axis=1) for s, t in offs])
            wt = np.tile(I, len(offs)) / len(offs)
            DX, DY = np.tile(dlx, len(offs)), np.tile(dly, len(offs))
            vv = np.array([[x, y, zc[La], zc[Lb], I] for x, y, La, Lb, I in T[ph]["vias"]], float)
            Pv = np.stack([vv[:, 0], vv[:, 1], 0.5 * (vv[:, 2] + vv[:, 3]) + dz0 - kb * PITCH], axis=1)
            out[(kb, ph)] = (P, wt, DX, DY, Pv, vv[:, 4], vv[:, 3] - vv[:, 2])
    return out


def torque_per_amp(cs, theta, sh, m_eff):
    """k = -T_copper / I (Wb/rad) for every (board, phase) at rotor angle theta."""
    res = {}
    for key, (P, wt, DX, DY, Pv, Iv, dzv) in cs.items():
        B = field(P, theta, sh, m_eff)
        t = -np.sum(wt * B[:, 2] * (P[:, 0] * DX + P[:, 1] * DY)) * 1e-6          # mm * mm -> m^2
        Bv = field(Pv, theta, sh, m_eff)
        t += np.sum(Iv * dzv * (Pv[:, 0] * Bv[:, 0] + Pv[:, 1] * Bv[:, 1])) * 1e-6
        res[key] = -t
    return res


def fourier(thetas, ks, p=POLES // 2):
    th = np.radians(p * np.asarray(thetas))
    ks = np.asarray(ks)
    c = [2.0 / len(ks) * np.sum(ks * np.exp(-1j * h * th)) for h in (1, 3, 5, 7)]
    K1 = abs(c[0])
    psi = math.degrees(math.atan2(-c[0].imag, c[0].real))
    return K1, psi, [100 * abs(x) / K1 for x in c[1:]]


# ------------------------------------------------------------------------------------------------ machines
def machine_setup(design):
    """Returns list of stators: (name, board-1 top z, sheets builder args) for the ORIGINAL geometry."""
    zm0_1 = TOP1 + GAP
    r1 = Rotor(zm0_1, zm0_1 + MAG_T)
    if design == "Rev0":
        return [("S1", TOP1, [r1], [r1.z1])]
    r1_steel_top = r1.z1 + BI_T
    bot5 = TOP1 - 2 * 0.51016 - (N_BOARDS - 1) * PITCH            # board-5 bottom surface (board-1 frame)
    dz = r1_steel_top + RS_GAP - bot5                               # S2 offset
    top2 = TOP1 + dz
    r2 = Rotor(top2 + GAP, top2 + GAP + MAG_T)
    return [("S1", TOP1, [r1], [r1.z1]),
            ("S2", top2, [r2], [r1_steel_top, r2.z1])]


def solve(design, T, n_ang=16, width_avg=False, steel=True, recoil=True, n_img=4, br=BR, log=print):
    thetas = [i * 45.0 / n_ang for i in range(n_ang)]
    out = {"design": design, "thetas": thetas, "stators": {}, "boards": {}, "settings": dict(
        n_ang=n_ang, width_avg=width_avg, steel=steel, recoil=recoil, n_img=n_img, Br=br, mu_r=MU_R)}
    for name, ztop, rotors, planes in machine_setup(design):
        pl = planes if steel else []
        sh = sheets(rotors, pl, n_img)
        ro = rotors[0]
        nz = demag_factor(sheets([ro], pl, n_img), ro.z0, ro.z1)
        m = br / MU0
        m_eff = m / (1.0 + (MU_R - 1.0) * nz) if recoil else m
        cs = conductor_set(T, ztop, width_avg)
        t0 = time.time()
        ks = {key: [] for key in cs}
        for th in thetas:
            r = torque_per_amp(cs, th, sh, m_eff)
            for key in cs:
                ks[key].append(r[key])
        st = {"demag_Nz": nz, "M_eff_over_M": m_eff / m, "sheets": len(sh), "planes": pl}
        for ph in ("PHASE_A", "PHASE_B", "PHASE_C"):
            tot = np.sum([ks[(kb, ph)] for kb in range(N_BOARDS)], axis=0)
            K1, psi, H = fourier(thetas, tot)
            st[ph] = {"K1_mNm_per_A": 1e3 * K1, "psi_deg": psi, "H3_pct": H[0], "H5_pct": H[1], "H7_pct": H[2],
                      "k": list(tot)}
            for kb in range(N_BOARDS):
                k1, ps, hh = fourier(thetas, ks[(kb, ph)])
                out["boards"]["%s_B%d_%s" % (name, kb + 1, ph)] = {"K1_mNm_per_A": 1e3 * k1, "psi_deg": ps}
        out["stators"][name] = st
        log("  %s %s: K_A %.3f mN.m/A (psi %.2f deg), N_z %.3f, M_eff/M %.4f, %d sheets, %.0f s"
            % (design, name, st["PHASE_A"]["K1_mNm_per_A"], st["PHASE_A"]["psi_deg"], nz, m_eff / m, len(sh),
               time.time() - t0))
    # machine: stators in series, same sense (rotors aligned; checked by the phase angles)
    mach = {}
    for ph in ("PHASE_A", "PHASE_B", "PHASE_C"):
        tot = np.sum([out["stators"][s][ph]["k"] for s in out["stators"]], axis=0)
        K1, psi, H = fourier(thetas, tot)
        wm = 1000.0 * 2 * math.pi / 60
        mach[ph] = {"K1_mNm_per_A": 1e3 * K1, "psi_deg": psi, "H3_pct": H[0], "H5_pct": H[1], "H7_pct": H[2],
                    "E_ph_rms_1000rpm_V": K1 * wm / math.sqrt(2),
                    # line voltage: triplen harmonics cancel; 5th and 7th kept (needs >= 16 angles, no aliasing)
                    "E_line_rms_1000rpm_V": math.sqrt(3) * K1 * wm / math.sqrt(2) * math.sqrt(
                        1 + (H[1] / 100) ** 2 + (H[2] / 100) ** 2),
                    "torque_per_Apk_mNm": 1.5e3 * K1}
    out["machine"] = mach
    return out


def main():
    fast = "--fast" in sys.argv
    T = load_traces()
    res = {}
    for d in ("Rev0", "Rev1S"):
        print("== %s (primary: steel images, recoil-corrected, centre-line)" % d)
        res[d] = solve(d, T, n_ang=8 if fast else 16)
    with open(os.path.join(HERE, "out", "analytical_primary.json"), "w") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    main()
