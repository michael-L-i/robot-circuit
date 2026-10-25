"""Pick the probe off the floor tape, touch its tip to the middle copper group until pressure, hold, put it back.

    .venv-robot/bin/python scripts/so101_pick/probe_touch.py [--target U V] [--hold 3] [--dry-run]
Target is a reference-view pixel on the copper (default: middle group). Arm starts at rest.
"""
import argparse, json, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import pickplace as P
import run2 as R
import probe as PR
from meter import Meter
from run1 import solve, ticks, fk, set_torque, final_pitch, tick2rad, OPEN, CLOSED, REST, CAM, px2robot

TILT = 0.6             # with the probe turned round (needle toward the arm), gripper tilted forward -> needle ~30 deg down
SEARCH = [(0, 0), (0.005, 0), (-0.005, 0), (0, 0.005), (0, -0.005), (0.01, 0), (-0.01, 0)]   # (sideways, outward) m
REACH_OUT = 0.02       # extra reach away from the arm (user: needle was landing ~2 cm short)
FLIP = 2048            # wrist roll +180 deg after pickup so the needle points back toward the arm
BOARD_Z = 0.0205        # copper surface estimate for the touch (independent of the pickup floor height)
VOLT_OK = 3.0          # stop pressing once the meter reads above this
MEASURE_DEPTH = 0.006  # --measure: press to where the needle reached copper in the good runs (z ~0.0145)
DEPTH = 0.008          # travel past the board estimate (contact happens at ~the estimate; probe pivots in the jaws)
NEEDLE_PX = 38         # needle length beyond the red handle, reference-view pixels


def q5(t): return [t[m] for m in range(1, 6)]


def tip_pose(target, roll, p_g, pitch=TILT):
    """Joint ticks that put the probe tip (offset p_g in the gripper frame) at target xyz."""
    tcp = np.array(target, float)
    for _ in range(4):
        q = solve(tcp, roll, pitch); M = fk(q)
        tcp = tcp + (np.array(target) - (M[:3, :3] @ p_g + M[:3, 3]))
    return q5(ticks(q)), q


def plan_touch(tgt, board_z, roll, p_g):
    """All touch poses; raises ValueError if any is out of reach."""
    high, _ = tip_pose((tgt[0], tgt[1], 0.06), roll, p_g)
    above, _ = tip_pose((tgt[0], tgt[1], board_z + 0.018), roll, p_g)
    start, _ = tip_pose((tgt[0], tgt[1], board_z + 0.012), roll, p_g)
    depth = DEPTH
    while depth > 0:
        try: tip_pose((tgt[0], tgt[1], board_z - depth), roll, p_g); break
        except ValueError: depth -= 0.001
    return high, above, start, depth


