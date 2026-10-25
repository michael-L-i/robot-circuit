import sys, os, time, json, base64, urllib.request, numpy as np, cv2
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
os.chdir('/Users/michaelli/code.tmp/Hackathons/robot-circuit')
from kin import ik, fk, tick2rad, rad2tick, ORI, LIM
from arm import Arm
from cam import px2robot, M as CAM
from det2 import blocks
import pp
REST={1:1951,2:1013,3:3004,4:908}; OPEN=2450; CLOSED=1568; PITCH=0.2
PLACE_PX=(382,450)
def frame(path):
    t=time.time()
    while time.time()-t<30:
        d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/phone/latest'))
        if d['received_at']>t+0.3:
            open(path,'wb').write(base64.b64decode(d['image'].split(',')[1])); img=cv2.imread(path)
            Hp=os.path.join(HERE,'H_new2old.npy')
            if os.path.exists(Hp): img=cv2.warpPerspective(img,np.load(Hp),(720,1280)); cv2.imwrite(path,img)
            return img
        time.sleep(0.5)
    raise RuntimeError('no fresh camera frame')
def solve(xyz, roll, pitch=None):
    pitch=PITCH if pitch is None else pitch
    seed=tick2rad([2048,1900,2300,2900,roll]); best=None
    for s in [seed, tick2rad([2048,2048,2048,2048,roll]), tick2rad([2048,1700,2500,2700,roll])]:
        q,e=ik(np.asarray(xyz,float),s,pitch=pitch)
        t=rad2tick(q)
        if e<3e-3 and all(LIM[i+1][0]+15<=t[i]<=LIM[i+1][1]-15 for i in range(4)):
            if best is None or e<best[1]: best=(q,e)
    if best is None: raise ValueError(f'unreachable {xyz}')
    return best[0]
def jaw_dir(q):
    Mt=fk(q); Mg=Mt@np.linalg.inv(ORI[5]); piv=(Mg@np.array([0.0202,0.0188,-0.0234,1]))[:3]
    d=(piv-Mt[:3,3])[:2]; return d/np.linalg.norm(d)
def choose_roll(xy, close_dir):
    rad=pp.radial(xy); best=None
    for roll in range(1200,2600,48):
        q=solve((xy[0],xy[1],0.02),roll,final_pitch(xy,roll)); d=jaw_dir(q)
        c=d@close_dir
        if c<0: continue   # moving jaw must be on +close_dir side
        score=c+0.05*(d@rad)
        if best is None or score>best[0]: best=(score,roll,d)
    return best[1],best[2]
def ticks(q): t=rad2tick(q); return {i+1:int(t[i]) for i in range(5)}
def line(a, p0, p1, roll, dur, n=8, pitch=None, pitch0=None):
    for s in np.linspace(0,1,n)[1:]:
        p=np.asarray(p0)+(np.asarray(p1)-np.asarray(p0))*s
        pi=None if pitch is None else (pitch if pitch0 is None else pitch0+(pitch-pitch0)*s)
        t=ticks(solve(p,roll,pi))
        for m in (1,2,3,4,5):
            a.pk.write2ByteTxRx(a.port,m,46,300); a.pk.write2ByteTxRx(a.port,m,42,t[m])
        time.sleep(dur/n)
    time.sleep(0.4)
def set_torque(a, lim):
    for m in (2,3,4): a.pk.write2ByteTxRx(a.port,m,48,lim)
def descend(a, xy, roll, z0, zmin=-0.02, step=0.001, gap_mm=2.5, fp=0.0, trace=False, zignore=1.0, sliding=False):
    """Reduced torque, small steps. Contact = measured tip stops following the commanded height."""
    set_torque(a,500)
    def zmeas(): return fk(tick2rad([a.rd(m,56) for m in (1,2,3,4,5)]))[2,3]
    t=ticks(solve((xy[0],xy[1],z0),roll,fp))
    for m in (1,2,3,4): a.pk.write2ByteTxRx(a.port,m,42,t[m])
    time.sleep(1.0); z=z0; gaps=[]
    while z>zmin:
        z-=step; t=ticks(solve((xy[0],xy[1],z),roll,fp))
        for m in (1,2,3,4): a.pk.write2ByteTxRx(a.port,m,42,t[m])
        time.sleep(0.25); zm=zmeas(); gaps.append(zm-z)
        ref=(np.median(gaps[-6:-1]) if len(gaps)>=6 else None) if sliding else (np.median(gaps[:4]) if len(gaps)>=4 else None)
        if trace: print(f'  cmd {z:.4f} meas {zm:.4f} gap {1000*(zm-z):.1f}mm')
        if ref is not None and z<zignore and (zm-z-ref)*1000>gap_mm:
            back=z+(zm-z-ref)   # where commanded and real coincide = surface
            t=ticks(solve((xy[0],xy[1],back),roll,fp))
            for m in (1,2,3,4): a.pk.write2ByteTxRx(a.port,m,42,t[m])
            time.sleep(0.4); print(f'  surface at model z={back:.4f}'); return back
    print('  no contact'); return z
