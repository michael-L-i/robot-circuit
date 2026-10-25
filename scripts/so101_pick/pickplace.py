"""Smooth SO101 pick-and-place: black block on the tape strip -> copper gap, parallel to the strips.

    .venv-robot/bin/python scripts/so101_pick/pickplace.py            # run (replays cached path)
    .venv-robot/bin/python scripts/so101_pick/pickplace.py --dry-run  # plan only, no motion
    options: --target U V (reference-view pixel, default 289 460), --replan, --slow 1.5, --verify

The arm must start at rest. Tuned values live in corr.json; the planned path is cached in path.json
and reused while the block sits within a few pixels of the cached spot.
"""
import argparse, json, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import run2 as R
from run1 import solve, ticks, final_pitch, blocks, reachable, px2robot, CAM, PITCH, REST, CLOSED, OPEN
import scservo_sdk as sdk
import cv2, base64, urllib.request

PATH = os.path.join(HERE, 'path.json')
READY = (0.20, 0.0, 0.12)
SEEDS = dict(pick_roll=1924, place_roll=2148)   # last approved wrist rolls


def get_frame(max_age=4.0):
    """Latest phone frame (warped into the reference view); waits for a new one if stale."""
    t = time.time()
    while time.time() - t < 30:
        d = json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/phone/latest'))
        if d['received_at'] > time.time() - max_age:
            img = cv2.imdecode(np.frombuffer(base64.b64decode(d['image'].split(',')[1]), np.uint8), cv2.IMREAD_COLOR)
            H = os.path.join(HERE, 'H_new2old.npy')
            return cv2.warpPerspective(img, np.load(H), (720, 1280)) if os.path.exists(H) else img
        time.sleep(0.3)
    raise SystemExit('No fresh camera frame: is the phone streaming to http://127.0.0.1:8000?')


def model_angle(xy, roll, pitch):
    d = R.jaw_dir(solve((xy[0], xy[1], 0.02), roll, pitch)); jp = d @ R.Jinv
    return R.img_angle(np.array([-jp[1], jp[0]]))


def roll_near(xy, want, around, pitch, window=240):
    best = None
    for r in range(around - window, around + window + 1, 16):
        try: e = abs((model_angle(xy, r, pitch) - want + 90) % 180 - 90)
        except ValueError: continue
        if best is None or e < best[0]: best = (e, r)
    return best[1]


def line(p0, p1, roll, n, pitch=None, pitch0=None):
    out = []
    for s in np.linspace(0, 1, n)[1:]:
        p = np.asarray(p0) + (np.asarray(p1) - np.asarray(p0)) * s
        pi = None if pitch is None else (pitch if pitch0 is None else pitch0 + (pitch - pitch0) * s)
        t = ticks(solve(p, roll, pi)); out.append([t[m] for m in range(1, 6)])
    return out


