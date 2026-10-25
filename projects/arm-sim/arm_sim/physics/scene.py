"""MuJoCo scene: Seeed Studio reBot B601-RS + stock gripper over a breadboard repair bench.

World frame matches arm_sim.world: arm base at the origin, +x forward, +z up, metres.
"""
from pathlib import Path
import mujoco
import numpy as np

ASSETS = Path(__file__).resolve().parent.parent/'assets/mjcf'
ARM_JOINTS = [f'joint{i}' for i in range(1, 7)]
ARM_BIT = 2                                     # collision bit shared by arm links and the bench

BOARD_TOP = .03                                 # breadboard surface, on a 2 cm riser
BOARD = dict(pos=[.33, 0, .025], size=[.045, .105, .005])
PAD = dict(pos=[.35, -.035, BOARD_TOP+.001], size=[.008, .008, .001])      # enlarged probe test pad
MESH = dict(pos=[.35, .035, BOARD_TOP+.0015], size=[.014, .012, .0015])   # copper mesh landing zone
JUMPER_START = [.31, .08]                       # misplaced hole (xy); world.py adds seeded jitter
DOCK_XY = [.23, -.15]

PROBE_HANDLE = (.0095, .03)                     # radius, half-length
PROBE_NEEDLE = (.0012, .011)
JUMPER_HOUSING = [.0045, .0045, .012]           # gripper-friendly sleeve over a Dupont lead
JUMPER_PIN = [.0012, .0012, .003]

COPPER = [.85, .5, .25, 1]
LED_OFF, LED_ON = [.45, .05, .05, .55], [1, .15, .1, 1]


def _box(body, name, pos, size, rgba, collide=True, **kw):
    return body.add_geom(name=name, type=mujoco.mjtGeom.mjGEOM_BOX, pos=pos, size=size, rgba=rgba,
                         contype=int(collide), conaffinity=(1 | ARM_BIT)*collide, **kw)


def _cyl(body, name, fromto, r, rgba, kind=mujoco.mjtGeom.mjGEOM_CYLINDER, collide=False, **kw):
    if rgba is not None:
        kw['rgba'] = rgba
    return body.add_geom(name=name, type=kind, fromto=fromto, size=[r, 0, 0],
                         contype=int(collide), conaffinity=int(collide), **kw)


def _arm(spec):
    grip = mujoco.MjSpec.from_file(str(ASSETS/'linear_4310.xml'))
    grip.meshdir = spec.meshdir
    spec.body('gripper').add_frame().attach_body(grip.body('gripper'), 'g_', '')
    for body in spec.bodies:
        if body.name and body.name != 'world':
            body.gravcomp = 1                    # the real arm runs gravity-compensated torque control
    for geom in spec.geoms:
        if geom.type == mujoco.mjtGeom.mjGEOM_MESH:
            # Link hulls hit the bench (bit 2) but not each other or the task objects, which catches
            # bad trajectories. The base is bolted to the table. Fingertip hulls bridge the finger gap,
            # so the pads below do the gripping instead.
            skip = geom.parent.name in ('base', 'g_tip_left', 'g_tip_right')
            geom.contype, geom.conaffinity = (0 if skip else ARM_BIT), 0
    # Flat rubber pads on the distal 24 mm of each finger's inner face (poses in tip body frames).
    for tip, pos, quat in [('g_tip_left', [-.07809, .02399, -.04682], [-.5, .5, .5, -.5]),
                           ('g_tip_right', [-.0238, -.07809, -.0469], [.70711, .70711, 0, 0])]:
        spec.body(tip).add_geom(name=tip, type=mujoco.mjtGeom.mjGEOM_BOX, pos=pos, quat=quat,
                                size=[.0065, .0015, .012], rgba=[.15, .15, .15, 1], friction=[1.6, .02, .002],
                                condim=4, solref=[.004, 1], group=3)
    for name in ARM_JOINTS:
        j = spec.joint(name)
        j.armature, j.damping = .05, [1., 0, 0]
        a = spec.add_actuator(name=name, target=name, trntype=mujoco.mjtTrn.mjTRN_JOINT)
        a.set_to_position(kp=180, kv=12)
        a.ctrlrange, a.ctrllimited = j.range, True
        a.forcerange, a.forcelimited = [-10, 10], True   # actuatorfrcrange from the I2RT model
    for name in ('g_joint7', 'g_joint8'):
        spec.joint(name).damping = [2., 0, 0]
    g = spec.add_actuator(name='gripper', target='g_joint7', trntype=mujoco.mjtTrn.mjTRN_JOINT)
    g.set_to_position(kp=400, kv=10)
    g.ctrlrange, g.ctrllimited = [0, .0475], True
    g.forcerange, g.forcelimited = [-12, 12], True        # ~12 N squeeze, kind to a probe


