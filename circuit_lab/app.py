import base64
import binascii
import io
import tempfile
import threading
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from .circuit import Pins, inspect
from .inference import LocalVision, MODEL, BACKEND, VISION_BACKEND, THINKING

app = FastAPI(title='Circuit Lab', docs_url='/api/docs')
static = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=static), name='static')
vision = LocalVision()
lock = threading.Lock()

class Capture(BaseModel):
    image: str = Field(max_length=8_000_000)
    detailed: bool = False

@app.get('/')
def index():
    return FileResponse(static / 'index.html')

@app.get('/api/health')
def health():
    return dict(model_present=MODEL.is_file(), model=MODEL.name, backend=BACKEND, vision_backend=VISION_BACKEND, thinking=THINKING,
                loaded=vision.engine is not None, busy=lock.locked(), runtime='LiteRT-LM', local_only=True)

@app.post('/api/check')
def check(pins: Pins):
    return inspect(pins)

@app.post('/api/analyze')
def analyze(capture: Capture):
    if not MODEL.is_file():
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
        with tempfile.TemporaryDirectory(prefix='circuit-') as directory:
            path = Path(directory) / 'frame.jpg'
            image.save(path, quality=95)
            result = vision.analyze(path, detailed=capture.detailed)
        return {**result, 'seconds': round(time.monotonic()-start, 2), 'model': MODEL.name, 'detailed': capture.detailed, 'requires_review': True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f'Local inference failed: {exc}') from exc
    finally:
        lock.release()
