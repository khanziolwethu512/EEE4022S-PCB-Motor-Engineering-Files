"""Ratings rev C: L = 25 uH per stator; Rev1-S parallel with unequal S1/S2 back-EMF (K1 18.54, K2 20.96)."""
import math
a=0.00393; pp=8; K1,K2=18.54e-3,20.96e-3; L1=25e-6
def Rst(T,lo=True):
    v=[(1.89-rc)*(1+a*(T-tm))+rc for tm in (15,30) for rc in (0,0.1)]
    return min(v) if lo else max(v)
def w(rpm): return rpm*math.pi/30
def single(K,ns,rpm,Ipk,T,lo):   # series string of ns stators, phase quantities (peak)
    r=Rst(T,lo)*ns; E=K*w(rpm); X=2*math.pi*rpm*pp/60*L1*ns
    V=math.hypot(E+Ipk*r,X*Ipk); return E,V,r
def parallel(rpm,Iterm,T,lo):    # q-axis currents; S1 and S2 in parallel per phase
    r=Rst(T,lo); E1,E2=K1*w(rpm),K2*w(rpm)
    V=(Iterm*r+E1+E2)/2; I1=(V-E1)/r; I2=(V-E2)/r
    X=2*math.pi*rpm*pp/60*L1/2; V=math.hypot(V,X*Iterm)
    return E1,E2,V,I1,I2,r
def vll_dc(Vph): return Vph*math.sqrt(3)/math.sqrt(2)*math.sqrt(2)/0.95 if False else Vph*math.sqrt(3)/0.95/ (math.sqrt(3)/math.sqrt(2))*1/math.sqrt(2)*math.sqrt(2)
# SVPWM: max phase peak = m*Vdc/sqrt(3)  -> Vdc = sqrt(3)*Vph_pk/m
def vdc(Vph_pk,m=0.95): return math.sqrt(3)*Vph_pk/m
rpm=1000
print("== parallel current sharing at 1000 rpm")
for T,lo in ((25,True),(60,False)):
    for It in (1.68,1.54):
        E1,E2,V,I1,I2,r=parallel(rpm,It,T,lo)
        Tem=1.5*(K1*I1+K2*I2)*1e3; Pcu=1.5*r*(I1**2+I2**2)
        print("T %d r %.2f Iterm %.2f: I1 %.3f I2 %.3f (circ %.3f) Tem %.2f Pcu %.2f W (equal-share %.2f) Vdc %.2f"%(T,r,It,I1,I2,(I1-I2)/2,Tem,Pcu,1.5*r*It**2/2,vdc(V)))
    E1,E2,V,I1,I2,r=parallel(rpm,0,T,lo); print("   no-load circulating %.3f A pk, loss %.1f mW"%(I1,1.5*r*(I1**2+I2**2)*1e3))
# limit: S1 current <= 0.84 at 25 C (largest circulating)
lo_,hi=0,2
for _ in range(50):
    m=(lo_+hi)/2
    if parallel(rpm,m,25,True)[3]<=0.84: lo_=m
    else: hi=m
It=lo_; E1,E2,V,I1,I2,r=parallel(rpm,It,25,True); Tem=1.5*(K1*I1+K2*I2)*1e3
Td=0.0442/w(rpm)*1e3
print("parallel limit Iterm %.3f -> I1 %.3f I2 %.3f Tem %.2f Tsh %.1f-%.1f Pout %.2f-%.2f"%(It,I1,I2,Tem,Tem-Td-5,Tem-Td-2,(Tem-Td-5)*w(rpm)/1e3,(Tem-Td-2)*w(rpm)/1e3))
for T,lo in ((25,True),(100,False)):
    E1,E2,V,I1,I2,r=parallel(rpm,It,T,lo); print("  Vdc at %d C %.2f ; Pcu %.2f"%(T,vdc(V),1.5*r*(I1**2+I2**2)))
for T,lo in ((25,True),(60,False)):
    E1,E2,V,I1,I2,r=parallel(rpm,It,T,lo); print("  Pcu %d C %.2f"%(T,1.5*r*(I1**2+I2**2)))
def nmax(f,Vdc):
    l,h=0,20000
    for _ in range(60):
        m=(l+h)/2
        if f(m)<0.95*Vdc/math.sqrt(3): l=m
        else: h=m
    return l
for Vdc in (12,24):
    print("parallel nmax %dV: %d-%d"%(Vdc,nmax(lambda n:parallel(n,It,100,False)[2],Vdc),nmax(lambda n:parallel(n,It,25,True)[2],Vdc)))
print("== single strings")
for nm,K,ns,Td in (("Rev0",18.534e-3,1,0.0204),("Rev1-S series",39.50e-3,2,0.0442)):
    I=0.84; Tem=1.5*K*I*1e3; Tdr=Td/w(rpm)*1e3
    print(nm,"Tem %.2f eddy drag %.2f Tsh %.1f-%.1f"%(Tem,Tdr,Tem-Tdr-5,Tem-Tdr-2),
      "Vdc %.1f-%.1f"%(vdc(single(K,ns,rpm,I,25,True)[1]),vdc(single(K,ns,rpm,I,100,False)[1])),
      "nmax12 %d-%d nmax24 %d-%d"%(nmax(lambda n:single(K,ns,n,I,100,False)[1],12),nmax(lambda n:single(K,ns,n,I,25,True)[1],12),nmax(lambda n:single(K,ns,n,I,100,False)[1],24),nmax(lambda n:single(K,ns,n,I,25,True)[1],24)))
print("== ripple Vdc/(6 L f) pk-pk")
for nm,L in (("Rev0",L1),("Rev1-S series",2*L1),("Rev1-S parallel",L1/2)):
    print(nm," ".join("%dV/%dk %.2f"%(V,f/1e3,V/(6*L*f)) for V in (12,24) for f in (20e3,50e3)), "| +0.5 mH 12V/50k %.3f"%(12/(6*(L+0.5e-3)*50e3)))
