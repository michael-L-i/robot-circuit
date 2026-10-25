"""pick at pixel, place at pixel."""
import sys, os, time, json, numpy as np, subprocess
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
os.chdir('/Users/michaelli/code.tmp/Hackathons/robot-circuit')
from kin import plan
from go import goto
from arm import Arm
from cam import px2robot
OPEN, CLOSED = 2150, 1568
def radial(xy): v=np.array([xy[0]-0.0388, xy[1]]); return v/np.linalg.norm(v)
def err(a, tgt): return sum(abs(tgt[m]-a.rd(m,56)) for m in (2,3,4))
def descend(a, xy, z0=0.045, zmin=-0.035, step=0.003, roll=2048):
    tgt=plan((xy[0],xy[1],z0),roll); a.move(tgt,1.5); time.sleep(0.3); base=err(a,tgt)
    z=z0
    while z>zmin:
        z-=step; tgt=plan((xy[0],xy[1],z),roll)
        for m in (1,2,3,4): a.pk.write2ByteTxRx(a.port,m,42,tgt[m])
        time.sleep(0.35)
        e=err(a,tgt); loads=[a.load(m) for m in (2,3,4)]
        if e-base>30 or max(loads)>650:
            print(f'contact at model z={z:.3f} err+{e-base} loads {loads}'); return z
    print('no contact down to', z); return z
def grip(a, target, dur=2.0):
    a.pk.write2ByteTxRx(a.port,6,46,400); a.pk.write2ByteTxRx(a.port,6,42,target); time.sleep(dur)
    return a.rd(6,56), a.load(6)
def main(pick_px, place_px):
    a=Arm()
    pick=px2robot(*pick_px); place=px2robot(*place_px)
    pick_tip=pick-0.010*radial(pick); place_tip=place-0.010*radial(place)
    print('pick',pick.round(3),'tip',pick_tip.round(3),'place',place.round(3))
    print('open', grip(a,OPEN,1.0))
    print(goto(a,(pick_tip[0],pick_tip[1],0.08),2048,4)['pos'])
    zc=descend(a,pick_tip)
    a.move(plan((pick_tip[0],pick_tip[1],zc+0.006),2048),1.0)
    g=grip(a,CLOSED,2.5); print('closed at',g)
    print(goto(a,(pick_tip[0],pick_tip[1],0.09),2048,2)['pos'])
    g2=a.rd(6,56); print('gripper after lift',g2, 'HOLDING' if g2>CLOSED+40 else 'EMPTY?')
    if g2<=CLOSED+40 and '--force' not in sys.argv:
        print('nothing in gripper; stopping above pick'); return
    print(goto(a,(place_tip[0],place_tip[1],0.09),2048,4)['pos'])
    zc=descend(a,place_tip,z0=0.06)
    print('release', grip(a,OPEN,1.0))
    print(goto(a,(place_tip[0],place_tip[1],0.10),2048,2)['pos'])
    a.move({1:1951,2:1013,3:3004,4:908},4)
if __name__=='__main__':
    p=list(map(float,sys.argv[1:5])); main(p[:2],p[2:4])
