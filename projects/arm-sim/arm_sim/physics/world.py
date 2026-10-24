"""World-compatible task wrapper whose actions run as guarded skills in MuJoCo."""
from ..world import World
from .bench import Bench, SkillError
from . import scene


class PhysicsWorld(World):
    backend = 'mujoco'

    def __init__(self, config=None):
        super().__init__(config)
        connected = self.config.scenario == 'already_connected'
        self.bench = Bench(jumper_xy=None if connected else self.jumper[:2], jumper_on_mesh=connected)
        scenario = self.config.scenario
        self.bench.led_rule = lambda closed: closed and scenario not in ('supply_off', 'reversed_led')
        self._sync()

    def _sync(self):
        self.q = self.bench.arm_q()
        self.jumper = self.bench.site_pos('jumper_grasp').round(4).tolist()

    def mesh_contact(self):
        return self.bench.circuit_closed()          # pin physically touching the copper mesh

    def observation(self):
        # Physical fixture surfaces, not the kinematic backend's nominal TCP targets.
        return dict(super().observation(), targets=dict(
            probe_dock=[*scene.DOCK_XY, 0.], test_pad=self.bench.site_pos('pad_top').round(4).tolist(),
            copper_mesh=self.bench.site_pos('mesh_top').round(4).tolist()))

    def snapshot(self):
        return dict(super().snapshot(), backend=self.backend, tcp=self.bench.tcp().tolist(),
                    objects=self.bench.objects())

    def step(self, action):
        if action not in self.allowed():
            raise ValueError(f'{action} is not allowed; choose from {self.allowed()}')
        before, bench = self.snapshot(), self.bench
        bench.frames = []
        note, ok = action.replace('_', ' '), True
        try:
            if action == 'pick_probe':
                bench.pick('probe')
                self.tool = 'probe'
            elif action == 'dock_probe':
                bench.dock_probe()
                self.tool = None
            elif action == 'pick_jumper':
                bench.pick('jumper')
                self.tool = 'jumper'
            elif action == 'place_mesh':
                hits = bench.place_jumper(self.config.placement_error_mm/1000)
                self.tool, self.placed = None, True
                note = 'Jumper seated on copper mesh' if ('jumper_pin', 'copper_mesh') in hits else \
                    'Jumper released, but its pin never touched the copper mesh'
            elif action == 'measure':
                valid = bench.measure(self.config.probe_error_mm/1000)
                e = self.electrical()
                v = round(e['node_v'], 3) if valid else None
                self.measurements.append(dict(voltage=v, valid_contact=valid, led_on=e['led_on'],
                                              after_placement=self.placed))
                note = f'Probe reads {v:.2f} V relative to GND' if valid else \
                    'No probe contact — reading unavailable (not 0 V)'
            elif action == 'finish':
                bench.home()
                self.done = self.success = True
            elif action == 'abort':
                bench.home()
                self.done = True
        except SkillError as exc:
            # The physical attempt failed; whatever the gripper still holds is the new truth.
            ok, note = False, f'{note} failed: {exc}'
            self.tool = bench.held = bench.holding()
        self._sync()
        self.revision += 1
        self.events.append(dict(step=self.revision, action=action, note=note, ok=ok))
        frames = [{k: v for k, v in f.items() if k != 'qpos'} | dict(links=self.arm.fk(f['q'])[2])
                  for f in bench.frames]
        return dict(before=before, frames=frames, state=self.snapshot())
