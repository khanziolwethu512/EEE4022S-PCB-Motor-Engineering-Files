import numpy as np
def sheet_H(a1,a2,b1,b2,c):
    """H/(sigma/4pi) of a uniform sheet over u'[u1,u2] v'[v1,v2] at z'=0, evaluated at offsets
    a_i=u-u_i, b_j=v-v_j, c=z (arrays). Returns Hu,Hv,Hz without the sigma/4pi factor."""
    def G(a):   # int over v' of 1/R
        s=np.sqrt(a*a+c*c); return np.arcsinh(b1/s)-np.arcsinh(b2/s)
    def Gp(b):
        s=np.sqrt(b*b+c*c); return np.arcsinh(a1/s)-np.arcsinh(a2/s)
    Hu=G(a2)-G(a1)
    Hv=Gp(b2)-Gp(b1)
    def F(a,b): R=np.sqrt(a*a+b*b+c*c); return np.arctan(a*b/(c*R))
    Hz=F(a1,b1)-F(a1,b2)-F(a2,b1)+F(a2,b2)
    return Hu,Hv,Hz
# brute force
u1,u2,v1,v2=-1.0,2.0,-0.5,1.5
for P in [(0.3,0.2,0.7),(3.0,-1.0,0.4),(-2,2.5,-1.2),(0.5,0.5,0.05)]:
    u,v,z=P
    n=800; us=np.linspace(u1,u2,n+1); vs=np.linspace(v1,v2,n+1); uc=0.5*(us[1:]+us[:-1]); vc=0.5*(vs[1:]+vs[:-1])
    U,V=np.meshgrid(uc,vc); dA=(u2-u1)*(v2-v1)/n/n
    dx,dy,dz=u-U,v-V,z; R3=(dx*dx+dy*dy+dz*dz)**1.5
    bf=[np.sum(dx/R3)*dA,np.sum(dy/R3)*dA,np.sum(dz/R3)*dA]
    an=sheet_H(np.array(u-u1),np.array(u-u2),np.array(v-v1),np.array(v-v2),np.array(z))
    print(P,[round(x,5) for x in bf],[round(float(x),5) for x in an])
