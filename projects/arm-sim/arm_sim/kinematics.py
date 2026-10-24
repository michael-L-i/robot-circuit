"""URDF FK and bounded numerical IK. Kinematics only, not rigid-body dynamics."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np


def rotation(axis, theta):
    axis = np.asarray(axis, dtype=float)
    axis /= np.linalg.norm(axis)
    x, y, z = axis
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(theta)*k + (1-np.cos(theta))*(k@k)


class Arm:
    def __init__(self):
        root = ET.parse(Path(__file__).parent/'assets/yam_ultra.urdf').getroot()
        self.joints = []
        for i in range(1, 7):
            j = root.find(f"joint[@name='joint{i}']")
            origin = j.find('origin')
            xyz = np.fromstring(origin.get('xyz'), sep=' ')
            r, p, y = np.fromstring(origin.get('rpy'), sep=' ')
            t = np.eye(4)
            t[:3, :3] = rotation([0,0,1], y)@rotation([0,1,0], p)@rotation([1,0,0], r)
            t[:3, 3] = xyz
            lim = j.find('limit')
            self.joints.append((t, np.fromstring(j.find('axis').get('xyz'), sep=' '), float(lim.get('lower')), float(lim.get('upper'))))
        self.lower = np.array([j[2] for j in self.joints])
        self.upper = np.array([j[3] for j in self.joints])

    def fk(self, q):
        t = np.eye(4)
        points = [[0., 0., 0.]]
        for angle, (origin, axis, _, _) in zip(q, self.joints):
            r = np.eye(4)
            r[:3, :3] = rotation(axis, angle)
            t = t@origin@r
            points.append(t[:3,3].tolist())
        # Nominal gripper TCP, replace with measured tool calibration on hardware.
        tcp = t[:3,3] + t[:3,:3]@np.array([0.,0.,.09])
        points.append(tcp.tolist())
        return tcp, t[:3,2], points

    def solve(self, target, seed):
        target = np.asarray(target)
        q = np.array(seed, dtype=float)
        def residual(v):
            pos, axis, _ = self.fk(v)
            return np.concatenate((pos-target, .12*(axis-[0,0,-1])))
        for _ in range(150):
            e = residual(q)
            if np.linalg.norm(e[:3]) < .0006 and np.linalg.norm(e[3:]) < .003:
                return q
            jac = np.column_stack([(residual(q+np.eye(6)[i]*1e-5)-e)/1e-5 for i in range(6)])
            dq = -jac.T@np.linalg.solve(jac@jac.T + np.eye(6)*.00004, e)
            q = np.clip(q+np.clip(dq,-.16,.16), self.lower, self.upper)
        raise ValueError(f'No bounded IK solution for {target.tolist()} (error {np.linalg.norm(e[:3]):.4f} m)')

    def path(self, q, target):
        """Cartesian lift/translate/descend, with bounded joint interpolation."""
        q = np.array(q)
        start = self.fk(q)[0]
        safe = max(.19, start[2], target[2])
        waypoints = [[*start[:2],safe], [*target[:2],safe], target]
        frames = []
        for waypoint in waypoints:
            a = self.fk(q)[0]
            count = max(1,int(np.ceil(np.linalg.norm(np.asarray(waypoint)-a)/.012)))
            for point in np.linspace(a, waypoint, count+1)[1:]:
                nxt = self.solve(point, q)
                dt = max(.04, float(np.max(np.abs(nxt-q)))/.6)
                q = nxt
                tcp, _, links = self.fk(q)
                # Conservative tabletop bound for joint origins; not mesh collision checking.
                if min(p[2] for p in links[1:]) < .008:
                    raise ValueError('Trajectory crosses tabletop bound')
                frames.append(dict(q=q.tolist(), tcp=tcp.tolist(), links=links, dt=dt))
        return q, frames
