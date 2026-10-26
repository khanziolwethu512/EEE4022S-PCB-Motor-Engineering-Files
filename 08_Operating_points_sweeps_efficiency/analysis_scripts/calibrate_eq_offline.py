"""Offline equivalent-coil calibration from a saved eq_progress.json (no Ansys needed).

Used for Rev1-S on 18 Oct 2026: the HPC job solved 7 of the 8 rotor angles before the scratch quota corrupted the
project. Every torque obeys half-wave antisymmetry, T(theta + 22.5 deg) = -T(theta) (checked on the solved pairs:
worst mismatch 0.08 mN.m out of 7.3 mN.m), so the missing 39.375 deg angle is filled as -T(16.875 deg) and
eqcoil.calibrate() is run unchanged.

usage (from the repository root):
  python analysis/calibrate_eq_offline.py <eq_progress.json> <FIELDMAP_..._fieldmap_results.json> <profile> <out_dir>
  e.g. profile = EQ_REV1S_CAL, field map = results/rev1s/.../fieldmap_results.json
"""
import json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "maxwell", "lab_scripts"))
import config, eqcoil

prog_path, fm_path, profile, out = sys.argv[1:5]
p = json.load(open(prog_path))
done = p["done"]
period = 45.0                       # mechanical degrees per electrical period (16 poles)
half = period / 2.0
have = sorted(float(k) for k in done)
cfg0 = config.Config(profile, {})
for th in cfg0.FM_THETAS:
    if "%g" % th in done:
        continue
    src = "%g" % ((th - half) % period)
    if src not in done:
        sys.exit("cannot fill %g deg: %s deg not solved" % (th, src))
    done["%g" % th] = {"T": {k: -v for k, v in done[src]["T"].items()}, "note": "filled by antisymmetry from %s deg" % src}
    print("filled %g deg from -%s deg" % (th, src))
shared = os.path.join(out, "shared"); ref = os.path.join(shared, cfg0.FM_REF_PROJECT + "_results")
os.makedirs(ref, exist_ok=True); shutil.copy(fm_path, os.path.join(ref, "fieldmap_results.json"))
cfg = config.Config(profile, {"SAVE_DIR": out, "SHARED_RESULTS_DIR": shared})

class Ctx:
    def __init__(self, c): self.cfg = c
    def results_dir(self):
        d = os.path.join(out, cfg.PROJECT_NAME + "_results"); os.makedirs(d, exist_ok=True); return d
    def log(self, m, level=0): print(m)

eqcoil.calibrate(Ctx(cfg), p)
