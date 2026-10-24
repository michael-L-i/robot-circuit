"""Demo 2 bench: same YAM Ultra, probe and breadboard, but the fault is an open resistor module.

Arduino 5V -> TP1 -> socket (resistor module) -> TP2 / LED anode -> red LED -> GND.
Reuses demo 1's arm, primitives and camera poses by import only.
"""
import mujoco
import numpy as np
from ..physics.scene import ASSETS, ARM_JOINTS, BOARD, BOARD_TOP, DOCK_XY, PROBE_HANDLE, PROBE_NEEDLE, COPPER, \
    LED_OFF, LED_ON, _arm, _box, _cyl, _camera

TP_IN = dict(pos=[.36, .07, BOARD_TOP+.001], size=[.008, .008, .001])       # supply-side test pad
TP_OUT = dict(pos=[.34, -.035, BOARD_TOP+.001], size=[.008, .008, .001])    # LED anode test pad
SOCKET_XY = [.35, .02]                     # module pins straddle two wide copper pads along x
PAD_DX, PAD_SIZE = .012, [.008, .010, .0015]
CADDY_XY = [.25, .10]                      # spare parts caddy (seeded jitter in world.py)
CADDY_TOP = .02
BIN_XY, BIN_HALF, BIN_H = [.39, .13], .024, .025
LED_XY = [.29, -.035]

HOUSING = [.0045, .012, .009]              # 3D-printed grip block (fingers close across x)
PIN = [.0008, .0008, .003]
PIN_Y = .010                               # 2-pin header pitch 20 mm, along the module's y axis
SEATED_Z = BOARD_TOP + 2*PAD_SIZE[2] + 2*PIN[2] + HOUSING[2]
CADDY_Z = CADDY_TOP + 2*PIN[2] + HOUSING[2]
MODULE_YAW = -np.pi/2                      # module y (pin axis, marker flag) along world +x
MODULES = ('resistor_a', 'resistor_b')     # a starts in the socket, b in the spare caddy


def _breadboard(w):
    _box(w, 'table', [.3, 0, -.01], [.45, .45, .01], [.32, .30, .29, 1])
    _box(w, 'riser', [.33, 0, .01], [.045, .105, .01], [.2, .2, .22, 1])
    _box(w, 'board', BOARD['pos'], BOARD['size'], [.93, .92, .88, 1]).friction = [.9, .01, .001]
    _box(w, '', [.33, 0, BOARD_TOP+.00005], [.0015, .09, .00004], [.36, .36, .35, 1], collide=False)
    for row in range(63):
        for x in [-.01524, -.0127, -.01016, -.00762, -.00508, .00508, .00762, .01016, .0127, .01524]:
            w.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[.33+x, (row-31)*.00254, BOARD_TOP+.00008],
                       size=[.00048, .00005, 0], rgba=[.19, .19, .18, 1], contype=0, conaffinity=0)
    for x, color in [(-.033, [.75, .18, .15, 1]), (.033, [.16, .35, .65, 1])]:
        _box(w, '', [.33+x, 0, BOARD_TOP+.00005], [.00035, .09, .00004], color, collide=False)


