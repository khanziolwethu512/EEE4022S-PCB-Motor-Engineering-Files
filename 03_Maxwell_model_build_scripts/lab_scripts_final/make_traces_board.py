# Provenance tool (plain Python 3 + numpy/scipy/shapely, NOT run in AEDT): rebuilds traces_board.json from the ODB++
# export.  python make_traces_board.py <...\05_ODBPP\odb> <folder with pcb_geometry.py>
"""Trace-resolved winding paths of ONE board from the ODB++ export.
Track centre-lines (lines + arcs as 0.4 mm chords) are grouped by copper island (pcb_geometry, net-correct), vias of
the same net join every layer island they touch (barrel = chain of layer nodes), terminals: In on L1, Out on L6.
A DC nodal solve with 1 A In->Out gives the current in every track piece and via barrel step (handles the parallel
L2/L3, L4/L5 copper and dead-end stubs). Output traces_board.json: per phase, pieces [layer, x0,y0,x1,y1, I] and
via steps [x, y, layer_from, layer_to, I] (board-1 coordinates, mm; z added later from the stack-up)."""
import sys, os, math, json
import numpy as np
from shapely.geometry import Point, Polygon, LineString
from scipy.spatial import cKDTree
import scipy.sparse as sp, scipy.sparse.linalg as spl
ODB, REV0 = sys.argv[1], sys.argv[2]
sys.path.insert(0, REV0)
import pcb_geometry
LAY = {'L1': 'top_layer', 'L2': 'layer_1', 'L3': 'layer_2', 'L4': 'layer_3', 'L5': 'layer_4', 'L6': 'bottom_layer'}
ORDER = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6']
TCU = {'L1': 0.03556, 'L2': 0.0350012, 'L3': 0.0350012, 'L4': 0.0350012, 'L5': 0.0350012, 'L6': 0.03556}
ZC = {'L1': 0.48222, 'L2': 0.301015, 'L3': 0.12009, 'L4': -0.12009, 'L5': -0.301015, 'L6': -0.48222}   # board 1
RHO, W, OX, OY = 1.0 / 5.8e7, 0.499999e-3, 100.0, 100.0
TERM = {'PHASE_A': (-22.75, 39.40416), 'PHASE_B': (0.0, 45.5), 'PHASE_C': (22.75, 39.40416)}
G = pcb_geometry.load()

SYMS = {}
def feats(name, kinds=('L ', 'A ')):
    sym = {}
    for line in open(os.path.join(ODB, 'steps/pcb/layers', name, 'features')):
        line = line.strip()
        if line.startswith('$'):
            k, v = line[1:].split(None, 1); sym[int(k)] = v
        if line[:2] in kinds:
            yield line.split(';')[0].split(), sym

def sym_radius(name):
    import re
    if name.startswith('r'):
        return float(name[1:]) / 2000.0
    m = re.match(r'oct([\d.]+)x([\d.]+)x', name)
    if m:
        return max(float(m.group(1)), float(m.group(2))) / 2000.0
    return 0.25

