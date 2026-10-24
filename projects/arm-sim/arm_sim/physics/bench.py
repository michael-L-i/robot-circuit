"""Guarded manipulation skills on the simulated YAM Ultra; electrical state comes from contacts."""
import io
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import mujoco
from PIL import Image
from . import scene

CONTROL_DT = .02          # setpoint period (50 Hz), physics runs at scene timestep
FRAME_EVERY = 2           # record a playback frame every N control ticks
OPEN, CLOSED = .02, 0.    # finger joint setpoints (each finger), 4 cm gap when open
GL = ThreadPoolExecutor(1, 'mujoco-gl')   # every OpenGL call stays on one thread (macOS CGL deadlocks otherwise)
CLEAR = .085              # approach/retreat height above a grasp or contact point
HOME = ([.28, 0, .18], np.pi/2)   # top-down reach of the YAM Ultra tops out near z = .2 m here
READY_Q = [.1, 1.9, 1.5, -1.2, 0, .1]


def _quat_conj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


class SkillError(RuntimeError):
    pass


class Bench:
    def __init__(self, jumper_xy=None, jumper_on_mesh=False):
        self.m = scene.build()
        self.d = mujoco.MjData(self.m)
        self.scratch = mujoco.MjData(self.m)
        m = self.m
        self.site = m.site('g_grasp_site').id
        self.arm_qadr = np.array([m.joint(n).qposadr[0] for n in scene.ARM_JOINTS])
        self.arm_dof = np.array([m.joint(n).dofadr[0] for n in scene.ARM_JOINTS])
        self.lower, self.upper = m.jnt_range[[m.joint(n).id for n in scene.ARM_JOINTS]].T
        self.seat = m.eq('jumper_seat').id
        self.geom = {n: m.geom(n).id for n in ('probe_tip', 'test_pad', 'jumper_pin', 'copper_mesh', 'board',
                                                 'table', 'g_tip_left', 'g_tip_right', 'probe_handle',
                                                 'jumper_housing')}
        self.frames, self.held, self.led = [], None, False
        self.visual_targets = None
        self.tool_offset = None
        self.tool_offset_provider = None
        self.led_rule = lambda closed: closed        # scenario hook: supply off / reversed LED
        self._renderers, self._view = {}, mujoco.MjData(self.m)
        if jumper_on_mesh:
            jumper_xy = scene.MESH['pos'][:2]
        if jumper_xy is not None:
            adr = m.joint('jumper').qposadr[0]
            self.d.qpos[adr:adr+2] = jumper_xy
            if jumper_on_mesh:
                self.d.qpos[adr+2] = scene.MESH['pos'][2]+scene.MESH['size'][2]+2*scene.JUMPER_PIN[2]+scene.JUMPER_HOUSING[2]
        mujoco.mj_forward(m, self.d)
        self._seat_jumper()
        home = self.ik(*HOME, READY_Q)
        self.d.qpos[self.arm_qadr] = home
        self.d.ctrl[:6], self.d.ctrl[6] = home, OPEN
        self.d.qpos[m.joint('g_joint7').qposadr[0]] = self.d.qpos[m.joint('g_joint8').qposadr[0]] = OPEN
        self.settle(.4, record=False)

    # ---- state -------------------------------------------------------------------------
    def arm_q(self):
        return self.d.qpos[self.arm_qadr].copy()

    def tcp(self):
        return self.d.site_xpos[self.site].copy()

    def site_pos(self, name):
        return self.d.site(name).xpos.copy()

    def touching(self, a, b):
        ga, gb = self.geom[a], self.geom[b]
        c = self.d.contact[:self.d.ncon]
        return bool(np.any(((c.geom1 == ga) & (c.geom2 == gb)) | ((c.geom1 == gb) & (c.geom2 == ga))))

    def gripped(self, obj):
        part = 'probe_handle' if obj == 'probe' else 'jumper_housing'
        return all(self.touching(tip, part) for tip in ('g_tip_left', 'g_tip_right'))

    def holding(self):
        return next((obj for obj in ('probe', 'jumper') if self.gripped(obj)), None)

    def upright(self, body, max_tilt_deg=10):
        return self.d.body(body).xmat[8] > np.cos(np.radians(max_tilt_deg))

    def circuit_closed(self):
        return self.touching('jumper_pin', 'copper_mesh')

    def objects(self):
        return {b: dict(pos=self.d.body(b).xpos.round(5).tolist(), quat=self.d.body(b).xquat.round(5).tolist())
                for b in ('probe', 'jumper')}

    # ---- low level ---------------------------------------------------------------------
    def ik(self, pos, yaw, seed, iters=80):
        """Damped least squares on the fingertip centre, approach axis pointing straight down."""
        m, d = self.m, self.scratch
        d.qpos[:] = self.d.qpos
        q = np.clip(np.asarray(seed, float), self.lower, self.upper)
        y = np.array([np.cos(yaw), np.sin(yaw), 0])
        z = np.array([0, 0, -1.])
        target = np.column_stack([np.cross(y, z), y, z])
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        for _ in range(iters):
            d.qpos[self.arm_qadr] = q
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            rot = d.site_xmat[self.site].reshape(3, 3)
            err = np.concatenate([np.asarray(pos) - d.site_xpos[self.site],
                                  .5*sum(np.cross(rot[:, i], target[:, i]) for i in range(3))])
            if np.linalg.norm(err[:3]) < 2e-4 and np.linalg.norm(err[3:]) < 2e-3:
                return q
            mujoco.mj_jacSite(m, d, jp, jr, self.site)
            jac = np.vstack([jp[:, self.arm_dof], jr[:, self.arm_dof]])
            dq = jac.T@np.linalg.solve(jac@jac.T + 1e-4*np.eye(6), err)
            q = np.clip(q + np.clip(dq, -.2, .2), self.lower, self.upper)
        raise SkillError(f'IK failed for {np.round(pos, 3).tolist()} (residual {np.linalg.norm(err[:3])*1000:.1f} mm)')

    def tick(self, record=True):
        for _ in range(round(CONTROL_DT/self.m.opt.timestep)):
            mujoco.mj_step(self.m, self.d)
        self._ticks = getattr(self, '_ticks', 0) + 1
        self.set_led(self.led_rule(self.circuit_closed()))
        if record and self._ticks % FRAME_EVERY == 0:
            self.frames.append(dict(q=self.arm_q().tolist(), tcp=self.tcp().round(5).tolist(),
                                    objects=self.objects(), circuit_closed=self.circuit_closed(),
                                    led_on=self.led, dt=CONTROL_DT*FRAME_EVERY, qpos=self.d.qpos.copy()))

    def settle(self, seconds, record=True):
        for _ in range(int(seconds/CONTROL_DT)):
            self.tick(record)

    def move(self, pos, yaw, speed=.15, until=None):
        """Straight-line fingertip motion; stops early when `until()` becomes true (guarded move)."""
        start, pos = self.tcp(), np.asarray(pos, float)
        n = max(1, int(np.ceil(np.linalg.norm(pos-start)/(speed*CONTROL_DT))))
        q = self.d.ctrl[:6].copy()
        for p in np.linspace(start, pos, n+1)[1:]:
            q = self.ik(p, yaw, q)
            self.d.ctrl[:6] = q
            self.tick()
            self.check_collision()
            if self.held and not self.gripped(self.held):
                self._lost_grasp_ticks=getattr(self,'_lost_grasp_ticks',0)+1
                if self._lost_grasp_ticks>=5:
                    raise SkillError(f'{self.held} lost finger contact during motion')
            else:
                self._lost_grasp_ticks=0
            if until and until():
                self.d.ctrl[:6] = self.arm_q()     # hold where contact was made
                self.settle(.1)
                return True
        for _ in range(40):                        # converge on the final setpoint
            if np.linalg.norm(self.tcp()-pos) < 1.5e-3 or (until and until()):
                break
            self.tick()
        return bool(until and until())

    def check_collision(self):
        c = self.d.contact[:self.d.ncon]
        arm = self.m.geom_contype == scene.ARM_BIT
        pad, fixed = np.zeros(self.m.ngeom, bool), (self.m.geom_conaffinity & scene.ARM_BIT) > 0
        pad[[self.geom['g_tip_left'], self.geom['g_tip_right']]] = True
        hit = arm[c.geom1] | arm[c.geom2] | (pad[c.geom1] & fixed[c.geom2]) | (pad[c.geom2] & fixed[c.geom1])
        if np.any(hit):
            i = int(np.argmax(hit))
            names = sorted(self.m.body(self.m.geom_bodyid[g]).name or self.m.geom(g).name
                           for g in (c.geom1[i], c.geom2[i]))
            raise SkillError(f'Collision between {names[0]} and {names[1]}; motion stopped')

    def grip(self, close):
        self.d.ctrl[6] = CLOSED if close else OPEN
        self.settle(.45)

    def _seat_jumper(self, active=True):
        """Insertion retention (breadboard hole or copper mesh) as a weld to the world."""
        body = self.m.body('jumper').id
        data = self.m.eq_data[self.seat]
        data[3:6] = -self.d.xmat[body].reshape(3, 3).T@self.d.xpos[body]
        data[6:10] = _quat_conj(self.d.xquat[body])
        self.d.eq_active[self.seat] = active

    # ---- skills ------------------------------------------------------------------------
    @staticmethod
    def yaw_for(xy):
        return float(np.arctan2(xy[1], xy[0]) + np.pi/2)      # fingers close tangentially

    def pick(self, obj):
        grasp = self.target(obj) if self.visual_targets is not None else self.site_pos(f'{obj}_grasp')
        yaw = self.yaw_for(grasp)
        below = grasp - [0, 0, .008]                         # fingertips just past the grasp point
        self.grip(False)
        self.move(below + [0, 0, CLEAR], yaw)
        self.move(below, yaw, speed=.05)
        self.settle(.15)
        self.grip(True)
        if not self.gripped(obj):
            self.move(below + [0, 0, CLEAR], yaw)
            raise SkillError(f'Fingers did not close on the {obj}')
        self.held = obj
        self.visual_tool_local = None
        if self.visual_targets is not None:
            from ..perception import REGISTRY
            entry = REGISTRY[obj]
            # Taught grasp-to-tip geometry; no query of the simulated object's pose.
            self.tool_offset = np.asarray(entry['target_offset']) - np.asarray(entry['point_offset']) - [0,0,.008]
        if obj == 'jumper':
            self.d.eq_active[self.seat] = 0                  # pull the lead out of its hole
        self.move(self.tcp() + [0, 0, CLEAR], yaw, speed=.08)
        if not self.gripped(obj):
            self.held = None
            raise SkillError(f'The {obj} slipped out of the gripper while lifting')

    def target(self, name):
        from ..perception import MarkerPerception
        return MarkerPerception.require(self.visual_targets, name)

    def _point_offset(self, point_site):
        if self.visual_targets is not None:
            if self.tool_offset_provider is not None:
                return self.tool_offset_provider()
            if self.tool_offset is None: raise SkillError('Tool geometry has not been calibrated by a grasp')
            return self.tool_offset.copy()
        return self.tcp() - self.site_pos(point_site)

    def touch(self, point_site, xy, surface_z, target_geoms, yaw=None, depth=.012):
        """Bring the held object's contact point down onto (xy, surface_z), stopping on contact."""
        off = self._point_offset(point_site)
        yaw = self.yaw_for(xy) if yaw is None else yaw
        local=getattr(self,'visual_tool_local',None)
        if self.visual_targets is not None and local is not None:
            y=np.array([np.cos(yaw),np.sin(yaw),0.]); z=np.array([0.,0.,-1.])
            off=np.column_stack([np.cross(y,z),y,z])@local
        above = np.array([*xy, surface_z]) + off
        self.move(above + [0, 0, .03], yaw)
        contact = lambda: any(self.touching(*pair) for pair in target_geoms)
        self.move(above - [0, 0, depth], yaw, speed=.02, until=contact)
        return [pair for pair in target_geoms if self.touching(*pair)], yaw

    def measure(self, pad_offset_x=0.):
        pad = self.target('test_pad') if self.visual_targets is not None else np.array(scene.PAD['pos']) + [0,0,scene.PAD['size'][2]]
        hits, yaw = self.touch('probe_point', pad[:2] + [pad_offset_x, 0], pad[2],
                               [('probe_tip', 'test_pad'), ('probe_tip', 'board'), ('probe_tip', 'copper_mesh')])
        self.settle(.25)
        valid = self.touching('probe_tip', 'test_pad')
        self.move(self.tcp() + [0, 0, .04], yaw, speed=.08)
        return valid

    def release(self, point_site, xy, floor_z, target_geoms, seat=False):
        hits, yaw = self.touch(point_site, xy, floor_z, target_geoms)
        self.move(self.tcp() - [0, 0, .001], yaw, speed=.01)     # light press into the fixture
        self.settle(.1)
        # The mesh only captures a pin that is still pressed into it and roughly vertical.
        if seat and self.touching('jumper_pin', 'copper_mesh') and self.upright('jumper'):
            self._seat_jumper()
        self.grip(False)
        self.held = None
        self.move(self.tcp() + [0, 0, CLEAR], yaw, speed=.08)
        return hits

    def dock_probe(self):
        p = self.target('probe_dock') if self.visual_targets is not None else [*scene.DOCK_XY,0.]
        return self.release('probe_point', p[:2], p[2], [('probe_tip', 'table')])

    def place_jumper(self, offset_x=0., offset_y=0.):
        mesh = self.target('copper_mesh') if self.visual_targets is not None else np.array(scene.MESH['pos']) + [0,0,scene.MESH['size'][2]]
        return self.release('jumper_point', mesh[:2] + [offset_x, offset_y], mesh[2],
                            [('jumper_pin', 'copper_mesh'), ('jumper_pin', 'board')], seat=True)

    def home(self):
        self.move(*HOME)

    # ---- visuals -----------------------------------------------------------------------
    def set_led(self, on):
        self.led = bool(on)
        mat = self.m.material('led_on' if on else 'led_off').id
        for g in ('led', 'led_dome'):
            self.m.geom_matid[self.m.geom(g).id] = mat
        self.m.light_diffuse[self.m.light('led_glow').id] = [2, .3, .2] if on else [0, 0, 0]

    # ---- rendering ---------------------------------------------------------------------
    def _cable(self, scn, a, b, rgba, sag=.05, width=.0018, n=10):
        a, b = np.asarray(a), np.asarray(b)
        mid = (a+b)/2 + [0, 0, sag]
        pts = [(1-t)**2*a + 2*(1-t)*t*mid + t**2*b for t in np.linspace(0, 1, n+1)]
        for p0, p1 in zip(pts, pts[1:]):
            if scn.ngeom >= scn.maxgeom:
                return
            g = scn.geoms[scn.ngeom]
            mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_CAPSULE, np.zeros(3), np.zeros(3), np.zeros(9),
                                np.asarray(rgba, np.float32))
            mujoco.mjv_connector(g, mujoco.mjtGeom.mjGEOM_CAPSULE, width, p0, p1)
            scn.ngeom += 1

    def render(self, camera='overview', frame=None, size=(440, 1060)):
        """RGB image of the live state, or of a recorded frame (from self.frames)."""
        return GL.submit(self._render, camera, frame, size).result()

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
            mujoco.mj_camlight(self.m, d)       # camera poses aren't updated by kinematics alone
            led = frame['led_on']
        live = self.led
        self.set_led(led)
        renderer.update_scene(d, camera)
        scn = renderer.scene
        self._cable(scn, d.site('jumper_top').xpos, [.31, .178, .023], [.85, .12, .1, 1])
        self._cable(scn, d.site('probe_grasp').xpos + [0, 0, .025], [.16, -.17, .04], [.12, .12, .12, 1],
                    sag=.08)
        image = renderer.render()
        self.set_led(live)
        return image

    def clip(self, camera='overview', fps=12, size=(330, 795)):
        """Animated WebP of the frames recorded since the last reset of self.frames."""
        step = max(1, round(1/(fps*CONTROL_DT*FRAME_EVERY)))
        picks = self.frames[::step] or [None]
        images = GL.submit(lambda: [Image.fromarray(self._render(camera, f, size)) for f in picks]).result()
        buf = io.BytesIO()
        images[0].save(buf, 'WEBP', save_all=True, append_images=images[1:], duration=int(1000/fps),
                       loop=1, quality=70, method=2)
        return buf.getvalue()

    def close(self):
        def release():
            for renderer in self._renderers.values():
                renderer.close()
            self._renderers.clear()
        GL.submit(release).result()

    def video(self, camera='overview', size=(720,1280)):
        """One-shot H.264 replay. Stream frames into ffmpeg; never retain RGB clips."""
        import subprocess, tempfile, shutil
        from pathlib import Path
        executable=shutil.which('ffmpeg')
        if not executable: raise RuntimeError('ffmpeg is required for smooth MP4 playback')
        height,width=size
        def encode():
            with tempfile.TemporaryDirectory(prefix='arm-replay-') as directory:
                path=Path(directory)/'action.mp4'
                with (Path(directory)/'encoder.log').open('w+b') as errors:
                    proc=subprocess.Popen([executable,'-hide_banner','-loglevel','error','-y',
                        '-f','rawvideo','-pixel_format','rgb24','-video_size',f'{width}x{height}',
                        '-framerate','25','-i','pipe:0','-an','-c:v','libx264','-threads','2',
                        '-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],
                        stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
                    try:
                        for frame in self.frames or [None]:
                            proc.stdin.write(self._render(camera,frame,size).tobytes())
                        # The exact final state is held by HTML video after ended; never loop.
                        proc.stdin.write(self._render(camera,None,size).tobytes())
                        proc.stdin.close()
                        if proc.wait(timeout=30):
                            errors.seek(0); raise RuntimeError(errors.read().decode()[-1000:])
                        return path.read_bytes()
                    finally:
                        if proc.poll() is None: proc.kill(); proc.wait()
        return GL.submit(encode).result()