def _bench(spec):
    w = spec.worldbody
    w.add_light(name='key', pos=[.6, -.4, 1.2], dir=[-.4, .3, -1], diffuse=[.75, .75, .75], castshadow=True)
    w.add_light(name='fill', pos=[-.2, .5, 1.], dir=[.3, -.4, -1], diffuse=[.35, .35, .38])
    w.add_light(name='led_glow', pos=[*LED_XY, BOARD_TOP+.02], dir=[0, 0, -1], diffuse=[0, 0, 0],
                type=mujoco.mjtLightType.mjLIGHT_POINT, attenuation=[0, 0, 600])
    _breadboard(w)
    for name, part in (('tp_in', TP_IN), ('tp_out', TP_OUT)):
        _box(w, name, part['pos'], part['size'], COPPER)
        w.add_site(name=f'{name}_top', pos=[*part['pos'][:2], part['pos'][2]+part['size'][2]], size=[.001, 0, 0])
    # Socket: two wide copper landing pads, input (outer, +x) and output (inner, -x).
    for name, dx in (('socket_in', PAD_DX), ('socket_out', -PAD_DX)):
        _box(w, name, [SOCKET_XY[0]+dx, SOCKET_XY[1], BOARD_TOP+PAD_SIZE[2]], PAD_SIZE, [.8, .48, .22, 1])
    w.add_site(name='socket_top', pos=[*SOCKET_XY, BOARD_TOP+2*PAD_SIZE[2]], size=[.001, 0, 0])
    h = .0003
    _box(w, 'trace_in', [.362, .045, BOARD_TOP+h], [.0025, .017, h], COPPER, collide=False)      # TP1 -> socket_in
    _box(w, 'trace_out', [.338, -.005, BOARD_TOP+h], [.0025, .022, h], COPPER, collide=False)    # socket_out -> TP2
    _cyl(w, 'anode_lead', [.332, -.035, BOARD_TOP+.002, LED_XY[0], LED_XY[1], BOARD_TOP+.002], .0005, [.7, .7, .7, 1])
    for name, rgba, emission in [('led_off', LED_OFF, 0), ('led_on', LED_ON, 1)]:
        spec.add_material(name=name, rgba=rgba, emission=emission, specular=.6)
    _cyl(w, 'led', [*LED_XY, BOARD_TOP+.004, *LED_XY, BOARD_TOP+.012], .0025, None, material='led_off')
    w.add_geom(name='led_dome', type=mujoco.mjtGeom.mjGEOM_SPHERE, pos=[*LED_XY, BOARD_TOP+.012],
               size=[.0025, 0, 0], material='led_off', contype=0, conaffinity=0)
    # 100 kOhm pulldown on TP2 (SMD, visual only): defines 0 V when the series resistor is open.
    _box(w, 'pulldown', [.322, -.05, BOARD_TOP+.0006], [.0016, .0008, .0006], [.12, .12, .12, 1], collide=False)
    _box(w, 'arduino', [.33, .2, .0075], [.034, .026, .0075], [.05, .45, .55, 1])
    _box(w, 'header_5v', [.31, .178, .019], [.003, .0015, .004], [.08, .08, .08, 1], collide=False)
    _cyl(w, 'gnd_wire', [LED_XY[0], LED_XY[1], BOARD_TOP+.002, .26, -.035, BOARD_TOP+.002], .001, [.1, .1, .1, 1])
    _cyl(w, 'gnd_return', [.26, -.035, BOARD_TOP+.002, .3, .178, .016], .0012, [.1, .1, .1, 1],
         kind=mujoco.mjtGeom.mjGEOM_CAPSULE)
    for i, (dx, dy) in enumerate([(1, 0), (-1, 0), (0, 1), (0, -1)]):             # probe dock, as demo 1
        r = PROBE_HANDLE[0]+.0055
        _box(w, f'dock{i}', [DOCK_XY[0]+dx*r, DOCK_XY[1]+dy*r, .015],
             [.0025 if dx else r+.0025, .0025 if dy else r+.0025, .015], [.15, .15, .17, 1])
    _box(w, 'multimeter', [.16, -.2, .02], [.035, .05, .02], [.95, .75, .1, 1])
    _box(w, 'caddy', [*CADDY_XY, CADDY_TOP/2], [.022, .022, CADDY_TOP/2], [.24, .26, .3, 1])
    # Reject bin: open tray the faulty part is dropped into.
    _box(w, 'bin_floor', [*BIN_XY, .001], [BIN_HALF+.002, BIN_HALF+.002, .001], [.55, .12, .1, 1])
    for i, (dx, dy) in enumerate([(1, 0), (-1, 0), (0, 1), (0, -1)]):
        r = BIN_HALF+.001
        _box(w, f'bin{i}', [BIN_XY[0]+dx*r, BIN_XY[1]+dy*r, BIN_H/2],
             [.001 if dx else r+.001, .001 if dy else r+.001, BIN_H/2], [.7, .16, .12, 1])


def _probe(w):
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


