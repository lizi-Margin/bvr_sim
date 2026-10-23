"""Rebuild the training range height field from a deterministic terrain recipe."""
import json,math
from pathlib import Path
path=Path(__file__).resolve().parents[1]/'maps/training.json'
scene=json.loads(path.read_text(encoding='utf8'))
n=129;spacing=2000;origin=-128000
heights=[]
for row in range(n):
    west=origin+row*spacing
    for col in range(n):
        north=origin+col*spacing
        blend=min(1,max(0,(abs(west)-4000)/5000))
        ridges=200+650*(.5+.5*math.sin(north/5000+math.sin(west/7300)))**2
        hills=200*math.sin(north/2300)*math.cos(west/3500)
        heights.append(round(max(0,ridges+hills)*blend,3))
scene['terrain']={'origin_north':origin,'origin_west':origin,'spacing':spacing,'columns':n,'rows':n,'heights':heights}
scene['terrain_recipe']='range_hills_v1: 129x129, 2km grid, sinusoidal ridges, flat +/-4km mission corridor; build_training_map.py'
scene['description']='Reproducible training range with low hills surrounding a flat interception and bombing corridor. Rendering and headless physics use identical saved heights.'
scene['version']=3
path.write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'map':str(path),'height_samples':len(heights),'cells':(n-1)**2,'max_height_m':max(heights)}))