def arc_pts(xs, ys, xe, ye, xc, yc, cw):
    r0 = math.hypot(xs - xc, ys - yc); a0 = math.atan2(ys - yc, xs - xc); a1 = math.atan2(ye - yc, xe - xc)
    full = abs(xs - xe) < 1e-9 and abs(ys - ye) < 1e-9
    if cw:
        while a1 >= a0: a1 -= 2 * math.pi
        if full: a1 = a0 - 2 * math.pi
    else:
        while a1 <= a0: a1 += 2 * math.pi
        if full: a1 = a0 + 2 * math.pi
    n = max(1, int(math.ceil(abs(a1 - a0) * r0 / 0.4)))
    return [(xc + r0 * math.cos(a0 + (a1 - a0) * i / n), yc + r0 * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]

raw = {L: [] for L in ORDER}
for L in ORDER:
    for f, _ in feats(LAY[L]):
        if f[0] == 'L':
            pts = [(float(f[1]) - OX, float(f[2]) - OY), (float(f[3]) - OX, float(f[4]) - OY)]
        else:
            v = [float(x) for x in f[1:7]]
            pts = arc_pts(v[0] - OX, v[1] - OY, v[2] - OX, v[3] - OY, v[4] - OX, v[5] - OY, f[10].upper() == 'Y')
        for a, b in zip(pts[:-1], pts[1:]):
            if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6:
                raw[L].append((a, b))

pads = {L: [] for L in ORDER}
for L in ORDER:
    for f, sym in feats(LAY[L], ('P ',)):
        pads[L].append((float(f[1]) - OX, float(f[2]) - OY, sym_radius(sym.get(int(f[3]), 'r500'))))
print('pads per layer', dict((L, len(v)) for L, v in pads.items()))

out = {'_meta': {'z_layer_board1_mm': ZC, 'pitch_mm': 1.02032, 'width_mm': W * 1e3, 'source': 'ODB++ top_layer..bottom_layer'}}
for ph in ('PHASE_A', 'PHASE_B', 'PHASE_C'):
    vias = [(v['x'], v['y']) for v in G['vias'] if v['net'] == ph]
    nodes = {}
    def node(key):
        if key not in nodes: nodes[key] = len(nodes)
        return nodes[key]
    edges = []            # (a, b, g, info)
    nseg = 0
    for L in ORDER:
        isl = [Polygon(p).buffer(0.02) for p in G['layers'][L][ph]]
        for ii, P in enumerate(isl):
            S = [s for s in raw[L] if P.contains(Point(0.5 * (s[0][0] + s[1][0]), 0.5 * (s[0][1] + s[1][1])))]
            if not S: continue
            # attach points: vias of this net inside the island, and the terminal pad
            att = [('v', j, vx, vy) for j, (vx, vy) in enumerate(vias) if P.buffer(0.3).contains(Point(vx, vy))]
            tx, ty = TERM[ph]
            if L in ('L1', 'L6') and P.buffer(0.6).contains(Point(tx, ty)):
                att.append(('t', L, tx, ty))
            # split segments at the projection of each attach point onto the nearest segment
            splits = {}
            for a in att:
                if a[0] == 't':
                    continue
                best = None
                for si, (p0, p1) in enumerate(S):
                    ls = LineString([p0, p1]); d = ls.distance(Point(a[2], a[3]))
                    if best is None or d < best[0]:
                        best = (d, si, ls.project(Point(a[2], a[3]), normalized=True))
                if best[0] < (2.0 if a[0] == 't' else 0.45):
                    splits.setdefault(best[1], []).append((best[2], a))
            pieces = []
            for si, (p0, p1) in enumerate(S):
                ts = sorted(splits.get(si, []), key=lambda t: t[0])
                pts = [(0.0, None)] + ts + [(1.0, None)]
                for (t0, a0), (t1, a1) in zip(pts[:-1], pts[1:]):
                    q0 = (p0[0] + (p1[0] - p0[0]) * t0, p0[1] + (p1[1] - p0[1]) * t0)
                    q1 = (p0[0] + (p1[0] - p0[0]) * t1, p0[1] + (p1[1] - p0[1]) * t1)
                    pieces.append((q0, q1, a0 if t0 > 0 else None, a1 if t1 < 1 else None))
            # island-local node merge (0.03 mm)
            pts_all = []
            for q0, q1, _, _ in pieces:
                pts_all += [q0, q1]
            T = cKDTree(np.array(pts_all))
            parent = list(range(len(pts_all)))
            def find(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]; i = parent[i]
                return i
            for a, b in T.query_pairs(0.03):
                parent[find(a)] = find(b)
            for k, (q0, q1, a0, a1) in enumerate(pieces):
                n0 = node((L, ii, find(2 * k))); n1 = node((L, ii, find(2 * k + 1)))
                ln = math.hypot(q1[0] - q0[0], q1[1] - q0[1]) * 1e-3
                if ln < 1e-9:
                    edges.append((n0, n1, 1e6, None))
                else:
                    edges.append((n0, n1, W * TCU[L] * 1e-3 / (RHO * ln), ('t', L, q0, q1)))
                for qa, nn in ((a0, n0), (a1, n1)):
                    if qa is None: continue
                    if qa[0] == 'v':
                        edges.append((nn, node(('via', qa[1], L)), 1e6, None))
                    else:
                        edges.append((nn, node(('term', qa[1])), 1e6, None))
                nseg += 1
            Tn = cKDTree(np.array(pts_all))
            for pi_, (px, py, pr) in enumerate(pads[L]):
                if not P.contains(Point(px, py)):
                    continue
                pn = node(('pad', L, pi_))
                for idx in Tn.query_ball_point([px, py], pr + 0.26):
                    edges.append((node((L, ii, find(idx))), pn, 1e6, None))
                for j, (vx, vy) in enumerate(vias):
                    if math.hypot(vx - px, vy - py) < 0.05:
                        edges.append((pn, node(('via', j, L)), 1e6, None))
                if L in ('L1', 'L6') and math.hypot(px - TERM[ph][0], py - TERM[ph][1]) < 0.05:
                    edges.append((pn, node(('term', L)), 1e6, None))
            for a in att:            # terminal pad (3 x 2 mm): joins every track node on the pad
                if a[0] != 't': continue
                for k, (q0, q1, _, _) in enumerate(pieces):
                    for q, idx in ((q0, 2 * k), (q1, 2 * k + 1)):
                        if math.hypot(q[0] - a[2], q[1] - a[3]) < 1.6:
                            edges.append((node((L, ii, find(idx))), node(('term', a[1])), 1e6, None))
    # via barrels: chain of the six layer nodes of every via
    gv = W * 0 + math.pi * (0.15e-3) ** 2 / (RHO * 0.181e-3)
    for j, (vx, vy) in enumerate(vias):
        for La, Lb in zip(ORDER[:-1], ORDER[1:]):
            edges.append((node(('via', j, La)), node(('via', j, Lb)), gv, ('v', vx, vy, La, Lb)))
    nin, nout = nodes.get(("term", "L1")), nodes.get(("term", "L6"))
    print(ph, "terminal nodes", nin, nout)
    N = len(nodes)
    r, c, v = [], [], []
    for a, b, g, _ in edges:
        r += [a, b, a, b]; c += [a, b, b, a]; v += [g, g, -g, -g]
    Y = sp.csr_matrix((v, (r, c)), shape=(N, N)) + sp.identity(N) * 1e-9   # tiny leak: floating stubs stay solvable
    keep = np.array([i for i in range(N) if i != nout])
    rhs = np.zeros(N); rhs[nin] = 1.0
    V = np.zeros(N); V[keep] = spl.spsolve(Y.tocsr()[keep][:, keep].tocsc(), rhs[keep])
    R = V[nin] - V[nout]
    tracks, vsteps = [], []
    for a, b, g, info in edges:
        if info is None: continue
        I = g * (V[a] - V[b])
        if info[0] == 't':
            tracks.append([info[1], info[2][0], info[2][1], info[3][0], info[3][1], float(I)])
        else:
            if abs(I) > 1e-9:
                vsteps.append([info[1], info[2], info[3], info[4], float(I)])
    live = [t for t in tracks if abs(t[5]) > 0.01]
    # KCL check at the In terminal and total copper length carrying current
    print('%s: R_dc = %.4f ohm (FEM 0.2777, solid vias); pieces %d, carrying >10 mA %d; vias %d, via steps %d; '
          'current-weighted length %.0f mm' % (ph, R, len(tracks), len(live), len(vias), len(vsteps),
          sum(abs(t[5]) * math.hypot(t[3] - t[1], t[4] - t[2]) for t in tracks)))
    out[ph] = {'R_dc_ohm': R, 'tracks': [t for t in tracks if abs(t[5]) > 1e-6], 'vias': vsteps}
json.dump(out, open('traces_board.json', 'w'))
print('written traces_board.json', os.path.getsize('traces_board.json'), 'bytes')
