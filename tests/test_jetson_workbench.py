import base64
import io
import json
import time
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
import circuit_lab.app as module
import circuit_lab.assistant as assistant
import circuit_lab.phone as phone
import circuit_lab.speech as speech
from circuit_lab.ollama import OllamaClient, OllamaVision


def events(response):
    return [json.loads(line) for line in response.text.splitlines()]


def test_chat_stream_and_lock_recovery(monkeypatch):
    def stream(messages):
        assert 'resistor replacement' in messages[0]['content']
        assert messages[-1]['content'] == 'What next?'
        assert 'images' not in messages[-1]
        yield 'Check '
        yield 'the probe reference.'
    monkeypatch.setattr(assistant.client, 'stream', stream)
    with TestClient(module.app, client=('127.0.0.1', 1)) as client:
        result = events(client.post('/api/assistant/chat', json={'prompt': 'What next?'}))
        assert ''.join(e.get('text', '') for e in result) == 'Check the probe reference.'
        assert result[-1]['type'] == 'done'
        assert not module.lock.locked()
        def broken(messages):
            yield 'Partial'
            raise RuntimeError('Connection lost')
        monkeypatch.setattr(assistant.client, 'stream', broken)
        result = events(client.post('/api/assistant/chat', json={'prompt': 'Again'}))
        assert result[-1]['type'] == 'error'
        assert not any(e['type'] == 'done' for e in result)
        assert not module.lock.locked()


def test_camera_requires_fresh_frame_and_passes_real_image(monkeypatch):
    with TestClient(module.app, client=('127.0.0.1', 1)) as client:
        monkeypatch.setattr(phone, 'latest', None)
        assert client.post('/api/assistant/chat', json={'prompt': 'Look', 'use_camera': True}).status_code == 409
        frame = dict(received_at=time.time()-60, image='data:image/jpeg;base64,YWJj', sequence=3)
        monkeypatch.setattr(phone, 'latest', frame)
        assert client.post('/api/assistant/chat', json={'prompt': 'Look', 'use_camera': True}).status_code == 409
        frame['received_at'] = time.time()
        def stream(messages):
            assert messages[-1]['images'] == ['YWJj']
            yield 'Image received'
        monkeypatch.setattr(assistant.client, 'stream', stream)
        result = events(client.post('/api/assistant/chat', json={'prompt': 'Look', 'use_camera': True}))
        assert result[-1]['frame_sequence'] == 3


def test_busy_chat_does_not_release_other_inference_lock():
    with TestClient(module.app, client=('127.0.0.1', 1)) as client:
        module.lock.acquire()
        try:
            result = events(client.post('/api/assistant/chat', json={'prompt': 'Hello'}))
            assert result[0]['type'] == 'error' and module.lock.locked()
        finally:
            module.lock.release()


def test_remote_and_tunnel_cannot_access_chat_or_speaker():
    with TestClient(module.app, client=('192.168.2.90', 1)) as client:
        assert client.get('/api/system').status_code == 403
        assert client.post('/api/assistant/chat', json={'prompt': 'Hello'}).status_code == 403
        assert client.post('/api/speaker/play', json={'text': 'Hello'}).status_code == 403
    with TestClient(module.app, base_url='http://camera-relay.invalid', client=('127.0.0.1', 1)) as client:
        assert client.get('/api/system').status_code == 403
        assert client.post('/api/assistant/chat', json={'prompt': 'Hello'}).status_code == 403


def test_remote_inspection_does_not_require_local_model(monkeypatch, tmp_path):
    monkeypatch.setattr(module, 'INFERENCE', 'ollama')
    monkeypatch.setattr(module, 'MODEL', tmp_path/'missing')
    captured = []
    def complete(messages, structured=False):
        assert structured and 'resistor replacement' in messages[0]['content']
        captured.append(Image.open(io.BytesIO(base64.b64decode(messages[0]['images'][0]))).size)
        return json.dumps(dict(pins={}, summary='No circuit visible', circuit_present=False, uncertainties=[]))
    monkeypatch.setattr(module.remote_vision.client, 'complete', complete)
    picture=Image.new('RGB',(80,60),'white');ImageDraw.Draw(picture).rectangle((10,10,40,40),fill='red')
    output=io.BytesIO();picture.save(output,'PNG')
    with TestClient(module.app) as client:
        result=client.post('/api/analyze',json={'image':base64.b64encode(output.getvalue()).decode(),'live':True})
        assert result.status_code == 200 and result.json()['model']=='gemma4:31b'
        assert result.json()['circuit_present'] is False
    assert captured == [(80,60)]


def test_ollama_stream_ignores_thinking_and_rejects_truncated_transport(monkeypatch):
    client=OllamaClient()
    def response(*args,**kwargs):
        return io.BytesIO(b'{"message":{"thinking":"private","content":"Hello"}}\n{"done":true}\n')
    monkeypatch.setattr(client,'open',response)
    assert list(client.stream([]))==['Hello']
    monkeypatch.setattr(client,'open',lambda *args,**kwargs:io.BytesIO(b'{"message":{"content":"Partial"}}\n'))
    with pytest.raises(RuntimeError,match='before the response completed'):
        list(client.stream([]))


def test_mute_skips_speech_and_stops_player(monkeypatch):
    import circuit_lab.live as live
    monkeypatch.setattr(live,'state',{**live.state,'voice':True})
    stopped=[]
    monkeypatch.setattr(live,'stop_playback',lambda:stopped.append(True))
    monkeypatch.setattr(speech,'synthesize',lambda text:pytest.fail('Muted voice must not synthesize'))
    with TestClient(module.app,client=('127.0.0.1',1)) as client:
        client.post('/api/live/settings',json={'voice':False})
        assert client.post('/api/speaker/play',json={'text':'Hello'}).json()=={'played':False}
    assert stopped