def gentle_close(a):
    a.pk.write2ByteTxRx(a.port,6,48,300); a.pk.write2ByteTxRx(a.port,6,46,250); a.pk.write2ByteTxRx(a.port,6,42,CLOSED)
    prev=None; still=0; t0=time.time()
    while time.time()-t0<4:
        p=a.rd(6,56); still=still+1 if prev is not None and abs(p-prev)<=2 else 0; prev=p
        if still>=5: break
        time.sleep(0.05)
    p=a.rd(6,56)
    if p>CLOSED+35: a.pk.write2ByteTxRx(a.port,6,42,p-20)
    return p
def open_grip(a, v=OPEN):
    a.pk.write2ByteTxRx(a.port,6,48,500); a.pk.write2ByteTxRx(a.port,6,46,500); a.pk.write2ByteTxRx(a.port,6,42,v); time.sleep(1.0)
def final_pitch(xy, roll=2048):
    for p in (0.0,0.05,0.1,0.15,0.2):
        try: solve((xy[0],xy[1],0.01),roll,p); solve((xy[0],xy[1],0.05),roll,p); return p
        except ValueError: pass
    raise ValueError(f'unreachable {xy}')
def reachable(xy):
    try:
        t=xy-0.015*pp.radial(xy); final_pitch(t); solve((t[0],t[1],0.07),1900); return True
    except ValueError: return False
def main(place_px):
    a=Arm()
    img=frame(HERE+'/r_before.jpg')
    bs=[b for b in blocks(img) if reachable(px2robot(*b[0]))]
    if not bs: raise SystemExit('no reachable block found')
    tgt_r=px2robot(*place_px)
    (cx,cy),(w,h),ang,box=min(bs,key=lambda b:np.linalg.norm(px2robot(*b[0])-tgt_r))
    e1=box[1]-box[0]; e2=box[2]-box[1]; short=e1 if np.linalg.norm(e1)<np.linalg.norm(e2) else e2
    J=CAM[:2,:2]; sdir=np.asarray(short)@J; width=np.linalg.norm(sdir); sdir/=width
    c=px2robot(cx,cy); print('block px',(round(cx),round(cy)),'robot',c.round(3),'width mm',round(width*1000,1))
    if sdir@pp.radial(c)<0: sdir=-sdir
    roll,d=choose_roll(c,sdir); print('pick roll',roll)
    tip=c-(width/2+0.007)*d
    fp=final_pitch(tip,roll); print('final pitch deg',round(np.degrees(fp),1))
    open_grip(a)
    a.move(ticks(solve((0.20,0.0,0.12),roll)),4)
    line(a,(0.20,0.0,0.12),(tip[0],tip[1],0.07),roll,2.5)
    line(a,(tip[0],tip[1],0.07),(tip[0],tip[1],0.045),roll,1.0,pitch=fp,pitch0=PITCH)
    zc=descend(a,tip,roll,0.045,fp=fp)
    g=gentle_close(a); set_torque(a,1000); print('gripper stopped at',g,'(closed=1568)')
    line(a,(tip[0],tip[1],zc),(tip[0],tip[1],0.05),roll,1.0,pitch=fp)
    line(a,(tip[0],tip[1],0.05),(tip[0],tip[1],0.08),roll,1.0,pitch=PITCH,pitch0=fp)
    g2=a.rd(6,56); print('after lift',g2,'HOLDING' if g2>CLOSED+30 else 'EMPTY')
    if g2<=CLOSED+30: open_grip(a); a.move({**REST,5:2048},4); return
    sd2=np.array([1.0,0.0])@J; sd2/=np.linalg.norm(sd2)
    if sd2@pp.radial(tgt_r)<0: sd2=-sd2
    roll2,d2=choose_roll(tgt_r,sd2); tip2=tgt_r-(width/2)*d2; fp2=final_pitch(tip2,roll2); print('place roll',roll2,'tip',tip2.round(3),'pitch deg',round(np.degrees(fp2),1))
    line(a,(tip[0],tip[1],0.08),(tip2[0],tip2[1],0.08),roll2,3)
    line(a,(tip2[0],tip2[1],0.08),(tip2[0],tip2[1],0.05),roll2,1.0,pitch=fp2,pitch0=PITCH)
    zc2=descend(a,tip2,roll2,0.05,fp=fp2)
    open_grip(a); set_torque(a,1000)
    line(a,(tip2[0],tip2[1],zc2),(tip2[0],tip2[1],0.06),roll2,1.0,pitch=fp2)
    line(a,(tip2[0],tip2[1],0.06),(0.20,0.0,0.12),roll2,2.0,pitch=PITCH,pitch0=fp2)
    a.move({**REST,5:2048},4)
    img=frame(HERE+'/r_after.jpg')
    for b in blocks(img):
        if b[0][0]<600: print('block now at px',np.round(b[0]),'angle',round(b[2]),'offset from target mm',np.round((px2robot(*b[0])-tgt_r)*1000,1))
if __name__=="__main__": main(tuple(map(float,sys.argv[1:3])))
