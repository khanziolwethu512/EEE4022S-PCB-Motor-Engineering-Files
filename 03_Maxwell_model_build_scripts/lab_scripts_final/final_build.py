# -*- coding: utf-8 -*-
"""REV0_FINAL / REV1_FINAL: complete validated build-only motor models made from a COPY of the frozen stator.

REV0_FINAL (N_STAGES = 1):  S1 - g - R1
    REV0_STATOR_FROZEN.aedt is copied (never opened for writing), the region is removed, the selected rotor is
    added at AIR_GAP above PCB1's top mask with BACK_IRON_THICK steel, the region is recreated (+Y face on the
    terminal lead ends), validated, saved and frozen as <PROJECT>_FROZEN.aedt.

REV1_FINAL (N_STAGES = 2):  S1 - g - R1 - g - S2 - g - R2          (spec locked 2026-10-07)
    S2 = exact copy of S1 translated along +Z (no rebuild; objects renamed S2_*). R1 and R2 are identical Rev0
    rotors (16 x N35 + steel back iron, magnets facing their own stator, back iron on the far side), same
    angular alignment (both rotated by the same rot_angle), one common 19 mm steel shaft through the S2 bore.
    R1's back iron faces S2's last board across the same clearance g. S1 and S2 in series per phase: S2's two
    coil terminals are added to the existing PhaseA/B/C windings (one current through both stators).
    Star point still open (12 lead ends exposed).

REV1D_FINAL (N_STAGES = 2, R1_DOUBLE = True):  S1 - g - [R1 face A | plate | R1 face B] - g - S2 - g - R2   (v9.4)
    48 magnets. R1 = Rev0 rotor (face A toward S1) with its plate LOWER_PLATE_THICK thick and a second 16-magnet face
    (R1B_*) on top of the plate, toward S2. "through" face relation: every magnet at a given angle has the same
    magnetisation vector (face A, face B and R2) -> opposite poles face each other across S2 and its axial field is
    the sum of both rotors. S2 terminals: S2_REVERSED selects the series polarity (to be set from the FEM phase).

No solver setup, no solve: these are the engineering geometry models. Quantitative results come from the
single-board FEM runs + board-by-board stack summation (stack_sum.py).
"""
import json
import os
import shutil

import build_pcb
import build_rotor
import pcb_geometry
import setup_model
from aedt_api import StageError, mm
from setup_model import ROT_VAR
from stages import validate_geometry

TAGS = {"PHASE_A": "A", "PHASE_B": "B", "PHASE_C": "C"}


def _solids(ctx):
    try:
        return [str(o) for o in ctx.editor.GetObjectsInGroup("Solids")]
    except Exception:
        return [str(o) for o in (ctx.objects_present() or [])]


def _bodies_at(ctx, x, y, z):
    try:
        return [str(b) for b in ctx.editor.GetBodyNamesByPosition(
            ["NAME:Parameters", "XPosition:=", mm(x), "YPosition:=", mm(y), "ZPosition:=", mm(z)])]
    except Exception:
        return None


def locate_frozen(cfg, shared_dir):
    cands = [os.path.join(shared_dir, "frozen", cfg.FROZEN_STATOR), os.path.join(cfg.SAVE_DIR, cfg.FROZEN_STATOR),
             os.path.join(r"D:\New folder", cfg.FROZEN_STATOR)]
    for c in cands:
        if os.path.isfile(c):
            return c
    raise StageError("Frozen stator %s not found. Put it in %s. Tried: %s"
                     % (cfg.FROZEN_STATOR, os.path.join(shared_dir, "frozen"), cands))


def expected_stator_objects(cfg, prefix=""):
    names = []
    for net in cfg.PHASES:
        t = TAGS[net]
        names += [prefix + "Phase%s%d_Cu" % (t, k) for k in range(1, cfg.N_BOARDS + 1)]
        names += [prefix + "Bridge%s_%d_%d" % (t, k, k + 1) for k in range(1, cfg.N_BOARDS)]
    return names


