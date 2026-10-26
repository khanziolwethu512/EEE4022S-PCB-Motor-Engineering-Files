"""Layout (analytical) DC resistance of one board-phase and one 5-board stator phase, from the same ODB++ copper paths
and DC current shares (traces_board.json). R = P / I^2 with I = 1 A: sum of I_piece^2 * rho * L / (w * t).
Two via models bracket the barrel: solid 0.30 mm copper cylinder (as in the FEM) and a plated barrel of 20 um wall.
Not FEM; measured values are listed separately for comparison only."""
import json, math, os
HERE = os.path.dirname(os.path.abspath(__file__))
RHO20 = 1.724e-8                       # ohm m, annealed copper at 20 C (IACS 100 %)
TCU = {"L1": 0.03556, "L2": 0.0350012, "L3": 0.0350012, "L4": 0.0350012, "L5": 0.0350012, "L6": 0.03556}   # mm
W = 0.5                                # mm, track width
VIA_D, PLATE = 0.30, 0.020             # mm


def board_phase_R(T, ph):
    zc = T["_meta"]["z_layer_board1_mm"]
    rt = sum(I * I * RHO20 * math.hypot(x1 - x0, y1 - y0) * 1e-3 / (W * 1e-3 * TCU[L] * 1e-3)
             for L, x0, y0, x1, y1, I in T[ph]["tracks"])
    a_solid = math.pi * (VIA_D / 2) ** 2
    a_plated = math.pi * ((VIA_D / 2) ** 2 - (VIA_D / 2 - PLATE) ** 2)
    lv = [(abs(zc[Lb] - zc[La]), I) for x, y, La, Lb, I in T[ph]["vias"]]
    rv_s = sum(I * I * RHO20 * l * 1e-3 / (a_solid * 1e-6) for l, I in lv)
    rv_p = sum(I * I * RHO20 * l * 1e-3 / (a_plated * 1e-6) for l, I in lv)
    return rt, rv_s, rv_p


def main():
    T = json.load(open(os.path.join(HERE, "traces_board.json")))
    out, lines = {}, ["| Phase | Tracks (Ω) | Vias solid / plated (Ω) | Board-phase, solid vias (Ω) | Board-phase, plated vias (Ω) | Stator phase, 5 boards (Ω) |",
                      "|---|---|---|---|---|---|"]
    for ph in ("PHASE_A", "PHASE_B", "PHASE_C"):
        rt, rs, rp = board_phase_R(T, ph)
        out[ph] = {"tracks": rt, "vias_solid": rs, "vias_plated": rp, "board_solid": rt + rs, "board_plated": rt + rp}
        lines.append("| %s | %.4f | %.4f / %.4f | %.4f | %.4f | %.3f – %.3f |" % (
            ph[-1], rt, rs, rp, rt + rs, rt + rp, 5 * (rt + rs), 5 * (rt + rp)))
    lines += ["", "Comparison (not inputs): FEM DC conduction 0.2778 / 0.2774 / 0.2779 Ω per board-phase (solid vias); "
              "measured 0.32–0.34 Ω per board (2-wire) and 1.87–1.90 Ω per stator phase including joints and leads."]
    json.dump(out, open(os.path.join(HERE, "out", "layout_resistance.json"), "w"), indent=1)
    open(os.path.join(HERE, "out", "layout_resistance.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    main()
