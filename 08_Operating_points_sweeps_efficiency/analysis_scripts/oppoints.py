import math, json
A = 0.00393
pp = 8
ALPHA_K = 0.303                    # /mm, decay of detailed board K with distance from the magnets
S1 = [6.2816, 4.5905, 3.3655, 2.4755, 1.8266]                  # Rev0 / Rev1-S S1, board 1 next to magnets
S2 = [2.5965, 3.0572, 3.8115, 4.9382, 6.5593]                  # Rev1-S S2, board 1 next to R1 bare steel, 5 next to R2 magnets
K0_full = 18.534                                               # Rev0 full-motor FEM
scale0 = K0_full / sum(S1)
def Kstack(boards, dgap, gib, near_first=True):
    n = len(boards); s = 0
    for i, k in enumerate(boards):
        idx = i if near_first else n - 1 - i
        s += k * math.exp(-ALPHA_K * (dgap + idx * gib))
    return s
out = {}
print("== K sensitivity (mN.m/A), detailed per-board values, exponential decay 0.303/mm ==")
rows = []
for g in (1.0, 1.25, 1.5, 2.0):
    for gib in (0.0, 0.1, 0.2):
        k0 = Kstack(S1, g - 1, gib) * scale0
        k2 = Kstack(S2, g - 1, gib, near_first=False)
        rows.append((g, gib, k0, k0 + k2, k0 / K0_full - 1))
        print("gap %.2f  interboard %.1f  Rev0 %.2f (%+.1f%%)  Rev1-S S1+S2 %.2f (%+.1f%%)" % (g, gib, k0, 100 * (k0 / K0_full - 1), k0 + k2, 100 * ((k0 + k2) / (K0_full + sum(S2)) - 1)))
out["Ksens"] = rows
# resistance
Rb_lo, Rb_hi = 0.32, 0.34
Tm_lo, Tm_hi = 15.0, 30.0         # ASSUMED bracket for the unrecorded measurement temperature
Rint = (0.0, 0.10)                # ASSUMED per-phase interconnect + lead allowance per 5-board stator (ohm)
def R20(Rm, Tm): return Rm / (1 + A * (Tm - 20))
R20_lo = 5 * R20(Rb_lo, Tm_hi) + Rint[0]
R20_hi = 5 * R20(Rb_hi, Tm_lo) + Rint[1]
print("\nRev0 phase R at 20 C: %.3f .. %.3f ohm (model 5 x 0.2777 = %.3f)" % (R20_lo, R20_hi, 5 * 0.2777))
def Rt(R20v, T): return R20v * (1 + A * (T - 20))
L1 = 110e-6                       # one 5-board stator, synchronous, analytic estimate (air 107, with image 110 uH)
designs = {
 "Rev0":              dict(K=K0_full, R20=(R20_lo, R20_hi), L=L1, Kterm=K0_full, Tedd=19.6e-3),
 "Rev1-S series":     dict(K=K0_full + sum(S2), R20=(2 * R20_lo, 2 * R20_hi), L=2 * L1, Kterm=K0_full + sum(S2), Tedd=42.7e-3),
 "Rev1-S parallel":   dict(K=(K0_full + sum(S2)) / 2, R20=(R20_lo / 2, R20_hi / 2), L=L1 / 2, Kterm=(K0_full + sum(S2)) / 2, Tedd=42.7e-3),
}
Tamb = 25.0
def point(d, rpm, Ipk, Tw, Rsel=1, Tmech=(2e-3, 5e-3)):
    w = rpm * 2 * math.pi / 60; fe = rpm * pp / 60
    K = d["Kterm"] * 1e-3
    E_ph = K * w / math.sqrt(2)
    R = Rt(d["R20"][Rsel], Tw)
    Irms = Ipk / math.sqrt(2)
    X = 2 * math.pi * fe * d["L"]
    Vph = math.hypot(E_ph + Irms * R, X * Irms)
    Vph0 = E_ph + Irms * R
    Tem = 1.5 * K * Ipk
    Pdrag = d["Tedd"] * (rpm / 1000) ** 2           # track eddy (W), scales with speed^2
    Tdrag = Pdrag / w if w else 0
    Tsh = [Tem - Tdrag - t for t in Tmech]
    Pcu = 3 * Irms ** 2 * R
    Pout = [t * w for t in Tsh]
    VLL = math.sqrt(3) * Vph
    Vdc_sv = VLL * math.sqrt(2) / 0.95
    Vdc_sp = VLL * math.sqrt(2) / (math.sqrt(3) / 2) / 0.95
    eff = [p / (p + Pcu + Pdrag + t * w) for p, t in zip(Pout, Tmech)]
    return dict(rpm=rpm, fe=fe, Ipk=Ipk, Irms=Irms, Tem=Tem * 1e3, Tsh=[t * 1e3 for t in Tsh], Pout=Pout, E_ph=E_ph,
                E_ll=E_ph * math.sqrt(3), R=R, X=X, Vph=Vph, VLL=VLL, Lerr=100 * (Vph / Vph0 - 1), Vdc_sv=Vdc_sv,
                Vdc_sp=Vdc_sp, Pcu=Pcu, Pdrag=Pdrag, eff=eff)
