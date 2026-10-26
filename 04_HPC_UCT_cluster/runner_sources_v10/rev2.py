# -*- coding: utf-8 -*-
"""Rev2-S final build: S1 - R1 - S2 - R2 - S3 - R3 (three stators, three single-sided rotors, 48 magnets).

The lab's final_build.py builds one or two stators. This extends its two-stator recipe (the Rev1-S one) to N stators
with the SAME helpers: S2..SN are exact copies of S1 moved along +Z (duplicate_stator), junction-probed (junction_probes),
every rotor is a Rev0 rotor (16 x N35, magnets toward its own stator, steel on the far side), all rotors aligned and on
one common 19 mm shaft, every stator's coil terminals added to the PhaseA/B/C windings (all stators in series).
Python 2.7 / IronPython compatible.
"""
import json
import os
import shutil

import build_pcb
import build_rotor
import final_build
import pcb_geometry
import setup_model
from aedt_api import StageError, mm
from setup_model import ROT_VAR
from stages import validate_geometry

TAGS = {"PHASE_A": "A", "PHASE_B": "B", "PHASE_C": "C"}


def add_terminals(ctx, geo, dz, y_end, k):
    """Coil terminals on stator k's lead ends (k >= 2), added to the existing PhaseX windings (series)."""
    cfg = ctx.cfg
    oB = ctx.design.GetModule("BoundarySetup")
    st1 = build_pcb.board_stack(cfg, geo, 1)
    stN = build_pcb.board_stack(cfg, geo, cfg.N_BOARDS)
    pre = "S%d_" % k
    out = {}
    for net in cfg.PHASES:
        t = TAGS[net]
        lg_top = build_pcb.lead_geometry(cfg, net, st1["layers"], y_end)
        lg_bot = build_pcb.lead_geometry(cfg, net, stN["layers"], y_end)
        terms = []
        for (fx, fy, fz), body, suffix, point_out in (
                (lg_top["face_in"], "%sPhase%s1_Cu" % (pre, t), "In", False),
                (lg_bot["face_out"], "%sPhase%s%d_Cu" % (pre, t, cfg.N_BOARDS), "Out", True)):
            fid = ctx.editor.GetFaceByPosition(["NAME:FaceParameters", "BodyName:=", body, "XPosition:=", mm(fx),
                                                "YPosition:=", mm(fy), "ZPosition:=", mm(fz + dz)])
            name = "Phase%s_S%d_%s" % (t, k, suffix)
            oB.AssignCoilTerminal(["NAME:" + name, "Faces:=", [int(fid)], "Conductor number:=", "1",
                                   "Point out of terminal:=", point_out])
            terms.append(name)
        oB.AddWindingTerminals("Phase%s" % t, terms)
        out[net] = terms
        ctx.log("Winding Phase%s: S%d terminals %s added (in series, same sense as S1)" % (t, k, terms))
    return out


