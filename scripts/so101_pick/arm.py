"""Guarded SO101 moves. usage: python arm.py status | python arm.py move DURATION id=tick ..."""
import scservo_sdk as sdk, sys, time, json, fcntl
PORT='/dev/cu.usbmodem5AE60583621'
LIM={1:(825,3311),2:(906,3286),3:(790,3014),4:(892,3204),5:(0,4095),6:(1568,2723)}
class Arm:
    def __init__(s):
        s.lock=open('.cache/so101-serial.lock','w'); fcntl.flock(s.lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        s.port,s.pk=sdk.PortHandler(PORT),sdk.PacketHandler(0); assert s.port.setBaudRate(1_000_000)
    def rd(s,m,a,n=2):
        for _ in range(3):
            v,r,e=(s.pk.read2ByteTxRx if n==2 else s.pk.read1ByteTxRx)(s.port,m,a)
            if r==0: return v
        raise RuntimeError(f'read fail {m} {a}')
    def pos(s): return {m:s.rd(m,56) for m in range(1,7)}
    def load(s,m): return s.rd(m,60)&1023
    def move(s,targets,duration,load_limit=750,grip_limit=None):
        start={m:s.rd(m,56) for m in targets}
        for m,t in targets.items():
            lo,hi=LIM[m]; assert lo<=t<=hi,(m,t)
            s.pk.write2ByteTxRx(s.port,m,46,max(15,min(600,int(abs(t-start[m])/duration))))
        for m,t in targets.items(): s.pk.write2ByteTxRx(s.port,m,42,t)
        t0=time.time(); peak={m:0 for m in targets}
        while time.time()-t0<duration+5:
            done=True
            for m,t in targets.items():
                p,l,mv=s.rd(m,56),s.load(m),s.rd(m,66,1); peak[m]=max(peak[m],l)
                lim=grip_limit if (m==6 and grip_limit) else load_limit
                if l>lim:
                    for k in targets: s.pk.write2ByteTxRx(s.port,k,42,s.rd(k,56))
                    return dict(stopped=m,load=l,pos=s.pos(),peak=peak)
                if mv or (abs(p-t)>40 and time.time()-t0<duration): done=False
            if done: break
            time.sleep(0.05)
        return dict(pos=s.pos(),peak=peak)
if __name__=='__main__':
    a=Arm()
    if sys.argv[1]=='status': print(a.pos(), {m:a.load(m) for m in range(1,7)})
    else:
        d=float(sys.argv[2]); t={int(k):int(v) for k,v in (x.split('=') for x in sys.argv[3:])}
        gl=t and None
        print(json.dumps(a.move(t,d)))