def _bench(spec):
    w = spec.worldbody
    w.add_light(name='key', pos=[.6, -.4, 1.2], dir=[-.4, .3, -1], diffuse=[.75, .75, .75], castshadow=True)
    w.add_light(name='fill', pos=[-.2, .5, 1.], dir=[.3, -.4, -1], diffuse=[.35, .35, .38])
    w.add_light(name='led_glow', pos=[.29, -.035, BOARD_TOP+.02], dir=[0, 0, -1], diffuse=[0, 0, 0],
                type=mujoco.mjtLightType.mjLIGHT_POINT, attenuation=[0, 0, 600])
    _box(w, 'table', [.3, 0, -.01], [.45, .45, .01], [.32, .30, .29, 1])
    _box(w, 'riser', [.33, 0, .01], [.045, .105, .01], [.2, .2, .22, 1])
    board = _box(w, 'board', BOARD['pos'], BOARD['size'], [.93, .92, .88, 1])
    board.friction = [.9, .01, .001]
    for x in (-.03, -.01, .01, .03):                                   # hole rows (visual)
        _box(w, '', [.33+x, 0, BOARD_TOP], [.0006, .095, .0002], [.75, .74, .7, 1], collide=False)
    # Standard 2.54 mm terminal grid, central channel and separate power rails (visual).
    _box(w, 'centre_channel', [.33,0,BOARD_TOP+.00005], [.0015,.09,.00004], [.36,.36,.35,1], collide=False)
    columns=[-.01524,-.0127,-.01016,-.00762,-.00508,.00508,.00762,.01016,.0127,.01524]
    for row in range(63):
        y=(row-31)*.00254
        for x in columns:
            w.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER,pos=[.33+x,y,BOARD_TOP+.00008],
                       size=[.00048,.00005,0],rgba=[.19,.19,.18,1],contype=0,conaffinity=0)
    for x,color in [(-.033,[.75,.18,.15,1]),(.033,[.16,.35,.65,1])]:
        _box(w,'',[.33+x,0,BOARD_TOP+.00005],[.00035,.09,.00004],color,collide=False)
    _box(w, 'test_pad', PAD['pos'], PAD['size'], COPPER)
    _box(w, 'copper_mesh', MESH['pos'], MESH['size'], [.8, .48, .22, 1])
    for name, part in (('pad_top', PAD), ('mesh_top', MESH)):
        w.add_site(name=name, pos=[*part['pos'][:2], part['pos'][2]+part['size'][2]], size=[.001, 0, 0])
    _box(w, 'trace', [.35, 0, BOARD_TOP+.0003], [.0025, .03, .0003], COPPER, collide=False)
    # resistor (pad node -> LED anode), LED, ground return to the Arduino
    _cyl(w, 'resistor_lead', [.343, -.035, BOARD_TOP+.002, .297, -.035, BOARD_TOP+.002], .0005, [.7, .7, .7, 1])
    _cyl(w, 'resistor', [.333, -.035, BOARD_TOP+.004, .309, -.035, BOARD_TOP+.004], .0028, [.82, .7, .5, 1],
         kind=mujoco.mjtGeom.mjGEOM_CAPSULE)
    for i, (x, c) in enumerate([(.329, [.55, .3, .1, 1]), (.325, [.1, .1, .1, 1]), (.317, [.9, .1, .1, 1])]):
        _cyl(w, f'band{i}', [x, -.035, BOARD_TOP+.004, x-.0015, -.035, BOARD_TOP+.004], .00295, c)
    for name, rgba, emission in [('led_off', LED_OFF, 0), ('led_on', LED_ON, 1)]:
        spec.add_material(name=name, rgba=rgba, emission=emission, specular=.6)
    _cyl(w, 'led', [.29, -.035, BOARD_TOP+.004, .29, -.035, BOARD_TOP+.012], .0025, None, material='led_off')
    w.add_geom(name='led_dome', type=mujoco.mjtGeom.mjGEOM_SPHERE, pos=[.29, -.035, BOARD_TOP+.012],
               size=[.0025, 0, 0], material='led_off', contype=0, conaffinity=0)
    _box(w, 'arduino', [.33, .2, .0075], [.034, .026, .0075], [.05, .45, .55, 1])
    _box(w, 'header_5v', [.31, .178, .019], [.003, .0015, .004], [.08, .08, .08, 1], collide=False)
    _cyl(w, 'gnd_wire', [.29, -.035, BOARD_TOP+.002, .26, -.035, BOARD_TOP+.002], .001, [.1, .1, .1, 1])
    _cyl(w, 'gnd_return', [.26, -.035, BOARD_TOP+.002, .3, .178, .016], .0012, [.1, .1, .1, 1],
         kind=mujoco.mjtGeom.mjGEOM_CAPSULE)
    # Probe sleeve guide: 1 mm radial clearance, 45 mm tall; supports upright re-grasp.
    for i, (dx, dy) in enumerate([(1, 0), (-1, 0), (0, 1), (0, -1)]):
        r = PROBE_HANDLE[0]+.0035
        _box(w, f'dock{i}', [DOCK_XY[0]+dx*r, DOCK_XY[1]+dy*r, .0225],
             [.0025 if dx else r+.0025, .0025 if dy else r+.0025, .0225], [.15, .15, .17, 1])
    _box(w, 'multimeter', [.16, -.2, .02], [.035, .05, .02], [.95, .75, .1, 1])


