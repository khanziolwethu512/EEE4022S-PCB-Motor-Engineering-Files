# -*- coding: utf-8 -*-
"""Stack-up, one detailed PCB, and the five-board stator stack.

Z convention: PCB1 copper+dielectric is centred on z = 0, its L1 (top) faces the rotor at +Z.
Board k (k = 1..N) is shifted by -(k-1) * pitch, pitch = PCB_THICKNESS + 2*MASK_T + INTERBOARD_GAP.
All boards have the same angular and layer orientation (no flipping).
"""
import math

LAYERS = ["L1", "L2", "L3", "L4", "L5", "L6"]
TAG = {"PHASE_A": "A", "PHASE_B": "B", "PHASE_C": "C"}
COLOR = {"PHASE_A": "(214 39 40)", "PHASE_B": "(44 160 44)", "PHASE_C": "(31 119 180)"}


# ---------------------------------------------------------------------------- stack-up
def board_stack(cfg, geo, k=1):
    """Return dict: layers {L: (z0, z1)}, diel [(z0, z1)] x5, mask_top, mask_bot, top_surface, bottom_surface."""
    cu = geo["copper_t"]
    alt = geo["dielectric_t"]
    if cfg.STACKUP_MODE == "altium":
        diel = list(alt)
    elif cfg.STACKUP_MODE == "manual":
        diel = list(cfg.DIELECTRIC_MANUAL)
        if len(diel) != 5:
            raise ValueError("DIELECTRIC_MANUAL needs 5 values (top -> bottom)")
    else:
        f = (cfg.PCB_THICKNESS - sum(cu)) / sum(alt)
        diel = [d * f for d in alt]
    total = sum(cu) + sum(diel)
    zc = -(k - 1) * cfg.board_pitch()
    z = zc + total / 2.0
    layers, diels = {}, []
    for i, key in enumerate(LAYERS):
        layers[key] = (z - cu[i], z)
        z -= cu[i]
        if i < 5:
            diels.append((z - diel[i], z))
            z -= diel[i]
    top_cu = layers["L1"][1]
    bot_cu = layers["L6"][0]
    return {"layers": layers, "diel": diels, "total": total, "centre": zc,
            "mask_top": (top_cu, top_cu + cfg.MASK_T), "mask_bot": (bot_cu - cfg.MASK_T, bot_cu),
            "top_surface": top_cu + cfg.MASK_T, "bottom_surface": bot_cu - cfg.MASK_T, "diel_t": diel}


# ---------------------------------------------------------------------------- terminal verification
def _point_in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def winding_graph(geo, net):
    nodes = []
    for L in LAYERS:
        for ring in geo["layers"][L].get(net, []):
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            nodes.append((L, ring, (min(xs), min(ys), max(xs), max(ys))))

    def hits(x, y, layer=None):
        return [k for k, (L, ring, bb) in enumerate(nodes)
                if (layer is None or L == layer) and bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]
                and _point_in_ring(x, y, ring)]

    adj = dict((k, set()) for k in range(len(nodes)))
    for v in geo["vias"]:
        if v["net"] == net:
            h = hits(v["x"], v["y"])
            for a in h:
                adj[a].update(b for b in h if b != a)
    return nodes, adj, hits


def verify_phase(geo, net, tmap):
    """Checks: one connected network; In/Out on different islands; report hop distance."""
    nodes, adj, hits = winding_graph(geo, net)
    t_in, t_out = tmap["in"], tmap["out"]
    a = hits(t_in[1], t_in[2], t_in[0])
    b = hits(t_out[1], t_out[2], t_out[0])
    if len(a) != 1 or len(b) != 1:
        raise RuntimeError("%s: a terminal pad is not on exactly one copper island" % net)
    a, b = a[0], b[0]
    if a == b:
        raise RuntimeError("%s: In and Out are on the SAME copper island (would short the winding)" % net)
    dist = {a: 0}
    q = [a]
    while q:
        u = q.pop(0)
        for w in adj[u]:
            if w not in dist:
                dist[w] = dist[u] + 1
                q.append(w)
    if len(dist) != len(nodes):
        raise RuntimeError("%s: winding is not one connected network (%d of %d islands reached)"
                           % (net, len(dist), len(nodes)))
    if b not in dist:
        raise RuntimeError("%s: In and Out are not connected" % net)
    return {"islands": len(nodes), "hops_in_out": dist[b], "max_hops": max(dist.values())}


