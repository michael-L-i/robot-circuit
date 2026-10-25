"""Ask Gemma (via the Mac dashboard on :8000) to announce a meter reading, then speak it on the Mac."""
import json, sys, urllib.request

BASE = 'http://127.0.0.1:8000'


def _post(path, body, timeout):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=timeout)


def announce(volts, where='the middle copper strip'):
    prompt = (f'The robot arm just touched the multimeter probe to {where} of the circuit board. '
              f'The Bluetooth multimeter reads {volts:.2f} volts DC. Announce this reading to a live demo audience '
              'in one short, natural spoken sentence. Plain text only, no markdown.')
    text = ''
    try:
        with _post('/api/assistant/chat', dict(prompt=prompt), 90) as r:
            for line in r:
                ev = json.loads(line)
                if ev.get('type') == 'text': text += ev['text']
                elif ev.get('type') == 'error': raise RuntimeError(ev['message'])
    except Exception as e:
        print('Gemma unavailable, using a plain announcement:', e)
        text = f'The probe reads {volts:.2f} volts.'
    text = ' '.join(text.split())[:400]
    print('Gemma says:', text)
    try: _post('/api/speaker/play', dict(text=text), 60).read()
    except Exception as e: print('speaker failed:', e)
    return text


if __name__ == '__main__':
    announce(float(sys.argv[1]))
