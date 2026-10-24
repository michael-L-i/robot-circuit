"""Demo 2 task: diagnose an open series resistor with two probe points, swap in the spare, verify.

Same conventions as demo 1: guarded MuJoCo skills, contact-derived electrical state, camera markers by
default, null (not 0 V) for a missed probe contact, and an allowed-action list the planner must obey.
"""
import copy
import json
import random
import uuid
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from ..perception import MarkerPerception, PerceptionError
from ..physics.bench import SkillError
from ..physics.camera import CameraObserver, calibration
from . import scene
from .bench import ResistorBench

REGISTRY = json.loads((Path(__file__).resolve().parents[2]/'config/resistor_objects.json').read_text())['objects']
POINTS = {'measure_input': 'tp_in', 'measure_output': 'tp_out'}
FIXTURES = ['probe_dock', 'tp_in', 'tp_out', 'socket', 'reject_bin']     # bolted down: last sighting stays valid
ACTIONS = ['pick_probe', 'measure_input', 'measure_output', 'dock_probe', 'remove_resistor', 'discard_resistor',
           'pick_spare', 'insert_resistor', 'finish', 'abort']
FAULTY = {'open_resistor': ('resistor_a',), 'healthy': (), 'supply_off': (), 'bad_spare': ('resistor_a', 'resistor_b')}


@dataclass
class ResistorConfig:
    scenario: str = 'open_resistor'
    seed: int = 7
    perception: str = 'camera_markers'
    probe_error_mm: float = 0


