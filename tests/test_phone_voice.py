import base64
import io
import json
from fastapi.testclient import TestClient
from PIL import Image
import circuit_lab.phone as phone
import circuit_lab.speech as speech
from circuit_lab.app import app
from circuit_lab.inference import parse_observation


def jpeg(color):
    output = io.BytesIO()
    Image.new('RGB', (80, 60), color).save(output, 'JPEG')
    return base64.b64encode(output.getvalue()).decode()


def test_pairing_is_local_and_upload_requires_token():
    with TestClient(app, client=('192.168.2.99', 50000)) as remote:
        assert remote.get('/phone').status_code == 200
        for path in ('/api/phone/info', '/api/phone/qr', '/api/phone/latest'):
            assert remote.get(path).status_code == 403
        assert remote.post('/api/phone/frame', json={'image': jpeg('red')}).status_code == 401
        assert remote.post('/api/phone/frame', headers={'Authorization': 'Bearer wrong'}, json={'image': jpeg('red')}).status_code == 401
        assert remote.post('/api/speak', json={'text': 'hello'}).status_code == 403
    with TestClient(app, client=('127.0.0.1', 50000)) as local:
        assert phone.TOKEN in local.get('/api/phone/info').json()['url']
        response = local.get('/api/phone/qr')
        assert response.status_code == 200 and '<svg' in response.text


def test_only_latest_phone_photo_is_retained(monkeypatch):
    monkeypatch.setattr(phone, 'latest', None)
    monkeypatch.setattr(phone, 'sequence', 0)
    auth = {'Authorization': f'Bearer {phone.TOKEN}'}
    with TestClient(app, client=('127.0.0.1', 50000)) as local:
        assert local.get('/api/phone/latest').status_code == 204
        assert local.post('/api/phone/frame', headers=auth, json={'image': 'bad'}).status_code == 400
        for color in ('red', 'blue'):
            assert local.post('/api/phone/frame', headers=auth, json={'image': jpeg(color)}).status_code == 200
        frame = local.get('/api/phone/latest?after=1').json()
        assert frame['sequence'] == 2
        image = Image.open(io.BytesIO(base64.b64decode(frame['image'].split(',')[1])))
        assert image.getpixel((20, 20))[2] > 240
        assert local.get('/api/phone/latest?after=2').status_code == 204


def test_led_state_and_spoken_findings_are_validated():
    result = parse_observation(json.dumps(dict(pins={}, summary='LED appears dark', uncertainties=[], led_state='unlit', spoken_feedback='The LED appears unlit.')))
    assert result['led_state'] == 'unlit'
    assert result['spoken_feedback'] == 'The LED appears unlit.'
    result = parse_observation(json.dumps(dict(pins={}, led_state='definitely broken', spoken_feedback=3)))
    assert result['led_state'] == 'uncertain' and result['spoken_feedback'] == ''


def test_speech_returns_local_audio_and_rejects_overlapping_synthesis(monkeypatch):
    class Audio(io.BytesIO):
        pass
    def synth(request, timeout):
        data = json.loads(request.data)
        assert data['model'] == 'kokoro' and data['input'] == 'The LED appears unlit.'
        assert data['stream'] is False
        return Audio(b'RIFF' + b'\x00' * 40)
    monkeypatch.setattr(speech.urllib.request, 'urlopen', synth)
    with TestClient(app, client=('127.0.0.1', 50000)) as local:
        response = local.post('/api/speak', json={'text': 'The LED appears unlit.'})
        assert response.status_code == 200 and response.content.startswith(b'RIFF')
        assert response.headers['X-Speech-Engine'] == 'Kokoro'
        assert local.post('/api/speak', json={'text': ''}).status_code == 422
        speech.speech_lock.acquire()
        try:
            assert local.post('/api/speak', json={'text': 'hello'}).status_code == 409
        finally:
            speech.speech_lock.release()


def test_tunnel_cannot_reach_dashboard_pairing_or_simulator():
    with TestClient(app, base_url='http://camera-relay.invalid', client=('127.0.0.1', 50000)) as client:
        for path in ('/', '/api/phone/info', '/api/phone/qr', '/api/health', '/sim/', '/api/live/state', '/api/docs'):
            assert client.get(path).status_code == 403
        assert client.get('/phone').status_code == 200
        assert client.get('/static/phone.js').status_code == 200
        assert client.post('/api/phone/frame', json={'image': jpeg('red')}).status_code == 401


def test_blank_frame_never_reaches_model(monkeypatch, tmp_path):
    import circuit_lab.app as module
    model = tmp_path / 'model'; model.touch()
    monkeypatch.setattr(module, 'MODEL', model)
    def unexpected(*args, **kwargs):
        raise AssertionError('Blank frame must not reach the vision model')
    monkeypatch.setattr(module.vision, 'analyze', unexpected)
    with TestClient(app) as client:
        result = client.post('/api/analyze', json={'image': jpeg('white')}).json()
        assert result['quality_rejected']
        assert result['led_state'] == 'uncertain'
        assert all(value is None for value in result['pins'].values())


def test_background_worker_skips_paused_and_duplicate_frames(monkeypatch):
    import circuit_lab.app as module
    import circuit_lab.live as live
    local_state = {**live.state, 'voice': False, 'paused': False, 'processed': 0}
    monkeypatch.setattr(live, 'state', local_state)
    monkeypatch.setattr(phone, 'latest', None)
    seen = []
    class Clock:
        tick = 0
        def wait(self, delay):
            self.tick += 1
            if self.tick > 4:
                return True
            local_state['paused'] = self.tick == 1
            phone.latest = dict(sequence=7 if self.tick == 4 else 4, image=str(self.tick if self.tick == 4 else 2))
            return False
        def is_set(self):
            return False
    clock = Clock()
    monkeypatch.setattr(live, 'shutdown', clock)
    monkeypatch.setattr(live.time, 'monotonic', lambda: clock.tick * 100)
    def analyze(capture):
        assert capture.live is True
        seen.append(capture.image)
        return dict(summary='test', spoken_feedback='test finding', seconds=1, led_state='uncertain')
    monkeypatch.setattr(module, 'analyze', analyze)
    live.run()
    assert seen == ['2', '4']
    assert local_state['processed'] == 2 and local_state['sequence'] == 7
