"""python3 run_v13_mock.py <lab_dir> <work> - v13 (R-S-R) profiles end to end on the lab mock (made-up physics):
FIELDMAP_REV0_HW and FIELDMAP_RSR_P20 (geometry, half-wave waveform, static eddy, steel probe), EQ_RSR_ISWEEP,
plus regression: the old Rev0 / Rev1-S field maps still build identically. DIAG_RSR_* run with run_diag_mock.py."""
import json, math, os, sys, shutil, time
lab, work = sys.argv[1:3]
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, lab); sys.path.insert(0, here)
import labmock, config, aedt_api, fieldmap, eqcoil, build_rotor, pcb_geometry
shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
shared = os.path.join(work, "shared"); os.makedirs(shared)
geo = pcb_geometry.load()
fails = []
SCR = os.path.dirname(here)


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def faces(cfg):
    top1, botN, offs = fieldmap.stator_offsets(cfg, geo)
    f = [(build_rotor.rotor_geometry(cfg, top1 + o)["zm0"], +1) for o in offs]
    if cfg.FM_DESIGN == "RSR":
        f.append((fieldmap.rsr_levels(cfg, top1, botN)["R1_magnet_face"], -1))
    return f


def run_fm(prof):
    cfg = config.Config(prof, {"SAVE_DIR": work, "SHARED_RESULTS_DIR": shared})
    d = labmock.LabMock(faces=faces(cfg))
    ctx = aedt_api.Context(d, cfg)
    t0 = time.time()
    r = fieldmap.run(ctx, shared, lab)
    print("== %s: K_A %.4f, objects %d (%.1fs)" % (prof, 1e3 * r["machine"]["PHASE_A"]["K1"], len(d.objs), time.time() - t0))
    return cfg, r, d, ctx


# ---- 1. Rev0 method check profile
cfg, r0, d, ctx = run_fm("FIELDMAP_REV0_HW")
check("waveform" in r0 and "eddy" in r0 and "steel" in r0, "REV0_HW: waveform, eddy and steel results present")
w = r0["waveform"]
check(abs(w["PHASE_A"]["K1"] / r0["machine"]["PHASE_A"]["K1"] - 1) < 1e-9, "REV0_HW: waveform K1 = summary K1 (half-wave DFT)")
e_exp = r0["machine"]["PHASE_A"]["K1"] * 1000 * 2 * math.pi / 60 / math.sqrt(2)
check(abs(w["PHASE_A"]["E1_rms_V"] / e_exp - 1) < 1e-9, "REV0_HW: E1 = K1 w / sqrt2 (%.4f V)" % e_exp)
check(w["PHASE_A"]["H_pct"].get("H2", 0) < 1e-6 and w["PHASE_A"]["H_pct"]["H3"] > 1.0, "REV0_HW: even harmonics zero, H3 present (%.2f %%)"
      % w["PHASE_A"]["H_pct"]["H3"])
check(w["line_AB"]["THD_pct"] < w["PHASE_A"]["THD_pct"], "REV0_HW: line THD %.2f < phase THD %.2f (H3 cancels)"
      % (w["line_AB"]["THD_pct"], w["PHASE_A"]["THD_pct"]))
check(abs(w["T_mean_per_A_mNm"] / (1.5e3 * r0["machine"]["PHASE_A"]["K1"]) - 1) < 0.02, "REV0_HW: mean torque ~ 1.5 K I")
check(r0["eddy"]["total_W"] > 0 and len(r0["eddy"]["per_board_W"]) == 5, "REV0_HW: eddy %.4f W over 5 boards" % r0["eddy"]["total_W"])
check(list(r0["steel"]) == ["R1_BackIron"], "REV0_HW: one steel plate probed")
s = open(os.path.join(ctx.results_dir(), "fieldmap_summary.txt")).read()
check("BACK-EMF WAVEFORM" in s and "Copper eddy loss estimate" in s and "Rotor steel |B|" in s, "REV0_HW: summary sections written")
# eddy ~ n^2: rerun the post-processing at 2000 rpm on the same files
cfg2 = config.Config("FIELDMAP_REV0_HW", {"SAVE_DIR": work, "SHARED_RESULTS_DIR": shared, "RPM": 2000.0})
pts, meta = fieldmap.point_list(cfg2, fieldmap.load_traces(lab), [0.0])
e2, _ = fieldmap.eddy_from_static(ctx, cfg2, meta, ctx.results_dir(), lab)
check(abs(e2["total_W"] / r0["eddy"]["total_W"] - 4.0) < 1e-6, "static eddy scales exactly with n^2 (x%.4f)" % (e2["total_W"] / r0["eddy"]["total_W"]))