def run(ctx, shared_dir):
    import transient
    cfg = ctx.cfg
    n_st = int(cfg.N_STAGES)
    if n_st < 3 or cfg.R1_DOUBLE:
        raise StageError("rev2.run builds single-sided S-R stacks with 3 or more stators")
    src = final_build.locate_frozen(cfg, shared_dir)
    dst = ctx.project_path()
    frozen_out = os.path.join(ctx.project_dir(), cfg.PROJECT_NAME + "_FROZEN.aedt")
    for p in (dst, frozen_out, os.path.splitext(dst)[0] + ".aedtresults"):
        if os.path.exists(p):
            raise StageError("%s already exists - final builds are never overwritten" % p)
    shutil.copyfile(src, dst)
    ctx.log("Copied frozen stator %s -> %s" % (src, dst))
    ctx.state = {"stages_done": [], "objects": {}, "profile": cfg.PROFILE, "source": src}
    ctx.project = ctx.desktop.OpenProject(dst)
    ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    ctx.attach_design()
    try:
        ctx.desktop.EnableAutoSave(False)
    except Exception:
        pass
    solids = final_build._solids(ctx)
    missing = [o for o in final_build.expected_stator_objects(cfg) if o not in solids]
    if missing:
        raise StageError("The copied project is not the 5-board frozen stator - missing %s" % missing[:6])
    stator_objs = [o for o in solids if o != "Region"]
    if "Region" in solids:
        ctx.editor.Delete(["NAME:Selections", "Selections:=", "Region"])

    geo = pcb_geometry.load()
    L = transient.levels(cfg)
    tops, dzs, geoms = L["stator_tops"], L["dz_list"], L["rotor_geoms"]
    y_end = max(p[1] for p in geo["outline"]) + cfg.REGION_PADDING
    problems = final_build.junction_probes(ctx, geo, 0.0, "")
    for k in range(2, n_st + 1):
        final_build.duplicate_stator(ctx, stator_objs, dzs[k - 2], prefix="S%d_" % k)
        problems += final_build.junction_probes(ctx, geo, dzs[k - 2], "S%d_" % k)
    shaft_top = L["shaft_top"]
    rotors = [build_rotor.build_rotor(ctx, tops[0], prefix="R1_", shaft=True, shaft_top=shaft_top)]
    for k in range(2, n_st + 1):
        rotors.append(build_rotor.build_rotor(ctx, tops[k - 1], prefix="R%d_" % k, make_cs=False, shaft=False))
    steel = ctx.rename(ctx.unite(sum([list(r["steel"]) for r in rotors], [])), "RotorSteel")
    ctx.log("Common shaft: %d rotor discs + 19 mm shaft united as %s" % (n_st, steel))
    mags = sum([list(r["magnets"]) for r in rotors], [])
    terms = {}
    for k in range(2, n_st + 1):
        terms["S%d" % k] = add_terminals(ctx, geo, dzs[k - 2], y_end, k)
    ctx.set_var(ROT_VAR, "0deg")
    ctx.editor.Rotate(["NAME:Selections", "Selections:=", ",".join(mags), "NewPartsModelFlag:=", "Model"],
                      ["NAME:RotateParameters", "RotateAxis:=", "Z", "RotateAngle:=", ROT_VAR])
    ctx.log("Rotor position: %d magnets rotated about +Z by %s" % (len(mags), ROT_VAR))
    setup_model.create_region(ctx, plus_y_zero=True)
    for k in range(n_st):
        gap = geoms[k]["zm0"] - tops[k]
        ctx.log("Acceptance: S%d top -> R%d magnet face = %.4f mm (target %.4f)" % (k + 1, k + 1, gap, cfg.AIR_GAP))
        if abs(gap - cfg.AIR_GAP) > 1e-6:
            problems.append("S%d air gap mismatch" % (k + 1))
        if k + 1 < n_st:
            clr = L["stator_bots"][k + 1] - geoms[k]["zb1"]
            ctx.log("Acceptance: R%d steel -> S%d bottom = %.4f mm" % (k + 1, k + 2, clr))
            if abs(clr - cfg.AIR_GAP) > 1e-6:
                problems.append("R%d -> S%d clearance mismatch" % (k + 1, k + 2))
    try:
        ok = validate_geometry(ctx, "Design")
    except StageError as e:
        ok = False
        problems.append(str(e))
    ctx.log("AEDT Validation Check returned %s" % ok)
    ctx.project.Save()
    ctx.save_state()
    if problems:
        raise StageError("; ".join(problems))
    shutil.copyfile(dst, frozen_out)
    with open(os.path.join(ctx.results_dir(), "final_build_manifest.json"), "w") as f:
        json.dump({"frozen_project": frozen_out, "source_stator": src, "stages": n_st,
                   "topology": "-".join("S%d-R%d" % (k, k) for k in range(1, n_st + 1)) + " (Rev2-S)",
                   "magnets": len(mags), "stator_offsets_mm": dzs, "stator_tops_mm": tops, "terminals": terms,
                   "air_gap_mm": cfg.AIR_GAP, "back_iron_mm": cfg.BACK_IRON_THICK, "star_point": "open"}, f, indent=1)
    with open(os.path.join(ctx.results_dir(), "run_complete.txt"), "w") as f:
        f.write("%s built, validated and frozen: %s\n" % (cfg.PROJECT_NAME, frozen_out))
    ctx.log("FINAL BUILD frozen: %s" % frozen_out)
