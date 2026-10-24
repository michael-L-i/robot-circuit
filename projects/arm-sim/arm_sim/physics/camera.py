"""Simulator camera adapter. Exposes images and fixed camera calibration only."""
import numpy as np
from ..perception import MarkerPerception

SIZE=(1440,1920)

def calibration(bench):
    cam=bench.m.camera('perception').id
    height,width=SIZE
    f=height/(2*np.tan(np.radians(bench.m.cam_fovy[cam])/2))
    t=np.eye(4)
    t[:3,:3]=bench.d.cam_xmat[cam].reshape(3,3)@np.diag([1,-1,-1])
    t[:3,3]=bench.d.cam_xpos[cam]
    return dict(image_size_hw=[height,width],camera_matrix=[[f,0,width/2],[0,f,height/2],[0,0,1]],
        distortion=[0,0,0,0,0],base_from_camera=t.tolist(),
        source='ideal_sim_camera_calibration; replace with measured intrinsics/extrinsics on hardware')

class CameraObserver:
    def __init__(self,bench):
        self.bench=bench
        self.estimator=MarkerPerception(calibration(bench))
        self.last={}
        self.rgb=None
    def scan(self):
        self.rgb=self.bench.render('perception',size=SIZE)
        self.last=self.estimator.detect(self.rgb)
        return self.last
