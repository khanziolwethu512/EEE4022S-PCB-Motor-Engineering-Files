# -*- coding: utf-8 -*-
"""hpc_motor transient stages (run INSIDE AEDT through inner.py). Python 2.7 / IronPython compatible.

Formulation: Maxwell 3D Transient (T-Omega). A-Phi has no motion in AEDT 2025 R2. Prescribed speed (no mechanical
transient). One cylindrical faceted band per rotor: Rev0 one band, Rev1-S / Rev1-D two bands (bands may not touch,
with stationary space between them; each band is a solid faceted cylinder enclosing every part that moves with it).

Rev1 geometry change (the only one): the lab build unites R1 disc + shaft + R2 disc into one RotorSteel body that
passes through S2's bore, which would cross the stationary region between the bands. It is replaced by
R1_Steel (R1 disc + shaft stub inside band R1), R2_Steel (R2 disc + stub inside band R2) and a stationary shaft piece
in S2's bore with 0.25 mm axial gaps at each band face. All three are bodies of revolution, so their rotation does not
change the field; the equivalence is proven by a static solve (split vs united) before any transient run.
"""
from __future__ import print_function

import json
import math
import os
import re
import shutil
import time

FACETS = 144                  # 2.5 deg per facet (Ansys: 2-3 deg per facet for cylindrical bands)
SHAFT_GAP = 0.25              # mm, axial gap between moving shaft stubs and the stationary bore piece
MESH_LEVELS = [               # transient meshes are fixed: these length operations set the accuracy
    {"name": "MT0", "band": 1.0, "magnets": 1.5, "steel": 4.0},
    {"name": "MT1", "band": 0.7, "magnets": 1.0, "steel": 3.0},
    {"name": "MT2", "band": 0.5, "magnets": 0.8, "steel": 2.5},
]
TAGS = {"PHASE_A": "A", "PHASE_B": "B", "PHASE_C": "C"}


# ------------------------------------------------------------------------------------------- geometry (pure numbers)
def levels(cfg):
    """Axial levels exactly as the final builds make them (final_build.py for 1-2 stators, rev2.py for 3+), plus
    band extents and the shaft split. Rotor k sits above stator k; only R1 may be double-sided (Rev1-D)."""
    import build_pcb
    import build_rotor
    import pcb_geometry
    geo = pcb_geometry.load()
    top1 = build_pcb.board_stack(cfg, geo, 1)["top_surface"]
    botN = build_pcb.board_stack(cfg, geo, cfg.N_BOARDS)["bottom_surface"]
    g = float(cfg.AIR_GAP)
    n = int(cfg.N_STAGES)
    out = {"top1": top1, "botN": botN, "gap": g, "n_stators": n}
    if n == 1:
        g1 = build_rotor.rotor_geometry(cfg, top1)
        r = g1["r_parts"] + cfg.BAND_CLEARANCE
        out["bands"] = [{"name": "Band_R1", "z0": top1 + g / 2.0, "z1": g1["shaft_z1"] + 1.0, "r": r}]
        out["split"] = None
        out["r_parts"] = g1["r_parts"]
        out["steel_planes"] = [("BackIron", 0.5 * (g1["zm1"] + g1["zb1"]))]
        out.update({"stator_tops": [top1], "stator_bots": [botN], "dz_list": [], "rotor_geoms": [g1],
                    "shaft_top": g1["shaft_z1"]})
        return out
    double = bool(cfg.R1_DOUBLE)
    tops, bots, geoms, dzs = [top1], [botN], [], []
    bi = cfg.BACK_IRON_THICK
    for k in range(1, n + 1):
        dbl = double and k == 1
        if dbl:
            cfg.BACK_IRON_THICK = cfg.LOWER_PLATE_THICK
        try:
            gk = build_rotor.rotor_geometry(cfg, tops[k - 1])
        finally:
            cfg.BACK_IRON_THICK = bi
        geoms.append(gk)
        if k < n:
            rk_top = gk["zb1"] + (cfg.MAG_THICK if dbl else 0.0)
            dz = (rk_top + g) - botN
            dzs.append(dz)
            tops.append(top1 + dz)
            bots.append(botN + dz)
    shaft_top = geoms[-1]["zb1"] + cfg.SHAFT_ABOVE_ROTOR
    r_parts = max(x["r_parts"] for x in geoms)
    r = r_parts + cfg.BAND_CLEARANCE
    bands = []
    for k in range(1, n + 1):
        z1 = (bots[k] - g / 2.0) if k < n else shaft_top + 1.0
        bands.append({"name": "Band_R%d" % k, "z0": tops[k - 1] + g / 2.0, "z1": z1, "r": r})
    discs = [(x["zm1"], x["zb1"]) for x in geoms]
    stubs = []
    for k in range(1, n + 1):
        b = bands[k - 1]
        lo = geoms[0]["shaft_z0"] if k == 1 else b["z0"] + SHAFT_GAP
        hi = shaft_top if k == n else b["z1"] - SHAFT_GAP
        stubs.append((lo, hi))
    bores = [(bands[j]["z1"] + SHAFT_GAP, bands[j + 1]["z0"] - SHAFT_GAP) for j in range(n - 1)]
    split = {"discs": discs, "stubs": stubs, "bores": bores,
             "r1_disc": discs[0], "r2_disc": discs[1], "stub1": stubs[0], "mid": bores[0], "stub2": stubs[-1]
             if n == 2 else stubs[1]}
    planes = [("R1_Plate" if double else "R1_BackIron", 0.5 * (geoms[0]["zm1"] + geoms[0]["zb1"]))]
    planes += [("R%d_BackIron" % k, 0.5 * (geoms[k - 1]["zm1"] + geoms[k - 1]["zb1"])) for k in range(2, n + 1)]
    out.update({"dz": dzs[0], "top2": tops[1], "s2_bot": bots[1], "r_parts": r_parts, "bands": bands,
                "split": split, "steel_planes": planes, "stator_tops": tops, "stator_bots": bots, "dz_list": dzs,
                "rotor_geoms": geoms, "shaft_top": shaft_top})
    return out