def cross_phase_check(geo):
    """No via of one net may land on copper of another net (unintended shortcut)."""
    bad = 0
    for net in ("PHASE_A", "PHASE_B", "PHASE_C"):
        others = [n for n in ("PHASE_A", "PHASE_B", "PHASE_C") if n != net]
        for v in geo["vias"]:
            if v["net"] != net:
                continue
            for L in LAYERS:
                for o in others:
                    for ring in geo["layers"][L].get(o, []):
                        if _point_in_ring(v["x"], v["y"], ring):
                            bad += 1
    return bad


# ---------------------------------------------------------------------------- one board
def build_board(ctx, geo, k, excite, y_lead_end):
    """Build detailed board k. Returns {'phases': {net: name}, 'leads': {...}, 'stack': {...}, 'fr4': name}."""
    cfg = ctx.cfg
    st = board_stack(cfg, geo, k)
    Lz = st["layers"]
    out = {"phases": {}, "leads": {}, "stack": st, "fr4": None}
    zb, zt = Lz["L6"][0], Lz["L1"][1]
    parts_by_net = {}
    vias_all = []
    for net in cfg.PHASES:
        tag = "%s%d" % (TAG[net], k)
        color = COLOR[net]
        parts = []
        for L in LAYERS:
            z0, z1 = Lz[L]
            sheets = [ctx.polygon_sheet("Cu%s_%s_%03d" % (tag, L, i), ring, z0, "copper", color)
                      for i, ring in enumerate(geo["layers"][L].get(net, []))]
            ctx.sweep_z(sheets, z1 - z0)
            parts += sheets
        vias = [ctx.cylinder("Via%s_%03d" % (tag, j), v["x"], v["y"], zb, zt - zb, cfg.VIA_DIAMETER / 2.0,
                             "copper", color, cfg.VIA_SIDES)
                for j, v in enumerate([v for v in geo["vias"] if v["net"] == net])]
        vias_all += vias
        ctx.log("PCB%d %s: %d copper islands on 6 layers, %d vias" % (k, net, len(parts), len(vias)))
        lead_parts = []
        if excite:
            lg = lead_geometry(cfg, net, Lz, y_lead_end)
            out["leads"][net] = lg
            for key in ("in_foot", "in_bar", "out_foot", "out_bar"):
                pts, za, zb2 = lg[key]
                lead_parts.append(ctx.prism("Lead%s_%s" % (tag, key), pts, za, zb2, "copper", color))
        parts_by_net[net] = (lead_parts[:1] + parts + vias + lead_parts[1:]) if lead_parts else (parts + vias)

    if cfg.BUILD_FR4:
        slabs = [ctx.prism("FR4_%d_%d" % (k, i + 1), geo["outline"], za, zb2, "FR4_epoxy", "(0 128 0)", 0.7)
                 for i, (za, zb2) in enumerate(st["diel"])]
        mm_ = ctx.state.get("mask_material", "FR4_epoxy")
        masks = [ctx.prism("Mask_%d_top" % k, geo["outline"], st["mask_top"][0], st["mask_top"][1],
                           mm_, "(0 90 0)", 0.7),
                 ctx.prism("Mask_%d_bot" % k, geo["outline"], st["mask_bot"][0], st["mask_bot"][1],
                           mm_, "(0 90 0)", 0.7)]
        z0, z1 = st["bottom_surface"] - 0.01, st["top_surface"] + 0.01
        cut = [ctx.cylinder("CutBore_%d" % k, 0, 0, z0, z1 - z0, geo["centre_bore_d"] / 2.0, "vacuum", "(0 0 0)")]
        for h, hole in enumerate(geo["npth"]):
            cut.append(ctx.cylinder("CutNPTH_%d_%02d" % (k, h + 1), hole["x"], hole["y"], z0, z1 - z0,
                                    hole["d"] / 2.0, "vacuum", "(0 0 0)"))
        ctx.subtract(slabs + masks, cut, keep_tools=False)
        if vias_all:
            ctx.subtract(slabs, vias_all, keep_tools=True)
        feet = [p for net in parts_by_net for p in parts_by_net[net] if "_foot" in p]
        if feet:   # solder-mask openings at the terminal pads
            ctx.subtract(masks, feet, keep_tools=True)
        out["fr4"] = ctx.rename(ctx.unite(slabs), "PCB%d_FR4" % k)
        out["mask"] = ctx.rename(ctx.unite(masks), "PCB%d_SolderMask" % k)
        ctx.log("PCB%d: FR-4 (5 dielectrics) + solder masks %.5f mm (%s) built" % (k, cfg.MASK_T, mm_))

    for net in cfg.PHASES:
        out["phases"][net] = ctx.rename(ctx.unite(parts_by_net[net]), "Phase%s%d_Cu" % (TAG[net], k))
    if cfg.STACK_SERIES:
        # drop the modelling history of this board (thousands of polyline/sweep/unite records per board);
        # 2026-10-06: the 5-board build ran > 2.5 h and AEDT closed - history/memory growth suspected
        try:
            ctx.editor.PurgeHistory(["NAME:Selections", "Selections:=", ",".join(sorted(out["phases"].values())),
                                     "NewPartsModelFlag:=", "Model"])
            ctx.log("PCB%d: modelling history purged" % k)
        except Exception as e:
            ctx.log("PCB%d: history purge skipped (%s)" % (k, e), 1)
    return out


