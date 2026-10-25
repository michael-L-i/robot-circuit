"""Pick block, place it parallel to the copper strips centred at a pixel target, then measure and correct."""
import sys, os, json
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
from run1 import *
CORR=os.path.join(HERE,'corr.json')
Jinv=np.linalg.inv(CAM[:2,:2])          # robot delta -> pixel delta
def img_angle(v_px):
    """angle of a long-axis pixel vector from image vertical, degrees in (-90,90]"""
    a=np.degrees(np.arctan2(v_px[0],-v_px[1]))
    while a>90: a-=180
    while a<=-90: a+=180
    return a
def long_axis(box):
    e1=box[1]-box[0]; e2=box[2]-box[1]; return e1 if np.linalg.norm(e1)>np.linalg.norm(e2) else e2
def model_angle(xy, roll):
    d=jaw_dir(solve((xy[0],xy[1],0.02),roll,final_pitch(xy,roll)))
    jp=d@Jinv; return img_angle(np.array([-jp[1],jp[0]]))   # block long axis is perpendicular to jaws
def roll_for(xy, want, around=2048, window=700):
    best=None
    for r in range(max(600,around-window),min(3500,around+window),16):
        try: e=abs(((model_angle(xy,r)-want)+90)%180-90)
        except ValueError: continue
        if best is None or e<best[0]: best=(e,r)
    return best[1]
def measure(img, tgt_r):
    bs=[b for b in blocks(img) if np.linalg.norm(px2robot(*b[0])-tgt_r)<0.06]
    if not bs: return None
    b=min(bs,key=lambda b:np.linalg.norm(px2robot(*b[0])-tgt_r))
    return px2robot(*b[0])-tgt_r, img_angle(long_axis(b[3])), b
def slow_close(a, pre=1950):
    """fast to just wider than the block, then creep in with low force and a light squeeze"""
    a.pk.write2ByteTxRx(a.port,6,48,300); a.pk.write2ByteTxRx(a.port,6,46,250); a.pk.write2ByteTxRx(a.port,6,42,pre); time.sleep(1.2)
    a.pk.write2ByteTxRx(a.port,6,46,100); a.pk.write2ByteTxRx(a.port,6,42,CLOSED)
    prev=None; still=0; t0=time.time()
    while time.time()-t0<8:
        time.sleep(0.1); p=a.rd(6,56)
        still=still+1 if prev is not None and abs(p-prev)<=1 else 0; prev=p
        if still>=4: break
    p=a.rd(6,56)
    a.pk.write2ByteTxRx(a.port,6,42,max(CLOSED,p-20)); time.sleep(0.3)
    return p
def pick(a, b, corr):
    (cx,cy),_,_,box=b
    e1=box[1]-box[0]; e2=box[2]-box[1]; short=e1 if np.linalg.norm(e1)<np.linalg.norm(e2) else e2
    sdir=np.asarray(short)@CAM[:2,:2]; width=np.linalg.norm(sdir); sdir/=width
    c=px2robot(cx,cy)
    if sdir@pp.radial(c)<0: sdir=-sdir
    base,_=choose_roll(c,sdir)
    roll=roll_for(c, img_angle(long_axis(box))-corr['dtheta'], around=base)
    tip=c-(width/2+0.003)*sdir; fp=final_pitch(tip,roll)
    print(f'pick at {c.round(3)} roll {roll}')
    open_grip(a)
    line(a,(0.20,0.0,0.12),(tip[0],tip[1],0.07),roll,2.5)
    line(a,(tip[0],tip[1],0.07),(tip[0],tip[1],0.045),roll,1.5,pitch=fp,pitch0=PITCH)
    if 'pick_z' in corr:
        zc=corr['pick_z']+0.009
        line(a,(tip[0],tip[1],0.045),(tip[0],tip[1],zc),roll,1.5,6,pitch=fp)
    else:
        s=descend(a,tip,roll,0.04,fp=fp,zignore=0.027,zmin=0.004); corr['pick_z']=s; zc=s+0.008
        line(a,(tip[0],tip[1],s),(tip[0],tip[1],zc),roll,0.3,2,pitch=fp)
    g=slow_close(a); set_torque(a,1000)
    line(a,(tip[0],tip[1],zc),(tip[0],tip[1],0.05),roll,1.0,pitch=fp)
    line(a,(tip[0],tip[1],0.05),(tip[0],tip[1],0.08),roll,1.0,pitch=PITCH,pitch0=fp)
    g2=a.rd(6,56); print('  grip',g,'after lift',g2)
    return tip, width, g2>CLOSED+30