def steel_points(L):
    """Mid-thickness planes of every rotor steel disc, r 2..42.5 mm, 2 deg."""
    grid = polar_grid(2.0, 42.5, 1.0, 2.0)
    return [(nm, [(x, y, z) for x, y in grid]) for nm, z in L["steel_planes"]]


def bstats(rows):
    # points outside the solved objects come back as NaN from the field export - skip them
    mags = sorted(m for m in (math.sqrt(r[3] ** 2 + r[4] ** 2 + r[5] ** 2) for r in rows) if m == m and m != float("inf"))
    if not mags:
        return None
    return {"max_T": mags[-1], "p99_T": mags[int(0.99 * (len(mags) - 1))], "mean_T": sum(mags) / len(mags),
            "points": len(mags), "frac_above_1p6T": sum(1 for m in mags if m > 1.6) / float(len(mags))}


def check_levels(cfg, L):
    """Clearances the Ansys band rules need, checked before anything is built."""
    import build_pcb
    import pcb_geometry
    geo = pcb_geometry.load()
    y_end = max(p[1] for p in geo["outline"]) + cfg.REGION_PADDING
    st1 = build_pcb.board_stack(cfg, geo, 1)
    r_lead = min(build_pcb.lead_geometry(cfg, n, st1["layers"], y_end)["r_inner"] for n in cfg.PHASES)
    problems, notes = [], []
    for b in L["bands"]:
        if b["r"] >= r_lead - 0.2:
            problems.append("%s radius %.2f mm reaches the terminal leads (r >= %.2f mm)" % (b["name"], b["r"], r_lead))
        if b["r"] - L["r_parts"] < 0.3:
            problems.append("%s encloses the rotor with only %.2f mm radial clearance" % (b["name"], b["r"] - L["r_parts"]))
        notes.append("%s: r %.2f mm (rotor parts to %.2f, leads from %.2f), z %.5f..%.5f mm"
                     % (b["name"], b["r"], L["r_parts"], r_lead, b["z0"], b["z1"]))
    bands = L["bands"]
    for j in range(len(bands) - 1):
        b1, b2 = bands[j], bands[j + 1]
        if b2["z0"] - b1["z1"] <= 0.5:
            problems.append("bands %s/%s too close (%.3f mm stationary space)" % (b1["name"], b2["name"], b2["z0"] - b1["z1"]))
        notes.append("stationary space between %s and %s: %.5f..%.5f mm (S%d %.5f..%.5f)"
                     % (b1["name"], b2["name"], b1["z1"], b2["z0"], j + 2, L["stator_bots"][j + 1], L["stator_tops"][j + 1]))
    sp = L["split"]
    if sp:
        for nm, (a_, c_) in [("stub%d" % (i + 1), x) for i, x in enumerate(sp["stubs"])] + \
                [("bore%d" % (i + 2), x) for i, x in enumerate(sp["bores"])]:
            if c_ - a_ <= 0.2:
                problems.append("shaft piece %s too short (%.3f mm)" % (nm, c_ - a_))
        if cfg.SHAFT_D / 2.0 >= 12.5 - 0.5:
            problems.append("shaft too close to the 25 mm stator bore")
        notes.append("shaft split: " + ", ".join(["stub%d %.3f..%.3f (moves with R%d)" % (i + 1, x[0], x[1], i + 1)
                                                  for i, x in enumerate(sp["stubs"])] +
                                                 ["bore piece in S%d %.3f..%.3f (stationary)" % (i + 2, x[0], x[1])
                                                  for i, x in enumerate(sp["bores"])]))
    return problems, notes


