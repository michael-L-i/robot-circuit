import numpy as np, xml.etree.ElementTree as ET, os
U=ET.parse(os.path.join(os.path.dirname(__file__),'urdf/so101.urdf')).getroot()
J={j.get('name'):j for j in U.findall('joint')}
CHAIN=['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper_frame_joint']
def rpy(r,p,y):
    cr,sr,cp,sp,cy,sy=np.cos(r),np.sin(r),np.cos(p),np.sin(p),np.cos(y),np.sin(y)
    return np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],[sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])
def T(R,t): M=np.eye(4); M[:3,:3]=R; M[:3,3]=t; return M
def rotz(a): c,s=np.cos(a),np.sin(a); return np.array([[c,-s,0],[s,c,0],[0,0,1]])
ORI=[T(rpy(*map(float,J[n].find('origin').get('rpy').split())),list(map(float,J[n].find('origin').get('xyz').split()))) for n in CHAIN]
def fk(q):  # q: 5 radians
    M=np.eye(4)
    for i,O in enumerate(ORI):
        M=M@O
        if i<5: M=M@T(rotz(q[i]),[0,0,0])
    return M
def tick2rad(t): return (np.asarray(t,float)-2048)*2*np.pi/4096
def rad2tick(r): return np.round(np.asarray(r)*4096/(2*np.pi)+2048).astype(int)
def ik(target, q0, down=True, iters=300, pitch=0.0):
    """position target (m, base frame) with gripper z-axis pointing down if down."""
    q=np.array(q0,float)
    for _ in range(iters):
        def err(q):
            M=fk(q); e=list(M[:3,3]-target)
            if down:
                phi=np.arctan2(target[1],target[0]-0.0388); app=np.array([np.sin(pitch)*np.cos(phi),np.sin(pitch)*np.sin(phi),-np.cos(pitch)])
                e+=list(0.05*(M[:3,2]-app))
            return np.array(e)
        e=err(q)
        if np.linalg.norm(e)<1e-5: break
        Jm=np.zeros((len(e),4))
        for k in range(4):
            dq=np.zeros(5); dq[k]=1e-5; Jm[:,k]=(err(q+dq)-e)/1e-5
        q[:4]-=np.linalg.solve(Jm.T@Jm+1e-4*np.eye(4),Jm.T@e)
    return q, np.linalg.norm(err(q))
if __name__=='__main__':
    for name,t in [('rest',[1951,1013,3004,908,215]),('middle',[1951,2048,2048,2048,215]),('zero',[2048]*5)]:
        M=fk(tick2rad(t)); print(name, np.round(M[:3,3],3), 'zaxis',np.round(M[:3,2],2))
LIM={1:(825,3311),2:(906,3286),3:(790,3014),4:(892,3204),5:(0,4095),6:(1568,2723)}
def plan(xyz, roll_tick=None, q0=None, pitch=0.2):
    q0=tick2rad([2048,1400,2600,2600,2048]) if q0 is None else q0
    best=None
    for seed in [q0, tick2rad([2048,1700,2400,2900,2048]), tick2rad([2048,2048,2048,2048,2048])]:
        q,e=ik(np.asarray(xyz,float),seed,pitch=pitch)
        t=rad2tick(q)
        ok=e<1e-3 and all(LIM[i+1][0]+20<=t[i]<=LIM[i+1][1]-20 for i in range(4))
        if ok and (best is None or e<best[1]): best=(t,e)
    if best is None: raise ValueError(f'unreachable {xyz}')
    t=best[0]
    if roll_tick is not None: t[4]=roll_tick
    return {i+1:int(t[i]) for i in range(5)}
