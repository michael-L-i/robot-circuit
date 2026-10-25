"""Jetson inference over Ollama's HTTP API (normally an SSH loopback tunnel)."""
import base64
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


class OllamaClient:
    def __init__(self, url=None, model=None):
        self.url = (url or os.getenv('CIRCUIT_OLLAMA_URL', 'http://127.0.0.1:11435')).rstrip('/')
        self.model = model or os.getenv('CIRCUIT_OLLAMA_MODEL', 'gemma4:31b')

    def open(self, endpoint, payload=None, timeout=180):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.url + endpoint, data=data,
                                         headers={'Content-Type': 'application/json'})
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2000).decode(errors='replace')
            raise RuntimeError(f'Jetson inference returned HTTP {exc.code}: {detail}') from exc
        except OSError as exc:
            raise RuntimeError('Cannot reach Jetson inference. Check the SSH tunnel and Jetson power/network.') from exc

    def status(self):
        with self.open('/api/tags', timeout=3) as response:
            names = [item['name'] for item in json.load(response).get('models', [])]
        return {'reachable': True, 'model_present': self.model in names, 'model': self.model}

    def payload(self, messages, stream=False, structured=False):
        result = dict(model=self.model, messages=messages, stream=stream, think=False,
                      keep_alive='30m', options=dict(num_ctx=8192, num_predict=700, temperature=0.1))
        if structured:
            result['format'] = 'json'
        return result

    def complete(self, messages, structured=False):
        with self.open('/api/chat', self.payload(messages, structured=structured)) as response:
            result = json.load(response)
        if result.get('error'):
            raise RuntimeError(result['error'])
        if not result.get('done') or result.get('done_reason') == 'length':
            raise RuntimeError('Jetson response was incomplete. Try a shorter question.')
        return result['message']['content']

    def stream(self, messages):
        with self.open('/api/chat', self.payload(messages, stream=True)) as response:
            for line in response:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get('error'):
                    raise RuntimeError(event['error'])
                content = event.get('message', {}).get('content', '')
                if content:
                    yield content
                if event.get('done'):
                    if event.get('done_reason') == 'length':
                        raise RuntimeError('The response reached its length limit; ask a shorter question.')
                    return
        raise RuntimeError('The Jetson connection ended before the response completed.')


class OllamaVision:
    def __init__(self, client=None):
        self.client = client or OllamaClient()

    def analyze(self, image_path, detailed=False, simple=False):
        from .inference import LIVE_PROMPT, PROMPT, parse_observation
        encoded = base64.b64encode(Path(image_path).read_bytes()).decode()
        raw = self.client.complete([dict(role='user', content=LIVE_PROMPT if simple else PROMPT,
                                         images=[encoded])], structured=True)
        return parse_observation(raw)
