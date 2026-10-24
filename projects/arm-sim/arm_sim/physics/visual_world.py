"""Camera-guided task mode. Oracle coordinates remain in the baseline only."""
from .world import PhysicsWorld
from ..world import World
from .camera import CameraObserver
from ..perception import MarkerPerception, PerceptionError, REGISTRY
import numpy as np

class VisualWorld(PhysicsWorld):
    def __init__(self,config=None):
        self.observer=None
        super().__init__(config)
        self.observer=CameraObserver(self.bench)
        self.bench.tool_offset_provider=self.measured_tool_offset
        self.refresh_perception()

    def measured_tool_offset(self):
        orientation=self.bench.d.site_xmat[self.bench.site].reshape(3,3)
        cached=getattr(self.bench,'visual_tool_local',None)
        if cached is not None: return orientation@cached
        detections=self.refresh_perception()
        name=self.bench.held
        if name not in detections:
            # Explicit taught tool geometry, never simulator object truth.
            offset=self.bench.tool_offset.copy()
            self.bench.visual_tool_local=orientation.T@offset
            return offset
        t=np.asarray(detections[name]['base_from_marker'])
        tip=(t@np.r_[REGISTRY[name]['point_offset'],1])[:3]
        offset=self.bench.tcp()-tip
        self.bench.visual_tool_local=orientation.T@offset
        return offset

    def refresh_perception(self):
        self.bench.visual_targets=self.observer.scan()
        return self.observer.last

    def observation(self):
        obs=World.observation(self)
        detected=self.observer.last if self.observer else {}
        obs['targets']={name:d['target_xyz'] for name,d in detected.items()}
        obs['jumper_xyz']=detected.get('jumper',{}).get('target_xyz')
        obs['perception']=dict(method='calibrated camera + taught ArUco identities',
            detections=detected,missing=[n for n in ['probe','jumper','test_pad','copper_mesh','probe_dock'] if n not in detected])
        return obs

    def snapshot(self):
        return dict(super().snapshot(), perception_mode='camera_markers')

    def step(self,action):
        # Every required target is reacquired before executing a skill. No truth fallback.
        self.refresh_perception()
        target={'pick_probe':'probe','pick_jumper':'jumper','measure':'test_pad',
                'dock_probe':'probe_dock','place_mesh':'copper_mesh'}.get(action)
        if target: MarkerPerception.require(self.observer.last,target)
        return super().step(action)
