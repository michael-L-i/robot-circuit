"""Local Kokoro synthesis with a macOS system voice fallback."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from .phone import require_local

router = APIRouter()
speech_lock = threading.Lock()
playback_lock = threading.Lock()
process_lock = threading.Lock()
player = None
TTS_URL = os.environ.get('CIRCUIT_TTS_URL', 'http://127.0.0.1:8880/v1/audio/speech')


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=1500)


@router.post('/api/speak')
def speak(body: Speech, request: Request):
    require_local(request)
    return synthesize(body.text)


def stop_playback():
    with process_lock:
        if player is not None and player.poll() is None:
            player.terminate()


def play_on_mac(text, allowed=lambda: True):
    """One Mac speaker for both automatic findings and explicit chat replies."""
    global player
    with playback_lock:
        if not allowed():
            return {'played': False}
        if not Path('/usr/bin/afplay').exists():
            raise HTTPException(503, 'Run the workbench server on the Mac to use its speakers.')
        audio = synthesize(text[:1500])
        with tempfile.TemporaryDirectory(prefix='circuit-voice-') as directory:
            path = Path(directory) / 'reply.wav'
            path.write_bytes(audio.body)
            with process_lock:
                if not allowed():
                    return {'played': False}
                player = subprocess.Popen(['/usr/bin/afplay', str(path)], stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
            try:
                code = player.wait(timeout=90)
                if code and allowed():
                    raise HTTPException(503, 'Mac audio playback failed. Check the selected output device.')
                return {'played': code == 0, 'engine': audio.headers.get('X-Speech-Engine')}
            finally:
                with process_lock:
                    if player.poll() is None:
                        player.terminate()
                        player.wait(timeout=5)
                    player = None


@router.post('/api/speaker/play')
def speaker_play(body: Speech, request: Request):
    require_local(request)
    from . import live
    return play_on_mac(body.text, allowed=lambda: live.state['voice'])


def synthesize(text):
    if not speech_lock.acquire(blocking=False):
        raise HTTPException(409, 'Speech is already being generated.')
    try:
        payload = json.dumps(dict(model='kokoro', input=text, voice='af_heart',
                                  response_format='wav', stream=False)).encode()
        req = urllib.request.Request(TTS_URL, data=payload, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                audio = response.read()
                if not audio.startswith(b'RIFF'):
                    raise ValueError('TTS did not return a WAV file')
            return Response(audio, media_type='audio/wav', headers={'X-Speech-Engine': 'Kokoro', 'Cache-Control': 'no-store'})
        except (OSError, ValueError, urllib.error.URLError):
            if not Path('/usr/bin/say').exists():
                raise HTTPException(503, 'Start a local Kokoro server, or use the browser voice fallback.')
            with tempfile.TemporaryDirectory(prefix='circuit-speech-') as directory:
                path = Path(directory) / 'speech.wav'
                subprocess.run(['/usr/bin/say', '--file-format=WAVE', '--data-format=LEI16@22050',
                                '-o', str(path), '--', text], check=True, timeout=45, capture_output=True)
                return Response(path.read_bytes(), media_type='audio/wav',
                                headers={'X-Speech-Engine': 'macOS', 'Cache-Control': 'no-store'})
    except (subprocess.SubprocessError, OSError) as exc:
        raise HTTPException(503, 'Local speech synthesis failed. Try the browser voice.') from exc
    finally:
        speech_lock.release()