def place(a, frm, width, tgt_r, corr):
    sd2=np.array([1.0,0.0])@CAM[:2,:2]; sd2/=np.linalg.norm(sd2)
    if sd2@pp.radial(tgt_r)<0: sd2=-sd2
    base,_=choose_roll(tgt_r,sd2)
    roll=roll_for(tgt_r, -corr['dtheta'], around=base)
    aim=tgt_r-np.array(corr['dxy']); tip=aim-(width/2)*sd2; fp=final_pitch(tip,roll)
    print(f'place roll {roll} aim {aim.round(4)}')
    line(a,(frm[0],frm[1],0.08),(tip[0],tip[1],0.08),roll,3)
    line(a,(tip[0],tip[1],0.08),(tip[0],tip[1],0.04),roll,1.5,pitch=fp,pitch0=PITCH)
    if 'place_z' in corr:
        zc=corr['place_z']+0.002
        line(a,(tip[0],tip[1],0.04),(tip[0],tip[1],zc),roll,1.0,4,pitch=fp)
    else:
        s=descend(a,tip,roll,0.04,fp=fp,zignore=0.029,zmin=0.006); corr['place_z']=s; zc=s+0.002
        line(a,(tip[0],tip[1],s),(tip[0],tip[1],zc),roll,0.3,2,pitch=fp)
    g=a.rd(6,56); a.pk.write2ByteTxRx(a.port,6,46,120); a.pk.write2ByteTxRx(a.port,6,42,g+250); time.sleep(1.5)
    set_torque(a,1000)
    line(a,(tip[0],tip[1],zc),(tip[0],tip[1],0.06),roll,1.5,pitch=fp)
    open_grip(a)
    line(a,(tip[0],tip[1],0.06),(0.20,0.0,0.12),roll,2.0,pitch=PITCH,pitch0=fp)
    a.move({**REST,5:2048},4)
def main(tx, ty, tries=3):
    a=Arm(); tgt_r=px2robot(tx,ty)
    corr=json.load(open(CORR)) if os.path.exists(CORR) else dict(dxy=[0,0],dtheta=0)
    print('corrections', corr)
    img=frame(HERE+'/r_before.jpg')
    bs=[b for b in blocks(img) if reachable(px2robot(*b[0]))]
    if not bs: raise SystemExit('no reachable block')
    b=min(bs,key=lambda b:np.linalg.norm(px2robot(*b[0])-tgt_r))
    a.move(ticks(solve((0.20,0.0,0.12),2048)),4)
    for k in range(tries):
        frm,width,ok=pick(a,b,corr)
        if not ok: print('missed'); open_grip(a); a.move({**REST,5:2048},4); return
        place(a,frm,width,tgt_r,corr)
        img=frame(HERE+f'/r_after{k}.jpg'); m=measure(img,tgt_r)
        if m is None: print('cannot see block near target'); return
        err,ang,b=m; print(f'  result: offset {np.round(err*1000,1)} mm, angle {ang:.1f} deg')
        corr['dxy']=list(np.array(corr['dxy'])+err); corr['dtheta']+=ang
        json.dump(corr,open(CORR,'w'))
        if np.linalg.norm(err)<0.004 and abs(ang)<4: print('DONE: centred and parallel'); return
        a.move(ticks(solve((0.20,0.0,0.12),2048)),4)
    print('stopped after',tries,'tries')
if __name__=='__main__': main(float(sys.argv[1]),float(sys.argv[2]))
