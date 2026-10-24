"""Bounded missed-contact check against an existing server; no extra engine.

This resets the shared simulation. Run only when nobody is using its UI.
"""
import json
from pathlib import Path
import httpx
base='http://127.0.0.1:8000/sim/api/'
with httpx.Client(timeout=120) as c:
    try:
        response=c.post(base+'reset',json={'probe_error_mm':25})
        response.raise_for_status()
        s=response.json()
        for _ in range(4):
            r=c.post(base+'step',json={'mode':'gemma','revision':s['revision']})
            if r.is_error: raise RuntimeError(r.text)
            data=r.json()
            s=data['state']
            print(data['decision'],flush=True)
            if s['done']: break
        assert s['done'] and not s['success']
        assert s['measurements'][0]['voltage'] is None
        Path(__file__).parent.joinpath('evidence/gemma-probe-miss.json').write_text(json.dumps(c.get(base+'trace').json(),indent=2)+'\n')
    finally:
        # No inference loop or warm engine remains after this bounded check.
        c.post(base+'reset',json={}).raise_for_status()
        c.post(base+'unload',json={}).raise_for_status()
