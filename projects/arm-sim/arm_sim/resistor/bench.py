"""Demo 2 skills. Reuses demo 1's motion, collision guard and rendering primitives by subclassing."""
import mujoco
import numpy as np
from ..physics.bench import Bench, SkillError, OPEN, CLEAR, HOME, READY_Q, CONTROL_DT, _quat_conj
from . import scene

VF, R_OHM, SUPPLY = 2.0, 330., 5.         # red LED forward drop, series resistor, Arduino rail
TRANSIT_Z = .15                           # carried probe/module clears the socketed module and bin walls


class ResistorBench(Bench):
    def __init__(self, registry, faulty=('resistor_a',), spare_xy=None, spare_yaw=scene.MODULE_YAW, supply=True):
        self.registry, self.faulty, self.supply = registry, set(faulty), supply
        self.m = scene.build(registry, scene.CADDY_XY if spare_xy is None else spare_xy, spare_yaw, faulty)
        self.d, self.scratch = mujoco.MjData(self.m), mujoco.MjData(self.m)
        m = self.m
        self.site = m.site('g_grasp_site').id
        self.arm_qadr = np.array([m.joint(n).qposadr[0] for n in scene.ARM_JOINTS])
        self.arm_dof = np.array([m.joint(n).dofadr[0] for n in scene.ARM_JOINTS])
        self.lower, self.upper = m.jnt_range[[m.joint(n).id for n in scene.ARM_JOINTS]].T
        names = ['probe_tip', 'probe_handle', 'tp_in', 'tp_out', 'socket_in', 'socket_out', 'board', 'table',
                 'g_tip_left', 'g_tip_right', 'caddy', 'bin_floor']
        names += [f'{r}_{p}' for r in scene.MODULES for p in ('housing', 'pin0', 'pin1')]
        self.geom = {n: m.geom(n).id for n in names}
        self.seats = {r: m.eq(f'{r}_seat').id for r in scene.MODULES}
        self.frames, self.held, self.led = [], None, False
        self.visual_targets = self.tool_offset = self.tool_offset_provider = None
        self.led_rule = lambda closed: closed
        self._renderers, self._view = {}, mujoco.MjData(m)
        mujoco.mj_forward(m, self.d)
        for r in scene.MODULES:
            self._seat(r)
        home = self.ik(*HOME, READY_Q)
        self.d.qpos[self.arm_qadr] = home
        self.d.ctrl[:6], self.d.ctrl[6] = home, OPEN
        self.d.qpos[m.joint('g_joint7').qposadr[0]] = self.d.qpos[m.joint('g_joint8').qposadr[0]] = OPEN
        self.settle(.4, record=False)

    # ---- state -------------------------------------------------------------------------
    def gripped(self, obj):
        part = 'probe_handle' if obj == 'probe' else f'{obj}_housing'
        return all(self.touching(tip, part) for tip in ('g_tip_left', 'g_tip_right'))

    def holding(self):
        return next((o for o in ('probe', *scene.MODULES) if self.gripped(o)), None)

    def bridges(self, r):
        """Both header pins pressed onto opposite socket pads (the resistor is non-polar)."""
        t = self.touching
        return (t(f'{r}_pin0', 'socket_in') and t(f'{r}_pin1', 'socket_out')) or \
               (t(f'{r}_pin1', 'socket_in') and t(f'{r}_pin0', 'socket_out'))

    def installed(self):
        return next((r for r in scene.MODULES if self.bridges(r)), None)

    def in_bin(self, r):
        p = self.d.body(r).xpos
        return bool(np.all(np.abs(p[:2]-scene.BIN_XY) < scene.BIN_HALF) and p[2] < scene.BIN_H)

    def electrical(self):
        r = self.installed()
        closed = self.supply and r is not None and r not in self.faulty
        out = VF if closed else 0.           # open series path: 100 kOhm pulls TP2 to ground
        return dict(input_v=SUPPLY if self.supply else 0., output_v=out, installed=r,
                    current_ma=round((SUPPLY-VF)/R_OHM*1000, 2) if closed else 0., led_on=closed)

    def circuit_closed(self):
        return self.electrical()['led_on']

    def objects(self):
        return {b: dict(pos=self.d.body(b).xpos.round(5).tolist(), quat=self.d.body(b).xquat.round(5).tolist())
                for b in ('probe', *scene.MODULES)}

    def yaw_of(self, obj):
        """Module x axis (the finger closing direction) from the marker pose, or truth in oracle mode."""
        if self.visual_targets is not None:
            self.target(obj)                                  # fail closed when the marker is missing
            rot = np.asarray(self.visual_targets[obj]['base_from_marker'])[:3, :3]
        else:
            rot = self.d.body(obj).xmat.reshape(3, 3)
        return float(np.arctan2(rot[1, 0], rot[0, 0]))

    def _closest(self, yaw, xy):
        """Of yaw and yaw+pi (symmetric grasp), the one nearest the natural tangential wrist angle."""
        ref = self.yaw_for(xy)
        return min((yaw, yaw+np.pi), key=lambda a: abs((a-ref+np.pi) % (2*np.pi)-np.pi))

    def _seat(self, r, active=True):
        body, eq = self.m.body(r).id, self.seats[r]
        self.m.eq_data[eq][3:6] = -self.d.xmat[body].reshape(3, 3).T@self.d.xpos[body]
        self.m.eq_data[eq][6:10] = _quat_conj(self.d.xquat[body])
        self.d.eq_active[eq] = active

    # ---- motion ------------------------------------------------------------------------
    def move(self, pos, yaw, speed=.15, until=None):
        """Bench.move with a smooth (cubic) time scaling. Demo 1 starts and stops each segment at full speed;
        that jerk swings a gripped probe several millimetres off the tip offset the motion was planned with."""
        start, pos = self.tcp(), np.asarray(pos, float)
        n = max(1, int(np.ceil(1.5*np.linalg.norm(pos-start)/(speed*CONTROL_DT))))   # peak = 1.5x mean speed
        q = self.d.ctrl[:6].copy()
        for t in np.linspace(0, 1, n+1)[1:]:
            q = self.ik(start + (pos-start)*(3*t**2-2*t**3), yaw, q)
            self.d.ctrl[:6] = q
            self.tick()
            self.check_collision()
            if self.held and not self.gripped(self.held):
                self._lost_grasp_ticks = getattr(self, '_lost_grasp_ticks', 0)+1
                if self._lost_grasp_ticks >= 5:
                    raise SkillError(f'{self.held} lost finger contact during motion')
            else:
                self._lost_grasp_ticks = 0
            if until and until():
                self.d.ctrl[:6] = self.arm_q()
                self.settle(.1)
                return True
        for _ in range(40):
            if np.linalg.norm(self.tcp()-pos) < 1.5e-3 or (until and until()):
                break
            self.tick()
        return bool(until and until())

    # ---- skills ------------------------------------------------------------------------
    def hop(self, xy, yaw):
        """Lift, turn the wrist in place, then cross at transit height. A straight diagonal drags the
        probe over the socketed module, and a sudden 40-degree wrist snap shakes a gripped probe loose."""
        p, rot = self.tcp(), self.d.site_xmat[self.site].reshape(3, 3)
        now = float(np.arctan2(rot[1, 1], rot[0, 1]))                   # fingers close along site y
        top = [*p[:2], max(p[2], TRANSIT_Z)]
        if p[2] < TRANSIT_Z - .005:
            self.move(top, now, speed=.1)
        turn = (yaw-now+np.pi) % (2*np.pi)-np.pi
        for k in range(1, int(abs(turn)/np.radians(3))+1):              # ~75 deg/s
            self.move(top, now+np.sign(turn)*np.radians(3)*k)
            self.settle(.02)
        self.move([*xy, TRANSIT_Z], yaw)

    def touch(self, point_site, xy, surface_z, target_geoms, yaw=None, depth=.012):
        yaw = self.yaw_for(xy) if yaw is None else yaw
        self.hop(xy, yaw)
        return super().touch(point_site, xy, surface_z, target_geoms, yaw, depth)

    def _where(self, name, site):
        return self.target(name) if self.visual_targets is not None else self.site_pos(site)

    def pick(self, obj):
        grasp = self._where(obj, f'{obj}_grasp')
        yaw = self.yaw_for(grasp) if obj == 'probe' else self._closest(self.yaw_of(obj), grasp[:2])
        below = grasp - [0, 0, .008]                          # fingertips just past the grasp point
        self.grip(False)
        self.hop(grasp[:2], yaw)
        self.move(below + [0, 0, CLEAR], yaw)
        self.move(below, yaw, speed=.05)
        self.settle(.15)
        self.grip(True)
        if not self.gripped(obj):
            self.move(below + [0, 0, CLEAR], yaw)
            raise SkillError(f'Fingers did not close on the {obj}')
        self.held, self.visual_tool_local = obj, None
        if self.visual_targets is not None:                   # taught grasp-to-contact-point geometry
            e = self.registry[obj]
            self.tool_offset = np.asarray(e['target_offset']) - e['point_offset'] - [0, 0, .008]
        if obj in self.seats:
            self.d.eq_active[self.seats[obj]] = 0             # pull the header out of the socket / caddy
        self.move(self.tcp() + [0, 0, CLEAR], yaw, speed=.06)
        if not self.gripped(obj):
            self.held = None
            raise SkillError(f'The {obj} slipped out of the gripper while lifting')

    def measure(self, point, offset_x=0.):
        pad = self._where(point, f'{point}_top')
        board = [('probe_tip', 'board')] + [('probe_tip', g) for g in ('tp_in', 'tp_out', 'socket_in', 'socket_out')]
        self.touch('probe_point', pad[:2] + [offset_x, 0], pad[2], board)
        self.settle(.25)
        valid = self.touching('probe_tip', point)
        self.move(self.tcp() + [0, 0, .04], self.yaw_for(pad[:2]), speed=.08)
        return valid

    def dock_probe(self):
        p = self.target('probe_dock') if self.visual_targets is not None else [*scene.DOCK_XY, 0.]
        return self.release('probe_point', p[:2], p[2], [('probe_tip', 'table')])

    def insert(self):
        """Lower the held module's pins onto the socket pads, press, and let the socket capture it."""
        r = self.held
        p = self._where('socket', 'socket_top')
        yaw = self._closest(np.pi/2, p[:2])                   # pins along world x, across both pads
        pins = [(f'{r}_pin{i}', g) for i in (0, 1) for g in ('socket_in', 'socket_out', 'board')]
        self.touch(f'{r}_point', p[:2], p[2], pins, yaw=yaw)
        self.move(self.tcp() - [0, 0, .001], yaw, speed=.01)
        self.settle(.1)
        if self.bridges(r) and self.upright(r):
            self._seat(r)
        self.grip(False)
        self.held = None
        self.move(self.tcp() + [0, 0, CLEAR], yaw, speed=.08)
        return self.bridges(r)

    def discard(self):
        r = self.held
        p = self._where('reject_bin', 'bin_floor') if self.visual_targets is not None else \
            np.array([*scene.BIN_XY, .002])
        yaw = self.yaw_for(p[:2])
        self.hop(p[:2], yaw)
        self.move(p + [0, 0, .09], yaw)
        self.grip(False)
        self.held = None
        self.settle(.4)
        self.move(self.tcp() + [0, 0, .04], yaw, speed=.08)
        return self.in_bin(r)

    # ---- visuals -----------------------------------------------------------------------
    def _render(self, camera, frame, size):
        renderer = self._renderers.get(size)
        if renderer is None:
            renderer = self._renderers[size] = mujoco.Renderer(self.m, *size)
        d, led = self.d, self.led
        if frame is not None:
            d = self._view
            d.qpos[:] = frame['qpos']
            mujoco.mj_kinematics(self.m, d)
            mujoco.mj_comPos(self.m, d)
            mujoco.mj_camlight(self.m, d)
            led = frame['led_on']
        live = self.led
        self.set_led(led)
        renderer.update_scene(d, camera)
        scn = renderer.scene
        self._cable(scn, [.31, .178, .023], [scene.TP_IN['pos'][0], .077, .0325], [.85, .12, .1, 1], sag=.03)
        self._cable(scn, d.site('probe_grasp').xpos + [0, 0, .025], [.16, -.17, .04], [.12, .12, .12, 1], sag=.08)
        image = renderer.render()
        self.set_led(live)
        return image