# ------------------------------------------------------------------------------------------- model edits
def split_rotor_steel(ctx, cfg, L):
    """Rev1 / Rev2: replace the united RotorSteel by R<k>_Steel (disc + shaft stub, moves with band k) and
    Shaft_S<j>bore (stationary, in stator j's bore). All are bodies of revolution."""
    sp = L["split"]
    if not sp:
        return None
    ed = ctx.editor
    try:
        solids = [str(o) for o in ed.GetObjectsInGroup("Solids")]
    except Exception:
        solids = [str(o) for o in (ctx.objects_present() or [])]
    if "RotorSteel" not in solids:
        raise RuntimeError("RotorSteel not found - not a lab final build")
    ed.Delete(["NAME:Selections", "Selections:=", "RotorSteel"])
    R, rs = cfg.BACK_IRON_OD / 2.0, cfg.SHAFT_D / 2.0
    mat, col = cfg.BACK_IRON_MATERIAL, "(110 110 110)"
    moving, stationary, txt = {}, [], []
    for k, ((d0, d1), (s0, s1)) in enumerate(zip(sp["discs"], sp["stubs"])):
        k += 1
        d = ctx.cylinder("R%d_Disc" % k, 0, 0, d0, d1 - d0, R, mat, col)
        st = ctx.cylinder("R%d_ShaftStub" % k, 0, 0, s0, s1 - s0, rs, mat, col)
        moving["Band_R%d" % k] = [ctx.rename(ctx.unite([d, st]), "R%d_Steel" % k)]
        txt.append("R%d_Steel (disc %.3f..%.3f + stub %.3f..%.3f)" % (k, d0, d1, s0, s1))
    for j, (b0, b1) in enumerate(sp["bores"]):
        nm = ctx.cylinder("Shaft_S%dbore" % (j + 2), 0, 0, b0, b1 - b0, rs, mat, col)
        stationary.append(nm)
        txt.append("stationary %s %.3f..%.3f" % (nm, b0, b1))
    ctx.log("Rotor steel split for %d bands: %s (bodies of revolution)" % (len(sp["discs"]), "; ".join(txt)))
    return {"moving": moving, "stationary": stationary}


def magnets_by_band(solids, L):
    """Rev0: all magnets in Band_R1. Otherwise R1_* and R1B_* in Band_R1, R<k>_* in Band_R<k>."""
    mags = sorted(o for o in solids if "Magnet_" in o)
    if len(L["bands"]) == 1:
        return {"Band_R1": mags}
    out = {"Band_R1": [m for m in mags if m.startswith("R1_") or m.startswith("R1B_")]}
    for k in range(2, len(L["bands"]) + 1):
        out["Band_R%d" % k] = [m for m in mags if m.startswith("R%d_" % k)]
    return out


def set_solution_transient(ctx):
    d = ctx.design
    err = None
    for args in ((["NAME:Options", "EnableMissingSourceCheck:=", False],), ()):
        try:
            d.SetSolutionType("Transient", *args)
            err = None
            break
        except Exception as e:
            err = e
    if err is not None:
        raise RuntimeError("Could not switch the design to Transient (%s)" % err)
    try:
        st = str(d.GetSolutionType())
        if "transient" not in st.lower():
            raise RuntimeError("Solution type is %s after switching to Transient" % st)
    except AttributeError:
        pass
    ctx.log("Design solution type: Transient (T-Omega)")


