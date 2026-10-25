"""Unattended phone-frame inspection and local speaker output."""
import os
import threading
import time
from fastapi import APIRouter, Request
from pydantic import BaseModel
from . import phone
from .speech import play_on_mac, stop_playback

router = APIRouter()
state_lock = threading.Lock()
state = dict(phase='waiting', paused=False, voice=True, processed=0, sequence=0,
             summary='', spoken_feedback='', led_state='uncertain', error='', seconds=None,
             demo=False, demo_step='', feed=[])
shutdown = threading.Event()
thread = None


class Settings(BaseModel):
    paused: bool | None = None
    voice: bool | None = None


def update(**values):
    with state_lock:
        state.update(values)


@router.get('/api/live/state')
def get_state(request: Request):
    phone.require_local(request)
    with state_lock, phone.frame_lock:
        return {**state, 'running': thread is not None and thread.is_alive(),
                'received_sequence': phone.sequence,
                'received_at': phone.latest['received_at'] if phone.latest else None}


@router.post('/api/live/settings')
def settings(body: Settings, request: Request):
    phone.require_local(request)
    update(**body.model_dump(exclude_none=True))
    if body.voice is False or body.paused is True:
        stop_playback()
    return get_state(request)


def run():
    from .app import analyze, Capture
    last_sequence = 0
    last_attempt = 0
    last_spoken = ''
    while not shutdown.wait(.5):
        with state_lock:
            paused = state['paused']
        if paused or time.monotonic() - last_attempt < 10:
            continue
        with phone.frame_lock:
            frame = phone.latest.copy() if phone.latest else None
        if frame is None or frame['sequence'] <= last_sequence:
            continue
        last_attempt = time.monotonic()
        update(phase='inspecting', error='')
        try:
            result = analyze(Capture(image=frame['image'], live=True))
            last_sequence = frame['sequence']
            with state_lock:
                count = state['processed'] + 1
                paused = state['paused']
                voice = state['voice']
            if paused:
                update(phase='paused')
                continue
            text = result.get('spoken_feedback') or result['summary']
            update(phase='ready', processed=count, sequence=last_sequence,
                   summary=result['summary'], spoken_feedback=text,
                   led_state=result.get('led_state', 'uncertain'), seconds=result['seconds'])
            print(f"[camera {last_sequence}] LED={result.get('led_state', 'uncertain')} {text}", flush=True)
            with state_lock:
                demo = state['demo']
            if voice and not demo and text != last_spoken:   # the robot demo narrates instead
                update(phase='speaking')
                played = play_on_mac(text, allowed=lambda: state['voice'] and not state['paused'] and not shutdown.is_set())
                if played['played']:
                    last_spoken = text
                update(phase='ready')
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            update(phase='error', error=str(detail))
            print(f'[camera] {detail}', flush=True)


class DemoControl(BaseModel):
    active: bool
    step: str = ''


class Narration(BaseModel):
    step: str
    facts: str


@router.post('/api/demo/control')
def demo_control(body: DemoControl, request: Request):
    phone.require_local(request)
    with state_lock:
        state.update(demo=body.active, demo_step=body.step)
        if body.active and not body.step: state['feed'] = []
    return dict(ok=True)


@router.post('/api/demo/narrate')
def demo_narrate(body: Narration, request: Request):
    """Gemma comments on a robot demo step; the text streams into the dashboard feed, then plays on the Mac."""
    phone.require_local(request)
    from .app import lock
    from .assistant import client
    item = dict(step=body.step, text='', done=False, t=time.time())
    with state_lock:
        state['feed'] = (state['feed'] + [item])[-12:]
        state['demo_step'] = body.step
    messages = [dict(role='system', content=(
        'You are Gemma, the live commentator for a robot-arm circuit repair demo running on a Jetson. '
        'Speak to the audience in one or two short, lively spoken sentences. State measured numbers exactly as given. '
        'Plain text only, no markdown, no emojis.')),
        dict(role='user', content=f'Step: {body.step}. What just happened: {body.facts}')]
    got = lock.acquire(timeout=90)               # wait for any in-flight frame inspection on the Jetson
    try:
        for chunk in client.stream(messages):
            with state_lock: item['text'] += chunk
    except Exception as exc:
        with state_lock: item['text'] = item['text'] or body.facts
        print(f'[demo] Gemma unavailable: {exc}', flush=True)
    finally:
        if got: lock.release()
    text = ' '.join(item['text'].split())[:600]
    with state_lock:
        item.update(text=text, done=True); state['phase'] = 'speaking'
    play_on_mac(text, allowed=lambda: state['voice'])
    update(phase='ready')
    return dict(text=text)


def start():
    global thread
    if os.environ.get('CIRCUIT_AUTO_INSPECT') == '1' and (thread is None or not thread.is_alive()):
        shutdown.clear()
        thread = threading.Thread(target=run, daemon=True, name='circuit-camera')
        thread.start()


def stop():
    shutdown.set()
    stop_playback()