def _module(spec, name, pos, yaw, faulty):
    """Axial 330 Ohm resistor on a 2-pin carrier with a gripper-friendly block (visual: scorched if faulty)."""
    w = spec.worldbody
    body = w.add_body(name=name, pos=pos, quat=[np.cos(yaw/2), 0, 0, np.sin(yaw/2)])
    body.add_freejoint(name=name)
    body.add_geom(name=f'{name}_housing', type=mujoco.mjtGeom.mjGEOM_BOX, size=HOUSING, rgba=[.14, .32, .55, 1],
                  mass=.004, friction=[1.4, .02, .002], condim=4)
    for i, s in enumerate((-1, 1)):
        body.add_geom(name=f'{name}_pin{i}', type=mujoco.mjtGeom.mjGEOM_BOX, size=PIN, rgba=[.85, .8, .55, 1],
                      pos=[0, s*PIN_Y, -HOUSING[2]-PIN[2]], mass=.0005)
        _cyl(body, '', [0, s*PIN_Y, -HOUSING[2], 0, s*.007, HOUSING[2]+.0025], .0004, [.72, .72, .72, 1])  # lead
    z = HOUSING[2]+.0028
    _cyl(body, f'{name}_body', [0, -.007, z, 0, .007, z], .0028, [.3, .22, .16, 1] if faulty else [.82, .7, .5, 1],
         kind=mujoco.mjtGeom.mjGEOM_CAPSULE)
    bands = [(-.004, [.95, .55, .1, 1]), (-.0015, [.95, .55, .1, 1]), (.001, [.55, .3, .1, 1]), (.005, [.8, .65, .2, 1])]
    for y, c in bands:                                                             # orange-orange-brown, gold
        _cyl(body, '', [0, y, z, 0, y+.0012, z], .00295, c)
    if faulty:                                                                     # burnt, cracked centre
        _cyl(body, f'{name}_scorch', [0, -.0005, z, 0, .0025, z], .0031, [.05, .04, .03, 1])
    body.add_site(name=f'{name}_grasp', pos=[0, 0, .002])
    body.add_site(name=f'{name}_point', pos=[0, 0, -HOUSING[2]-2*PIN[2]])
    spec.add_equality(name=f'{name}_seat', type=mujoco.mjtEq.mjEQ_WELD, objtype=mujoco.mjtObj.mjOBJ_BODY,
                      name1=name, active=True, data=[0]*10+[1, 1])


def _plate(body, entry, centre):
    import cv2
    pixels = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), entry['marker_id'], 6)
    size, (x, y, z) = entry['marker_size'], centre
    cell = size/6

    def square(pos, half, c):
        body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, pos=pos, size=[half, half, .00005], rgba=[c, c, c, 1],
                      contype=0, conaffinity=0, mass=0)
    square([x, y, z], size*.65, 1.)
    for row in range(6):
        for col in range(6):
            square([x+(col-2.5)*cell, y+(2.5-row)*cell, z+.00011], cell/2, float(pixels[row, col])/255)


def _markers(spec, registry):
    """Optical plates only (no contact): flags on movable parts, plates beside fixtures."""
    probe = spec.body('probe')
    probe.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[.004, 0, .03, .045, 0, .03], size=[.0006, 0, 0],
                   rgba=[.3, .3, .3, 1], mass=0, contype=0, conaffinity=0)
    _plate(probe, registry['probe'], [.045, 0, .031])
    for name in MODULES:
        body = spec.body(name)
        body.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, HOUSING[1], .007, 0, .045, .007],
                      size=[.0006, 0, 0], rgba=[.3, .3, .3, 1], mass=0, contype=0, conaffinity=0)
        _plate(body, registry[name], [0, .045, .008])
    w = spec.worldbody
    for name, (x, y, z) in [('tp_in', [TP_IN['pos'][0]+.032, TP_IN['pos'][1], BOARD_TOP+.002]),
                            ('tp_out', [TP_OUT['pos'][0]+.032, TP_OUT['pos'][1], BOARD_TOP+.002]),
                            ('socket', [SOCKET_XY[0]-.04, SOCKET_XY[1], BOARD_TOP+.0005]),
                            ('reject_bin', [BIN_XY[0]+.05, BIN_XY[1], .001]),
                            ('probe_dock', [DOCK_XY[0], DOCK_XY[1]-.04, .001])]:
        _plate(w, registry[name], [x, y, z])


def build(registry, spare_xy=CADDY_XY, spare_yaw=MODULE_YAW, faulty=('resistor_a',)):
    spec = mujoco.MjSpec.from_file(str(ASSETS/'yam_ultra.xml'))
    spec.meshdir = str(ASSETS/'meshes')
    spec.option.timestep = .002
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.option.noslip_iterations = 3
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 1920, 1440
    spec.visual.quality.shadowsize = 2048
    spec.add_texture(name='sky', type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                     rgb1=[.16, .18, .22], rgb2=[.04, .05, .07], width=256, height=256)
    _arm(spec)
    _bench(spec)
    _probe(spec.worldbody)
    _module(spec, 'resistor_a', [*SOCKET_XY, SEATED_Z], MODULE_YAW, 'resistor_a' in faulty)
    _module(spec, 'resistor_b', [*spare_xy, CADDY_Z], spare_yaw, 'resistor_b' in faulty)
    _markers(spec, registry)
    _camera(spec, 'perception', [.65, -.30, .65], [.30, -.015, .025], fovy=42)
    _camera(spec, 'overview', [1.1, .28, .56], [.25, -.02, .17])
    _camera(spec, 'bench', [.62, -.02, .3], [.32, .02, .03], fovy=50)
    spec.worldbody.add_camera(name='top', pos=[.3, .02, .8], xyaxes=[0, -1, 0, 1, 0, 0], fovy=40)
    return spec.compile()
