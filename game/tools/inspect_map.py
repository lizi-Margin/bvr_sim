"""Check saved terrain, placement heights and registered asset budgets without a GPU."""
import argparse,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import GAME,load_runtime
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,default=GAME/'maps/training.json');p.add_argument('--runtime',type=Path,default=GAME/'runtime.json');a=p.parse_args()
    scene=json.loads(a.map.read_text(encoding='utf8'));runtime=load_runtime(a.runtime);terrain=native.GameTerrain()
    for k,v in scene['terrain'].items():setattr(terrain,k,v)
    cells=(terrain.columns-1)*(terrain.rows-1)
    if cells>scene['budget']['terrain_cells_max']:raise ValueError('Terrain exceeds cell budget')
    placements=[];ids=set()
    for obj in scene.get('assets',[]):
        if obj['id'] in ids:raise ValueError('Duplicate placement id: '+obj['id'])
        ids.add(obj['id']);pos=obj['position'];scale=obj.get('scale',1)
        if scale<=0 or any(not math.isfinite(x) for x in pos):raise ValueError('Invalid placement transform')
        file=Path(runtime['models'][obj['model']]);m=json.loads((file.parent/'manifest.json').read_text(encoding='utf8'))
        if m['faces']>scene['budget']['aircraft_faces_max']:raise ValueError('Asset face budget exceeded')
        surface=terrain.height(pos[0],pos[1]);bottom=pos[2]+m['bounds_blender']['min'][2]*scale
        if abs(bottom-surface)>.15:raise ValueError('Asset floats or penetrates terrain: '+obj['id'])
        placements.append({'id':obj['id'],'model':obj['model'],'ground_m':surface,'mesh_bottom_m':bottom,'faces':m['faces'],'sha256':m['glb_sha256']})
    for name,key in [('depot','ground_target'),('runway','runway')]:
        pos=scene[key]['position']
        if abs(pos[2]-terrain.height(pos[0],pos[1]))>.01:raise ValueError(name+' does not match physics terrain')
    print(json.dumps({'map':scene['id'],'version':scene['version'],'sha256':hashlib.sha256(a.map.read_bytes()).hexdigest(),'cells':cells,'height_range_m':[min(terrain.heights),max(terrain.heights)],'collision_surface':'same indexed triangle planes used by core and renderer','placements':placements,'status':'passed'},indent=2))
if __name__=='__main__':main()
