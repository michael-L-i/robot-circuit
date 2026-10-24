"""Task/contact simulation. SI units; ideal DC circuit, explicit probe ground."""
from dataclasses import dataclass
import copy
import random
import uuid
from .kinematics import Arm

PAD = [.35, -.035, .065]
MESH = [.35, .035, .065]
DOCK = [.23, -.15, .10]
HOME = [.26, 0, .24]

@dataclass
class Config:
    scenario: str = 'misplaced'
    seed: int = 7
    placement_error_mm: float = 0
    probe_error_mm: float = 0

class World:
    def __init__(self, config=None):
        self.config = config or Config()
        self.arm = Arm()
        self.q = self.arm.solve(HOME, [0,1.5,1.5,0,0,0])
        rng = random.Random(self.config.seed)
        self.jumper = [.31+rng.uniform(-.012,.012), .08+rng.uniform(-.01,.01), .065]
        if self.config.scenario == 'already_connected':
            self.jumper = MESH.copy()
        self.tool = None
        self.measurements = []
        self.events = []
        self.placed = False
        self.done = False
        self.success = False
        self.revision = 0
        self.episode = uuid.uuid4().hex[:8]  # distinguishes resets that restart revision at 0

    def mesh_contact(self):
        return abs(self.jumper[0]-MESH[0]) <= .014 and abs(self.jumper[1]-MESH[1]) <= .012 and abs(self.jumper[2]-MESH[2]) <= .002 and self.tool != 'jumper'

    def electrical(self):
        contact = self.mesh_contact()
        supply = 0. if self.config.scenario == 'supply_off' else 5.
        node = supply if contact else 0. # 100k pulldown fixes the disconnected node potential.
        current = max(0., (node-2.)/330.) if self.config.scenario != 'reversed_led' else 0.
        return dict(contact=contact, node_v=node, current_ma=round(current*1000,3), led_on=current>.001)

    def allowed(self):
        if self.done: return []
        if self.tool == 'probe':
            return ['dock_probe','abort'] if self.events and self.events[-1]['action'] == 'measure' else ['measure','abort']
        if self.tool == 'jumper': return ['place_mesh','abort']
        if not self.measurements: return ['pick_probe','abort']
        last = self.measurements[-1]
        if last['voltage'] is None: return ['abort']
        if last['voltage'] > 4 and last['led_on']: return ['finish','abort']
        if self.placed: return ['pick_probe','abort'] if not last['after_placement'] else ['abort']
        return ['pick_jumper','abort']

    def observation(self):
        # Model gets sensor history and nominal fixture locations, not hidden fault/contact truth.
        return dict(tool=self.tool, measurements=copy.deepcopy(self.measurements), jumper_xyz=self.jumper.copy(),
            targets=dict(probe_dock=DOCK,test_pad=PAD,copper_mesh=MESH),
            led_visible=self.electrical()['led_on'], placed=self.placed,
            allowed_actions=self.allowed(), revision=self.revision)

    def snapshot(self):
        tcp, _, links = self.arm.fk(self.q)
        return dict(**self.observation(), q=self.q.tolist(), tcp=tcp.tolist(), links=links,
            electrical=self.electrical(), done=self.done, success=self.success,
            events=self.events[-60:], config=vars(self.config), simulation=True, episode=self.episode)

    def step(self, action):
        if action not in self.allowed(): raise ValueError(f'{action} is not allowed; choose from {self.allowed()}')
        # Plan all motion before committing any mutation.
        target = {'pick_probe':DOCK, 'measure':PAD, 'dock_probe':DOCK,
                  'pick_jumper':self.jumper, 'place_mesh':MESH}.get(action)
        if target is not None:
            target = target.copy()
            if action == 'place_mesh': target[0] += self.config.placement_error_mm/1000
            if action == 'measure': target[0] += self.config.probe_error_mm/1000
            q, frames = self.arm.path(self.q, target)
        else: q, frames = self.q, []
        before = self.snapshot()
        self.q = q
        note = action.replace('_',' ')
        if action == 'pick_probe': self.tool = 'probe'
        elif action == 'dock_probe': self.tool = None
        elif action == 'pick_jumper': self.tool = 'jumper'
        elif action == 'place_mesh':
            self.jumper = self.arm.fk(self.q)[0].tolist()
            self.tool = None
            self.placed = True
        elif action == 'measure':
            tcp = self.arm.fk(self.q)[0]
            valid = abs(tcp[0]-PAD[0]) <= .012 and abs(tcp[1]-PAD[1]) <= .012 and abs(tcp[2]-PAD[2]) <= .002
            e = self.electrical()
            v = round(e['node_v'],3) if valid else None
            self.measurements.append(dict(voltage=v,valid_contact=bool(valid),led_on=e['led_on'],after_placement=self.placed))
            note = f'Probe reads {v:.2f} V relative to GND' if v is not None else 'No probe contact — reading unavailable (not 0 V)'
        elif action == 'finish': self.done, self.success = True, True
        elif action == 'abort': self.done = True
        self.revision += 1
        self.events.append(dict(step=self.revision,action=action,note=note))
        return dict(before=before,frames=frames,state=self.snapshot())


def scripted_action(world):
    """Explicit non-AI baseline used in tests and the rehearsal button."""
    allowed = world.allowed()
    if world.tool == 'probe':
        # Dock after each measurement; measurement history doesn't imply a fresh sample.
        return 'dock_probe' if world.events and world.events[-1]['action']=='measure' else 'measure'
    return next((a for a in ['finish','pick_probe','pick_jumper','place_mesh','abort'] if a in allowed), None)
