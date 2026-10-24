"""Build an isolated source-grove grounding scene on unchanged shared terrain."""
from pathlib import Path
import argparse,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json
from bvr_game.ground_atlas import write_atlas


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--asset',default='fir_grove_conform_a');a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    document=json.loads(a.map.read_text(encoding='utf8'));terrain=document['terrain']
    height_file=(a.map.parent/terrain['file']).resolve()
    if sha(height_file)!=terrain['sha256']:raise ValueError('Source terrain version mismatch')
    arrays=dict(np.load(height_file,allow_pickle=False));manifest=json.loads((ASSETS/'registered'/a.asset/'manifest.json').read_text(encoding='utf8'))
    if not manifest['cluster'].get('ground_conform'):raise ValueError('Probe requires an explicitly registered source-anchor mesh')
    grid={'origin_north':-10000,'origin_west':-10000,'spacing':5,'columns':4001,'rows':4001}
    atlas=write_atlas(a.output/'atlas',arrays,terrain,grid);terrain['file']=str(height_file);terrain['ground_atlas']=atlas
    source=[i for i in document['instances'] if i['model']=='fir_grove_normal_a']
    placements=[]
    for index,(north,west,yaw,scale) in enumerate([(-2450,-2200,0.,1.),(-2800,-2750,.73,.8),(-3200,-2900,-1.8,1.25)]):
        available=[i for i in source if all(np.linalg.norm(np.asarray(i['position'][:2])-p['position'][:2])>350 for p in placements)]
        item=dict(min(available,key=lambda i:(i['position'][0]-north)**2+(i['position'][1]-west)**2))
        item.update(id='ground_probe_'+str(index),model=a.asset,yaw=yaw,scale=scale,up_normal=[0,1,0])
        item.pop('grove_ground_fit',None);placements.append(item)
        if manifest['cluster']['ground_conform'].get('anchor_encoding')=='source_tree_index_uv1':
            rng=np.random.default_rng(5000+index);center=np.asarray(item['position'][:2])
            item['ground_stems']=np.round(center+rng.uniform([-75,-20],[55,35],([64,37,1][index],2)),4).tolist()
    document['instances']=placements;document['name']='isolated_source_grove_ground_probe'
    document['resource_versions']={a.asset:{'sha256':manifest['glb_sha256'],'lods':manifest['lods']}}
    document['ground_probe']={'source_map':str(a.map.resolve()),'source_map_sha256':sha(a.map),
        'asset_manifest_sha256':sha(ASSETS/'registered'/a.asset/'manifest.json'),
        'scope':'Three isolated decorative groves with varied scale and yaw; source terrain/contact/water/obstacle data unchanged. Not a full forest layout or naturalness acceptance.'}
    write_json(a.output/'generated-map.json',document)
    print('GROUND_PROBE_MAP',a.output/'generated-map.json', 'atlas_bytes',atlas['bytes'])


if __name__=='__main__':main()