class ResistorWorld:
    backend = 'mujoco'

    def __init__(self, config=None):
        self.config = c = config or ResistorConfig()
        if c.scenario not in FAULTY: raise ValueError(f'Unknown scenario {c.scenario}')
        rng = random.Random(c.seed)
        spare_xy = [scene.CADDY_XY[0]+rng.uniform(-.008, .008), scene.CADDY_XY[1]+rng.uniform(-.008, .008)]
        self.bench = ResistorBench(REGISTRY, FAULTY[c.scenario], spare_xy,
                                   scene.MODULE_YAW+np.radians(rng.uniform(-20, 20)), c.scenario != 'supply_off')
        self.bench.led_rule = lambda closed: closed
        self.socket, self.spare = 'resistor_a', 'resistor_b'     # what the operator set up, not fault truth
        self.discarded = []
        self.tool, self.measurements, self.events = None, [], []
        self.epoch = 0                                           # bumps whenever the socket contents change
        self.done = self.success = False
        self.revision, self.episode = 0, uuid.uuid4().hex[:8]
        self.observer, self.fixtures = None, {}
        if c.perception == 'camera_markers':
            self.observer = CameraObserver(self.bench)
            self.observer.estimator = MarkerPerception(calibration(self.bench), REGISTRY)
            self.bench.tool_offset_provider = self.measured_tool_offset
            self.refresh_perception()

    # ---- perception (camera mode) ------------------------------------------------------
    def refresh_perception(self):
        if self.observer is None: return {}
        seen = self.observer.scan()
        for name in FIXTURES:                    # the arm often occludes a fixture; parts must be seen live
            if name not in seen and name in self.fixtures:
                seen[name] = dict(self.fixtures[name], source='last sighting (fixed fixture)')
        self.fixtures.update({n: seen[n] for n in FIXTURES if n in seen})
        self.observer.last = self.bench.visual_targets = seen
        return seen

    def measured_tool_offset(self):
        """TCP-to-contact-point offset: re-measured from the held part's marker when visible, else taught."""
        b = self.bench
        orientation = b.d.site_xmat[b.site].reshape(3, 3)
        if getattr(b, 'visual_tool_local', None) is not None: return orientation@b.visual_tool_local
        seen = self.refresh_perception().get(b.held)
        if seen is None:
            offset = b.tool_offset.copy()
        else:
            tip = (np.asarray(seen['base_from_marker'])@np.r_[REGISTRY[b.held]['point_offset'], 1])[:3]
            offset = b.tcp()-tip
        b.visual_tool_local = orientation.T@offset
        return offset

    # ---- task state --------------------------------------------------------------------
    def current(self):
        """Latest valid-or-null reading per probe point since the socket last changed."""
        return {m['point']: m for m in self.measurements if m['epoch'] == self.epoch}

    def allowed(self):
        if self.done: return []
        if self.events and not self.events[-1]['ok']: return ['abort']     # fail closed after a physical fault
        if self.tool == 'probe':
            since = {e['action'] for e in self.events[self._picked_probe_at():]}
            acts = [a for a in POINTS if a not in since]
            return acts + (['dock_probe'] if since & set(POINTS) else []) + ['abort']
        if self.tool and self.tool == self.spare: return ['insert_resistor', 'abort']
        if self.tool: return ['discard_resistor', 'abort']
        if self.socket is None: return ['pick_spare', 'abort'] if self.spare else ['abort']
        cur = self.current()
        if any(m['voltage'] is None for m in cur.values()): return ['abort']
        inp, out = cur.get('input'), cur.get('output')
        if out and out['voltage'] > 1.5 and out['led_on']: return ['finish', 'abort']
        if inp and inp['voltage'] < 4: return ['abort']                 # supply fault: a new resistor won't help
        if out and out['voltage'] < .5 and self.epoch: return ['abort']    # the swap did not fix it: stop
        if inp and out and out['voltage'] < .5:
            return ['remove_resistor', 'abort'] if self.spare else ['abort']
        return ['pick_probe', 'abort']

    def _picked_probe_at(self):
        return max((i for i, e in enumerate(self.events) if e['action'] == 'pick_probe'), default=0)

    def electrical(self):
        return self.bench.electrical()

    def observation(self):
        # Sensor history and setup facts only; which module is faulty is never revealed.
        obs = dict(tool=self.tool, measurements=[{k: v for k, v in m.items() if k != 'epoch'} for m in self.measurements],
                   socket='original module installed' if self.socket == 'resistor_a' else
                          'spare module installed' if self.socket else 'empty',
                   spare_available=self.spare is not None, discarded=list(self.discarded),
                   led_visible=self.bench.led, allowed_actions=self.allowed(), revision=self.revision)
        if self.observer is None:
            pos = lambda s: self.bench.site_pos(s).round(4).tolist()
            obs['targets'] = dict(probe=pos('probe_grasp'), tp_in=pos('tp_in_top'), tp_out=pos('tp_out_top'),
                                  socket=pos('socket_top'), reject_bin=[*scene.BIN_XY, .002], probe_dock=[*scene.DOCK_XY, 0.],
                                  **{r: pos(f'{r}_grasp') for r in scene.MODULES})
        else:
            seen = self.observer.last
            obs['targets'] = {n: d['target_xyz'] for n, d in seen.items()}
            obs['perception'] = dict(method='calibrated camera + taught ArUco identities', detections=seen,
                                     missing=[n for n in ['probe', *FIXTURES, *scene.MODULES] if n not in seen])
        return copy.deepcopy(obs)

    def snapshot(self):
        b = self.bench
        return dict(**self.observation(), q=b.arm_q().tolist(), tcp=b.tcp().tolist(), objects=b.objects(),
                    electrical=self.electrical(), done=self.done, success=self.success, events=self.events[-60:],
                    config=vars(self.config), simulation=True, episode=self.episode, backend=self.backend,
                    perception_mode=self.config.perception)

    def step(self, action):
        if action not in self.allowed():
            raise ValueError(f'{action} is not allowed; choose from {self.allowed()}')
        target = {'pick_probe': 'probe', 'measure_input': 'tp_in', 'measure_output': 'tp_out',
                  'dock_probe': 'probe_dock', 'remove_resistor': self.socket, 'discard_resistor': 'reject_bin',
                  'pick_spare': self.spare, 'insert_resistor': 'socket'}.get(action)
        if self.observer is not None:                          # reacquire before moving; no truth fallback
            self.refresh_perception()
            if target: MarkerPerception.require(self.observer.last, target)
        before, b = self.snapshot(), self.bench
        b.frames = []
        note, ok = action.replace('_', ' '), True
        try:
            if action == 'pick_probe':
                b.pick('probe')
                self.tool = 'probe'
            elif action in POINTS:
                point = 'input' if action == 'measure_input' else 'output'
                valid = b.measure(POINTS[action], self.config.probe_error_mm/1000)
                e = self.electrical()
                v = round(e[f'{point}_v'], 3) if valid else None
                self.measurements.append(dict(point=point, voltage=v, valid_contact=valid, led_on=e['led_on'],
                                              after_replacement=self.epoch > 0, epoch=self.epoch))
                label = 'TP1 (supply side)' if point == 'input' else 'TP2 (LED anode)'
                note = f'{label} reads {v:.2f} V relative to GND' if valid else \
                    f'No probe contact on {label} — reading unavailable (not 0 V)'
            elif action == 'dock_probe':
                b.dock_probe()
                self.tool = None
            elif action == 'remove_resistor':
                b.pick(self.socket)
                self.tool, self.socket, self.epoch = self.socket, None, self.epoch+1
                note = 'Pulled the resistor module out of the socket'
            elif action == 'discard_resistor':
                landed = b.discard()
                self.discarded.append(self.tool)
                self.tool = None
                note = 'Dropped the removed module in the reject bin' if landed else \
                    'Released the removed module, but it missed the reject bin'
            elif action == 'pick_spare':
                b.pick(self.spare)
                self.tool = self.spare
                note = 'Picked the spare 330 Ω module from the caddy'
            elif action == 'insert_resistor':
                seated = b.insert()
                self.socket, self.spare, self.tool, self.epoch = self.tool, None, None, self.epoch+1
                note = 'Spare module seated across both socket pads' if seated else \
                    'Module released, but its pins are not bridging both socket pads'
            elif action == 'finish':
                b.home()
                self.done = self.success = True
            elif action == 'abort':
                b.home()
                self.done = True
        except SkillError as exc:
            ok, note = False, f'{note} failed: {exc}'
            self.tool = b.held = b.holding()
        self.revision += 1
        self.events.append(dict(step=self.revision, action=action, note=note, ok=ok))
        frames = [{k: v for k, v in f.items() if k != 'qpos'} for f in b.frames]
        return dict(before=before, frames=frames, state=self.snapshot())


def scripted_action(world):
    """Reference (non-AI) policy: prove the supply, find the dead node, swap, verify."""
    allowed = world.allowed()
    if world.tool == 'probe':
        order = ['measure_output'] if world.epoch else ['measure_input', 'measure_output']
        return next((a for a in order if a in allowed), 'dock_probe' if 'dock_probe' in allowed else 'abort')
    return next(a for a in ['finish', 'remove_resistor', 'discard_resistor', 'pick_spare', 'insert_resistor',
                            'pick_probe', 'abort'] if a in allowed)