def add_bands(ctx, cfg, L, rpm):
    names = []
    oM = ctx.design.GetModule("ModelSetup")
    for b in L["bands"]:
        n = ctx.cylinder(b["name"], 0, 0, b["z0"], b["z1"] - b["z0"], b["r"], "vacuum", "(128 255 255)", FACETS, 0.9)
        oM.AssignBand(["NAME:Data", "Move Type:=", "Rotate", "Coordinate System:=", "Global", "Axis:=", "Z",
                       "Is Positive:=", True, "InitPos:=", "0deg", "HasRotateLimit:=", False, "NonCylindrical:=", False,
                       "Consider Mechanical Transient:=", False, "Angular Velocity:=", "%grpm" % rpm, "Objects:=", [n]])
        names.append(n)
        ctx.log("Motion: %s (%d facets, r %.2f mm, z %.5f..%.5f) rotates about +Z at %g rpm, initial position 0 deg"
                % (n, FACETS, b["r"], b["z0"], b["z1"], rpm))
    return names


def set_windings(ctx, cfg, psi_deg, n_stators):
    """Synchronous sinusoidal currents: I_X = Ipk*cos(2*pi*fe*Time + (-psi + PHASE_DEG[X]) deg), the time form of the
    static sweep's I_X = Ipk*cos(p*theta - psi + PHASE_DEG[X]) with theta = omega_m * t."""
    oB = ctx.design.GetModule("BoundarySetup")
    out = {}
    for net in cfg.PHASES:
        t = TAGS[net]
        w = "Phase%s" % t
        ang = -psi_deg + cfg.PHASE_DEG[net]
        cur = "Ipk*cos(2*pi*fe*Time + (%.6f)*pi/180)" % ang
        args = ["NAME:" + w, "Type:=", "Current", "IsSolid:=", True, "Current:=", cur, "Resistance:=", "0ohm",
                "Inductance:=", "0nH", "Voltage:=", "0mV", "ParallelBranchesNum:=", "1", "Phase:=", "0deg"]
        how = None
        try:
            oB.EditWindingGroup(w, args)
            how = "edited"
        except Exception as e1:
            terms = ["Phase%s_In" % t, "Phase%s_Out" % t]
            for k in range(2, n_stators + 1):
                terms += ["Phase%s_S%d_In" % (t, k), "Phase%s_S%d_Out" % (t, k)]
            try:
                oB.DeleteBoundaries([w])
            except Exception:
                pass
            oB.AssignWindingGroup(args)
            oB.AddWindingTerminals(w, terms)
            how = "re-created with terminals %s (edit failed: %s)" % (terms, e1)
        out[w] = cur
        ctx.log("Winding %s %s: current %s" % (w, how, cur))
    return out


def set_eddy(ctx, copper, magnets, steel):
    import setup_model
    setup_model.set_eddy(ctx, copper, True, "stator copper (solid conductors)")
    setup_model.set_eddy(ctx, magnets, True, "magnets")
    setup_model.set_eddy(ctx, steel, False, "rotor steel (turns with the field; ~DC flux)")


def mesh_ops(ctx, level, bands, magnets, steel):
    m = ctx.design.GetModule("MeshSetup")
    for name in ("TR_Len_Band", "TR_Len_Magnets", "TR_Len_Steel"):
        try:
            m.DeleteOp([name])
        except Exception:
            pass
    for name, objs, Lmax in (("TR_Len_Band", bands, level["band"]), ("TR_Len_Magnets", magnets, level["magnets"]),
                             ("TR_Len_Steel", steel, level["steel"])):
        if objs:
            m.AssignLengthOp(["NAME:" + name, "RefineInside:=", True, "Enabled:=", True, "Objects:=", list(objs),
                              "RestrictElem:=", False, "NumMaxElem:=", "1000", "RestrictLength:=", True,
                              "MaxLength:=", "%.6fmm" % Lmax])
    ctx.log("Transient mesh %s: band %.2f mm, magnets %.2f mm, steel %.2f mm (inside selection)"
            % (level["name"], level["band"], level["magnets"], level["steel"]))