def nmax(d, Vdc, Ipk, Tw, Rsel=1, m=0.95):
    VLLmax = m * Vdc / math.sqrt(2)
    lo, hi = 0.0, 20000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if point(d, mid, Ipk, Tw, Rsel)["VLL"] < VLLmax: lo = mid
        else: hi = mid
    return lo
print("\n== Operating points (R upper bound, winding at 60 C and 100 C) ==")
for name, d in designs.items():
    print("\n--", name, "K_term %.2f mN.m/A, R20 %.3f..%.3f ohm, L %.0f uH" % (d["Kterm"], *d["R20"], d["L"] * 1e6))
    for rpm in (500, 750, 1000):
        for Ipk in ((0.5, 1.0, 1.5) if "parallel" not in name else (1.0, 2.0, 3.0)):
            p = point(d, rpm, Ipk, 60.0)
            print(" %4d rpm %5.1f Hz  Ipk %.2f (rms %.3f)  Tem %5.1f  Tsh %5.1f..%5.1f mNm  Pout %.2f..%.2f W  E ph/ll %.3f/%.3f V  "
                  "R %.2f X %.3f  VLL %.2f (L adds %.2f%%)  Vdc SVPWM %.1f / SPWM %.1f  Pcu %.2f W  eff %.0f..%.0f%%" % (
                  rpm, p["fe"], Ipk, p["Irms"], p["Tem"], p["Tsh"][1], p["Tsh"][0], p["Pout"][1], p["Pout"][0], p["E_ph"], p["E_ll"],
                  p["R"], p["X"], p["VLL"], p["Lerr"], p["Vdc_sv"], p["Vdc_sp"], p["Pcu"], 100 * p["eff"][1], 100 * p["eff"][0]))
    for Vdc in (12, 24):
        print("  max speed @%d V (SVPWM m=0.95, 100 C winding, R high): " % Vdc +
              ", ".join("Ipk %.1f -> %4.0f rpm" % (I, nmax(d, Vdc, I, 100.0)) for I in ((0.5, 1.0, 1.5) if "parallel" not in name else (1.0, 2.0, 3.0))))
# Rev1-S parallel circulating current (back-EMF mismatch S1 vs S2)
for rpm in (1000,):
    w = rpm * math.pi / 30
    dE = (sum(S2) - K0_full) * 1e-3 * w / math.sqrt(2)
    R1 = Rt(R20_hi, 60)
    Ic = dE / (2 * R1)
    print("\nRev1-S parallel: EMF mismatch %.3f V rms/phase at %d rpm -> circulating %.3f A rms, loss %.3f W (3 phases), R/stator %.2f" % (dE, rpm, Ic, 3 * 2 * R1 * Ic ** 2, R1))
# thermal provisional limits
print("\n== Provisional continuous current per 5-board stator (rotor still, steady) ==")
for Rth in (8.75, 15.0):
    for Tmax in (60.0, 100.0):
        R = Rt(R20_hi, Tmax)
        I = math.sqrt((Tmax - Tamb) / (Rth * 1.5 * R))
        print(" Rth %.2f K/W  Tmax %3.0f C  ambient %.0f  R_hot %.2f  -> Ipk %.2f A (Irms %.2f)  P %.2f W  Rev0 Tem %.1f mNm" % (Rth, Tmax, Tamb, R, I, I / math.sqrt(2), 1.5 * I * I * R, 1.5 * K0_full * I))
# PWM ripple
print("\n== PWM ripple, approx dIpp ~ Vdc/(6 L fsw) ==")
for name, L in (("Rev0 / one stator", L1), ("Rev1-S series", 2 * L1), ("Rev1-S parallel", L1 / 2)):
    print(" %-18s" % name + "  ".join("%dV %dkHz %.2f App" % (V, f / 1e3, V / (6 * L * f)) for V in (12, 24) for f in (20e3, 50e3, 100e3)))
