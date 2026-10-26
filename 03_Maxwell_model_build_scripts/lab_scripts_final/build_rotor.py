# -*- coding: utf-8 -*-
"""Single-sided PM rotor: 16 x N35 20x6x2 magnets (alternating +-Z), 86/19 x 2 mm steel back iron,
19 mm steel shaft. Rotor sits above PCB1 (+Z). Everything here belongs to the rotating band."""
import math


def radial_rect(a_deg, r0, r1, half_w):
    a = math.radians(a_deg)
    ux, uy = math.cos(a), math.sin(a)
    tx, ty = -uy, ux
    return [[ux * r0 - tx * half_w, uy * r0 - ty * half_w], [ux * r1 - tx * half_w, uy * r1 - ty * half_w],
            [ux * r1 + tx * half_w, uy * r1 + ty * half_w], [ux * r0 + tx * half_w, uy * r0 + ty * half_w]]


def rotor_geometry(cfg, stator_top_surface):
    """Pure numbers (no AEDT) so they can be checked before building."""
    r_in = cfg.MAG_CENTRE_R - cfg.MAG_LENGTH / 2.0
    r_out = cfg.MAG_CENTRE_R + cfg.MAG_LENGTH / 2.0
    zm0 = stator_top_surface + cfg.AIR_GAP
    zm1 = zm0 + cfg.MAG_THICK
    zb1 = zm1 + cfg.BACK_IRON_THICK
    band_z0 = stator_top_surface + cfg.AIR_GAP / 2.0
    shaft_z0 = band_z0 + 0.1
    shaft_z1 = zb1 + cfg.SHAFT_ABOVE_ROTOR
    r_mag_corner = math.hypot(r_out, cfg.MAG_WIDTH / 2.0)
    r_parts = max(r_mag_corner, cfg.BACK_IRON_OD / 2.0)
    return {"mag_r_in": r_in, "mag_r_out": r_out, "zm0": zm0, "zm1": zm1, "zb1": zb1,
            "band_z0": band_z0, "band_z1": shaft_z1 + 1.0, "band_r": r_parts + cfg.BAND_CLEARANCE,
            "shaft_z0": shaft_z0, "shaft_z1": shaft_z1, "r_parts": r_parts}


def magnet_array(ctx, z0, prefix, flip=False):
    """One extra 16-magnet face (Rev1-D) between z0 and z0 + MAG_THICK, same angles as the rotor magnets.
    flip=False: magnet k has the SAME magnetisation vector as rotor magnet k (CS_MagUp on even k) -> across a coreless
    stator this means opposite poles face each other and the axial fields add. CS_MagUp/Down must already exist."""
    cfg = ctx.cfg
    g = rotor_geometry(cfg, 0.0)
    mags = []
    for k in range(cfg.POLES):
        a = cfg.MAG_ANGLE_OFFSET + k * 360.0 / cfg.POLES
        up = (k % 2 == 0) != bool(flip)
        n = ctx.prism(prefix + "Magnet_%02d" % (k + 1), radial_rect(a, g["mag_r_in"], g["mag_r_out"], cfg.MAG_WIDTH / 2.0),
                      z0, z0 + cfg.MAG_THICK, cfg.MAG_MATERIAL, "(128 0 255)" if up else "(255 0 255)")
        ctx.set_orientation(n, "CS_MagUp" if up else "CS_MagDown")
        mags.append(n)
    ctx.log("%sMagnet_01..%02d: z %.5f..%.5f, %s the main rotor pattern" % (prefix, cfg.POLES, z0, z0 + cfg.MAG_THICK,
                                                                         "REVERSED from" if flip else "same vectors as"))
    return mags