def transient_setup(ctx, stop_ms, step_ms, save_every):
    oA = ctx.design.GetModule("AnalysisSetup")
    try:
        for s in [str(x) for x in oA.GetSetups()]:
            oA.DeleteSetups([s])
    except Exception:
        pass
    args = ["NAME:Setup1", "Enabled:=", True, ["NAME:MeshLink", "ImportMesh:=", False],
            "NonlinearSolverResidual:=", "0.005", "TimeIntegrationMethod:=", 0,
            "StopTime:=", "%.9gms" % stop_ms, "TimeStep:=", "%.9gms" % step_ms, "OutputError:=", False,
            "UseControlProgram:=", False, "ControlProgramName:=", " ", "ControlProgramArg:=", " ",
            "CallCtrlProgAfterLastStep:=", False, "FastReachSteadyState:=", False,
            "AutoDetectSteadyState:=", False, "IsGeneralTransient:=", True, "IsHalfPeriodicTransient:=", False] + (
        ["SaveFieldsType:=", "Every N Steps", "N Steps:=", str(int(save_every)), "Steps From:=", "0ms",
         "Steps To:=", "%.9gms" % stop_ms] if save_every else ["SaveFieldsType:=", "None"]) + [
            "UseNonLinearIterNum:=", False, "CacheSaveKind:=", "Count", "NumberSolveSteps:=", 1,
            "RangeStart:=", "0s", "RangeEnd:=", "0.1s"]
    oA.InsertSetup("Transient", args)
    ctx.log("Transient setup: stop %.6f ms, step %.6f ms (%d steps), fields %s"
            % (stop_ms, step_ms, int(round(stop_ms / step_ms)), ("every %d steps" % save_every) if save_every else "not saved"))


def reports(ctx, n_bands, torque_names, windings):
    oR = ctx.design.GetModule("ReportSetup")
    ws = sorted(windings)
    moving = ["Moving%d.Torque" % (i + 1) for i in range(n_bands)]
    defs = [("TR_Torque", moving + ["%s.Torque" % t for t in torque_names], True),
            ("TR_BackEMF", ["InducedVoltage(%s)" % w for w in ws], True),
            ("TR_Current", ["Current(%s)" % w for w in ws], False),
            ("TR_Flux", ["FluxLinkage(%s)" % w for w in ws], False),
            ("TR_Loss", ["SolidLoss"], False),
            ("TR_Position", ["Moving%d.Position" % (i + 1) for i in range(n_bands)], False)]
    made, missing = [], []
    for name, ys, req in defs:
        try:
            oR.CreateReport(name, "Transient", "Rectangular Plot", "Setup1 : Transient", ["Domain:=", "Sweep"],
                            ["Time:=", ["All"]], ["X Component:=", "Time", "Y Component:=", ys])
            made.append(name)
        except Exception as e:
            if req:
                missing.append("%s (%s)" % (name, e))
            else:
                ctx.log("Optional report %s not created (%s)" % (name, e), 1)
    if missing:
        raise RuntimeError("Required transient reports could not be created: %s" % "; ".join(missing))
    ctx.log("Transient reports: %s" % ", ".join(made))
    return made


# ------------------------------------------------------------------------------------------- results
_PREFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "meg": 1e6, "M": 1e6}
_BASES = ["newtonmeter", "wb", "v", "a", "w", "s", "deg", "rad", "ohm", "h", "t"]


def unit_scale(header):
    m = re.search(r"\[([^\]]+)\]", header)
    if not m:
        return 1.0
    u = m.group(1).strip().replace(" ", "")
    low = u.lower()
    if low == "rad":
        return 180.0 / math.pi
    for b in sorted(_BASES, key=len, reverse=True):
        if low.endswith(b):
            pre = u[:len(u) - len(b)]
            if pre in ("M",):
                return 1e6
            return _PREFIX.get(pre.lower() if pre != "M" else pre, 1.0) if pre.lower() != "meg" else 1e6
    return 1.0


def read_csv(path):
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip()]
    head = [h.strip().strip('"') for h in lines[0].split(",")]
    names = [h.split("[")[0].strip() for h in head]
    scale = [unit_scale(h) for h in head]
    cols = dict((n, []) for n in names)
    for row in lines[1:]:
        v = row.split(",")
        for i, n in enumerate(names):
            try:
                cols[n].append(float(v[i]) * scale[i])
            except (ValueError, IndexError):
                cols[n].append(float("nan"))
    return cols