def tip_z_measured(bus, p_g):
    M = fk(tick2rad(bus.pos())); return (M[:3, :3] @ p_g + M[:3, 3])[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', nargs=2, type=float, default=[345, 470])   # middle copper group
    ap.add_argument('--hold', type=float, default=3.0)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--announce', action='store_true', help='have Gemma announce the reading on the Mac speaker')
    ap.add_argument('--measure', action='store_true', help='single press to a fixed depth, report whatever the meter reads (no retry search)')
    a = ap.parse_args()
    g = PR.geometry(P.get_frame())
    if g is None: raise SystemExit('probe not found on the tape strip')
    tgt = px2robot(*a.target); board_z = BOARD_Z
    tgt = tgt + REACH_OUT * tgt / np.linalg.norm(tgt)       # needle landed short of the copper; reach further out
    needle_xy = px2robot(*(np.array(g['px']) + g['u_px'] * (g['half_len_px'] + NEEDLE_PX)))
    print(f"probe at {g['c'].round(3)}, needle at {needle_xy.round(3)}, touch target {tgt.round(3)}")
    side0 = PR.preferred_sides()[0]                        # plan the whole touch before picking anything up
    tip0 = g['c'] - side0 * (g['width'] / 2 + 0.004) * g['sdir']; fp0 = final_pitch(tip0, PR.ROLL)
    M0 = fk(solve((tip0[0], tip0[1], PR.FLOOR_Z + 0.003), PR.ROLL, fp0))
    p_g0 = M0[:3, :3].T @ (np.r_[needle_xy, PR.FLOOR_Z + 0.006] - M0[:3, 3])
    try: _, _, _, d0 = plan_touch(tgt, board_z, (PR.ROLL + FLIP) % 4096, p_g0)
    except ValueError as e: raise SystemExit(f'touch out of reach, not moving: {e}')
    print(f'touch plan ok, press limit {d0*1000:.0f} mm past the board estimate')
    if a.dry_run: return

    meter = Meter()                                       # connect to the DM40C while the arm picks the probe
    bus = P.Bus(); q = P.stream(bus, bus.pos(), [q5(ticks(solve(P.READY, 2048)))], 2.4)
    held = PR.grip(bus, q, g, PR.preferred_sides())          # same pickup as the calibration
    if held is None:
        print('could not pick the probe'); P.stream(bus, bus.pos(), [[*REST.values(), 2048]], 2.6); return
    q, roll = held['q'], held['roll']
    if not meter.wait_ready():
        print('meter not available:', meter.error, '- pressing to the depth limit'); meter = None
    else:
        print(f'meter connected: {meter.value} V ({meter.mode})')
    M = fk(solve((held['tip'][0], held['tip'][1], held['zg']), roll, held['fp']))
    p_g = M[:3, :3].T @ (np.r_[needle_xy, held['table_z'] + 0.006] - M[:3, 3])
    roll = (held['roll'] + FLIP) % 4096                    # turn the probe round for the touch
    try: high, above, start, depth = plan_touch(tgt, board_z, roll, p_g)
    except ValueError as e:
        print('touch out of reach after pickup, putting the probe back:', e); PR.put_back(bus, q, held); return
    if a.measure: depth = min(depth, MEASURE_DEPTH)
    print(f'touch limit {depth*1000:.0f} mm past the board estimate')

    # move over the copper with the tip pointing down
    q = P.stream(bus, q, [high], 2.0)
    q = P.stream(bus, q, [above], 1.2)
    q = P.stream(bus, q, [start], 0.8); time.sleep(0.6)
    set_torque(bus.arm, 500)
    rad = tgt / np.linalg.norm(tgt); tan = np.array([-rad[1], rad[0]])
    contact, log, z = None, [], board_z + 0.012
    peak = 0.0
    for k, (dt, dr) in enumerate(SEARCH[:1] if a.measure else SEARCH):                  # press; if no voltage, lift, shift a few mm and press again
        p = tgt + dt * tan + dr * rad
        z0 = board_z + (0.012 if k == 0 else 0.006)
        try: tip_pose((p[0], p[1], board_z - depth), roll, p_g)
        except ValueError: continue
        if k:
            t, _ = tip_pose((p[0], p[1], z0), roll, p_g); bus.send(np.array(t, float)); time.sleep(0.6)
            print(f'  no voltage; retry {k} shifted {dt*1000:+.0f} mm sideways, {dr*1000:+.0f} mm out')
        z = z0
        while z > board_z - depth:                         # press down 1 mm at a time until the meter reads > VOLT_OK
            z -= 0.001
            t, _ = tip_pose((p[0], p[1], z), roll, p_g); bus.send(np.array(t, float)); time.sleep(0.35)
            v = meter.fresh() if meter else None
            if v is not None: peak = max(peak, v)
            log.append(dict(try_=k, z=round(z, 4), volts=v, wrist_load=bus.arm.load(4)))
            print(f'  z={z:.4f}  meter={v}')
            if v is not None and v > VOLT_OK:
                contact = z; break
        if contact is not None or meter is None: break
        t, _ = tip_pose((p[0], p[1], board_z + 0.006), roll, p_g); bus.send(np.array(t, float)); time.sleep(0.5)
    json.dump(log, open(os.path.join(HERE, 'probe_touch_log.json'), 'w'), indent=0)
    import cv2
    cv2.imwrite(os.path.join(HERE, 'probe_touch_bottom.jpg'), P.get_frame(max_age=0.6))
    print(f'READING {meter.value:.3f} V at z={contact:.4f}' if contact is not None else f'no reading over {VOLT_OK} V down to z={z:.4f}',
          f'(board estimate {board_z:.4f}); holding {a.hold:.0f}s')
    t0 = time.time()
    while time.time() - t0 < a.hold:
        time.sleep(0.5)
        if meter: print(f'  holding: {meter.value} V')
    reading = meter.value if meter else None
    if reading is not None: peak = max(peak, reading)
    if meter: meter.close()
    set_torque(bus.arm, 1000)
    q = bus.pos(); q = P.stream(bus, q, [above, high], 1.5)

    PR.put_back(bus, q, held)
    print('done')
    print('RESULT ' + json.dumps(dict(reading=round(peak, 4), contact=contact is not None)), flush=True)
    if a.announce and contact is not None and reading is not None:
        from announce import announce
        announce(reading)


if __name__ == '__main__':
    main()
