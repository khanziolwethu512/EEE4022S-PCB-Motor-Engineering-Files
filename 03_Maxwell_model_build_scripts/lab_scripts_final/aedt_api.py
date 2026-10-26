# -*- coding: utf-8 -*-
"""Thin wrappers around the native AEDT scripting API (recorded-script syntax) + run context."""
import json
import os
import time


def attach_desktop(main_globals):
    if "oDesktop" in main_globals:
        return main_globals["oDesktop"]
    try:
        import ScriptEnv  # inside AEDT (Tools > Run Script)
        ScriptEnv.Initialize("Ansoft.ElectronicsDesktop")
        import __main__
        return __main__.oDesktop
    except Exception:
        pass
    from ansys.aedt.core import Desktop  # outside AEDT: pip install pyaedt
    return Desktop(new_desktop=False, non_graphical=False, close_on_exit=False).odesktop


def mm(v):
    return "%.6fmm" % v


class StageError(Exception):
    pass


class Context(object):
    """Everything a stage needs: AEDT handles, config, persistent state, logging."""

    def __init__(self, desktop, cfg):
        self.desktop = desktop
        self.cfg = cfg
        self.project = None
        self.design = None
        self.editor = None
        self.state = {"stages_done": [], "objects": {}}
        self.t0 = time.time()
        self._ready = False

    # ----------------------------------------------------------------- logging
    def log(self, msg, level=0):
        line = "[REV0 %s %6.1fs] %s" % (self.cfg.PROFILE, time.time() - self.t0, msg)
        print(line)
        tgt = (self.cfg.PROJECT_NAME, self.cfg.DESIGN_NAME) if self._ready else ("", "")
        try:
            self.desktop.AddMessage(tgt[0], tgt[1], level, line)
        except Exception:
            pass
        try:
            with open(self.log_path(), "a") as f:
                f.write(line + "\n")
        except Exception:
            pass

    # ----------------------------------------------------------------- paths / state
    def project_dir(self):
        return self.cfg.SAVE_DIR or self.desktop.GetProjectDirectory()

    def project_path(self):
        return os.path.join(self.project_dir(), self.cfg.PROJECT_NAME + ".aedt")

    def results_dir(self):
        d = self.cfg.EXPORT_DIR or os.path.join(self.project_dir(), self.cfg.PROJECT_NAME + "_results")
        if not os.path.isdir(d):
            try:
                os.makedirs(d)
            except Exception:
                pass
        return d

    def log_path(self):
        return os.path.join(self.results_dir(), "rev0_run_log.txt")

    def state_path(self):
        return os.path.join(self.results_dir(), "rev0_state.json")

    def save_state(self):
        with open(self.state_path(), "w") as f:
            json.dump(self.state, f, indent=1, sort_keys=True)

    def load_state(self):
        if os.path.isfile(self.state_path()):
            with open(self.state_path()) as f:
                self.state = json.load(f)
        return self.state

    def attach_design(self):
        self.editor = self.design.SetActiveEditor("3D Modeler")
        self._ready = True

    # ----------------------------------------------------------------- geometry helpers
    def attrs(self, name, material, color="(255 128 64)", transparency=0.0, nonmodel=False):
        return ["NAME:Attributes", "Name:=", name, "Flags:=", "NonModel#" if nonmodel else "", "Color:=", color,
                "Transparency:=", transparency, "PartCoordinateSystem:=", "Global", "UDMId:=", "",
                "MaterialValue:=", "\"%s\"" % material, "SurfaceMaterialValue:=", "\"\"",
                "SolveInside:=", True, "ShellElement:=", False, "ShellElementThickness:=", "0mm",
                "IsMaterialEditable:=", True, "UseMaterialAppearance:=", False, "IsLightweight:=", False]

    def polygon_sheet(self, name, pts, z, material, color="(255 128 64)", transparency=0.0):
        P = ["NAME:PolylinePoints"]
        for x, y in list(pts) + [pts[0]]:
            P.append(["NAME:PLPoint", "X:=", mm(x), "Y:=", mm(y), "Z:=", mm(z)])
        S = ["NAME:PolylineSegments"]
        for i in range(len(pts)):
            S.append(["NAME:PLSegment", "SegmentType:=", "Line", "StartIndex:=", i, "NoOfPoints:=", 2])
        X = ["NAME:PolylineXSection", "XSectionType:=", "None", "XSectionOrient:=", "Auto",
             "XSectionWidth:=", "0mm", "XSectionTopWidth:=", "0mm", "XSectionHeight:=", "0mm",
             "XSectionNumSegments:=", "0", "XSectionBendType:=", "Corner"]
        return self.editor.CreatePolyline(
            ["NAME:PolylineParameters", "IsPolylineCovered:=", True, "IsPolylineClosed:=", True, P, S, X],
            self.attrs(name, material, color, transparency))

    def sweep_z(self, names, dz):
        for i in range(0, len(names), 60):
            self.editor.SweepAlongVector(
                ["NAME:Selections", "Selections:=", ",".join(names[i:i + 60]), "NewPartsModelFlag:=", "Model"],
                ["NAME:VectorSweepParameters", "DraftAngle:=", "0deg", "DraftType:=", "Round",
                 "CheckFaceFaceIntersection:=", False, "SweepVectorX:=", "0mm", "SweepVectorY:=", "0mm",
                 "SweepVectorZ:=", mm(dz)])

    def prism(self, name, pts, z0, z1, material, color, transparency=0.0):
        n = self.polygon_sheet(name, pts, z0, material, color, transparency)
        self.sweep_z([n], z1 - z0)
        return n

    def cylinder(self, name, x, y, z0, h, r, material, color, sides=0, transparency=0.0):
        return self.editor.CreateCylinder(
            ["NAME:CylinderParameters", "XCenter:=", mm(x), "YCenter:=", mm(y), "ZCenter:=", mm(z0),
             "Radius:=", mm(r), "Height:=", mm(h), "WhichAxis:=", "Z", "NumSides:=", str(sides)],
            self.attrs(name, material, color, transparency))

    def disc_sheet(self, name, z, r, nonmodel=True):
        return self.editor.CreateCircle(
            ["NAME:CircleParameters", "IsCovered:=", True, "XCenter:=", "0mm", "YCenter:=", "0mm",
             "ZCenter:=", mm(z), "Radius:=", mm(r), "WhichAxis:=", "Z", "NumSegments:=", "0"],
            self.attrs(name, "vacuum", "(255 255 0)", 0.8, nonmodel))

    def unite(self, names):
        names = list(names)
        while len(names) > 1:
            out = []
            for i in range(0, len(names), 80):
                chunk = names[i:i + 80]
                if len(chunk) > 1:
                    sel = ["NAME:Selections", "Selections:=", ",".join(chunk)]
                    try:
                        self.editor.Unite(sel, ["NAME:UniteParameters", "KeepOriginals:=", False,
                                                "TurnOnNBodyBoolean:=", True])
                    except Exception:
                        self.editor.Unite(sel, ["NAME:UniteParameters", "KeepOriginals:=", False])
                out.append(chunk[0])
            names = out
        return names[0]

    def subtract(self, blanks, tools, keep_tools=True):
        sel = ["NAME:Selections", "Blank Parts:=", ",".join(blanks), "Tool Parts:=", ",".join(tools)]
        try:
            self.editor.Subtract(sel, ["NAME:SubtractParameters", "KeepOriginals:=", keep_tools,
                                       "TurnOnNBodyBoolean:=", True])
        except Exception:
            self.editor.Subtract(sel, ["NAME:SubtractParameters", "KeepOriginals:=", keep_tools])

    def rename(self, old, new):
        self.editor.ChangeProperty(["NAME:AllTabs", ["NAME:Geometry3DAttributeTab", ["NAME:PropServers", old],
                                    ["NAME:ChangedProps", ["NAME:Name", "Value:=", new]]]])
        return new

    def set_orientation(self, obj, cs):
        self.editor.ChangeProperty(["NAME:AllTabs", ["NAME:Geometry3DAttributeTab", ["NAME:PropServers", obj],
                                    ["NAME:ChangedProps", ["NAME:Orientation", "Value:=", cs]]]])

    def relative_cs(self, name, xvec, yvec):
        self.editor.CreateRelativeCS(
            ["NAME:RelativeCSParameters", "Mode:=", "Axis/Position", "OriginX:=", "0mm", "OriginY:=", "0mm",
             "OriginZ:=", "0mm", "XAxisXvec:=", mm(xvec[0]), "XAxisYvec:=", mm(xvec[1]),
             "XAxisZvec:=", mm(xvec[2]), "YAxisXvec:=", mm(yvec[0]), "YAxisYvec:=", mm(yvec[1]),
             "YAxisZvec:=", mm(yvec[2])], ["NAME:Attributes", "Name:=", name])
        self.editor.SetWCS(["NAME:SetWCS Parameter", "Working Coordinate System:=", "Global",
                            "RegionDepCSOk:=", False])

    def set_var(self, name, value):
        try:
            self.design.ChangeProperty(["NAME:AllTabs", ["NAME:LocalVariableTab",
                                        ["NAME:PropServers", "LocalVariables"],
                                        ["NAME:NewProps", ["NAME:" + name, "PropType:=", "VariableProp",
                                                           "UserDef:=", True, "Value:=", value]]]])
        except Exception:
            self.design.ChangeProperty(["NAME:AllTabs", ["NAME:LocalVariableTab",
                                        ["NAME:PropServers", "LocalVariables"],
                                        ["NAME:ChangedProps", ["NAME:" + name, "Value:=", value]]]])

    def objects_present(self):
        try:
            return list(self.editor.GetMatchedObjectName("*"))
        except Exception:
            return None
