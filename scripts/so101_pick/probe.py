"""Red probe on the floor tape strip: detection and the calibrated pickup, shared by probe_touch.py.

    .venv-robot/bin/python scripts/so101_pick/probe.py [--dry-run]
Run directly to (re)calibrate: picks the probe, lifts it, puts it back, writes probe.json.
"""
import argparse, json, os, sys, time
import numpy as np, cv2
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import pickplace as P
from run1 import solve, ticks, descend, set_torque, final_pitch, OPEN, CLOSED, REST, CAM, px2robot

OUT = os.path.join(HERE, 'probe.json')
ROLL = 1192                 # calibrated wrist roll: jaws close across the probe
FLOOR_Z = 0.012             # grip at +3 mm; probe back end now rests on the breadboard, handle ~4 mm higher (was 0.006 flat)


def q5(t): return [t[m] for m in range(1, 6)]


def find_probe(img):
    """Needle-side red part of the handle on the tape strip: (centre px, box, width px)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    red = (((hsv[..., 0] < 8) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 120) & (hsv[..., 2] > 70)).astype(np.uint8)
    red = cv2.morphologyEx(red, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))       # drop thin wires
    roi = np.zeros_like(red); roi[280:400, 100:470] = 1; red *= roi              # the tape strip above the board
    n, lab, st, _ = cv2.connectedComponentsWithStats(red)
    best = None
    for i in range(1, n):
        if st[i, 4] < 150: continue
        ys, xs = np.nonzero(lab == i)
        (cx, cy), (w, h), ang = cv2.minAreaRect(np.c_[xs, ys].astype(np.float32))
        L, S = max(w, h), min(w, h)
        if S < 15 or S > 40 or L < 2.5 * S: continue       # handle is ~27 px thick; the cable is ~11 px
        if best is None or cx < best[1][0]: best = (st[i, 4], (cx, cy), (w, h), ang)
    if best is None: return None
    _, (cx, cy), (w, h), ang = best
    return (cx, cy), cv2.boxPoints(((cx, cy), (w, h), ang)), min(w, h)


def geometry(img):
    """Probe pose in robot coordinates. sdir (across the handle) always points to robot +y."""
    f = find_probe(img)
    if f is None: return None
    (cx, cy), box, _ = f
    e1, e2 = box[1] - box[0], box[2] - box[1]
    short, long_ = (e1, e2) if np.linalg.norm(e1) < np.linalg.norm(e2) else (e2, e1)
    sdir = np.asarray(short) @ CAM[:2, :2]; width = max(np.linalg.norm(sdir), 0.008); sdir /= np.linalg.norm(sdir)
    if sdir[1] < 0: sdir = -sdir
    u = np.asarray(long_) / np.linalg.norm(long_)
    if u[0] > 0: u = -u                                  # needle points to image-left
    return dict(px=(float(cx), float(cy)), c=px2robot(cx, cy), sdir=sdir, width=width, box=box,
                half_len_px=float(np.linalg.norm(long_) / 2), u_px=u)


def grip(bus, q, g, sides=(-1, +1), roll=ROLL, floor_z=None):
    """Calibrated pickup: preferred jaw side first, fixed grip height above the floor, grip firmly, lift to 6.5 cm."""
    floor_z = FLOOR_Z if floor_z is None else floor_z
    for side in sides:
        tip = g['c'] - side * (g['width'] / 2 + 0.004) * g['sdir']
        fp = final_pitch(tip, roll)
        bus.gripper(OPEN, 800)
        q = P.stream(bus, q, P.line(P.READY, (tip[0], tip[1], 0.06), roll, 10), 1.8)
        q = P.stream(bus, q, P.line((tip[0], tip[1], 0.06), (tip[0], tip[1], 0.045), roll, 5, fp, P.PITCH), 0.8)
        z = floor_z
        zg = z + 0.003                                    # fixed grip height: no floor feeling (it was unreliable)
        q = P.stream(bus, q, P.line((tip[0], tip[1], 0.045), (tip[0], tip[1], zg), roll, 6, fp), 1.2); time.sleep(0.2)
        bus.gripper(1950, 600, 500); time.sleep(0.9); bus.gripper(CLOSED, 120, 600)
        prev, still, t0 = None, 0, time.time()
        while time.time() - t0 < 5:
            time.sleep(0.1); p = bus.arm.rd(6, 56)
            still = still + 1 if prev is not None and abs(p - prev) <= 1 else 0; prev = p
            if still >= 4: break
        closed = bus.arm.rd(6, 56)
        if closed > CLOSED + 15: bus.gripper(max(CLOSED, closed - 110), 200, 1000); time.sleep(0.6)
        q = P.stream(bus, bus.pos(), P.line((tip[0], tip[1], zg), (tip[0], tip[1], 0.065), roll, 6, P.PITCH, fp), 1.5)
        if bus.arm.rd(6, 56) <= CLOSED + 30:
            print(f'  side {side:+d}: nothing in the jaws'); bus.gripper(OPEN, 800); continue
        print(f'  picked on side {side:+d}, floor z={z:.3f}, gripper {closed}')
        return dict(q=q, tip=tip, zg=zg, fp=fp, closed=closed, side=side, table_z=z, roll=roll)
    return None


def put_back(bus, q, s):
    """Lower the held probe back to where it was picked, release, park."""
    tip, zg, fp, roll = s['tip'], s['zg'], s['fp'], s['roll']
    q = P.stream(bus, q, [q5(ticks(solve((tip[0], tip[1], 0.065), roll, P.PITCH)))], 2.5)
    q = P.stream(bus, q, P.line((tip[0], tip[1], 0.065), (tip[0], tip[1], zg + 0.002), roll, 6, fp, P.PITCH), 1.5)
    bus.gripper(s['closed'] + 250, 200); time.sleep(0.9)
    q = P.stream(bus, q, P.line((tip[0], tip[1], zg), (tip[0], tip[1], 0.06), roll, 4, fp), 0.8)
    q = P.stream(bus, q, [q5(ticks(solve(P.READY, 2048)))], 1.5)
    return P.stream(bus, q, [[*REST.values(), 2048]], 2.4)


def preferred_sides():
    try: s = json.load(open(OUT))['side']; return (s, -s)
    except (OSError, KeyError, ValueError): return (-1, +1)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
    img = P.get_frame(); g = geometry(img)
    if g is None: raise SystemExit('probe not found on the tape strip')
    print(f"probe at px {np.round(g['px']).tolist()} robot {g['c'].round(3)} width {g['width']*1000:.1f} mm")
    if a.dry_run:
        cv2.drawContours(img, [np.int32(g['box'])], 0, (0, 255, 0), 2); cv2.imwrite(os.path.join(HERE, 'probe_detect.jpg'), img); return
    bus = P.Bus(); q = P.stream(bus, bus.pos(), [q5(ticks(solve(P.READY, 2048)))], 2.4)
    s = grip(bus, q, g, preferred_sides())
    if s is None:
        print('could not pick the probe'); P.stream(bus, bus.pos(), [[*REST.values(), 2048]], 2.6); return
    json.dump(dict(roll=s['roll'], side=s['side'], table_z=s['table_z'], grip=s['closed'], width=g['width']), open(OUT, 'w'))
    time.sleep(1.0); put_back(bus, s['q'], s); print('calibrated; probe put back')


if __name__ == '__main__':
    main()
