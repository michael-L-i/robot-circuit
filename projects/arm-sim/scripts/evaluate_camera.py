"""Bounded offline evaluation; no model inference and no hardware access."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from arm_sim.physics.visual_world import VisualWorld
from arm_sim.world import Config,scripted_action

results=[]
for seed in range(20):
    w=VisualWorld(Config(seed=seed));start=time.monotonic()
    try:
        d=w.observer.last['jumper']
        # Ground truth is used only by this evaluator, never the estimator/controller.
        error_mm=float(np.linalg.norm(np.array(d['target_xyz'])-w.bench.site_pos('jumper_grasp'))*1000)
        while not w.done and w.revision<12:w.step(scripted_action(w))
        result=dict(seed=seed,success=w.success,initial_jumper_error_mm=round(error_mm,2),steps=w.revision)
    except Exception as exc:result=dict(seed=seed,success=False,error=str(exc),steps=w.revision)
    finally:w.bench.close()
    results.append(result);print(result,flush=True)
path=Path(__file__).resolve().parents[1]/'evidence/camera-layout-evaluation.json'
path.write_text(json.dumps(dict(conditions='20 jumper layouts; ideal calibrated camera; no noise; taught marker IDs; scripted task policy',runs=results),indent=2)+'\n')
print(f'{sum(r["success"] for r in results)}/{len(results)} succeeded')
