import base64
import binascii
import io
import os
import tempfile
import threading
import time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, ImageStat, UnidentifiedImageError
from .circuit import Pins, inspect
from .inference import LocalVision, MODEL, BACKEND, VISION_BACKEND, THINKING
from .phone import router as phone_router
from .speech import router as speech_router
from . import live
from .assistant import router as assistant_router
from .ollama import OllamaVision

@asynccontextmanager
async def lifespan(application):
    live.start()
    try:
        yield
    finally:
        live.stop()

app = FastAPI(title='Circuit Lab', docs_url='/api/docs', lifespan=lifespan)
app.include_router(phone_router)
app.include_router(speech_router)
app.include_router(live.router)
app.include_router(assistant_router)

@app.middleware('http')
async def camera_gateway(request, call_next):
    # Cloudflared fixes this Host header. The tunnel cannot reach the dashboard,
    # model/speech APIs, pairing secret, or either simulator.
    if request.url.hostname == 'camera-relay.invalid':
        allowed = {'/phone', '/static/phone.js', '/static/live-loop.mjs',
                   '/static/style.css', '/api/phone/frame'}
        if request.url.path not in allowed:
            from fastapi.responses import Response
            return Response('Camera upload endpoint only', status_code=403)
    return await call_next(request)
static = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=static), name='static')
vision = LocalVision()
# Keep the simulator's existing local engine intact; only camera inspection is routed.
INFERENCE = os.getenv('CIRCUIT_INFERENCE', 'local')
if INFERENCE not in ('local', 'ollama'):
    raise ValueError('CIRCUIT_INFERENCE must be local or ollama')
remote_vision = OllamaVision()
lock = threading.Lock()

class Capture(BaseModel):
    image: str = Field(max_length=8_000_000)
    detailed: bool = False
    live: bool = False

@app.get('/')
def index():
    return FileResponse(static / 'live.html')

@app.get('/review')
def detailed_review():
    return FileResponse(static / 'index.html')

@app.get('/api/health')
def health():
    if INFERENCE == 'ollama':
        return dict(model=remote_vision.client.model, backend='Jetson', runtime='Ollama',
                    busy=lock.locked(), model_present=None, loaded=None, local_only=False,
                    inference_location='Jetson over SSH; no cloud inference', speaker='Mac')
    return dict(model_present=MODEL.is_file(), model=MODEL.name, backend=BACKEND, vision_backend=VISION_BACKEND, thinking=THINKING,
                loaded=vision.engine is not None, busy=lock.locked(), runtime='LiteRT-LM', local_only=True)

@app.post('/api/check')
def check(pins: Pins):
    return inspect(pins)

@app.post('/api/analyze')
def analyze(capture: Capture):
    if INFERENCE == 'local' and not MODEL.is_file():
        raise HTTPException(503, 'Model missing. Run uv run python scripts/download_model.py')
    if not lock.acquire(blocking=False):
        raise HTTPException(409, 'An inspection is already running. Wait for it to finish.')
    start = time.monotonic()
    try:
        try:
            data = capture.image.split(',', 1)[-1]
            image = Image.open(io.BytesIO(base64.b64decode(data, validate=True)))
            if image.width * image.height > 16_000_000:
                raise ValueError('Image exceeds 16 megapixels.')
            image.load()
            image = image.convert('RGB')
            image.thumbnail((1600, 1600))
        except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise HTTPException(400, 'Use a valid JPEG or PNG under 16 megapixels.') from exc
        if max(ImageStat.Stat(image).stddev) < 2:
            # Reject near-uniform/covered-lens frames before asking the VLM to
            # interpret a circuit. It can otherwise hallucinate the prompt's board.
            return dict(circuit_present=None, summary='This frame has too little visible detail to inspect a circuit.',
                        visual_analysis='', led_state='uncertain',
                        spoken_feedback='I cannot see enough detail in this frame to check the LED. Check that the camera is uncovered and pointed at the board.',
                        uncertainties=['Near-uniform image; circuit details are not visible.'], next_view='Point the camera at the circuit in good light.',
                        pin_evidence={}, pins=Pins().model_dump(), seconds=round(time.monotonic()-start, 2),
                        model=remote_vision.client.model if INFERENCE == 'ollama' else MODEL.name,
                        detailed=capture.detailed, requires_review=True, quality_rejected=True)
        with tempfile.TemporaryDirectory(prefix='circuit-') as directory:
            path = Path(directory) / 'frame.jpg'
            image.save(path, quality=95)
            provider = remote_vision if INFERENCE == 'ollama' else vision
            result = provider.analyze(path, detailed=capture.detailed, simple=capture.live)
        return {**result, 'seconds': round(time.monotonic()-start, 2),
                'model': remote_vision.client.model if INFERENCE == 'ollama' else MODEL.name,
                'detailed': capture.detailed, 'requires_review': True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f'Inference failed: {exc}') from exc
    finally:
        lock.release()
