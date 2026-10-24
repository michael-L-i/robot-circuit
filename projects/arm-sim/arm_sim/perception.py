"""Camera-only marker perception. No simulator imports or scene-state access.

Inputs are RGB pixels, calibration and an explicitly taught object registry.
The same estimator can consume a real camera frame with measured calibration.
"""
import json
from pathlib import Path
import cv2
import numpy as np

REGISTRY_PATH = Path(__file__).resolve().parents[1]/'config/objects.json'
REGISTRY = json.loads(REGISTRY_PATH.read_text())['objects']

class PerceptionError(RuntimeError): pass

class MarkerPerception:
    def __init__(self, calibration, registry=None):
        self.calibration = calibration
        self.registry = registry if registry is not None else REGISTRY
        self.matrix = np.array(calibration['camera_matrix'], dtype=float)
        self.distortion = np.array(calibration['distortion'], dtype=float)
        self.base_from_camera = np.array(calibration['base_from_camera'], dtype=float)
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),params)

    def detect(self, rgb):
        if list(rgb.shape[:2]) != self.calibration['image_size_hw']:
            raise PerceptionError('Image resolution does not match camera calibration')
        corners, ids, _ = self.detector.detectMarkers(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY))
        found = {}
        if ids is None: return found
        for name, entry in self.registry.items():
            hits = np.flatnonzero(ids.ravel()==entry['marker_id'])
            if len(hits)!=1: continue  # ambiguous duplicate identity is not a valid target
            uv = corners[int(hits[0])].reshape(4,2)
            s = entry['marker_size']/2
            xyz = np.array([[-s,s,0],[s,s,0],[s,-s,0],[-s,-s,0]],dtype=float)
            ok,r,t = cv2.solvePnP(xyz,uv,self.matrix,self.distortion,flags=cv2.SOLVEPNP_IPPE_SQUARE)
            if not ok or t[2,0]<=0: continue
            projected,_ = cv2.projectPoints(xyz,r,t,self.matrix,self.distortion)
            error = float(np.sqrt(np.mean(np.sum((projected.reshape(4,2)-uv)**2,axis=1))))
            if error>1.5: continue
            cam_from_marker = np.eye(4)
            cam_from_marker[:3,:3] = cv2.Rodrigues(r)[0]
            cam_from_marker[:3,3] = t.ravel()
            transform = self.base_from_camera@cam_from_marker
            target = (transform@np.r_[entry['target_offset'],1])[:3]
            # This first taught skill handles upright tools, not arbitrary 6D grasps.
            tilt = float(np.degrees(np.arccos(np.clip(transform[2,2],-1,1))))
            found[name] = dict(marker_id=entry['marker_id'],target_xyz=target.tolist(),
                base_from_marker=transform.tolist(),pixel_corners=uv.tolist(),
                reprojection_px=round(error,3),tilt_deg=round(tilt,2),source='camera_aruco')
        return found

    @staticmethod
    def require(detections,name):
        if name not in detections: raise PerceptionError(f'{name}: marker not visible; no motion authorized')
        detection=detections[name]
        if detection['tilt_deg']>15: raise PerceptionError(f'{name}: orientation exceeds taught upright skill')
        p=np.asarray(detection['target_xyz'])
        if not np.all(np.isfinite(p)) or not (.12<p[0]<.5 and -.3<p[1]<.3 and -.015<p[2]<.18):
            raise PerceptionError(f'{name}: estimate outside calibrated bench workspace')
        return p
