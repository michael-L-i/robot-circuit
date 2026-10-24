import gc
import io
import threading
import time
import tempfile
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image
from circuit_lab.app import app as combined_app, vision, lock as model_lock
from .planner import decide

app = FastAPI(title='Open resistor repair simulation')
static = Path(__file__).parent/'static'
app.mount('/static', StaticFiles(directory=static), name='static')
world = None

def create_world(config):
    from .world import ResistorWorld, ResistorConfig
    return ResistorWorld(ResistorConfig(**config))

def get_world():
    global world
    # Caller owns world_lock; importing the app never allocates a physics world.
    if world is None: world = create_world(Reset().model_dump())
    return world

def scripted_action(world):
    from .world import scripted_action as policy
    return policy(world)
world_lock = threading.Lock()
progress = dict(phase="idle", action=None, started=time.monotonic())

class Reset(BaseModel):
    scenario: Literal['open_resistor','healthy','supply_off','bad_spare'] = 'open_resistor'
    seed: int = Field(default=7, ge=0, le=1000000)
    perception: Literal['camera_markers','oracle'] = 'camera_markers'

class Step(BaseModel):
    mode: Literal['gemma','scripted'] = 'gemma'
    revision: int
    episode: str

@app.get('/')
def index(): return FileResponse(static/'index.html',headers={'Cache-Control':'no-store'})

@app.get('/api/state')
def state():
    with world_lock: return get_world().snapshot()

@app.post('/api/reset')
def reset(config: Reset):
    global world
    if not world_lock.acquire(timeout=3): raise HTTPException(409,'Simulation or renderer is busy; wait for the current operation')
    try:
        if world is not None:
            world.bench.close()
            world = None
        world = create_world(config.model_dump())
        phase('idle')
        return world.snapshot()
    finally: world_lock.release()

def phase(name,action=None,model_seconds=None):
    global progress
    progress=dict(phase=name,action=action,model_seconds=model_seconds,started=time.monotonic())

@app.get('/api/progress')
def get_progress():
    p=progress.copy()
    return {**p,'elapsed':round(time.monotonic()-p.pop('started'),1)}

@app.post('/api/step')
def step(request: Step):
    global world
    if not world_lock.acquire(timeout=3): raise HTTPException(409,'Simulation or renderer is busy; wait for the current operation')
    try:
        get_world()
        if request.revision != world.revision or request.episode != world.episode:
            raise HTTPException(409,'State changed; refresh before continuing')
        if world.done: raise HTTPException(409,'Run has ended; reset to start another')
        if world.revision >= 20: raise HTTPException(409,'Action budget reached; reset and inspect the trace')
        if world.observer is not None:
            phase('perception')
            world.refresh_perception()
        if request.mode == 'gemma':
            if not model_lock.acquire(False): raise HTTPException(409,'Model is busy with another request')
            try:
                phase('inference')
                if world.observer is not None:
                    with tempfile.TemporaryDirectory(prefix='arm-camera-') as directory:
                        frame=Path(directory)/'observation.jpg'
                        image=Image.fromarray(world.observer.rgb)
                        image.thumbnail((1280,960))
                        image.save(frame,quality=90)
                        decision=decide(world.observation(),world.events,image_path=frame)
                else:
                    decision = decide(world.observation(), world.events)
            finally: model_lock.release()
        else:
            decision = dict(action=scripted_action(world), reason='Scripted rehearsal — no model inference.', source='scripted baseline', seconds=0)
        if decision['action'] not in world.allowed():
            raise ValueError('Disallowed action; nothing moved')
        phase('physics',decision['action'],decision['seconds'])
        result = world.step(decision['action'])
        result['decision'] = decision
        world.events[-1]['decision'] = decision
        result['state'] = world.snapshot()
        phase('ready',decision['action'],decision['seconds'])
        return result
    except HTTPException: raise
    except Exception as exc:
        phase('error')
        raise HTTPException(422,str(exc)) from exc
    finally: world_lock.release()

Camera = Literal['overview','bench','top','perception']

def physics(revision=None):
    if not world_lock.acquire(timeout=30): raise HTTPException(409,'A step is running')
    try: get_world()
    except Exception:
        world_lock.release()
        raise
    if revision not in (None, world.revision):
        world_lock.release(); raise HTTPException(409,'That action has been superseded')
    return world

@app.get('/api/render.jpg')
def render(camera: Camera = 'overview'):
    w = physics()
    try:
        buf = io.BytesIO()
        Image.fromarray(w.bench.render(camera,size=(720,1280))).save(buf, 'JPEG', quality=92)
        return Response(buf.getvalue(), media_type='image/jpeg', headers={'Cache-Control':'no-store'})
    finally: world_lock.release()

@app.get('/api/action.mp4')
def video(camera: Camera = 'overview', r: int | None = None, episode: str | None = None):
    w=physics(r)
    try:
        if episode != w.episode: raise HTTPException(409,'Episode changed; discard stale replay')
        phase('rendering', w.events[-1]['action'] if w.events else None)
        data=w.bench.video(camera)
        phase('playback')
        return Response(data,media_type='video/mp4',headers={'Cache-Control':'no-store'})
    finally: world_lock.release()

@app.get('/api/perception')
def perception():
    with world_lock:
        get_world()
        if world.observer is None: raise HTTPException(409,'Choose camera perception mode')
        return dict(calibration=getattr(getattr(world.observer,'estimator',None),'calibration',None),detections=world.observer.last,
                    source='rendered RGB pixels only; explicitly taught marker identities')

@app.get('/api/observations.jpg')
def observation_image():
    import cv2
    import numpy as np
    with world_lock:
        get_world()
        if world.observer is None: raise HTTPException(409,'Choose camera perception mode')
        rgb=world.observer.rgb.copy()
        for name,detection in world.observer.last.items():
            corners=np.asarray(detection['pixel_corners'],dtype=np.int32)
            cv2.polylines(rgb,[corners],True,(90,235,170),3)
            x,y=corners[0]
            cv2.putText(rgb,f"{name} / ID {detection['marker_id']}",(int(x),max(24,int(y)-12)),
                        cv2.FONT_HERSHEY_SIMPLEX,.7,(90,235,170),2,cv2.LINE_AA)
        buf=io.BytesIO()
        Image.fromarray(rgb).save(buf,'JPEG',quality=92)
        return Response(buf.getvalue(),media_type='image/jpeg',headers={'Cache-Control':'no-store'})

@app.post('/api/unload')
def unload():
    if not model_lock.acquire(False): raise HTTPException(409,'Wait for current model request before unloading')
    try:
        if vision.engine is not None:
            vision.engine.close()
            vision.engine = None
            gc.collect()
        return {'loaded':False}
    finally: model_lock.release()

@app.get('/api/trace')
def trace():
    with world_lock:
        get_world()
        arm = 'YAM Ultra v2 MJCF + linear gripper, MuJoCo contacts'
        return dict(schema_version=1, simulation=True, arm=arm,
                    units='meters/radians/volts', state=world.snapshot())

combined_app.mount('/resistor', app)

# Release OpenGL contexts on their owning thread before process shutdown.
from contextlib import asynccontextmanager
_previous_lifespan=combined_app.router.lifespan_context
@asynccontextmanager
async def lifespan(application):
    async with _previous_lifespan(application):
        try: yield
        finally:
            with world_lock:
                if world is not None: world.bench.close()
combined_app.router.lifespan_context=lifespan