def build(block, target_px, corr):
    """Same geometry as the approved run2 sequence, as a list of joint-space segments."""
    (cx, cy), _, _, box = block
    e1, e2 = box[1] - box[0], box[2] - box[1]
    short = e1 if np.linalg.norm(e1) < np.linalg.norm(e2) else e2
    sdir = np.asarray(short) @ CAM[:2, :2]; width = np.linalg.norm(sdir); sdir /= width
    c = px2robot(cx, cy)
    if sdir @ R.pp.radial(c) < 0: sdir = -sdir
    tip = c - (width / 2 + 0.003) * sdir + corr.get('pick_out', 0.0) * R.pp.radial(c)   # pick_out: shift away from the arm
    fp = final_pitch(tip, SEEDS['pick_roll'])
    roll = roll_near(c, R.img_angle(R.long_axis(box)) - corr['dtheta'], SEEDS['pick_roll'], fp)

    tgt = px2robot(*target_px)
    sd2 = np.array([1.0, 0.0]) @ CAM[:2, :2]; sd2 /= np.linalg.norm(sd2)
    if sd2 @ R.pp.radial(tgt) < 0: sd2 = -sd2
    fp2 = final_pitch(tgt, SEEDS['place_roll'])
    roll2 = roll_near(tgt, -corr['dtheta'], SEEDS['place_roll'], fp2)
    tip2 = tgt - np.array(corr['dxy']) - (width / 2) * sd2
    zc, zp = corr['pick_z'] + 0.009, corr['place_z'] + 0.002
    T, U = (tip[0], tip[1]), (tip2[0], tip2[1])
    ready = ticks(solve(READY, roll)); ready = [ready[m] for m in range(1, 6)]
    return dict(block_px=[float(cx), float(cy)], target_px=list(target_px), corr=corr, rolls=[roll, roll2],
                width=float(width), segments=[
        ['move', [ready], 2.4, 'open'],
        ['move', line(READY, (*T, 0.07), roll, 12), 1.6],
        ['move', line((*T, 0.07), (*T, 0.045), roll, 6, fp, PITCH), 0.8],
        ['move', line((*T, 0.045), (*T, zc), roll, 6, fp), 1.0],
        ['grip'],
        ['move', line((*T, zc), (*T, 0.05), roll, 5, fp), 0.7],
        ['move', line((*T, 0.05), (*T, 0.08), roll, 4, PITCH, fp), 0.5],
        ['check'],
        ['move', line((*T, 0.08), (*U, 0.08), roll2, 12), 1.8],
        ['move', line((*U, 0.08), (*U, 0.04), roll2, 6, fp2, PITCH), 0.9],
        ['move', line((*U, 0.04), (*U, zp), roll2, 4, fp2), 0.8],
        ['release'],
        ['move', line((*U, zp), (*U, 0.06), roll2, 5, fp2), 0.8, 'open'],
        ['move', line((*U, 0.06), READY, roll2, 10, PITCH, fp2), 1.4],
        ['move', [[*REST.values(), 2048]], 2.4]])


class Bus:
    def __init__(self):
        self.arm = R.Arm(); self.pk, self.port = self.arm.pk, self.arm.port
        self.sync = sdk.GroupSyncWrite(self.port, self.pk, 42, 2)
        for m in range(1, 6):
            self.pk.write2ByteTxRx(self.port, m, 48, 1000)   # full holding torque
            self.pk.write1ByteTxRx(self.port, m, 41, 100)    # acceleration
            self.pk.write2ByteTxRx(self.port, m, 46, 2500)   # speed cap; setpoints are streamed
    def pos(self): return np.array([self.arm.rd(m, 56) for m in range(1, 6)], float)
    def send(self, q):
        self.sync.clearParam()
        for m, v in zip(range(1, 6), np.round(q).astype(int)):
            self.sync.addParam(m, [v & 0xFF, (v >> 8) & 0xFF])
        self.sync.txPacket()
    def gripper(self, goal, speed, torque=500):
        self.pk.write2ByteTxRx(self.port, 6, 48, torque); self.pk.write2ByteTxRx(self.port, 6, 46, speed)
        self.pk.write2ByteTxRx(self.port, 6, 42, goal)


def stream(bus, start, waypoints, duration, hz=50):
    """Min-jerk timing along the joint-space polyline start -> waypoints."""
    pts = np.vstack([start] + [np.asarray(w, float) for w in waypoints])
    seg = np.abs(np.diff(pts, axis=0)).max(1); s_at = np.r_[0, np.cumsum(seg)]
    total = s_at[-1]
    if total < 1: return pts[-1]
    t0 = time.time()
    while True:
        u = min(1.0, (time.time() - t0) / duration)
        s = total * (10 * u**3 - 15 * u**4 + 6 * u**5)
        i = min(np.searchsorted(s_at, s, 'right') - 1, len(seg) - 1)
        f = 0 if seg[i] == 0 else (s - s_at[i]) / seg[i]
        bus.send(pts[i] + (pts[i + 1] - pts[i]) * f)
        if u >= 1: return pts[-1]
        time.sleep(1 / hz)


def slow_close(bus):
    bus.gripper(1950, 150, 200); time.sleep(1.8)          # gentle swing in to just wider than the block
    bus.gripper(CLOSED, 50, 200)                          # slow, soft creep until the jaws stop on the block
    prev, still, t0 = None, 0, time.time()
    while time.time() - t0 < 9:
        time.sleep(0.1); p = bus.arm.rd(6, 56)
        still = still + 1 if prev is not None and abs(p - prev) <= 1 else 0; prev = p
        if still >= 4: break
    p = bus.arm.rd(6, 56); bus.gripper(max(CLOSED, p - 10), 50, 200); time.sleep(0.4)   # light squeeze
    return p