def lead_geometry(cfg, net, Lz, y_end):
    """Raised straight leads from the mapped In (L1) / Out (L6) pads to the region +Y face."""
    t_in, t_out = cfg.TERMINAL_MAP[net]["in"], cfg.TERMINAL_MAP[net]["out"]
    hw = cfg.LEAD_WIDTH / 2.0
    z1b, z1t = Lz["L1"]
    z6b, z6t = Lz["L6"]
    out = {"r_inner": 1e9}
    for role, (layer, x, y) in (("in", t_in), ("out", t_out)):
        foot = [[x - hw, y - hw], [x + hw, y - hw], [x + hw, y + hw], [x - hw, y + hw]]
        bar = [[x - hw, y - hw], [x + hw, y - hw], [x + hw, y_end], [x - hw, y_end]]
        if layer == "L1":
            b0 = z1t + cfg.MASK_T + cfg.LEAD_RISE
            b1 = b0 + cfg.LEAD_HEIGHT
            f0, f1 = z1t - (z1t - z1b) / 2.0, b1
        elif layer == "L6":
            b1 = z6b - cfg.MASK_T - cfg.LEAD_RISE
            b0 = b1 - cfg.LEAD_HEIGHT
            f0, f1 = b0, z6b + (z6t - z6b) / 2.0
        else:
            raise RuntimeError("terminal pads must be on L1 or L6")
        out[role + "_foot"] = (foot, f0, f1)
        out[role + "_bar"] = (bar, b0, b1)
        out["face_" + role] = (x, y_end, (b0 + b1) / 2.0)
        out["r_inner"] = min(out["r_inner"], math.hypot(x, y) - cfg.LEAD_WIDTH)
        out["z_top"] = max(out.get("z_top", -1e9), f1, b1)
    return out


# ---------------------------------------------------------------------------- phase rotation check
def rotation_match(geo, net, ref, ang_deg, layer="L1", step=0.25):
    """Fraction of `net` copper on `layer` that coincides with `ref` copper rotated by ang_deg about the
    board centre (grid sampling, no external libraries). 1.0 = net is ref rotated by ang_deg."""
    def rings_bb(n):
        out = []
        for ring in geo["layers"][layer].get(n, []):
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            out.append((ring, min(xs), min(ys), max(xs), max(ys)))
        return out

    def inside(rb, x, y):
        return any(b[1] <= x <= b[3] and b[2] <= y <= b[4] and _point_in_ring(x, y, b[0]) for b in rb)

    tgt, src = rings_bb(net), rings_bb(ref)
    c, s = math.cos(math.radians(-ang_deg)), math.sin(math.radians(-ang_deg))
    hit = tot = 0
    for ring, x0, y0, x1, y1 in tgt:
        x = x0 + step / 2.0
        while x < x1:
            y = y0 + step / 2.0
            while y < y1:
                if _point_in_ring(x, y, ring):
                    tot += 1
                    if inside(src, x * c - y * s, x * s + y * c):   # rotate back by -ang into ref frame
                        hit += 1
                y += step
            x += step
    return hit / float(tot) if tot else 0.0