def build_rotor(ctx, stator_top_surface, prefix="", make_cs=True, shaft=True, shaft_top=None):
    """prefix: object-name prefix (Rev1 builds two rotors, e.g. "R1_" / "R2_"); make_cs: create the magnet
    coordinate systems (once per project); shaft: model the shaft on this rotor; shaft_top: z of the shaft
    end (default: SHAFT_ABOVE_ROTOR beyond this back iron). Defaults reproduce the Rev0 single rotor exactly."""
    cfg = ctx.cfg
    g = rotor_geometry(cfg, stator_top_surface)
    if shaft_top is not None:
        g["shaft_z1"] = shaft_top
    if g["mag_r_in"] <= cfg.BACK_IRON_ID / 2.0:
        raise RuntimeError("Magnet inner radius %.2f mm is inside the back-iron bore" % g["mag_r_in"])
    if make_cs:
        ctx.relative_cs("CS_MagUp", [0, 0, 1], [0, 1, 0])     # NdFe35 is magnetised along local X
        ctx.relative_cs("CS_MagDown", [0, 0, -1], [0, 1, 0])
    mags = []
    for k in range(cfg.POLES):
        a = cfg.MAG_ANGLE_OFFSET + k * 360.0 / cfg.POLES
        n = ctx.prism(prefix + "Magnet_%02d" % (k + 1), radial_rect(a, g["mag_r_in"], g["mag_r_out"], cfg.MAG_WIDTH / 2.0),
                      g["zm0"], g["zm1"], cfg.MAG_MATERIAL, "(128 0 255)" if k % 2 == 0 else "(255 0 255)")
        ctx.set_orientation(n, "CS_MagUp" if k % 2 == 0 else "CS_MagDown")
        mags.append(n)
    bi = ctx.cylinder(prefix + "BackIron", 0, 0, g["zm1"], cfg.BACK_IRON_THICK, cfg.BACK_IRON_OD / 2.0,
                      cfg.BACK_IRON_MATERIAL, "(160 160 160)")
    if cfg.SHAFT_THROUGH_STATOR:
        raise RuntimeError("SHAFT_THROUGH_STATOR needs a non-cylindrical band - not enabled in this build")
    if not shaft:
        # shaft modelled on another rotor and passing through this disc's bore (Rev1 common shaft): the bore is
        # filled by that shaft, so the disc is left solid and united with it by the caller
        steel = [bi]
    elif cfg.UNITE_SHAFT_BACK_IRON:
        if cfg.SHAFT_MATERIAL != cfg.BACK_IRON_MATERIAL:
            raise RuntimeError("Cannot unite shaft and back iron of different materials")
        if abs(cfg.SHAFT_D - cfg.BACK_IRON_ID) > 1e-9:
            raise RuntimeError("Uniting assumes the shaft fills the bore (shaft %.2f vs bore %.2f mm)"
                               % (cfg.SHAFT_D, cfg.BACK_IRON_ID))
        # Boolean simplification only: the bore is not cut, the shaft overlaps the solid disc and both are
        # united -> identical steel volume, no coincident 19 mm cylinder interface.
        # Physical spec unchanged: 86 mm OD x 2 mm disc with 19 mm bore + 19 mm shaft.
        sh = ctx.cylinder(prefix + "Shaft", 0, 0, g["shaft_z0"], g["shaft_z1"] - g["shaft_z0"], cfg.SHAFT_D / 2.0,
                          cfg.SHAFT_MATERIAL, "(120 120 120)")
        steel = [ctx.rename(ctx.unite([bi, sh]), prefix + "RotorSteel")]
        ctx.log("Rotor steel: disc (bore not cut) + overlapping 19 mm shaft united as RotorSteel "
                "(EM Boolean simplification; same steel volume as disc-with-bore + shaft)")
    else:
        hole = ctx.cylinder(prefix + "BackIron_bore", 0, 0, g["zm1"] - 0.1, cfg.BACK_IRON_THICK + 0.2,
                            cfg.BACK_IRON_ID / 2.0, "vacuum", "(0 0 0)")
        ctx.subtract([bi], [hole], keep_tools=False)
        sh = ctx.cylinder(prefix + "Shaft", 0, 0, g["shaft_z0"], g["shaft_z1"] - g["shaft_z0"], cfg.SHAFT_D / 2.0,
                          cfg.SHAFT_MATERIAL, "(120 120 120)")
        steel = [bi, sh]
    ctx.log(prefix + "Rotor: %d magnets r %.1f-%.1f mm, z %.4f-%.4f (gap %.3f mm from stator surface z=%.5f); "
            "back iron OD %.1f / ID %.1f x %.1f mm; shaft %.1f mm %s"
            % (cfg.POLES, g["mag_r_in"], g["mag_r_out"], g["zm0"], g["zm1"], cfg.AIR_GAP, stator_top_surface,
               cfg.BACK_IRON_OD, cfg.BACK_IRON_ID, cfg.BACK_IRON_THICK, cfg.SHAFT_D, cfg.SHAFT_MATERIAL))
    return {"magnets": mags, "steel": steel, "geom": g}
