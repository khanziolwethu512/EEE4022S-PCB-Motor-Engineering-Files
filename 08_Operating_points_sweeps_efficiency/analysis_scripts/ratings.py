import math
a=0.00393; pp=8
def Rst(T, lo=True):          # one 5-board stator phase, from S1 = 1.8 ohm at 15-30 C, contact 0-0.1 ohm not T-corrected
    vals=[(1.8-rc)*(1+a*(T-tm))+rc for tm in (15,30) for rc in (0,0.1)]
    return min(vals) if lo else max(vals)
L1=110e-6
D={"Rev0":dict(K=18.534,ns=1,par=False,Tedd=0.0204),
   "Rev1-S series":dict(K=39.50,ns=2,par=False,Tedd=0.0442),
   "Rev1-S parallel":dict(K=39.50/2,ns=2,par=True,Tedd=0.0442)}
def R(d,T,lo): r=Rst(T,lo); return r*d["ns"] if not d["par"] else r/d["ns"]
def Lph(d): return L1*d["ns"] if not d["par"] else L1/d["ns"]
def op(d,rpm,Ipk,T,lo):
    w=rpm*math.pi/30; E=d["K"]*1e-3*w/math.sqrt(2); Ir=Ipk/math.sqrt(2); r=R(d,T,lo); X=2*math.pi*rpm*pp/60*Lph(d)
    V=math.hypot(E+Ir*r,X*Ir); return E,V*math.sqrt(3),r
def nmax(d,Vdc,Ipk,T=100,lo=False,m=0.95):
    lo_,hi=0,20000
    for _ in range(60):
        mid=(lo_+hi)/2
        if op(d,mid,Ipk,T,lo)[1]<m*Vdc/math.sqrt(2): lo_=mid
        else: hi=mid
    return lo_
for name,d in D.items():
    Is=(0.85,1.0) if not d["par"] else (1.7,2.0)
    for I in Is:
        rpm=1000; w=rpm*math.pi/30
        Tem=1.5*d["K"]*I; Tdrag=d["Tedd"]/w*1e3
        E,Vc,_=op(d,rpm,I,25,True); _,Vh,_=op(d,rpm,I,100,False)
        Pcu=[1.5*I*I*R(d,T,lo) for T,lo in ((25,True),(60,False))]
        print("%-16s I %.2f pk (%.2f rms) Tem %.1f Tsh %.1f-%.1f Pout %.2f-%.2f W | E ph %.3f ll %.3f | VLL %.2f-%.2f -> Vdc SV %.1f-%.1f SP %.1f-%.1f | Pcu %.2f-%.2f W | nmax12 %d-%d nmax24 %d-%d | R25 %.2f-%.2f R60 %.2f-%.2f"%(
          name,I,I/math.sqrt(2),Tem,Tem-Tdrag-5,Tem-Tdrag-2,(Tem-Tdrag-5)*w/1e3,(Tem-Tdrag-2)*w/1e3,E,E*math.sqrt(3),Vc,Vh,
          Vc*math.sqrt(2)/.95,Vh*math.sqrt(2)/.95,Vc*math.sqrt(2)/.95/(math.sqrt(3)/2),Vh*math.sqrt(2)/.95/(math.sqrt(3)/2),Pcu[0],Pcu[1],
          nmax(D[name],12,I),nmax(D[name],12,I,25,True),nmax(D[name],24,I),nmax(D[name],24,I,25,True),R(d,25,True),R(d,25,False),R(d,60,True),R(d,60,False)))
# thermal per stator
for Rth in (8.75,15):
    for Tm in (60,100):
        r=Rst(Tm,False); I=math.sqrt((Tm-25)/(Rth*1.5*r)); print("Rth %.2f Tmax %d -> Ipk %.2f per stator"%(Rth,Tm,I))
# ripple
for nm,L in (("Rev0",L1),("Rev1S ser",2*L1),("Rev1S par",L1/2)):
    print(nm, " ".join("%dV/%dk %.2f"%(V,f/1e3,V/(6*L*f)) for V in (12,24) for f in (20e3,50e3)))