# ---------------------------------------------------------------------------- five-board series stack
def build_stack_series(ctx, geo, board_objs, y_end):
    """Series-connect the phase windings of N identical, same-orientation, touching boards.

    board_objs: [{"k": k, "phases": {net: obj}}] (boards built WITHOUT leads).
    Per phase: board k L6 Out pad -> copper/solder bridge across the mask-to-mask interface at the rim
    terminal -> board k+1 L1 In pad (approved 2026-10-06: physical edge solder joint between the touching
    pads). The bridge spans EXACTLY from the board k L6 copper bottom face to the board k+1 L1 copper top face,
    so it touches both pads face-to-face; the boards are NOT united into one giant solid (v7.1 - the v7 united
    5 boards per phase and AEDT closed after > 2.5 h). Touching conductor objects form one conduction path.
    Raised external leads ONLY on the string ends (united with PCB1 / PCB N only). No star point."""
    cfg = ctx.cfg
    n = len(board_objs)
    stacks = dict((b["k"], board_stack(cfg, geo, b["k"])) for b in board_objs)
    hw = cfg.LEAD_WIDTH / 2.0
    out = {"phases": {}, "leads": {}, "bridges": {}, "strings": {}}
    for net in cfg.PHASES:
        tag = TAG[net]
        t_in, t_out = cfg.TERMINAL_MAP[net]["in"], cfg.TERMINAL_MAP[net]["out"]
        if (t_in[1], t_in[2]) != (t_out[1], t_out[2]):
            raise RuntimeError("%s: In/Out pads are not at the same XY - stacked boards would not meet" % net)
        x, y = t_in[1], t_in[2]
        sq = [[x - hw, y - hw], [x + hw, y - hw], [x + hw, y + hw], [x - hw, y + hw]]
        bridges = []
        for k in range(1, n):
            z_top = stacks[k]["layers"]["L6"][0]         # board k L6 copper, bottom face
            z_bot = stacks[k + 1]["layers"]["L1"][1]     # board k+1 L1 copper, top face
            if not z_bot < z_top:
                raise RuntimeError("bridge %s %d->%d has no height (boards overlap?)" % (net, k, k + 1))
            bridges.append(ctx.prism("Bridge%s_%d_%d" % (tag, k, k + 1), sq, z_bot, z_top, "copper", COLOR[net]))
        lg_top = lead_geometry(cfg, net, stacks[1]["layers"], y_end)       # start lead on board 1
        lg_bot = lead_geometry(cfg, net, stacks[n]["layers"], y_end)       # end lead on board N
        first = [b for b in board_objs if b["k"] == 1][0]["phases"][net]
        last = [b for b in board_objs if b["k"] == n][0]["phases"][net]
        sf = ctx.prism("Lead%s_start_foot" % tag, lg_top["in_foot"][0], lg_top["in_foot"][1], lg_top["in_foot"][2],
                       "copper", COLOR[net])
        sb = ctx.prism("Lead%s_start_bar" % tag, lg_top["in_bar"][0], lg_top["in_bar"][1], lg_top["in_bar"][2],
                       "copper", COLOR[net])
        ef = ctx.prism("Lead%s_end_foot" % tag, lg_bot["out_foot"][0], lg_bot["out_foot"][1], lg_bot["out_foot"][2],
                       "copper", COLOR[net])
        eb = ctx.prism("Lead%s_end_bar" % tag, lg_bot["out_bar"][0], lg_bot["out_bar"][1], lg_bot["out_bar"][2],
                       "copper", COLOR[net])
        first = ctx.unite([first, sf, sb])
        last = ctx.unite([last, ef, eb])
        string = [first] + [None] * (n - 2) + [last] if n > 1 else [first]
        for b in board_objs:
            if 1 < b["k"] < n:
                string[b["k"] - 1] = b["phases"][net]
        out["strings"][net] = {"boards": string, "bridges": bridges}
        out["phases"][net] = first           # object carrying the start terminal
        out["leads"][net] = {"face_in": lg_top["face_in"], "face_out": lg_bot["face_out"], "obj_in": first,
                             "obj_out": last, "r_inner": min(lg_top["r_inner"], lg_bot["r_inner"]),
                             "z_top": lg_top["z_top"]}
        out["bridges"][net] = len(bridges)
        ctx.log("Phase %s string: %s; %d bridges %.5f mm tall touching L6 Out / L1 In pad faces; start lead on "
                "PCB1 L1, end lead on PCB%d L6" % (tag, " -> ".join(string), len(bridges),
                                                     stacks[1]["layers"]["L6"][0] - stacks[2]["layers"]["L1"][1]
                                                     if n > 1 else 0.0, n))
    return out


def bridge_pad_check(geo, cfg):
    """[Py] every bridge footprint (LEAD_WIDTH square at the terminal) lies on the phase's own copper on L6
    (board k Out) and L1 (board k+1 In) and on no other phase's copper."""
    hw = cfg.LEAD_WIDTH / 2.0
    res = {}
    for net in cfg.PHASES:
        x, y = cfg.TERMINAL_MAP[net]["in"][1], cfg.TERMINAL_MAP[net]["in"][2]
        pts = [(x, y), (x - hw, y - hw), (x + hw, y - hw), (x + hw, y + hw), (x - hw, y + hw)]
        ok = True
        for L in ("L1", "L6"):
            for px, py in pts:
                own = any(_point_in_ring(px, py, r) for r in geo["layers"][L].get(net, []))
                other = any(_point_in_ring(px, py, r) for n2 in ("PHASE_A", "PHASE_B", "PHASE_C") if n2 != net
                            for r in geo["layers"][L].get(n2, []))
                if not own or other:
                    ok = False
        res[net] = ok
    return res
