# -*- coding: utf-8 -*-
"""
REV0 postprocess_ms.py - read the results out of an already-solved MAGNETOSTATIC project.
Runs no solve and makes no changes; the project is never saved.

AEDT: Tools > Run Script > postprocess_ms.py   (with no solver running)

Writes to <SAVE_DIR>/<PROJECT>_results/postprocess/:
  convergence.txt, profile.txt     - passes, tetrahedra, energy error, time and memory per pass
  ms_summary.csv                   - Ohmic loss per phase conductor, R = P / I^2, total magnetic energy
  postprocess_log.txt
"""
from __future__ import print_function

import os

PROJECT_PATH = r"D:\New folder\REV0_BOARD_3PH_MS_AIR.aedt"
DESIGN = "Rev0"
SETUP = "Setup1"
# DC currents the project was solved with (BOARD_3PH_MS / _AIR: A = 1 A, B = C = -0.5 A)
CURRENTS = {"A": 1.0, "B": -0.5, "C": -0.5}
COPPER_SIGMA = 5.8e7          # S/m, AEDT library "copper" (used only if Ohmic loss is not a named quantity)

try:
    oDesktop  # noqa: F821 - provided by AEDT
except NameError:
    import ScriptEnv
    ScriptEnv.Initialize("Ansoft.ElectronicsDesktop")
    import __main__
    oDesktop = __main__.oDesktop

NAME = os.path.splitext(os.path.basename(PROJECT_PATH))[0]
OUT = os.path.join(os.path.dirname(PROJECT_PATH), NAME + "_results", "postprocess")
if not os.path.isdir(OUT):
    os.makedirs(OUT)
_log = open(os.path.join(OUT, "postprocess_log.txt"), "w")


def log(msg, level=0):
    print(msg)
    _log.write(msg + "\n")
    _log.flush()
    try:
        oDesktop.AddMessage("", "", level, "[postprocess] " + msg)
    except Exception:
        pass


# ---------------------------------------------------------------- open (never save)
if NAME in [str(p) for p in oDesktop.GetProjectList()]:
    oProject = oDesktop.SetActiveProject(NAME)
else:
    oProject = oDesktop.OpenProject(PROJECT_PATH)
oDesign = oProject.SetActiveDesign(DESIGN)
log("Opened %s / %s" % (NAME, DESIGN))

oSol = oDesign.GetModule("Solutions")
try:
    sols = [str(s) for s in oSol.GetValidISolutionList()]
except Exception:
    sols = []
log("Valid solutions: %s" % (sols or "NONE"))

# ---------------------------------------------------------------- convergence + profile
oAS = oDesign.GetModule("AnalysisSetup")
for kind, fn, ext in (("convergence", "ExportConvergence", ".conv"), ("profile", "ExportProfile", ".prof")):
    done = None
    for mod in (oSol, oAS):
        for e in (ext, ".txt"):
            path = os.path.join(OUT, kind + e)
            for args in ((SETUP, "", path, True), (SETUP, "", path), (SETUP, path)):
                try:
                    getattr(mod, fn)(*args)
                    if os.path.isfile(path):
                        done = path
                        break
                except Exception:
                    pass
            if done:
                break
        if done:
            break
    log("%s -> %s" % (kind, done or "NOT available (right-click Setup1 > Convergence / Profile and screenshot)"),
        0 if done else 1)

sol = SETUP + " : LastAdaptive"
if sol not in sols:
    log("No '%s' solution stored - field values cannot be evaluated. Convergence/profile (if exported) "
        "are all that survived." % sol, 2)
    _log.close()
    raise SystemExit

# ---------------------------------------------------------------- field calculator
oF = oDesign.GetModule("FieldsReporter")
oEd = oDesign.SetActiveEditor("3D Modeler")


def evaluate(build):
    """build(): pushes one scalar onto the calculator stack. Returns float or None."""
    try:
        oF.CalcStack("clear")
        build()
        for args in ((sol, [], "Fields"), (sol, [])):
            try:
                oF.ClcEval(*args)
                break
            except Exception:
                continue
        v = oF.GetTopEntryValue(sol, [])
        oF.CalcStack("clear")
        return float(str(v[0]).split()[0])
    except Exception as e:
        log("  calculator step failed (%s)" % e, 1)
        try:
            oF.CalcStack("clear")
        except Exception:
            pass
        return None


def ohmic_named(obj, qty):
    def b():
        oF.EnterQty(qty)
        oF.EnterVol(obj)
        oF.CalcOp("Integrate")
    return b


def ohmic_from_j(obj):
    def b():
        oF.EnterQty("J")
        oF.CalcOp("Mag")
        oF.EnterScalar(2)
        oF.CalcOp("Pow")
        oF.EnterScalar(COPPER_SIGMA)
        oF.CalcOp("/")
        oF.EnterVol(obj)
        oF.CalcOp("Integrate")
    return b


def energy(vol):
    def b():
        oF.EnterQty("B")
        oF.EnterQty("H")
        oF.CalcOp("Dot")
        oF.EnterScalar(0.5)
        oF.CalcOp("*")
        oF.EnterVol(vol)
        oF.CalcOp("Integrate")
    return b


solids = [str(o) for o in oEd.GetObjectsInGroup("Solids")]
cu = sorted(o for o in solids if o.startswith("Phase") and o.endswith("_Cu"))
log("Phase conductors: %s" % cu)

rows = [("quantity", "object", "value", "unit", "method")]
for obj in cu:
    tag = obj[len("Phase")]
    P, how = None, None
    for qty in ("OhmicLoss", "Ohmic_Loss", "Ohmic-Loss"):   # AEDT 2025 R2 magnetostatic: OhmicLoss
        P = evaluate(ohmic_named(obj, qty))
        if P is not None:
            how = "integral of " + qty
            break
    if P is None:
        P = evaluate(ohmic_from_j(obj))
        how = "integral of |J|^2 / %.3g S/m" % COPPER_SIGMA
    if P is None:
        log("Ohmic loss for %s could not be evaluated" % obj, 1)
        continue
    rows.append(("OhmicLoss", obj, "%.6g" % P, "W", how))
    I = CURRENTS.get(tag)
    if I:
        R = P / (I * I)
        rows.append(("R=P/I^2", obj, "%.6g" % R, "ohm", "I = %g A" % I))
        log("%s: P = %.5g W (%s), I = %g A -> R = %.5f ohm" % (obj, P, how, I, R))

W = evaluate(energy("AllObjects"))
if W is not None:
    rows.append(("MagneticEnergy", "AllObjects", "%.6g" % W, "J", "0.5 * integral of B.H"))
    log("Total magnetic energy: %.5g J  (= 0.5 * I^T L I for I = %s)" % (W, CURRENTS))

csv = os.path.join(OUT, "ms_summary.csv")
with open(csv, "w") as f:
    for r in rows:
        f.write(",".join(r) + "\n")
log("Summary written: %s" % csv)
log("Done. Project NOT saved - close it with 'No' if AEDT asks.")
_log.close()