def junction_probes(ctx, geo, dz, prefix):
    """Same AEDT body probes as the stator build (board k L6 Out pad / bridge / board k+1 L1 In pad), at +dz."""
    cfg = ctx.cfg
    problems, n = [], 0
    st = dict((k, build_pcb.board_stack(cfg, geo, k)) for k in range(1, cfg.N_BOARDS + 1))
    for net in cfg.PHASES:
        t = TAGS[net]
        x, y = cfg.TERMINAL_MAP[net]["in"][1], cfg.TERMINAL_MAP[net]["in"][2]
        for k in range(1, cfg.N_BOARDS):
            L6, L1 = st[k]["layers"]["L6"], st[k + 1]["layers"]["L1"]
            for z, want in ((0.5 * (L6[0] + L6[1]), prefix + "Phase%s%d_Cu" % (t, k)),
                            (0.5 * (L6[0] + L1[1]), prefix + "Bridge%s_%d_%d" % (t, k, k + 1)),
                            (0.5 * (L1[0] + L1[1]), prefix + "Phase%s%d_Cu" % (t, k + 1))):
                got = _bodies_at(ctx, x, y, z + dz)
                if got is None:
                    ctx.log("GetBodyNamesByPosition not available - %sjunction probes skipped" % prefix, 1)
                    return []
                n += 1
                if want not in got:
                    problems.append("%s junction %s %d-%d: expected %s, AEDT reports %s" % (prefix or "S1", t, k, k + 1,
                                                                                          want, got))
    ctx.log("%s junction probes: %d checked, %d failed" % (prefix.rstrip("_") or "S1", n, len(problems)))
    return problems


def duplicate_stator(ctx, stator_objs, dz, prefix="S2_"):
    before = set(_solids(ctx))
    ctx.editor.DuplicateAlongLine(
        ["NAME:Selections", "Selections:=", ",".join(stator_objs), "NewPartsModelFlag:=", "Model"],
        ["NAME:DuplicateToAlongLineParameters", "CreateNewObjects:=", True, "XComponent:=", "0mm",
         "YComponent:=", "0mm", "ZComponent:=", mm(dz), "NumClones:=", "2"],
        ["NAME:Options", "DuplicateAssignments:=", False], ["CreateGroupsForNewObjects:=", False])
    new = [o for o in _solids(ctx) if o not in before]
    if len(new) != len(stator_objs):
        raise StageError("Stator duplication made %d objects, expected %d" % (len(new), len(stator_objs)))
    mapping = {}
    for o in new:
        src = sorted([s for s in stator_objs if o.startswith(s + "_") or o == s], key=len)
        if not src:
            raise StageError("Cannot match duplicated object %s to its original" % o)
        mapping[o] = src[-1]
    if len(set(mapping.values())) != len(stator_objs):
        raise StageError("Duplicated objects do not map one-to-one onto the stator objects")
    for o, s in mapping.items():
        ctx.rename(o, prefix + s)
    ctx.log("Stator S2: %d objects duplicated %.5f mm along +Z and renamed %s*" % (len(new), dz, prefix))
    return [prefix + s for s in stator_objs]


