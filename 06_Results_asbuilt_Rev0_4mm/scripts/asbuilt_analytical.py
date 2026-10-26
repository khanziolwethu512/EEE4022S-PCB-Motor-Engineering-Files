"""Independent analytical prediction for the Rev0 as-built study (no Maxwell input, no experimental input).
Charged-sheet magnets + one mu->inf steel plane (the backplate) + 2D sheet currents in the real copper islands
(sheet_current.py; reproduced the detailed FEM to 0.01-0.03 % at 1 mm). Also the centre-line network value, so that
the ratio K_sheet / K_centre-line per board can be applied to the Maxwell field maps (which integrate on the
centre-lines). The infinite-plane model cannot see the 86 -> 80 mm OD / 19 -> 25 mm bore change (Case C): that
effect comes from the Maxwell field maps only.
Gaps: 1.0 (Case A check), 3.5 / 4.0 / 4.5 mm (Case B and its +/-0.5 mm uncertainty band).
python asbuilt_analytical.py -> out/asbuilt_analytical.json
"""
import json, math, os, sys, time
import numpy as np
sys.argv = [sys.argv[0], "0.1"]
import sheet_current as S
import analytical_em as A
import pcb_geometry
HERE = os.path.dirname(os.path.abspath(__file__))
GAPS = [1.0, 4.0, 3.5, 4.5]


def main():
    T = A.load_traces(); G = pcb_geometry.load(); zc = T["_meta"]["z_layer_board1_mm"]
    sheets = {L: S.solve_layer(T, L, G["layers"][L]["PHASE_A"]) for L in S.LAYERS}
    st = A.machine_setup("Rev0")[0]                       # rotor at the 1 mm position, steel plane at its back
    name, ztop, rotors, planes = st
    sh = A.sheets(rotors, planes, 4)
    ro = rotors[0]
    nz = A.demag_factor(A.sheets([ro], planes, 4), ro.z0, ro.z1)
    m = A.BR / A.MU0 / (1 + (A.MU_R - 1) * nz)
    th_half = [i * 45.0 / 8 for i in range(4)]
    th = th_half + [t + 22.5 for t in th_half]
    out = {"Br_T": A.BR, "mu_r": A.MU_R, "N_z": nz, "cases": {}}
    t0 = time.time()
    for g in GAPS:
        cs = A.conductor_set(T, A.TOP1 - (g - A.GAP))     # whole stack moved away from the rotor by (g - 1) mm
        tot_s = np.zeros(len(th)); tot_c = np.zeros(len(th)); boards = {}
        for kb in range(A.N_BOARDS):
            dz = -(g - A.GAP) - kb * A.PITCH
            ks, kc = [], []
            for t in th_half:
                tot = 0.0
                for L in S.LAYERS:
                    s = sheets[L]
                    B = A.field(np.c_[s["mx"], s["my"], np.full(len(s["mx"]), zc[L] + dz)], t, sh, m)
                    tot += -np.sum(s["I"] * B[:, 2] * (s["mx"] * s["dlx"] + s["my"] * s["dly"])) * 1e-6
                P, wt, DX, DY, Pv, Iv, dzv = cs[(kb, "PHASE_A")]
                Bv = A.field(Pv, t, sh, m)
                tot += np.sum(Iv * dzv * (Pv[:, 0] * Bv[:, 0] + Pv[:, 1] * Bv[:, 1])) * 1e-6
                ks.append(-tot)
                kc.append(A.torque_per_amp({(kb, "PHASE_A"): cs[(kb, "PHASE_A")]}, t, sh, m)[(kb, "PHASE_A")])
            ks += [-x for x in ks]; kc += [-x for x in kc]
            tot_s += np.array(ks); tot_c += np.array(kc)
            K1, psi, _ = A.fourier(th, ks); Kc, _, _ = A.fourier(th, kc)
            d = g + kb * A.PITCH
            boards["B%d" % (kb + 1)] = {"distance_mm": d, "K_sheet": 1e3 * K1, "K_centreline": 1e3 * Kc,
                                        "ratio_sheet_over_cl": K1 / Kc, "psi": psi}
            print("gap %.2f B%d (d %.3f mm): sheet %.4f, centre-line %.4f, ratio %.4f  (%.0f s)"
                  % (g, kb + 1, d, 1e3 * K1, 1e3 * Kc, K1 / Kc, time.time() - t0), flush=True)
        K1, psi, H = A.fourier(th, tot_s); Kc, _, _ = A.fourier(th, tot_c)
        wm = 1000 * 2 * math.pi / 60
        out["cases"]["gap_%.2f" % g] = {"gap_mm": g, "boards": boards, "K_sheet": 1e3 * K1, "K_centreline": 1e3 * Kc,
                                        "psi": psi, "E_LL_rms_per_1000rpm": math.sqrt(3) * K1 * wm / math.sqrt(2)}
        print("gap %.2f: K sheet %.4f, centre-line %.4f mN.m/A, E_LL %.4f V rms / 1000 rpm"
              % (g, 1e3 * K1, 1e3 * Kc, math.sqrt(3) * K1 * wm / math.sqrt(2)), flush=True)
        json.dump(out, open(os.path.join(HERE, "out", "asbuilt_analytical.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
