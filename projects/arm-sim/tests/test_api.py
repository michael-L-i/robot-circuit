from fastapi.testclient import TestClient
from arm_sim.app import app
import arm_sim.app as module

client=TestClient(app)

def test_scripted_http_roundtrip_and_stale_rejection():
    assert client.post('/api/reset',json={}).status_code==200
    assert client.post('/api/step',json={'mode':'scripted','revision':99}).status_code==409
    for rev in range(9):
        r=client.post('/api/step',json={'mode':'scripted','revision':rev})
        assert r.status_code==200,r.text
    data=client.get('/api/trace').json()
    assert data['simulation'] and data['state']['success']
    assert client.post('/api/step',json={'mode':'scripted','revision':9}).status_code==409

def test_invalid_model_response_does_not_move(monkeypatch):
    client.post('/api/reset',json={})
    def fail(*args): raise ValueError('Invalid model response')
    monkeypatch.setattr(module,'decide',fail)
    assert client.post('/api/step',json={'mode':'gemma','revision':0}).status_code==422
    assert client.get('/api/state').json()['revision']==0

def test_inputs_and_static_assets():
    assert client.post('/api/reset',json={'scenario':'unknown'}).status_code==422
    assert client.post('/api/reset',json={'placement_error_mm':31}).status_code==422
    assert client.get('/').status_code==200
    assert client.get('/static/app.js').status_code==200

def test_reset_invalidates_stale_steps_and_clips():
    old = client.post('/api/reset',json={}).json()
    current=client.post('/api/reset',json={'scenario':'supply_off'}).json()
    assert client.post('/api/step',json={'mode':'scripted','revision':0,'episode':old['episode']}).status_code==409
    assert client.post('/api/step',json={'mode':'scripted','revision':0}).status_code==200
    video=client.get('/api/action.mp4',params={'r':1,'episode':current['episode']})
    assert video.status_code==200
    assert video.headers['content-type']=='video/mp4'
    assert b'ftyp' in video.content[:32]
    assert client.get('/api/action.mp4',params={'r':1,'episode':old['episode']}).status_code==409
    assert client.get('/api/action.mp4?r=0').status_code==409
    client.post('/api/reset',json={'backend':'kinematic'})
    assert client.get('/api/render.jpg').status_code==409

def test_step_waits_for_short_camera_render_lock():
    import threading
    client.post('/api/reset',json={})
    module.world_lock.acquire()
    timer=threading.Timer(.05,module.world_lock.release)
    timer.start()
    try:
        response=client.post('/api/step',json={'mode':'scripted','revision':0})
        assert response.status_code==200,response.text
    finally:timer.join()
