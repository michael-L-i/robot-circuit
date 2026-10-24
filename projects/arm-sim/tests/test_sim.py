import json
import numpy as np
import pytest
from arm_sim.world import World,Config,scripted_action
from arm_sim.planner import parse


def run(config):
    w=World(config)
    for _ in range(16):
        if w.done: break
        w.step(scripted_action(w))
    return w

@pytest.mark.parametrize('seed',[1,7,55])
def test_repair(seed):
    w=run(Config(seed=seed))
    assert w.success
    assert [m['voltage'] for m in w.measurements]==[0,5]
    assert [e['action'] for e in w.events]==['pick_probe','measure','dock_probe','pick_jumper','place_mesh','pick_probe','measure','dock_probe','finish']
    assert w.electrical()['current_ma']==9.091

@pytest.mark.parametrize('config',[Config(scenario='supply_off'),Config(scenario='reversed_led'),Config(placement_error_mm=25),Config(probe_error_mm=25)])
def test_failure_never_claims_success(config):
    w=run(config)
    assert w.done and not w.success
    assert w.events[-1]['action']=='abort'

def test_already_working():
    w=run(Config(scenario='already_connected'))
    assert w.success and not w.placed

def test_probe_miss_is_not_zero():
    w=run(Config(probe_error_mm=25))
    assert w.measurements[0]['voltage'] is None

def test_gripper_and_verification_guards():
    w=World()
    for action in ['finish','pick_jumper','place_mesh','measure']:
        with pytest.raises(ValueError): w.step(action)
    w.step('pick_probe')
    with pytest.raises(ValueError): w.step('pick_jumper')

def test_trajectory_bounds_and_fk():
    w=World()
    while not w.done:
        start=w.q.copy()
        result=w.step(scripted_action(w))
        for f in result['frames']:
            q=np.array(f['q'])
            assert np.all(q>=w.arm.lower) and np.all(q<=w.arm.upper)
            assert np.max(abs(q-start))/f['dt']<=.60001
            assert np.allclose(w.arm.fk(q)[0],f['tcp'])
            start=q

def test_model_validation():
    assert parse('{"action":"abort","reason":"No contact"}',['abort'])['action']=='abort'
    for text in ['not JSON','{"action":"finish","reason":"ok"}','{"action":"abort","reason":1}']:
        with pytest.raises((ValueError,TypeError)): parse(text,['abort'])
