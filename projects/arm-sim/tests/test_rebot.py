"""The RS adapter must preserve the manufacturer's mechanism and limits."""
import numpy as np
import mujoco
from arm_sim.physics.rebot import arm_spec


def test_rs_mechanism_and_actuator_limits():
    m = arm_spec().compile()
    assert m.nu == 7
    expected = [(-2.8,2.8),(-.2,3.14),(-.2,3.14),(-1.57,1.57),(-1.57,1.57),(-3.14,3.14)]
    for i, limits in enumerate(expected, 1):
        np.testing.assert_allclose(m.joint(f'joint{i}').range, limits)
    np.testing.assert_allclose(m.actuator_forcerange[:6,1], [36,36,36,14,14,14])
    assert m.neq == 2  # one gripper actuator, two coupled finger joints
    assert m.site('g_grasp_site').bodyid == m.body('gripper_end').id


def test_rs_gripper_opening_is_symmetric():
    m=arm_spec().compile();d=mujoco.MjData(m)
    positions=[]
    for opening in (0.,.02):
        for name in ('joint7','joint_left','joint_right'):
            d.qpos[m.joint(name).qposadr[0]]=opening
        mujoco.mj_forward(m,d)
        positions.append([d.geom(n).xpos.copy() for n in ('g_tip_left','g_tip_right')])
    delta=np.array(positions[1])-np.array(positions[0])
    np.testing.assert_allclose(delta[0],-delta[1],atol=1e-6)
    np.testing.assert_allclose(np.linalg.norm(delta,axis=1),.02,atol=1e-6)


def test_rs_ik_reaches_true_downward_orientation():
    from arm_sim.physics.bench import Bench
    b=Bench()
    try:
        for point in ([.28,0,.125],[.23,-.15,.06],[.35,.035,.06]):
            q=b.ik(point,0.,b.arm_q(),iters=160)
            d=mujoco.MjData(b.m);d.qpos[:]=b.d.qpos;d.qpos[b.arm_qadr]=q
            mujoco.mj_forward(b.m,d)
            np.testing.assert_allclose(d.site_xpos[b.site],point,atol=.0003)
            np.testing.assert_allclose(d.site_xmat[b.site].reshape(3,3)[:,2],[0,0,-1],atol=.003)
    finally:b.close()