def _objects(spec):
    w = spec.worldbody
    hr, hl = PROBE_HANDLE
    nr, nl = PROBE_NEEDLE
    probe = w.add_body(name='probe', pos=[*DOCK_XY, 2*nl+hl+.0005])
    probe.add_freejoint(name='probe')
    probe.add_geom(name='probe_handle', type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[hr, hl, 0],
                   rgba=[.75, .08, .08, 1], mass=.03, friction=[1.4, .02, .002], condim=4)
    probe.add_geom(name='probe_tip', type=mujoco.mjtGeom.mjGEOM_CAPSULE, size=[nr, nl, 0],
                   pos=[0, 0, -hl-nl], rgba=[.82, .82, .85, 1], mass=.002)
    probe.add_site(name='probe_grasp', pos=[0, 0, .3*hl])
    probe.add_site(name='probe_point', pos=[0, 0, -hl-2*nl-nr])
    jumper = w.add_body(name='jumper', pos=[*JUMPER_START, BOARD_TOP+2*JUMPER_PIN[2]+JUMPER_HOUSING[2]])
    jumper.add_freejoint(name='jumper')
    jumper.add_geom(name='jumper_housing', type=mujoco.mjtGeom.mjGEOM_BOX, size=JUMPER_HOUSING,
                    rgba=[.95, .55, .05, 1], mass=.004, friction=[1.4, .02, .002], condim=4)
    jumper.add_geom(name='jumper_pin', type=mujoco.mjtGeom.mjGEOM_BOX, size=JUMPER_PIN,
                    pos=[0, 0, -JUMPER_HOUSING[2]-JUMPER_PIN[2]], rgba=[.85, .85, .8, 1], mass=.001)
    jumper.add_site(name='jumper_grasp', pos=[0, 0, .25*JUMPER_HOUSING[2]])
    jumper.add_site(name='jumper_top', pos=[0, 0, JUMPER_HOUSING[2]])
    jumper.add_site(name='jumper_point', pos=[0, 0, -JUMPER_HOUSING[2]-2*JUMPER_PIN[2]])
    # Breadboard / copper-mesh retention modelled as welds toggled on seat and release.
    spec.add_equality(name='jumper_seat', type=mujoco.mjtEq.mjEQ_WELD, objtype=mujoco.mjtObj.mjOBJ_BODY,
                      name1='jumper', active=True, data=[0]*10+[1, 1])  # torquescale 1


def _camera(spec, name, pos, target, fovy=45):
    z = np.subtract(pos, target)
    z /= np.linalg.norm(z)
    x = np.cross([0, 0, 1], z)
    x /= np.linalg.norm(x)
    spec.worldbody.add_camera(name=name, pos=pos, xyaxes=[*x, *np.cross(z, x)], fovy=fovy)


def build():
    from .rebot import arm_spec
    spec = arm_spec()
    spec.option.timestep = .002
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.option.noslip_iterations = 3
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 1920, 1440
    spec.visual.quality.shadowsize = 2048
    spec.add_texture(name='sky', type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                     rgb1=[.16, .18, .22], rgb2=[.04, .05, .07], width=256, height=256)
    _bench(spec)
    _objects(spec)
    from .markers import add_markers
    add_markers(spec)
    _camera(spec, "perception", [.65, -.30, .65], [.30, -.015, .025], fovy=42)
    _camera(spec, 'overview', [1.1, .28, .56], [.25, -.02, .17])
    # Roughly where a laptop/phone camera sits when filming the bench, for Gemma's vision input.
    _camera(spec, 'bench', [.62, -.02, .3], [.32, 0, .03], fovy=50)
    spec.worldbody.add_camera(name='top', pos=[.25, 0, .8], xyaxes=[0, -1, 0, 1, 0, 0], fovy=40)
    return spec.compile()
