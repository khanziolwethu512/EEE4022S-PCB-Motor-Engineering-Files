"""Assemble dist/hpc_motor.py from maxwell/lab_scripts + the supervisor/inner sources in this folder + the PCB source package.
Run from anywhere: python maxwell/hpc/make_single_file.py  -> maxwell/hpc/dist/hpc_motor.py"""
import base64, csv, glob, hashlib, io, json, os, sys, tarfile
S = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.normpath(os.path.join(S, "..", "lab_scripts"))          # Maxwell pipeline modules (lab PCs)
REV0 = LAB
PKG = os.path.normpath(os.path.join(S, "..", "..", "hardware", "PCB_MAXWELL_SOURCE_PACKAGE"))
SKIP = {"main.py", "make_plots_v10.py", "make_traces_board.py", "check_traces_analytic.py", "make_single_file.py"}
files = {}
for p in sorted(glob.glob(os.path.join(REV0, "*.py"))):
    n = os.path.basename(p)
    if n.startswith("run_") or n in SKIP:
        continue
    files[n] = open(p, "rb").read()
for n in ("config.py", "fm_rotating.py", "eqcoil.py"):      # v10: config is a superset of rev0_v9's
    files[n] = open(os.path.join(LAB, n), "rb").read()
files["inner.py"] = open(os.path.join(S, "inner.py"), "rb").read()
files["transient.py"] = open(os.path.join(S, "transient.py"), "rb").read()
files["traces_board.json"] = open(os.path.join(REV0, "traces_board.json"), "rb").read()
refs = json.load(open(os.path.join(S, "references.json")))
r1s = refs["Rev1S"]
fm_b = dict((k, v) for k, v in r1s["fieldmap"]["boards"].items())
for k, v in r1s["fieldmap"]["boards"].items():
    if k.startswith("S2_"):
        fm_b["S3_" + k[3:]] = v
det_b = dict(r1s["detailed"]["boards"])
for k, v in r1s["detailed"]["boards"].items():
    if k.startswith("S2_"):
        det_b["S3_" + k] = None
        det_b["S3_" + k[3:]] = v
det_b = dict((k, v) for k, v in det_b.items() if v is not None)
s1 = r1s["fieldmap"]["stators"]["S1_PHASE_A"]["K1_mNm_per_A"]; s2 = r1s["fieldmap"]["stators"]["S2_PHASE_A"]["K1_mNm_per_A"]
refs["Rev2S"] = {"_note": "ESTIMATED, not solved: S1 = Rev1-S S1, S2 and S3 = Rev1-S S2 (both sit between a rotor's bare steel and the next rotor's magnets)",
                 "fieldmap": {"source": "estimated from FIELDMAP_REV1S_P20", "boards": fm_b,
                              "machine": {"PHASE_A": {"K1_mNm_per_A": round(s1 + 2 * s2, 4), "psi_deg": -30.08}}},
                 "detailed": {"note": "estimated from the Rev0 and REV1S_S2_J* single-board runs", "boards": det_b,
                              "machine_phaseA_K1_mNm_per_A": round(sum(v["K1_mNm_per_A"] for v in det_b.values()), 4)}}
print("Rev2-S estimated K: field map %.3f, detailed %.3f mN.m/A" % (refs["Rev2S"]["fieldmap"]["machine"]["PHASE_A"]["K1_mNm_per_A"], refs["Rev2S"]["detailed"]["machine_phaseA_K1_mNm_per_A"]))
files["references.json"] = json.dumps(refs, indent=1).encode()
files["rev2.py"] = open(os.path.join(S, "rev2.py"), "rb").read()
def rows(rel):
    with open(os.path.join(PKG, rel), newline="") as f:
        return list(csv.DictReader(f))
src = {"source": "PCB_MAXWELL_SOURCE_PACKAGE 07_NETLISTS / 09_MECHANICAL, Altium origin (100,100) moved to (0,0)",
       "vias": [{"net": r["net"], "x": round(float(r["x_mm"]) - 100, 5), "y": round(float(r["y_mm"]) - 100, 5)} for r in rows("07_NETLISTS/ALL_VIAS_WITH_NETS.csv")],
       "pads": [{"net": r["net"], "x": round(float(r["x_mm"]) - 100, 5), "y": round(float(r["y_mm"]) - 100, 5), "layer": r["layer"]} for r in rows("07_NETLISTS/ALL_EXTERNAL_PHASE_PADS.csv")],
       "npth": [{"x": round(float(r["x_mm"]) - 100, 5), "y": round(float(r["y_mm"]) - 100, 5)} for r in rows("09_MECHANICAL/NPTH_MECHANICAL_HOLE_POSITIONS.csv")]}
files["source_check.json"] = json.dumps(src).encode()
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tf:
    for n, data in sorted(files.items()):
        ti = tarfile.TarInfo(n); ti.size = len(data); ti.mtime = 1760140800; ti.mode = 0o644
        tf.addfile(ti, io.BytesIO(data))
data = buf.getvalue()
sha = hashlib.sha256(data).hexdigest()
b64 = base64.b64encode(data).decode()
b64 = "\n".join(b64[i:i + 120] for i in range(0, len(b64), 120))
tpl = open(os.path.join(S, "supervisor_template.py")).read()
out = tpl.replace("__PAYLOAD_SHA256__", sha).replace("__PAYLOAD_B64__", b64)
os.makedirs(os.path.join(S, "dist"), exist_ok=True)
dst = os.path.join(S, "dist", "hpc_motor.py")
open(dst, "w", newline="\n").write(out)
os.chmod(dst, 0o755)
print("wrote", dst, "%.0f kB" % (os.path.getsize(dst) / 1024), "payload files:", len(files), "sha", sha[:12])