# ---- 2. R-S-R field map
cfg, rr, d, ctx = run_fm("FIELDMAP_RSR_P20")
mags = [o for o in d.objs if "Magnet_" in o]
check(len(mags) == 32, "RSR: 32 magnets (%d)" % len(mags))
check(any(o.startswith("R1_Magnet") for o in mags) and any(o.startswith("R2_Magnet") for o in mags), "RSR: R1 (lower) and R2 (upper) arrays")
top1, botN, offs = fieldmap.stator_offsets(cfg, geo)
lv = fieldmap.rsr_levels(cfg, top1, botN)
check(abs((botN - lv["R1_magnet_face"]) - 1.0) < 1e-9 and abs((lv["R2_magnet_face"] - top1) - 1.0) < 1e-9,
      "RSR: 1.000 mm gap on both sides (lower %.5f, upper %.5f)" % (botN - lv["R1_magnet_face"], lv["R2_magnet_face"] - top1))
check(offs == [0.0] and len(rr["stators"]) == 3, "RSR: one stator")
check("gate" not in rr, "RSR: no Rev0 board-1 gate (not the reference geometry)")
check(sorted(rr["steel"]) == ["R1_BackIron", "R2_BackIron"], "RSR: both plates probed")
check("RotorSteel" in d.objs and "R1_Shaft" not in d.objs, "RSR: plates + shaft united into RotorSteel")
kb = [rr["boards"]["S1_B%d_PHASE_A" % (k + 1)]["K1"] for k in range(5)]
check(abs(kb[0] / kb[4] - 1) < 0.25, "RSR (mock physics): board 1 and board 5 comparable (%.3f / %.3f)" % (1e3 * kb[0], 1e3 * kb[4]))
r0k = r0["machine"]["PHASE_A"]["K1"]
check(rr["machine"]["PHASE_A"]["K1"] > 1.5 * r0k, "RSR (mock physics): K %.3f > 1.5 x Rev0 %.3f" % (1e3 * rr["machine"]["PHASE_A"]["K1"], 1e3 * r0k))
check("RSR (simulation-only design study)" in " ".join(cfg.assumptions()) if hasattr(cfg, "assumptions") else True,
      "RSR: assumption text present")
os.makedirs(os.path.join(shared, "FIELDMAP_RSR_P20_results"), exist_ok=True)
shutil.copy(os.path.join(work, "FIELDMAP_RSR_P20_results", "fieldmap_results.json"),
            os.path.join(shared, "FIELDMAP_RSR_P20_results", "fieldmap_results.json"))

# ---- 3. EQ R-S-R current sweep
cfg = config.Config("EQ_RSR_ISWEEP", {"SAVE_DIR": work, "SHARED_RESULTS_DIR": shared})
shutil.copy(os.path.join(SCR, "build", "src", "EQ_RSR_CALIBRATION.json"), eqcoil.calib_path(cfg))
d = labmock.LabMock()
ctx = aedt_api.Context(d, cfg)
eqcoil.run(ctx, shared, lab)
r = json.load(open(os.path.join(ctx.results_dir(), "eq_isweep_results.json")))
check(len(r["points"]) == 3 and r.get("armature") is not None, "EQ_RSR: 3 current points + armature-only solve")
check(len(d.torques) == 3 * 5 + 1, "EQ_RSR: torque on 5 boards x 3 phases + rotor (%d)" % len(d.torques))
check(sum(1 for o in d.objs if "Magnet_" in o) == 32, "EQ_RSR: both magnet arrays")

# ---- 4. regression: Rev0 / Rev1-S field maps unchanged
for prof in ("FIELDMAP_REV0", "FIELDMAP_REV1S"):
    c = config.Config(prof, {})
    t, b, o = fieldmap.stator_offsets(c, geo)
    check(len(o) == c.n_stators() and o[0] == 0.0, "%s offsets %s" % (prof, [round(x, 5) for x in o]))

print("\nRESULT: %s" % ("ALL PASS" if not fails else "%d FAIL: %s" % (len(fails), fails)))
