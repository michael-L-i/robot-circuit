"""Single paired camera, latest frame only. Images never persist on disk."""
import base64
import io
import ipaddress
import os
import secrets
import socket
import threading
import time
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from pathlib import Path

router = APIRouter()
TOKEN = secrets.token_urlsafe(24)
PUBLIC_URL = None
frame_lock = threading.Lock()
latest = None
sequence = 0


def authorize(authorization):
    if not secrets.compare_digest(authorization or '', f'Bearer {TOKEN}'):
        raise HTTPException(401, 'Pair this phone by scanning the QR code on your Mac.')


def require_local(request):
    try:
        if ipaddress.ip_address(request.client.host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(403, 'Open the dashboard on the Mac at http://127.0.0.1:8000 to pair a phone.')


def lan_ip():
    override = os.environ.get('CIRCUIT_LAN_IP')
    if override:
        return str(ipaddress.ip_address(override))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(('192.0.2.1', 9))  # Route lookup; no packet is sent.
            return sock.getsockname()[0]
        except OSError:
            return '127.0.0.1'


def phone_url(request):
    if PUBLIC_URL:
        return f'{PUBLIC_URL}/phone#{TOKEN}'
    port = request.url.port or (443 if request.url.scheme == 'https' else 80)
    return f'{request.url.scheme}://{lan_ip()}:{port}/phone#{TOKEN}'


@router.get('/phone')
def phone_page():
    return FileResponse(Path(__file__).parent / 'static/phone.html', headers={'Cache-Control': 'no-store'})


@router.get('/api/phone/info')
def info(request: Request):
    require_local(request)
    with frame_lock:
        return dict(url=phone_url(request), sequence=sequence,
                    received_at=latest['received_at'] if latest else None)


@router.get('/api/phone/qr')
def qr(request: Request):
    require_local(request)
    import qrcode
    from qrcode.image.svg import SvgPathImage
    output = io.BytesIO()
    qrcode.make(phone_url(request), image_factory=SvgPathImage, border=4).save(output)
    return Response(output.getvalue(), media_type='image/svg+xml', headers={'Cache-Control': 'no-store'})


class PhoneFrame(BaseModel):
    image: str = Field(max_length=8_000_000)


@router.post('/api/phone/frame')
def upload_frame(capture: PhoneFrame, authorization: str | None = Header(default=None)):
    authorize(authorization)
    try:
        image = Image.open(io.BytesIO(base64.b64decode(capture.image.split(',')[-1], validate=True)))
        if image.width * image.height > 16_000_000:
            raise ValueError('Image too large')
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((1600, 1600))
        output = io.BytesIO()
        image.save(output, 'JPEG', quality=93)
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, 'Send a valid JPEG or PNG under 16 megapixels.') from exc
    global latest, sequence
    with frame_lock:
        sequence += 1
        latest = dict(sequence=sequence, image='data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode(),
                      received_at=time.time())
        return dict(sequence=sequence, received_at=latest['received_at'])


@router.get('/api/phone/latest')
def latest_frame(request: Request, after: int = 0):
    require_local(request)
    with frame_lock:
        if latest is None or latest['sequence'] <= after:
            return Response(status_code=204, headers={'Cache-Control': 'no-store'})
        from fastapi.responses import JSONResponse
        return JSONResponse(latest, headers={'Cache-Control': 'no-store'})