def execute(plan, slow=1.0):
    bus = Bus(); q = bus.pos()
    for seg in plan['segments']:
        kind = seg[0]
        if kind == 'move':
            if len(seg) > 3 and seg[3] == 'open': bus.gripper(OPEN, 800)
            q = stream(bus, q, seg[1], seg[2] * slow)
            time.sleep(0.15)
        elif kind == 'grip':
            time.sleep(0.25); print('grip', slow_close(bus))
        elif kind == 'check':
            g = bus.arm.rd(6, 56)
            if g <= CLOSED + 30:
                print('MISSED: gripper empty, returning to rest'); bus.gripper(OPEN, 800)
                stream(bus, q, [[*REST.values(), 2048]], 2.5 * slow); return False
        elif kind == 'release':
            time.sleep(0.2); g = bus.arm.rd(6, 56); bus.gripper(g + 250, 200); time.sleep(0.9)
    return True


def calibrate_floor(block, corr):
    """Touch the tape beside the block (where the fixed jaw lands) and store its height as pick_z."""
    from run1 import descend, set_torque
    plan = build(block, (289, 460), corr)
    roll = plan['rolls'][0]
    (cx, cy), _, _, box = block
    e1, e2 = box[1] - box[0], box[2] - box[1]
    short = e1 if np.linalg.norm(e1) < np.linalg.norm(e2) else e2
    sdir = np.asarray(short) @ CAM[:2, :2]; width = np.linalg.norm(sdir); sdir /= width
    c = px2robot(cx, cy)
    if sdir @ R.pp.radial(c) < 0: sdir = -sdir
    tip = c - (width / 2 + 0.003) * sdir; fp = final_pitch(tip, roll)
    bus = Bus(); q = bus.pos()
    bus.gripper(OPEN, 800)
    q = stream(bus, q, plan['segments'][0][1], 2.4)
    q = stream(bus, q, plan['segments'][1][1], 1.6)
    q = stream(bus, q, plan['segments'][2][1], 0.8); time.sleep(0.3)
    z = descend(bus.arm, tip, roll, 0.045, zmin=0.0, fp=fp, zignore=0.035)
    set_torque(bus.arm, 1000)
    print(f'floor beside the block at model z={z:.4f} (was {corr["pick_z"]:.4f})')
    q = stream(bus, bus.pos(), [plan['segments'][1][1][-1], plan['segments'][0][1][0]], 2.0)
    stream(bus, q, [[*REST.values(), 2048]], 2.4)
    corr['pick_z'] = float(z); json.dump(corr, open(R.CORR, 'w'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', nargs=2, type=float, default=[289, 460])
    ap.add_argument('--replan', action='store_true'); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--slow', type=float, default=1.0); ap.add_argument('--verify', action='store_true')
    ap.add_argument('--calibrate', action='store_true', help='re-measure the floor height at the pickup')
    a = ap.parse_args()
    corr = json.load(open(R.CORR))
    t = time.time()
    tgt_r = px2robot(*a.target)
    bs = [b for b in blocks(get_frame()) if reachable(px2robot(*b[0])) and np.linalg.norm(px2robot(*b[0]) - tgt_r) > 0.03]
    if not bs: raise SystemExit('No block in reach (put it on the tape strip, arm at rest).')
    b = min(bs, key=lambda b: np.linalg.norm(px2robot(*b[0]) - tgt_r))
    if a.calibrate: calibrate_floor(b, corr); return
    plan = json.load(open(PATH)) if os.path.exists(PATH) else None
    if (a.replan or plan is None or plan['corr'] != corr or plan['target_px'] != list(a.target)
            or np.hypot(*(np.array(plan['block_px']) - b[0])) > 4):
        print('planning...'); plan = build(b, tuple(a.target), corr); json.dump(plan, open(PATH, 'w'))
    else:
        print('using cached path')
    print(f'block at px {np.round(b[0]).tolist()}, ready in {time.time() - t:.1f}s')
    if a.dry_run: return
    t = time.time(); ok = execute(plan, a.slow); print(f'{"done" if ok else "aborted"} in {time.time() - t:.1f}s')
    if a.verify and ok:
        time.sleep(1.0); cv2.imwrite(os.path.join(HERE, 'last_run.jpg'), get_frame(max_age=0.5))


if __name__ == '__main__':
    main()
