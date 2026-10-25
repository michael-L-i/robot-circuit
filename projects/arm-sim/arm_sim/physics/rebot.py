"""B601-RS adapter: official kinematics/inertias, simulated position servos.

The tool frame is at the official finger centre; +Z points out of the wrist,
+Y is the finger closing axis. No hardware communication is enabled.
"""
from pathlib import Path
import mujoco

ASSETS = Path(__file__).resolve().parents[1] / 'assets/rebot_rs'
READY_Q = [0., 1.7566, 1.6057, -1.4199, 0., -1.5708]
FINGER_JOINTS = ('joint7', 'joint_left', 'joint_right')


def arm_spec():
    spec = mujoco.MjSpec.from_file(str(ASSETS / 'rs_arm.xml'))
    spec.meshdir = str(ASSETS / 'meshes')
    for body in spec.bodies:
        if body.name != 'world':
            body.gravcomp = 1
    # Keep upstream visual meshes non-colliding and upstream collision hulls active.
    for geom in spec.geoms:
        if geom.contype:
            if geom.parent.name == 'base_link':
                geom.contype = geom.conaffinity = 0
            elif geom.parent.name in ('gripper_left', 'gripper_right'):
                geom.contype, geom.conaffinity = 1, 3
            else:
                geom.contype, geom.conaffinity = 2, 0
    spec.geom('gripper_left_front_collision').name = 'g_tip_left'
    spec.geom('gripper_right_front_collision').name = 'g_tip_right'
    # gripper_end +X points toward the fingertips; +Y is the jaw closing axis.
    spec.body('gripper_end').add_site(name='g_grasp_site', pos=[0, 0, 0],
                                    quat=[.70710678, 0, .70710678, 0], size=[.002, 0, 0], rgba=[0,0,0,0])
    for i, actuator in enumerate(spec.actuators):
        limit = 36 if i < 3 else 14 if i < 6 else 24
        actuator.set_to_position(kp=350 if i < 6 else 800, kv=30 if i < 6 else 20)
        joint = spec.joint(f'joint{i+1}')
        actuator.ctrlrange, actuator.ctrllimited = joint.range, True
        actuator.forcerange, actuator.forcelimited = [-limit, limit], True
        joint.armature = .05 if i < 6 else .001
    return spec
