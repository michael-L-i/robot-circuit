"""python go.py x y z [roll] [duration]  -> move gripper tip (pointing down) to base-frame xyz (m)."""
import sys, os, numpy as np, json
sys.path.insert(0, os.path.dirname(__file__)); os.chdir('/Users/michaelli/code.tmp/Hackathons/robot-circuit')
from kin import plan, fk, tick2rad
from arm import Arm
def min_z(a_t, b_t, n=30):
    zs=[]
    for s in np.linspace(0,1,n):
        q=tick2rad([a_t[i]+(b_t[i]-a_t[i])*s for i in range(1,6)]); zs.append(fk(q)[2,3])
    return min(zs)
def goto(arm, xyz, roll=None, duration=4.0, floor=0.015, pitch=0.2):
    cur=arm.pos(); tgt=plan(xyz, roll if roll is not None else cur[5], pitch=pitch)
    if min_z(cur,tgt) < min(floor, xyz[2]-0.005):
        mid=plan((xyz[0],xyz[1],max(0.12,xyz[2]+0.06)), tgt[5], pitch=pitch)
        r=arm.move(mid,duration);  print('via', r)
        if 'stopped' in r: return r
    r=arm.move(tgt,duration); r['target']=tgt; return r
if __name__=='__main__':
    a=sys.argv[1:]; xyz=tuple(map(float,a[:3]))
    roll=int(a[3]) if len(a)>3 and a[3]!='-' else None; d=float(a[4]) if len(a)>4 else 4.0
    p=float(a[5]) if len(a)>5 else 0.0
    print(goto(Arm(), xyz, roll, d, pitch=p))
