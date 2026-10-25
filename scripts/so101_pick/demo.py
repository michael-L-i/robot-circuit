"""Full robot demo with Gemma commentary on the dashboard (http://127.0.0.1:8000).

    .venv-robot/bin/python scripts/so101_pick/demo.py

1. Probe the middle copper (resistor missing -> expect ~0 V), Gemma comments.
2. Place the resistor across the gap with the approved pick-and-place, check the LED, Gemma comments.
3. Probe again until the meter reads > 3 V, Gemma confirms the repair.
The two skills run unchanged as subprocesses; this file only sequences them.
"""
import json, os, subprocess, sys, time, urllib.request
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
PY = os.path.join(ROOT, '.venv-robot/bin/python')
BASE = 'http://127.0.0.1:8000'


def post(path, body, timeout=240):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)


def step(name):
    post('/api/demo/control', dict(active=True, step=name)); print(f'\n=== {name} ===', flush=True)


def narrate(name, facts):
    try: print('Gemma:', post('/api/demo/narrate', dict(step=name, facts=facts))['text'], flush=True)
    except Exception as e: print('narration failed:', e, flush=True)


def run(script, *args):
    """Run a skill script unchanged, echo its output, return its RESULT dict / grip value if printed."""
    p = subprocess.Popen([PY, os.path.join(HERE, script), *args], cwd=ROOT, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    out = {}
    for line in p.stdout:
        if line.startswith(('Device', 'Connect', 'Setting')): continue
        print('  ' + line.rstrip(), flush=True)
        if line.startswith('RESULT '): out.update(json.loads(line[7:]))
        if line.startswith('grip '): out['grip'] = int(line.split()[1])
        if 'No block in reach' in line or 'could not pick' in line: out['failed'] = line.strip()
    p.wait(); out['code'] = p.returncode
    return out


def led_on():
    """LED next to the copper, from the camera (reference view): bright green pixels."""
    sys.path.insert(0, HERE); import pickplace as P
    time.sleep(1.0); img = P.get_frame(max_age=1.0)
    hsv = cv2.cvtColor(img[440:480, 360:400], cv2.COLOR_BGR2HSV)
    n = int((((hsv[..., 0] > 25) & (hsv[..., 0] < 45) & (hsv[..., 1] > 60)) & (hsv[..., 2] > 200)).sum())
    return n > 50, n


def main():
    post('/api/demo/control', dict(active=True, step=''))
    narrate('Start', 'A robot arm is about to diagnose and repair a simple LED circuit on the board: '
            'measure with a Bluetooth multimeter, replace the resistor, then measure again.')

    step('1 · Probe the circuit')
    r1 = run('probe_touch.py', '--measure')
    v1 = r1.get('reading'); lit1, _ = led_on()
    if v1 is None:
        narrate('1 · Probe', 'The robot could not complete the first measurement.')
    else:
        verdict = ('almost no voltage, so the resistor is missing or broken and the circuit is open'
                   if v1 < 3.0 else 'voltage is already present')
        narrate('1 · Probe', f'The robot touched the probe to the middle copper strip. The multimeter reads {v1:.2f} volts '
                f'and the LED is {"on" if lit1 else "off"}: {verdict}. Next the robot places a new resistor.')

    step('2 · Replace the resistor')
    r2 = run('pickplace.py', '--verify')
    lit2, _ = led_on()
    if r2.get('failed') or r2['code']:
        narrate('2 · Resistor', f'The robot could not place the resistor ({r2.get("failed", "error")}).')
    else:
        narrate('2 · Resistor', 'The robot picked up the resistor and placed it across the copper gap. '
                f'The camera shows the LED is {"now lit" if lit2 else "still off"}.')

    step('3 · Verify the repair')
    r3 = run('probe_touch.py')
    v3 = r3.get('reading')
    if v3 is None:
        narrate('3 · Verify', 'The robot could not complete the final measurement.')
    else:
        ok = v3 > 3.0
        narrate('3 · Verify', f'The robot probed the middle copper strip again. The multimeter now reads {v3:.2f} volts'
                + (f', up from {v1:.2f} volts before' if v1 is not None else '')
                + ('. Current is flowing and the repair is verified.' if ok else '. That is still too low; the repair needs a check.'))
    post('/api/demo/control', dict(active=False, step=''))
    print('\nDEMO DONE', dict(before=v1, led_after=lit2, after=v3), flush=True)


if __name__ == '__main__':
    main()
