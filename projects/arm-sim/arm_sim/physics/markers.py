"""Optical marker plates for the simulated teaching setup. No contact geometry."""
import cv2
import mujoco
from ..perception import REGISTRY

def plate(body, name, centre):
    entry=REGISTRY[name]
    pixels=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),entry['marker_id'],6)
    size=entry['marker_size']; cell=size/6
    def square(pos,half,color):
        body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX,pos=pos,size=[half,half,.00005],
            rgba=[color,color,color,1],contype=0,conaffinity=0,mass=0)
    x,y,z=centre
    square([x,y,z],size*.65,1.)
    for row in range(6):
        for col in range(6):
            square([x+(col-2.5)*cell,y+(2.5-row)*cell,z+.00011],cell/2,float(pixels[row,col])/255)

def add_markers(spec):
    from . import scene
    for name,z in [('probe',.031),('jumper',.013)]:
        spec.body(name).add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE,fromto=[.004,0,z-.001,.045,0,z-.001],size=[.0006,0,0],rgba=[.3,.3,.3,1],mass=0,contype=0,conaffinity=0)
    plate(spec.body('probe'),'probe',[.045,0,.031])
    plate(spec.body('jumper'),'jumper',[.045,0,.013])
    for name,part in [('test_pad',scene.PAD),('copper_mesh',scene.MESH)]:
        plate(spec.worldbody,name,[part['pos'][0]+.032,part['pos'][1],part['pos'][2]+part['size'][2]])
    plate(spec.worldbody,'probe_dock',[scene.DOCK_XY[0],scene.DOCK_XY[1]-.04,.001])