def add_s2_terminals(ctx, geo, dz, y_end):
    """Coil terminals on S2's lead ends, added to the existing PhaseX windings -> S1 and S2 in series."""
    cfg = ctx.cfg
    oB = ctx.design.GetModule("BoundarySetup")
    st1 = build_pcb.board_stack(cfg, geo, 1)
    stN = build_pcb.board_stack(cfg, geo, cfg.N_BOARDS)
    out = {}
    for net in cfg.PHASES:
        t = TAGS[net]
        lg_top = build_pcb.lead_geometry(cfg, net, st1["layers"], y_end)
        lg_bot = build_pcb.lead_geometry(cfg, net, stN["layers"], y_end)
        terms = []
        for (fx, fy, fz), body, suffix, point_out in (
                (lg_top["face_in"], "S2_Phase%s1_Cu" % t, "In", False),
                (lg_bot["face_out"], "S2_Phase%s%d_Cu" % (t, cfg.N_BOARDS), "Out", True)):
            fid = ctx.editor.GetFaceByPosition(["NAME:FaceParameters", "BodyName:=", body, "XPosition:=", mm(fx),
                                                "YPosition:=", mm(fy), "ZPosition:=", mm(fz + dz)])
            name = "Phase%s_S2_%s" % (t, suffix)
            oB.AssignCoilTerminal(["NAME:" + name, "Faces:=", [int(fid)], "Conductor number:=", "1",
                                   "Point out of terminal:=", point_out != bool(cfg.S2_REVERSED)])
            terms.append(name)
        oB.AddWindingTerminals("Phase%s" % t, terms)
        out[net] = terms
        ctx.log("Winding Phase%s: S2 terminals %s added (S1 and S2 in series, same current; S2 %s)"
                % (t, terms, "REVERSED" if cfg.S2_REVERSED else "same sense as S1"))
    return out


