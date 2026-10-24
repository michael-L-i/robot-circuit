"""Generate exact-size SVG markers from the taught object registry."""
import json
from pathlib import Path
import cv2
root=Path(__file__).resolve().parents[1]
registry=json.loads((root/'config/objects.json').read_text())['objects']
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">',
'<rect width="210" height="297" fill="white"/>',
'<text x="15" y="15" font-size="5">Circuit Lab — taught object markers</text>',
'<text x="15" y="24" font-size="3.5">Print at 100% / actual size. Measure the scale before calibration.</text>']
for index,(name,e) in enumerate(registry.items()):
    x,y=25,40+index*44;size=e['marker_size']*1000;cell=size/6
    pixels=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),e['marker_id'],6)
    for row in range(6):
        for col in range(6):
            if pixels[row,col]==0:svg.append(f'<rect x="{x+col*cell}" y="{y+row*cell}" width="{cell}" height="{cell}" fill="black"/>')
    svg.append(f'<text x="65" y="{y+10}" font-size="4">ID {e["marker_id"]}: {name} · {size:g} mm black square</text>')
svg += ['<path d="M25 275 h50 M25 272 v6 M75 272 v6" stroke="black"/>','<text x="32" y="284" font-size="4">This line must measure 50 mm</text>','</svg>']
path=root/'config/printable-markers.svg';path.write_text('\n'.join(svg));print(path)
