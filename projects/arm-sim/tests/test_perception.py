import numpy as np
import pytest
from arm_sim.perception import MarkerPerception,PerceptionError
from arm_sim.physics.visual_world import VisualWorld
from arm_sim.world import Config,scripted_action

@pytest.mark.parametrize('seed',[1,7,42,99,123])
def test_camera_guided_full_repair(seed):
    w=VisualWorld(Config(seed=seed))
    try:
        # Compare the independently estimated position to truth for scoring only.
        estimated=MarkerPerception.require(w.observer.last,'jumper')
        assert np.linalg.norm(estimated-w.bench.site_pos('jumper_grasp'))<.006
        while not w.done and w.revision<12: w.step(scripted_action(w))
        assert w.success and all(e['ok'] for e in w.events)
        assert [m['voltage'] for m in w.measurements]==[0,5]
    finally:w.bench.close()

def test_blank_camera_fails_closed_without_moving(monkeypatch):
    w=VisualWorld()
    try:
        q=w.bench.d.qpos.copy()
        monkeypatch.setattr(w.bench,'render',lambda *a,**k: np.zeros((1440,1920,3),dtype=np.uint8))
        with pytest.raises(PerceptionError,match='marker not visible'):w.step('pick_probe')
        assert np.array_equal(q,w.bench.d.qpos) and w.revision==0
    finally:w.bench.close()

def test_no_object_truth_fallback_and_real_coordinate_response():
    w=VisualWorld()
    try:
        w.jumper=[999,999,999] # simulator state cannot leak through planner's observation
        assert w.observation()['jumper_xyz'][0]<.5
        before=w.observer.last['jumper']['target_xyz']
        # Shift physical object in the scene; do not update the estimator or its registry.
        adr=w.bench.m.joint('jumper').qposadr[0]
        w.bench.d.qpos[adr]+=.01
        import mujoco
        mujoco.mj_forward(w.bench.m,w.bench.d)
        w.refresh_perception()
        after=w.observer.last['jumper']['target_xyz']
        assert .006<after[0]-before[0]<.014
    finally:w.bench.close()

def test_calibration_resolution_mismatch_is_rejected():
    w=VisualWorld()
    try:
        with pytest.raises(PerceptionError,match='resolution'):
            w.observer.estimator.detect(np.zeros((100,100,3),dtype=np.uint8))
    finally:w.bench.close()

def test_loss_of_grasp_stops_motion(monkeypatch):
    from arm_sim.physics.bench import SkillError
    w=VisualWorld()
    try:
        w.step('pick_probe')
        monkeypatch.setattr(w.bench,'gripped',lambda obj:False)
        with pytest.raises(SkillError,match='lost finger contact'):
            w.bench.move(w.bench.tcp()+[0,0,.03],w.bench.yaw_for(w.bench.tcp()))
    finally:w.bench.close()
