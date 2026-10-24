"""Inspect a real photograph using measured calibration. Never controls a robot."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
from arm_sim.perception import MarkerPerception

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--image',required=True)
p.add_argument('--calibration',required=True,help='Measured camera_matrix, distortion, base_from_camera, image_size_hw')
p.add_argument('--registry',default=str(Path(__file__).resolve().parents[1]/'config/objects.json'))
p.add_argument('--output',default='perception-check.json')
a=p.parse_args()
cal=json.loads(Path(a.calibration).read_text())
if cal.get('source','').startswith('ideal_sim'):
    p.error('This is simulator calibration. Supply measured calibration for the physical camera.')
image=cv2.imread(a.image)
if image is None:p.error('Could not read image')
estimator=MarkerPerception(cal,json.loads(Path(a.registry).read_text())['objects'])
detections=estimator.detect(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
Path(a.output).write_text(json.dumps({'detections':detections,'hardware_motion_enabled':False},indent=2)+'\n')
print(json.dumps({name:d['target_xyz'] for name,d in detections.items()},indent=2))