def run(ctx, shared_dir):
    cfg = ctx.cfg
    n_st = int(cfg.N_STAGES)
    if n_st not in (1, 2):
        raise StageError("N_STAGES must be 1 (Rev0) or 2 (Rev1)")
    if not cfg.UNITE_SHAFT_BACK_IRON and n_st == 2:
        raise StageError("REV1 common shaft assumes UNITE_SHAFT_BACK_IRON=True")
    src = locate_frozen(cfg, shared_dir)
    dst = ctx.project_path()
    frozen_out = os.path.join(ctx.project_dir(), cfg.PROJECT_NAME + "_FROZEN.aedt")
    for p in (dst, frozen_out, os.path.splitext(dst)[0] + ".aedtresults"):
        if os.path.exists(p):
            raise StageError("%s already exists - final builds are never overwritten. Delete/move it or change "
                             "PROJECT_NAME." % p)
    if not os.path.isdir(ctx.project_dir()):
        os.makedirs(ctx.project_dir())
    shutil.copyfile(src, dst)
    ctx.log("Copied frozen stator %s -> %s (the frozen file is never opened)" % (src, dst))
    ctx.state = {"stages_done": [], "objects": {}, "profile": cfg.PROFILE, "source": src}
    ctx.project = ctx.desktop.OpenProject(dst)
    ctx.design = ctx.project.SetActiveDesign(cfg.DESIGN_NAME)
    ctx.attach_design()
    try:
        ctx.desktop.EnableAutoSave(False)
    except Exception:
        pass
    for a in cfg.assumptions():
        ctx.log("ASSUMPTION: " + a)

    solids = _solids(ctx)
    need = expected_stator_objects(cfg)
    missing = [o for o in need if o not in solids]
    if missing:
        raise StageError("The copied project is not the 5-board frozen stator - missing %s" % missing[:6])
    stator_objs = [o for o in solids if o != "Region"]
    if "Region" in solids:
        ctx.editor.Delete(["NAME:Selections", "Selections:=", "Region"])
        ctx.log("Old stator-only region deleted (recreated around the full motor below)")

    geo = pcb_geometry.load()
    pitch = cfg.board_pitch()
    top1 = build_pcb.board_stack(cfg, geo, 1)["top_surface"]
    botN = build_pcb.board_stack(cfg, geo, cfg.N_BOARDS)["bottom_surface"]
    y_end = max(p[1] for p in geo["outline"]) + cfg.REGION_PADDING
    problems = junction_probes(ctx, geo, 0.0, "")
    levels = {"S1_top_surface": top1, "S1_bottom_surface": botN}
    mags = []
    if n_st == 1:
        r1 = build_rotor.build_rotor(ctx, top1)
        mags += r1["magnets"]
        levels.update({"R1_magnet_face": r1["geom"]["zm0"], "R1_backiron_top": r1["geom"]["zb1"]})
        rotors = {"R1": r1}
    else:
        double = bool(cfg.R1_DOUBLE)
        if double and cfg.R1_FACE_RELATION != "through":
            raise StageError("REV1D final build supports R1_FACE_RELATION='through' only (a mirrored face B would "
                             "also need R2 reversed)")
        bi_r2 = cfg.BACK_IRON_THICK
        if double:
            cfg.BACK_IRON_THICK = cfg.LOWER_PLATE_THICK   # R1's shared plate (restored below for R2)
        g1 = build_rotor.rotor_geometry(cfg, top1)
        r1_top = g1["zb1"] + (cfg.MAG_THICK if double else 0.0)   # R1's surface facing S2 (face-B magnets or steel)
        dz = (r1_top + cfg.AIR_GAP) - botN               # S2's last board sits g above R1's S2-facing surface
        top2 = top1 + dz
        s2 = duplicate_stator(ctx, stator_objs, dz)
        problems += junction_probes(ctx, geo, dz, "S2_")
        cfg.BACK_IRON_THICK = bi_r2
        g2 = build_rotor.rotor_geometry(cfg, top2)
        if double:
            cfg.BACK_IRON_THICK = cfg.LOWER_PLATE_THICK
        try:
            r1 = build_rotor.build_rotor(ctx, top1, prefix="R1_", shaft=True,
                                         shaft_top=g2["zb1"] + cfg.SHAFT_ABOVE_ROTOR)
        finally:
            cfg.BACK_IRON_THICK = bi_r2
        if double:
            r1b = build_rotor.magnet_array(ctx, g1["zb1"], "R1B_", flip=False)
            r1["magnets"] = list(r1["magnets"]) + r1b
            levels["R1B_magnet_face"] = r1_top
        r2 = build_rotor.build_rotor(ctx, top2, prefix="R2_", make_cs=False, shaft=False)
        steel = ctx.rename(ctx.unite(r1["steel"] + r2["steel"]), "RotorSteel")
        ctx.log("Common shaft: R1 disc + 19 mm shaft (through the S2 bore) + R2 disc united as %s" % steel)
        mags += r1["magnets"] + r2["magnets"]
        levels.update({"R1_magnet_face": g1["zm0"], "R1_backiron_top": g1["zb1"], "S2_bottom_surface": botN + dz,
                       "S2_top_surface": top2, "R2_magnet_face": g2["zm0"], "R2_backiron_top": g2["zb1"],
                       "S2_offset_dz": dz})
        rotors = {"R1": r1, "R2": r2}
        ctx.state["objects"]["s2_terminals"] = add_s2_terminals(ctx, geo, dz, y_end)
        ctx.state["objects"]["s2_objects"] = s2
        if abs((botN + dz) - r1_top - cfg.AIR_GAP) > 1e-6:
            problems.append("R1 -> S2 clearance mismatch")
        if abs(g2["zm0"] - top2 - cfg.AIR_GAP) > 1e-6:
            problems.append("S2 -> R2 air gap mismatch")
        if 12.5 - cfg.SHAFT_D / 2.0 < 0.5:
            problems.append("shaft too close to the 25 mm stator bore")

    # rotor position variable: all magnets of all rotors turn together (R2 aligned with R1)
    ctx.set_var(ROT_VAR, "0deg")
    ctx.editor.Rotate(["NAME:Selections", "Selections:=", ",".join(mags), "NewPartsModelFlag:=", "Model"],
                      ["NAME:RotateParameters", "RotateAxis:=", "Z", "RotateAngle:=", ROT_VAR])
    ctx.log("Rotor position: %d magnets rotated about +Z by %s (= 0 deg); back iron/shaft axisymmetric"
            % (len(mags), ROT_VAR))

    setup_model.create_region(ctx, plus_y_zero=True)
    ctx.log("Region recreated: padding %g mm, +Y face on the lead ends (all coil terminals on the boundary)"
            % cfg.REGION_PADDING)

    # acceptance
    gap = levels["R1_magnet_face"] - top1
    ctx.log("Acceptance: S1 top mask -> R1 magnet face = %.4f mm (target %.4f)" % (gap, cfg.AIR_GAP))
    if abs(gap - cfg.AIR_GAP) > 1e-6:
        problems.append("S1 air gap mismatch")
    r_lead = min(build_pcb.lead_geometry(cfg, n, build_pcb.board_stack(cfg, geo, 1)["layers"], y_end)["r_inner"]
                 for n in cfg.PHASES)
    r_parts = rotors["R1"]["geom"]["r_parts"]
    ctx.log("Acceptance: rotor parts r <= %.2f mm, terminal leads from r >= %.2f mm" % (r_parts, r_lead))
    if r_parts >= r_lead - 0.5:
        problems.append("rotor (r %.2f) too close to the terminal leads (r >= %.2f)" % (r_parts, r_lead))
    for k, v in sorted(levels.items(), key=lambda kv: kv[1]):
        ctx.log("Axial level %-20s z = %9.5f mm" % (k, v))
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
        json.dump({"frozen_project": frozen_out, "source_stator": src, "profile": cfg.PROFILE, "stages": n_st,
                   "topology": "S1-R1" if n_st == 1 else ("S1-R1(PM/Fe/PM)-S2-R2 (Rev1-D)" if cfg.R1_DOUBLE
                                                          else "S1-R1(PM/Fe)-S2-R2 (Rev1-S)"),
                   "magnets": cfg.POLES * (1 if n_st == 1 else (3 if cfg.R1_DOUBLE else 2)),
                   "r1_plate_mm": cfg.LOWER_PLATE_THICK if cfg.R1_DOUBLE else cfg.BACK_IRON_THICK,
                   "s2_series_polarity": None if n_st == 1 else ("reversed" if cfg.S2_REVERSED else
                                                                  "same sense as S1 (PROVISIONAL until the FEM phase check)"), "boards_per_stator": cfg.N_BOARDS,
                   "pitch_mm": pitch, "air_gap_mm": cfg.AIR_GAP, "back_iron_mm": cfg.BACK_IRON_THICK,
                   "magnet_centre_r_mm": cfg.MAG_CENTRE_R, "axial_levels_mm": levels,
                   "connection": "per phase S1 (5 boards series)" + ("" if n_st == 1 else " + S2 (5 boards) in series"),
                   "star_point": "open", "current_variables": ["I_%s" % TAGS[n] for n in cfg.PHASES],
                   "rotor_angle_variable": ROT_VAR, "assumptions": cfg.assumptions()}, f, indent=1)
    with open(os.path.join(ctx.results_dir(), "run_complete.txt"), "w") as f:
        f.write("%s built, validated and frozen: %s\n" % (cfg.PROJECT_NAME, frozen_out))
    ctx.log("FINAL BUILD frozen: %s (validated; star point open; currents I_A/I_B/I_C = 0 A; rotor angle %s)"
            % (frozen_out, ROT_VAR))
    # the frozen final model is a deliverable: also keep it in the shared (OneDrive) frozen folder, because the
    # local work folder of a lab PC may be wiped at logout
    try:
        shared_frozen = os.path.join(shared_dir, "frozen")
        if not os.path.isdir(shared_frozen):
            os.makedirs(shared_frozen)
        dst2 = os.path.join(shared_frozen, os.path.basename(frozen_out))
        if os.path.abspath(dst2) != os.path.abspath(frozen_out) and not os.path.exists(dst2):
            shutil.copyfile(frozen_out, dst2)
            ctx.log("Copy of the frozen final model kept in the shared folder: %s" % dst2)
    except Exception as e:
        ctx.log("Could not copy the frozen final model to the shared folder (%s) - copy %s by hand"
                % (e, frozen_out), 1)
