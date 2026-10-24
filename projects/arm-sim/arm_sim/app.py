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
from .world import World, Config, scripted_action
from .physics.world import PhysicsWorld
from .physics.visual_world import VisualWorld
from .planner import decide

app = FastAPI(title='Arm circuit simulation')
static = Path(__file__).parent/'static'
app.mount('/static', StaticFiles(directory=static), name='static')
world = VisualWorld()
world_lock = threading.Lock()
proposal = None
progress = dict(phase="idle", action=None, started=time.monotonic())

class Reset(BaseModel):
    scenario: Literal['misplaced','already_connected','supply_off','reversed_led'] = 'misplaced'
    seed: int = Field(default=7, ge=0, le=1000000)
    placement_error_mm: float = Field(default=0, ge=-30, le=30, allow_inf_nan=False)
    probe_error_mm: float = Field(default=0, ge=-30, le=30, allow_inf_nan=False)
    backend: Literal['mujoco','kinematic'] = 'mujoco'
    perception: Literal['camera_markers','oracle'] = 'camera_markers'

class Step(BaseModel):
    mode: Literal['gemma','scripted'] = 'gemma'
    revision: int
    episode: str | None = None

@app.get('/')
def index(): return FileResponse(static/'index.html',headers={'Cache-Control':'no-store'})

@app.get('/api/state')
def state():
    with world_lock: return world.snapshot()

@app.post('/api/reset')
def reset(config: Reset):
    global world, proposal
    if not world_lock.acquire(timeout=3): raise HTTPException(409,'Simulation or renderer is busy; wait for the current operation')
    try:
        options = config.model_dump()
        backend = options.pop('backend')
        perception = options.pop('perception')
        if isinstance(world, PhysicsWorld): world.bench.close()  # free the old GL contexts
        world = ((VisualWorld if perception=='camera_markers' else PhysicsWorld) if backend == 'mujoco' else World)(Config(**options))
        proposal = None
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
    if not world_lock.acquire(timeout=3): raise HTTPException(409,'Simulation or renderer is busy; wait for the current operation')
    try:
        if request.revision != world.revision or request.episode not in (None, world.episode):
            raise HTTPException(409,'State changed; refresh before continuing')
        if world.done: raise HTTPException(409,'Run has ended; reset to start another')
        if world.revision >= 16: raise HTTPException(409,'Action budget reached; reset and inspect the trace')
        if isinstance(world,VisualWorld):
            phase('perception')
            world.refresh_perception()
        if request.mode == 'gemma':
            if not model_lock.acquire(False): raise HTTPException(409,'Model is busy with another request')
            try:
                phase('inference')
                if isinstance(world,VisualWorld):
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
    if not isinstance(world, PhysicsWorld):
        world_lock.release(); raise HTTPException(409,'Kinematic backend has no renderer')
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
        if not isinstance(world,VisualWorld): raise HTTPException(409,'Choose camera perception mode')
        return dict(calibration=world.observer.estimator.calibration,detections=world.observer.last,
                    source='rendered RGB pixels only; explicitly taught marker identities')

@app.get('/api/observations.jpg')
def observation_image():
    import cv2
    import numpy as np
    with world_lock:
        if not isinstance(world,VisualWorld): raise HTTPException(409,'Choose camera perception mode')
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
        arm = 'YAM Ultra v2 MJCF + linear_4310 gripper, MuJoCo contacts' if isinstance(world, PhysicsWorld) else 'YAM Ultra v1 URDF, simplified links'
        return dict(schema_version=1, simulation=True, arm=arm,
                    units='meters/radians/volts', state=world.snapshot())

combined_app.mount('/sim', app)

# Release OpenGL contexts on their owning thread before process shutdown.
from contextlib import asynccontextmanager
_previous_lifespan=combined_app.router.lifespan_context
@asynccontextmanager
async def lifespan(application):
    async with _previous_lifespan(application):
        try: yield
        finally:
            if isinstance(world,PhysicsWorld): world.bench.close()
combined_app.router.lifespan_context=lifespan