def export_reports(ctx, rdir, made):
    oR = ctx.design.GetModule("ReportSetup")
    data = {}
    for name in made:
        p = os.path.join(rdir, name + ".csv")
        try:
            oR.ExportToFile(name, p)
            c = read_csv(p)
            for k, v in c.items():
                if k.lower().startswith("time"):
                    data["time_s"] = v
                else:
                    data[k] = v
        except Exception as e:
            ctx.log("Report %s not exported (%s)" % (name, e), 1)
    return data


def polar_grid(r0, r1, dr, dth):
    pts = []
    r = r0
    while r <= r1 + 1e-9:
        a = 0.0
        while a < 360.0 - 1e-9:
            pts.append((r * math.cos(math.radians(a)), r * math.sin(math.radians(a))))
            a += dth
        r += dr
    return pts


def export_fields(ctx, cfg, L, rdir, times_ms, with_J, code_dir):
    """|B| maps at mid-gap and J on board-1 trace centre-lines at the saved time steps (point files, readable by the
    animation helper). Uses the lab's field-export variants (fieldmap.py)."""
    import fieldmap
    oF = ctx.design.GetModule("FieldsReporter")
    planes = [("S1", L["top1"] + L["gap"] / 2.0)]
    for k in range(2, len(L.get("stator_tops", [])) + 1):
        planes += [("S%dlow" % k, L["stator_bots"][k - 1] - L["gap"] / 2.0),
                   ("S%dup" % k, L["stator_tops"][k - 1] + L["gap"] / 2.0)]
    grid = polar_grid(14.0, 44.0, 1.0, 2.0)
    files = []
    variant = None
    tfmt = None

    def one(qty, pts_path, out, t_ms):
        oF.CalcStack("clear")
        oF.EnterQty(qty)
        oF.ExportToFile(out, pts_path, "Setup1 : Transient", ["Time:=", tfmt(t_ms)],
                        ["NAME:ExportOption", "IncludePtInOutput:=", True, "RefCSName:=", "Global",
                         "PtInSI:=", variant[2], "FieldInRefCS:=", False])
        oF.CalcStack("clear")

    # find the point-file variant and the time format that AEDT accepts, on the first time
    probe = [(x, y, planes[0][1]) for x, y in grid[::300]][:20]
    for v in fieldmap.EXPORT_VARIANTS:
        for f in (lambda t: "%.9gms" % t, lambda t: "%.12gs" % (t * 1e-3)):
            pp = os.path.join(rdir, "probe.pts")
            out = os.path.join(rdir, "probe.fld")
            try:
                fieldmap.write_points(pp, probe, v[0], v[1])
                variant, tfmt = v, f
                one("B", pp, out, times_ms[0])
                rows = fieldmap.read_fld(out)
                if len(rows) == len(probe):
                    break
            except Exception:
                pass
            variant = None
        if variant:
            break
    if not variant:
        ctx.log("Field export: no point-file/time variant accepted - fields not exported", 1)
        return []
    sets = [("B_%s" % nm, [(x, y, z) for x, y in grid]) for nm, z in planes]
    sets += [("Bsteel_%s" % nm, pts) for nm, pts in steel_points(L)]
    if with_J:
        try:
            T = fieldmap.load_traces(code_dir)
            zc = T["_meta"]["z_layer_board1_mm"]
            pts = []
            for ph in ("PHASE_A", "PHASE_B", "PHASE_C"):
                for Lr, x0, y0, x1, y1, I in T[ph]["tracks"]:
                    pts.append((0.5 * (x0 + x1), 0.5 * (y0 + y1), zc[Lr]))
            sets.append(("J_S1PCB1", pts))
        except Exception as e:
            ctx.log("J export skipped (%s)" % e, 1)
    for nm, pts in sets:
        pp = os.path.join(rdir, nm + ".pts")
        fieldmap.write_points(pp, pts, variant[0], variant[1])
        for t in times_ms:
            out = os.path.join(rdir, "%s_t%08.4fms.fld" % (nm, t))
            try:
                one("J" if nm.startswith("J_") else "B", pp, out, t)
                files.append(os.path.basename(out))
            except Exception as e:
                ctx.log("Field export %s at %.4f ms failed (%s)" % (nm, t, e), 1)
    ctx.log("Field export: %d files (%s)" % (len(files), ", ".join(nm for nm, _ in sets)))
    return files
