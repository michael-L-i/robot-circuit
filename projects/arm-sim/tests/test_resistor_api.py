"""Contract tests never load Gemma; physics integration runs when Claude's world exists."""
import importlib.util
import uuid
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
import arm_sim.resistor.app as module


class FakeWorld:
    def __init__(self, config):
        self.config = config
        self.revision, self.episode = 0, uuid.uuid4().hex
        self.done = self.success = False
        self.events, self.measurements = [], []
        self.observer = None
        self.closed = False
        self.bench = SimpleNamespace(close=self.close,
            render=lambda *a, **k: np.zeros((72,128,3),dtype=np.uint8),
            video=lambda *a, **k: b'\x00\x00\x00\x18ftypmp42')

    def close(self): self.closed = True
    def allowed(self): return ['pick_probe', 'abort']
    def observation(self):
        return dict(allowed_actions=self.allowed(), measurements=self.measurements)
    def snapshot(self):
        return dict(**self.observation(), revision=self.revision, episode=self.episode,
            done=self.done, success=self.success, events=self.events, config=self.config)
    def step(self, action):
        assert action in self.allowed()
        before=self.snapshot()
        self.revision += 1
        self.events.append(dict(step=self.revision, action=action, note='Executed', ok=True))
        return dict(before=before, frames=[], state=self.snapshot())


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(module, 'world', None)
    monkeypatch.setattr(module, 'create_world', FakeWorld)
    monkeypatch.setattr(module, 'scripted_action', lambda w: 'pick_probe')
    monkeypatch.setattr(module, 'decide', lambda *a, **k: dict(
        action='pick_probe', reason='Test decision', seconds=0, source='fake'))
    with TestClient(module.app) as client: yield client
    if module.world is not None: module.world.bench.close()


def step(client, state, **overrides):
    return client.post('/api/step',json=dict(
        mode='gemma', revision=state['revision'], episode=state['episode'], **overrides))


def test_lazy_creation_static_and_reset_cleanup(client):
    assert module.world is None
    for path in ('/', '/static/app.js', '/static/style.css', '/api/progress'):
        assert client.get(path).status_code == 200
    assert module.world is None
    assert client.get('/api/state').status_code == 200
    old=module.world
    assert client.post('/api/reset',json={'scenario':'healthy'}).status_code == 200
    assert old.closed and module.world is not old


def test_stale_revision_episode_and_video(client):
    old=client.get('/api/state').json()
    state=client.post('/api/reset',json={}).json()
    assert step(client,old).status_code == 409
    assert step(client,{**state,'revision':99}).status_code == 409
    response=step(client,state)
    assert response.status_code == 200
    current=response.json()['state']
    assert step(client,state).status_code == 409
    for params in ({'r':0,'episode':current['episode']}, {'r':1,'episode':old['episode']}):
        assert client.get('/api/action.mp4',params=params).status_code == 409
    response=client.get('/api/action.mp4',params={'r':1,'episode':current['episode']})
    assert response.status_code == 200 and b'ftyp' in response.content


def test_disallowed_action_and_budget_do_not_move(client,monkeypatch):
    state=client.get('/api/state').json()
    monkeypatch.setattr(module,'decide',lambda *a,**k: dict(action='insert_resistor',seconds=0))
    assert step(client,state).status_code == 422
    assert module.world.revision == 0 and not module.world.events
    module.world.revision=20
    assert step(client,{**state,'revision':20}).status_code == 409


def test_validation_render_and_oracle_endpoints(client):
    assert client.post('/api/reset',json={'scenario':'misplaced'}).status_code == 422
    assert client.post('/api/reset',json={'seed':-1}).status_code == 422
    assert client.post('/api/step',json={'revision':0}).status_code == 422
    state=client.get('/api/state').json()
    assert step(client,state).status_code == 200
    assert client.get('/api/render.jpg').headers['content-type'] == 'image/jpeg'
    assert client.get('/api/perception').status_code == 409
    assert client.get('/api/observations.jpg').status_code == 409
    assert client.get('/api/trace').json()['simulation']


def test_shared_model_lock_released_after_failure(client,monkeypatch):
    def fail(*a,**k): raise ValueError('Invalid model response')
    monkeypatch.setattr(module,'decide',fail)
    state=client.get('/api/state').json()
    assert step(client,state).status_code == 422
    assert module.model_lock.acquire(False)
    module.model_lock.release()
    assert module.world.revision == 0


@pytest.mark.parametrize('scenario,success',[
    ('open_resistor',True),('healthy',True),('supply_off',False),('bad_spare',False)])
def test_real_scripted_run(monkeypatch,scenario,success):
    if importlib.util.find_spec('arm_sim.resistor.world') is None:
        pytest.skip('Resistor physics world has not landed yet')
    monkeypatch.setattr(module,'world',None)
    client=TestClient(module.app)
    try:
        response=client.post('/api/reset',json={'scenario':scenario,'perception':'oracle'})
        assert response.status_code == 200,response.text
        state=response.json()
        for _ in range(20):
            if state['done']: break
            response=client.post('/api/step',json=dict(mode='scripted',
                revision=state['revision'],episode=state['episode']))
            assert response.status_code == 200,response.text
            state=response.json()['state']
        assert state['done'] and state['success'] is success
        if scenario == 'open_resistor':
            assert any(m['point']=='input' and m['voltage']==5 for m in state['measurements'])
            assert state['measurements'][-1]['voltage'] == pytest.approx(2,abs=.1)
        if scenario in ('healthy','supply_off'):
            assert not any(e['action']=='remove_resistor' for e in state['events'])
    finally:
        if module.world is not None: module.world.bench.close()


def test_planner_compacts_evidence_and_retries_once(monkeypatch,tmp_path):
    import copy
    from arm_sim.resistor import planner
    messages=[]
    class Conversation:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def send_message(self,message):
            messages.append(message)
            return 'invalid JSON' if len(messages)==1 else '{"action":"dock_probe","reason":"Dock for replacement"}'
    class Engine:
        def create_conversation(self,**kwargs): return Conversation()
    model=tmp_path/'fake.litertlm'
    model.write_text('mock')
    monkeypatch.setattr(planner,'MODEL',model)
    monkeypatch.setattr(planner.vision,'engine',Engine())
    observation=dict(targets={'probe':[.2,-.15,.06]},allowed_actions=['dock_probe','abort'],
        measurements=[dict(point='input',voltage=5,valid_contact=True),
                      dict(point='output',voltage=0,valid_contact=True)],
        perception=dict(detections={'probe':{'matrix':'PRIVATE_MATRIX'}},missing=[]))
    original=copy.deepcopy(observation)
    result=planner.decide(observation,[dict(action='measure_output',note='TP2 reads 0V',ok=True,
        decision={'reason':'UNTRUSTED_OLD_EXPLANATION'})])
    assert result['formatting_retries']==1 and len(messages)==2
    assert 'UNTRUSTED_OLD_EXPLANATION' not in messages[0] and 'PRIVATE_MATRIX' not in messages[0]
    assert 'TP2 reads 0V' in messages[0] and observation==original


def test_combined_shutdown_closes_bench(client,monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def previous(application): yield
    monkeypatch.setattr(module,'_previous_lifespan',previous)
    client.get('/api/state')
    world=module.world
    async def shutdown():
        async with module.lifespan(module.combined_app): pass
    asyncio.run(shutdown())
    assert world.closed
